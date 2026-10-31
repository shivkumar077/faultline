"""Docker runtime abstraction for isolated code execution.

Wraps subprocess calls to Docker CLI with strict security flags.
Never executes untrusted code on the host — fails closed if Docker is unavailable.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import FaultlineException, ValidationException
from app.core.sandbox_config import SandboxConfig, sandbox_config

logger = logging.getLogger("faultline.sandbox.docker")


@dataclass
class ContainerResult:
    """Captured output from a container execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class DockerRuntime:
    """Manages Docker container lifecycle for sandboxed test execution."""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or sandbox_config

    def check_availability(self) -> bool:
        """Verify Docker daemon is reachable. Returns False if unavailable."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def require_availability(self) -> None:
        """Raise if Docker daemon is not available. Fail-closed policy."""
        if not self.check_availability():
            raise FaultlineException(
                status_code=503,
                detail=(
                    "Docker daemon is not available. "
                    "Faultline requires Docker for isolated test execution. "
                    "Code will never be executed on the host."
                ),
                error_code="DOCKER_UNAVAILABLE",
            )

    def run_in_container(
        self,
        workspace_path: Path,
        command: list[str],
        *,
        timeout_seconds: int | None = None,
        environment: dict[str, str] | None = None,
    ) -> ContainerResult:
        """Execute a command inside an isolated Docker container.

        Args:
            workspace_path: Host directory to mount read-only at /workspace.
            command: Command and arguments to run inside the container.
            timeout_seconds: Override default timeout.
            environment: Additional environment variables.

        Returns:
            ContainerResult with captured output.

        Raises:
            FaultlineException: If Docker is unavailable or container fails to start.
            ValidationException: If workspace path is invalid.
        """
        if not workspace_path.is_dir():
            raise ValidationException(f"Workspace directory does not exist: {workspace_path}")

        timeout = timeout_seconds or self.config.timeout_seconds

        docker_cmd = self._build_docker_command(workspace_path, command, environment=environment)

        logger.info(
            "Running container: image=%s, timeout=%ds, cmd=%s",
            self.config.docker_image,
            timeout,
            " ".join(command),
        )

        import time

        start_ns = time.perf_counter_ns()

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
            elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

            stdout = self._truncate_output(result.stdout, self.config.max_stdout_bytes)
            stderr = self._truncate_output(result.stderr, self.config.max_stderr_bytes)

            return ContainerResult(
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=elapsed_ms,
                timed_out=False,
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            logger.warning("Container execution timed out after %ds", timeout)
            return ContainerResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds.",
                duration_ms=elapsed_ms,
                timed_out=True,
            )

        except FileNotFoundError as exc:
            raise FaultlineException(
                status_code=503,
                detail="Docker CLI not found. Cannot execute sandboxed tests.",
                error_code="DOCKER_NOT_FOUND",
            ) from exc

    def _build_docker_command(
        self,
        workspace_path: Path,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> list[str]:
        """Assemble the full docker run command with security flags."""
        docker_cmd = ["docker", "run", "--rm"]

        # Add security and resource flags
        docker_cmd.extend(self.config.to_docker_flags())

        # Mount workspace as read-only
        workspace_abs = str(workspace_path.resolve())
        docker_cmd.extend(
            [
                "-v",
                f"{workspace_abs}:{self.config.workspace_mount_target}:ro",
            ]
        )

        # Set working directory
        docker_cmd.extend(["-w", self.config.workspace_mount_target])

        # Add environment variables
        if environment:
            for key, value in environment.items():
                docker_cmd.extend(["-e", f"{key}={value}"])

        # Image and command
        docker_cmd.append(self.config.docker_image)
        docker_cmd.extend(command)

        return docker_cmd

    @staticmethod
    def _truncate_output(output: str, max_bytes: int) -> str:
        """Truncate output to max_bytes, adding a truncation notice."""
        if len(output.encode("utf-8", errors="replace")) <= max_bytes:
            return output

        truncated = output.encode("utf-8", errors="replace")[:max_bytes].decode(
            "utf-8", errors="replace"
        )
        return truncated + "\n... [output truncated]"


docker_runtime = DockerRuntime()
