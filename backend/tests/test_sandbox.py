"""Unit tests for Docker sandbox configuration, runtime abstraction, and workspace management."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import FaultlineException, ValidationException
from app.core.sandbox_config import SandboxConfig
from app.services.sandbox.docker_runtime import DockerRuntime
from app.services.sandbox.workspace import WorkspaceManager


def test_sandbox_config_defaults():
    config = SandboxConfig()
    flags = config.to_docker_flags()
    assert "--network=none" in flags
    assert "--read-only" in flags
    assert "--cap-drop=ALL" in flags
    assert "--security-opt=no-new-privileges" in flags
    assert "--user" in flags
    assert "1000:1000" in flags
    assert "--memory" in flags
    assert "512m" in flags
    assert "--cpus" in flags
    assert "1.0" in flags
    assert "--pids-limit" in flags
    assert "128" in flags
    assert any("--tmpfs" in f for f in flags)


def test_docker_runtime_check_availability_success():
    runtime = DockerRuntime()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert runtime.check_availability() is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["docker", "info"]


def test_docker_runtime_check_availability_failure():
    runtime = DockerRuntime()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert runtime.check_availability() is False


def test_docker_runtime_check_availability_missing_cli():
    runtime = DockerRuntime()
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert runtime.check_availability() is False


def test_docker_runtime_require_availability_raises():
    runtime = DockerRuntime()
    with patch.object(runtime, "check_availability", return_value=False):
        with pytest.raises(FaultlineException) as exc_info:
            runtime.require_availability()
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "DOCKER_UNAVAILABLE"


def test_docker_runtime_build_docker_command(tmp_path: Path):
    runtime = DockerRuntime()
    cmd = runtime._build_docker_command(
        workspace_path=tmp_path,
        command=["python", "-m", "pytest"],
        environment={"PYTHONPATH": "."},
    )
    assert cmd[0:3] == ["docker", "run", "--rm"]
    assert "--network=none" in cmd
    assert "-v" in cmd
    assert f"{tmp_path.resolve()}:/workspace:ro" in cmd
    assert "-w" in cmd
    assert "/workspace" in cmd
    assert "-e" in cmd
    assert "PYTHONPATH=." in cmd
    assert cmd[-3:] == ["python", "-m", "pytest"]


def test_docker_runtime_run_in_container_success(tmp_path: Path):
    runtime = DockerRuntime()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="3 passed in 0.12s\n",
            stderr="",
        )
        result = runtime.run_in_container(tmp_path, ["python", "-m", "pytest"])
        assert result.exit_code == 0
        assert "3 passed" in result.stdout
        assert result.stderr == ""
        assert not result.timed_out
        assert result.duration_ms >= 0


def test_docker_runtime_run_in_container_timeout(tmp_path: Path):
    runtime = DockerRuntime()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=5)):
        result = runtime.run_in_container(tmp_path, ["python", "-m", "pytest"], timeout_seconds=5)
        assert result.exit_code == -1
        assert result.timed_out is True
        assert "timed out after 5 seconds" in result.stderr


def test_docker_runtime_run_in_container_invalid_dir():
    runtime = DockerRuntime()
    invalid_path = Path("/nonexistent/directory/path/12345")
    with pytest.raises(ValidationException):
        runtime.run_in_container(invalid_path, ["python", "-m", "pytest"])


def test_docker_runtime_output_truncation():
    runtime = DockerRuntime()
    large_output = "A" * 200
    truncated = runtime._truncate_output(large_output, max_bytes=50)
    assert len(truncated.encode("utf-8")) > 50  # includes suffix
    assert "[output truncated]" in truncated


def test_workspace_manager_lifecycle(tmp_path: Path):
    wm = WorkspaceManager()
    # Create source dir with files
    source = tmp_path / "source"
    source.mkdir()
    (source / "file1.py").write_text("print('hello')", encoding="utf-8")
    (source / "sub").mkdir()
    (source / "sub" / "file2.py").write_text("x = 1", encoding="utf-8")

    with wm.isolated_workspace(source_dir=source) as ws:
        assert ws.exists()
        assert (ws / "file1.py").read_text(encoding="utf-8") == "print('hello')"
        assert (ws / "sub" / "file2.py").read_text(encoding="utf-8") == "x = 1"
        # Modify file in isolated workspace
        (ws / "file1.py").write_text("print('mutated')", encoding="utf-8")
        # Ensure source remains unchanged
        assert (source / "file1.py").read_text(encoding="utf-8") == "print('hello')"

    # Cleaned up after context manager
    assert not ws.exists()

