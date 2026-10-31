"""Unit tests for the baseline test execution runner."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import FaultlineException, ValidationException
from app.services.sandbox.baseline_runner import BaselineRunner, parse_test_counts
from app.services.sandbox.docker_runtime import ContainerResult, DockerRuntime
from app.services.sandbox.test_discovery import TestDiscoveryResult, TestDiscoveryService


@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=DockerRuntime)
    runtime.check_availability.return_value = True
    runtime.require_availability.return_value = None
    return runtime


@pytest.fixture
def mock_discovery():
    discovery = MagicMock(spec=TestDiscoveryService)
    discovery.discover.return_value = TestDiscoveryResult(
        framework="pytest",
        test_files=["test_one.py"],
        recommended_command=[
            "python",
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ],
        has_tests=True,
    )
    return discovery


def test_baseline_runner_docker_unavailable(tmp_path: Path):
    runtime = MagicMock(spec=DockerRuntime)
    runtime.require_availability.side_effect = FaultlineException(
        status_code=503,
        detail="Docker unavailable",
        error_code="DOCKER_UNAVAILABLE",
    )
    runner = BaselineRunner(runtime=runtime)
    with pytest.raises(FaultlineException) as exc:
        runner.run_baseline(tmp_path)
    assert exc.value.status_code == 503


def test_baseline_runner_no_tests_discovered(tmp_path: Path, mock_runtime):
    discovery = MagicMock(spec=TestDiscoveryService)
    discovery.discover.return_value = TestDiscoveryResult(
        framework="none",
        test_files=[],
        recommended_command=[],
        has_tests=False,
    )
    runner = BaselineRunner(runtime=mock_runtime, discovery=discovery)
    output = runner.run_baseline(tmp_path)
    assert output.status == "failed"
    assert output.command == "none"
    assert "No test suite discovered" in output.stderr
    assert output.test_files_count == 0


def test_baseline_runner_success(tmp_path: Path, mock_runtime, mock_discovery):
    mock_runtime.run_in_container.return_value = ContainerResult(
        exit_code=0,
        stdout="1 passed in 0.05s",
        stderr="",
        duration_ms=50,
        timed_out=False,
    )
    runner = BaselineRunner(runtime=mock_runtime, discovery=mock_discovery)
    output = runner.run_baseline(tmp_path)
    assert output.status == "passed"
    assert output.exit_code == 0
    assert output.command == "python -m pytest -q --tb=short -p no:cacheprovider"
    assert "1 passed" in output.stdout
    assert output.duration_ms == 50
    assert output.framework == "pytest"
    assert output.test_files_count == 1


def test_baseline_runner_failing_tests(tmp_path: Path, mock_runtime, mock_discovery):
    mock_runtime.run_in_container.return_value = ContainerResult(
        exit_code=1,
        stdout="1 failed in 0.05s",
        stderr="AssertionError",
        duration_ms=60,
        timed_out=False,
    )
    runner = BaselineRunner(runtime=mock_runtime, discovery=mock_discovery)
    output = runner.run_baseline(tmp_path)
    assert output.status == "failed"
    assert output.exit_code == 1
    assert "1 failed" in output.stdout


def test_baseline_runner_timeout(tmp_path: Path, mock_runtime, mock_discovery):
    mock_runtime.run_in_container.return_value = ContainerResult(
        exit_code=-1,
        stdout="",
        stderr="Execution timed out",
        duration_ms=60000,
        timed_out=True,
    )
    runner = BaselineRunner(runtime=mock_runtime, discovery=mock_discovery)
    output = runner.run_baseline(tmp_path)
    assert output.status == "timeout"
    assert output.exit_code == -1


def test_baseline_runner_docker_failure_is_infrastructure_error(
    tmp_path: Path, mock_runtime, mock_discovery
):
    mock_runtime.run_in_container.return_value = ContainerResult(
        exit_code=125,
        stdout="",
        stderr="",
        duration_ms=10,
    )
    output = BaselineRunner(runtime=mock_runtime, discovery=mock_discovery).run_baseline(tmp_path)

    assert output.status == "error"
    assert output.infrastructure_error == "DOCKER_RUN_FAILED"


def test_baseline_runner_accepts_only_approved_command(
    tmp_path: Path, mock_runtime, mock_discovery
):
    mock_runtime.run_in_container.return_value = ContainerResult(
        exit_code=0,
        stdout="OK",
        stderr="",
        duration_ms=25,
        timed_out=False,
    )
    runner = BaselineRunner(runtime=mock_runtime, discovery=mock_discovery)
    command = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    output = runner.run_baseline(tmp_path, custom_command=command)
    assert output.command == " ".join(command)
    assert output.framework == "pytest"
    mock_discovery.discover.assert_not_called()


def test_baseline_runner_rejects_arbitrary_command(tmp_path: Path, mock_runtime):
    runner = BaselineRunner(runtime=mock_runtime)
    with pytest.raises(ValidationException, match="approved"):
        runner.run_baseline(tmp_path, custom_command=["sh", "-c", "echo unsafe"])


def test_parse_test_counts_handles_pytest_and_unittest_summaries():
    assert parse_test_counts("2 passed, 1 failed, 3 skipped") == {
        "passed_count": 2,
        "failed_count": 1,
        "skipped_count": 3,
    }
    assert parse_test_counts("Ran 4 tests\n\nOK")["passed_count"] == 4
