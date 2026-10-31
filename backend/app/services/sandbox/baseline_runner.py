"""Baseline test execution runner using sandboxed Docker container."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import FaultlineException, ValidationException
from app.services.sandbox.docker_runtime import DockerRuntime, docker_runtime
from app.services.sandbox.test_discovery import TestDiscoveryService, test_discovery_service

logger = logging.getLogger("faultline.sandbox.baseline")
_COUNT_PATTERNS = {
    "passed_count": re.compile(r"(\d+)\s+passed\b"),
    "failed_count": re.compile(r"(\d+)\s+failed\b"),
    "skipped_count": re.compile(r"(\d+)\s+skipped\b"),
}


def parse_test_counts(output: str) -> dict[str, int | None]:
    """Extract common pytest/unittest summary counts without retaining raw output."""
    counts = dict.fromkeys(_COUNT_PATTERNS)
    for name, pattern in _COUNT_PATTERNS.items():
        match = pattern.search(output)
        if match:
            counts[name] = int(match.group(1))
    unittest_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if unittest_match and counts["passed_count"] is None and "OK" in output:
        counts["passed_count"] = int(unittest_match.group(1))
    return counts


@dataclass
class BaselineRunOutput:
    """Result of running baseline tests against unmodified snapshot."""

    command: str
    status: str  # "passed", "failed", "timeout", "error"
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    framework: str
    test_files_count: int
    passed_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    infrastructure_error: str | None = None
    timed_out: bool = False


class BaselineRunner:
    """Executes unmodified test suites in an isolated Docker container."""

    def __init__(
        self,
        runtime: DockerRuntime | None = None,
        discovery: TestDiscoveryService | None = None,
    ):
        self.runtime = runtime or docker_runtime
        self.discovery = discovery or test_discovery_service

    def run_baseline(
        self,
        workspace_path: Path,
        *,
        custom_command: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> BaselineRunOutput:
        """Discover and execute baseline test suite.

        Fails closed: requires Docker daemon to be available.
        """
        # Fail-closed check
        self.runtime.require_availability()

        if custom_command is not None:
            if tuple(custom_command) not in DockerRuntime.APPROVED_COMMANDS:
                raise ValidationException(
                    "Only approved pytest and unittest runner commands are allowed."
                )
            command = custom_command
            framework = "pytest" if "pytest" in command else "unittest"
            test_files_count = 0
        else:
            discovery_result = self.discovery.discover(workspace_path)
            if not discovery_result.has_tests:
                return BaselineRunOutput(
                    command="none",
                    status="failed",
                    exit_code=1,
                    stdout="",
                    stderr="No test suite discovered in the repository.",
                    duration_ms=0,
                    framework="none",
                    test_files_count=0,
                )
            command = discovery_result.recommended_command
            framework = discovery_result.framework
            test_files_count = len(discovery_result.test_files)

        command_str = " ".join(command)
        command_identifier = framework
        logger.info("Executing baseline runner: %s", command_identifier)

        try:
            res = self.runtime.run_in_container(
                workspace_path=workspace_path,
                command=command,
                timeout_seconds=timeout_seconds,
            )

            if res.output_limited:
                status = "error"
                infrastructure_error = "OUTPUT_LIMIT_EXCEEDED"
            elif res.exit_code in {125, 126, 127}:
                status = "error"
                infrastructure_error = "DOCKER_RUN_FAILED"
            elif res.timed_out:
                status = "timeout"
                infrastructure_error = None
            elif res.exit_code == 0:
                status = "passed"
                infrastructure_error = None
            else:
                status = "failed"
                infrastructure_error = None

            return BaselineRunOutput(
                command=command_str,
                status=status,
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_ms=res.duration_ms,
                framework=framework,
                test_files_count=test_files_count,
                timed_out=res.timed_out,
                infrastructure_error=infrastructure_error,
                **parse_test_counts(f"{res.stdout}\n{res.stderr}"),
            )

        except FaultlineException:
            raise
        except Exception as exc:
            logger.error("Baseline execution failed (%s)", type(exc).__name__)
            return BaselineRunOutput(
                command=command_str,
                status="error",
                exit_code=None,
                stdout="",
                stderr="Baseline execution failed due to an execution infrastructure error.",
                duration_ms=0,
                framework=framework,
                test_files_count=test_files_count,
                infrastructure_error="BASELINE_EXECUTION_FAILED",
            )


baseline_runner = BaselineRunner()
