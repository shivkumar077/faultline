"""Baseline test execution runner using sandboxed Docker container."""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import FaultlineException
from app.services.sandbox.docker_runtime import DockerRuntime, docker_runtime
from app.services.sandbox.test_discovery import TestDiscoveryService, test_discovery_service

logger = logging.getLogger("faultline.sandbox.baseline")


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

        if custom_command:
            command = custom_command
            framework = "custom"
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
        logger.info("Executing baseline test command: %s", command_str)

        try:
            res = self.runtime.run_in_container(
                workspace_path=workspace_path,
                command=command,
                timeout_seconds=timeout_seconds,
            )

            if res.timed_out:
                status = "timeout"
            elif res.exit_code == 0:
                status = "passed"
            else:
                status = "failed"

            return BaselineRunOutput(
                command=command_str,
                status=status,
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_ms=res.duration_ms,
                framework=framework,
                test_files_count=test_files_count,
            )

        except FaultlineException:
            raise
        except Exception as exc:
            logger.error("Baseline execution failed: %s", exc)
            return BaselineRunOutput(
                command=command_str,
                status="error",
                exit_code=None,
                stdout="",
                stderr=f"Baseline execution error: {exc}",
                duration_ms=0,
                framework=framework,
                test_files_count=test_files_count,
            )


baseline_runner = BaselineRunner()

