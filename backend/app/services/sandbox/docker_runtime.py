"""Docker runtime abstraction for isolated code execution.

Wraps subprocess calls to Docker CLI with strict security flags.
Never executes untrusted code on the host — fails closed if Docker is unavailable.
"""

import logging
import subprocess
import threading
import time
import uuid
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
    output_limited: bool = False


class DockerRuntime:
    """Manages Docker container lifecycle for sandboxed test execution."""

    APPROVED_COMMANDS = {
        ("python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"),
        ("python", "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"),
    }

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
    ) -> ContainerResult:
        """Execute a command inside an isolated Docker container.

        Args:
            workspace_path: Host directory to mount read-only at /workspace.
            command: Command and arguments to run inside the container.
            timeout_seconds: Override default timeout.

        Returns:
            ContainerResult with captured output.

        Raises:
            FaultlineException: If Docker is unavailable or container fails to start.
            ValidationException: If workspace path is invalid.
        """
        if not workspace_path.is_dir():
            raise ValidationException(f"Workspace directory does not exist: {workspace_path}")

        if tuple(command) not in self.APPROVED_COMMANDS:
            raise ValidationException(
                "Only approved pytest and unittest runner commands are allowed."
            )

        timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds
        if timeout <= 0:
            raise ValidationException("Execution timeout must be greater than zero.")

        container_name = f"faultline-{uuid.uuid4().hex}"
        docker_cmd = self._build_docker_command(workspace_path, command, container_name)

        logger.info(
            "Running sandbox container: image=%s, timeout=%ds",
            self.config.docker_image,
            timeout,
        )

        start_ns = time.perf_counter_ns()
        process: subprocess.Popen[bytes] | None = None
        output = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}
        output_lock = threading.Lock()
        output_exceeded = threading.Event()
        capture_failed = threading.Event()
        readers: list[threading.Thread] = []
        timed_out = False

        try:
            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            readers = [
                threading.Thread(
                    target=self._capture_pipe,
                    args=(
                        process.stdout,
                        output["stdout"],
                        "stdout",
                        truncated,
                        self.config.max_stdout_bytes,
                        output_lock,
                        output_exceeded,
                        capture_failed,
                    ),
                    daemon=True,
                ),
                threading.Thread(
                    target=self._capture_pipe,
                    args=(
                        process.stderr,
                        output["stderr"],
                        "stderr",
                        truncated,
                        self.config.max_stderr_bytes,
                        output_lock,
                        output_exceeded,
                        capture_failed,
                    ),
                    daemon=True,
                ),
            ]
            for reader in readers:
                reader.start()

            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if output_exceeded.is_set():
                    logger.warning("Sandbox output limit exceeded; stopping container")
                    self._terminate_process(process)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    logger.warning("Sandbox execution timed out after %ds", timeout)
                    self._terminate_process(process)
                    break
                time.sleep(0.02)

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()

        except FileNotFoundError as exc:
            raise FaultlineException(
                status_code=503,
                detail="Docker CLI not found. Cannot execute sandboxed tests.",
                error_code="DOCKER_NOT_FOUND",
            ) from exc
        except OSError as exc:
            raise FaultlineException(
                status_code=503,
                detail="Docker CLI could not start the sandbox container.",
                error_code="DOCKER_START_FAILED",
            ) from exc
        finally:
            if process is not None:
                for reader in readers:
                    reader.join(timeout=2)
                for pipe in (process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()
                for reader in readers:
                    reader.join(timeout=1)
            self._remove_container(container_name)

        if capture_failed.is_set():
            raise FaultlineException(
                status_code=503,
                detail="Sandbox output capture failed.",
                error_code="OUTPUT_CAPTURE_FAILED",
            )
        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        stdout = self._decode_output(output["stdout"], truncated["stdout"])
        stderr = self._decode_output(output["stderr"], truncated["stderr"])
        if timed_out:
            stderr += f"\nExecution timed out after {timeout} seconds."
        elif output_exceeded.is_set():
            stderr += "\nExecution stopped because output exceeded the configured limit."
        return ContainerResult(
            exit_code=process.returncode if process is not None else -1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=elapsed_ms,
            timed_out=timed_out,
            output_limited=output_exceeded.is_set(),
        )

    def _build_docker_command(
        self, workspace_path: Path, command: list[str], container_name: str
    ) -> list[str]:
        """Assemble the full docker run command with security flags."""
        docker_cmd = ["docker", "run", "--name", container_name]

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

        # Image and command
        docker_cmd.append(self.config.docker_image)
        docker_cmd.extend(command)

        return docker_cmd

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        try:
            process.terminate()
        except ProcessLookupError:
            return

    @staticmethod
    def _capture_pipe(
        pipe,
        destination: bytearray,
        stream_name: str,
        truncated: dict[str, bool],
        max_bytes: int,
        lock: threading.Lock,
        output_exceeded: threading.Event,
        capture_failed: threading.Event,
    ) -> None:
        """Drain a pipe continuously while retaining only the configured byte limit."""
        try:
            while chunk := pipe.read(8192):
                with lock:
                    remaining = max_bytes - len(destination)
                    if remaining > 0:
                        destination.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated[stream_name] = True
                        output_exceeded.set()
        except (OSError, ValueError):
            capture_failed.set()

    @staticmethod
    def _decode_output(data: bytearray, truncated: bool) -> str:
        output = bytes(data).decode("utf-8", errors="replace")
        if truncated:
            output += "\n... [output truncated]"
        return output

    @staticmethod
    def _remove_container(container_name: str) -> None:
        """Remove the named container even if the docker run client was terminated."""
        try:
            result = subprocess.run(
                ["docker", "rm", "--force", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                check=False,
            )
        except FileNotFoundError:
            return
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("Docker container cleanup command failed (%s)", type(exc).__name__)
            raise FaultlineException(
                status_code=503,
                detail="Sandbox container cleanup could not be confirmed.",
                error_code="DOCKER_CLEANUP_FAILED",
            ) from exc
        if result.returncode != 0:
            if "no such container" in result.stderr.lower():
                return
            logger.error("Docker container cleanup returned a failure status")
            raise FaultlineException(
                status_code=503,
                detail="Sandbox container cleanup could not be confirmed.",
                error_code="DOCKER_CLEANUP_FAILED",
            )


docker_runtime = DockerRuntime()
