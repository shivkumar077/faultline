"""Execution sandbox configuration with strict resource and security limits."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SandboxConfig:
    """Immutable configuration for Docker-based execution sandboxes."""

    # Docker image for test execution
    docker_image: str = "python:3.12-slim"

    # Resource limits
    cpu_limit: float = 1.0  # CPU cores
    memory_limit: str = "512m"  # Docker memory notation
    max_pids: int = 128
    timeout_seconds: int = 60

    # Output capture limits (bytes)
    max_stdout_bytes: int = 100 * 1024  # 100 KB
    max_stderr_bytes: int = 100 * 1024  # 100 KB

    # Security flags
    network_disabled: bool = True
    read_only_rootfs: bool = True
    drop_all_capabilities: bool = True
    no_new_privileges: bool = True
    container_user: str = "1000:1000"

    # Workspace
    workspace_mount_target: str = "/workspace"
    tmpfs_mounts: dict[str, str] = field(default_factory=lambda: {"/tmp": "size=64m,noexec"})

    def to_docker_flags(self) -> list[str]:
        """Build the security and resource Docker CLI flags."""
        flags: list[str] = []

        # Network isolation
        if self.network_disabled:
            flags.append("--network=none")

        # Read-only root filesystem
        if self.read_only_rootfs:
            flags.append("--read-only")

        # Drop all Linux capabilities
        if self.drop_all_capabilities:
            flags.append("--cap-drop=ALL")

        # Prevent privilege escalation
        if self.no_new_privileges:
            flags.append("--security-opt=no-new-privileges")

        # Non-root user
        flags.extend(["--user", self.container_user])

        # Resource limits
        flags.extend(["--memory", self.memory_limit])
        flags.extend(["--cpus", str(self.cpu_limit)])
        flags.extend(["--pids-limit", str(self.max_pids)])

        # Tmpfs mounts for writable scratch space
        for mount_point, opts in self.tmpfs_mounts.items():
            flags.extend(["--tmpfs", f"{mount_point}:{opts}"])

        return flags


# Default sandbox configuration
sandbox_config = SandboxConfig()
