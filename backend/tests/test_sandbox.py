"""Unit tests for Docker sandbox configuration, runtime abstraction, and workspace management."""

import io
import time
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
    assert SandboxConfig().docker_image == "faultline-runner:py312"


@pytest.mark.parametrize(
    "values",
    [
        {"network_disabled": False},
        {"read_only_rootfs": False},
        {"drop_all_capabilities": False},
        {"no_new_privileges": False},
        {"container_user": "0:0"},
        {"timeout_seconds": 0},
    ],
)
def test_sandbox_config_rejects_weakened_security_or_limits(values):
    with pytest.raises(ValueError):
        SandboxConfig(**values)


def test_controlled_runner_image_uses_pinned_pytest_and_non_root_user():
    dockerfile = Path(__file__).parents[2] / "docker" / "runner.Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in content
    assert "pytest==8.3.5" in content
    assert "USER 1000:1000" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content
    assert "pip install" not in content.split("CMD", maxsplit=1)[-1]


def test_backend_and_untrusted_runner_images_are_separate():
    root = Path(__file__).parents[2]
    backend_dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM docker:27.5.1-cli AS docker-cli" in backend_dockerfile
    assert "COPY --from=docker-cli /usr/local/bin/docker" in backend_dockerfile
    assert "docker.sock" not in backend_dockerfile


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
    command = [
        "python",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
    ]
    cmd = runtime._build_docker_command(
        workspace_path=tmp_path,
        command=command,
        container_name="faultline-test",
    )
    assert cmd[0:4] == ["docker", "run", "--name", "faultline-test"]
    assert "--network=none" in cmd
    assert "--read-only" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges" in cmd
    assert "-v" in cmd
    assert f"{tmp_path.resolve()}:/workspace:ro" in cmd
    assert "-w" in cmd
    assert "/workspace" in cmd
    assert "faultline-runner:py312" in cmd
    assert cmd[-7:] == command
    assert "--privileged" not in cmd
    assert not any("docker.sock" in item for item in cmd)
    assert "--rm" not in cmd


class FakeProcess:
    def __init__(self, stdout=b"", stderr=b"", *, keep_running=False):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = 0
        self.keep_running = keep_running
        self.terminated = False

    def poll(self):
        if self.keep_running and not self.terminated:
            return None
        time.sleep(0.05)
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def test_docker_runtime_run_in_container_success(tmp_path: Path):
    runtime = DockerRuntime()
    process = FakeProcess(b"3 passed in 0.12s\n", b"runner warning\n")
    command = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    with (
        patch("subprocess.Popen", return_value=process),
        patch.object(runtime, "_remove_container") as cleanup,
    ):
        result = runtime.run_in_container(tmp_path, command)
        assert result.exit_code == 0
        assert "3 passed" in result.stdout
        assert result.stderr == "runner warning\n"
        assert not result.timed_out
        assert result.duration_ms >= 0
        cleanup.assert_called_once()


def test_docker_runtime_run_in_container_timeout(tmp_path: Path):
    runtime = DockerRuntime()
    process = FakeProcess(keep_running=True)
    command = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    with (
        patch("subprocess.Popen", return_value=process),
        patch.object(runtime, "_remove_container") as cleanup,
    ):
        result = runtime.run_in_container(tmp_path, command, timeout_seconds=1)
        assert result.exit_code == -15
        assert result.timed_out is True
        assert "timed out after 1 seconds" in result.stderr
        assert process.terminated
        cleanup.assert_called_once()


def test_docker_runtime_run_in_container_invalid_dir():
    runtime = DockerRuntime()
    invalid_path = Path("/nonexistent/directory/path/12345")
    with pytest.raises(ValidationException):
        runtime.run_in_container(
            invalid_path, ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
        )


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_docker_runtime_stops_when_stream_output_exceeds_limit(tmp_path: Path, stream: str):
    runtime = DockerRuntime(SandboxConfig(max_stdout_bytes=32, max_stderr_bytes=32))
    process = FakeProcess(
        stdout=b"A" * 4096 if stream == "stdout" else b"",
        stderr=b"A" * 4096 if stream == "stderr" else b"",
        keep_running=True,
    )
    command = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    with (
        patch("subprocess.Popen", return_value=process),
        patch.object(runtime, "_remove_container") as cleanup,
    ):
        result = runtime.run_in_container(tmp_path, command)

    assert result.output_limited
    captured = result.stdout if stream == "stdout" else result.stderr
    assert len(captured.split("\n...")[0].encode("utf-8")) <= 32
    assert process.terminated
    cleanup.assert_called_once()


def test_docker_runtime_rejects_repository_supplied_command(tmp_path: Path):
    runtime = DockerRuntime()
    with (
        patch("subprocess.Popen") as popen,
        pytest.raises(ValidationException, match="approved"),
    ):
        runtime.run_in_container(tmp_path, ["sh", "-c", "echo unsafe"])
    popen.assert_not_called()


def test_docker_runtime_cleanup_accepts_already_removed_container():
    with patch(
        "subprocess.run",
        return_value=MagicMock(returncode=1, stderr="Error: No such container"),
    ) as run:
        DockerRuntime._remove_container("faultline-test")
    assert run.call_args.args[0][:3] == ["docker", "rm", "--force"]


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


def test_workspace_manager_cleans_up_after_execution_failure(tmp_path: Path):
    manager = WorkspaceManager()
    workspace = None
    with pytest.raises(RuntimeError, match="execution failed"):
        with manager.isolated_workspace() as workspace:
            (workspace / "partial.py").write_text("x = 1", encoding="utf-8")
            raise RuntimeError("execution failed")
    assert workspace is not None
    assert not workspace.exists()
