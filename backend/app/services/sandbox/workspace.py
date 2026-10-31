"""Isolated workspace management for sandboxed test execution."""

import logging
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.exceptions import FaultlineException

logger = logging.getLogger("faultline.sandbox.workspace")


class WorkspaceManager:
    """Manages ephemeral directory environments for isolated test execution."""

    def __init__(self, prefix: str = "faultline_sandbox_"):
        self.prefix = prefix

    def create_workspace(self) -> Path:
        """Create a new temporary directory for an isolated workspace."""
        temp_dir = tempfile.mkdtemp(prefix=self.prefix)
        return Path(temp_dir).resolve()

    def clone_workspace(self, source_dir: Path) -> Path:
        """Create a full isolated copy of an existing workspace directory."""
        if not source_dir.is_dir():
            raise FaultlineException(
                status_code=400,
                detail=f"Source directory for workspace copy does not exist: {source_dir}",
                error_code="INVALID_SOURCE_WORKSPACE",
            )
        target_dir = self.create_workspace()
        try:
            # Copy all files and directories preserving contents
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True, symlinks=False)
            return target_dir
        except Exception as exc:
            self.cleanup_workspace(target_dir)
            raise FaultlineException(
                status_code=500,
                detail=f"Failed to clone isolated workspace: {exc}",
                error_code="WORKSPACE_CLONE_FAILED",
            ) from exc

    def cleanup_workspace(self, workspace_path: Path) -> None:
        """Safely remove a workspace directory."""
        if workspace_path.exists():
            try:
                shutil.rmtree(workspace_path)
            except Exception as exc:
                logger.error("Workspace cleanup failed (%s)", type(exc).__name__)
                raise FaultlineException(
                    status_code=500,
                    detail="Isolated workspace cleanup failed.",
                    error_code="WORKSPACE_CLEANUP_FAILED",
                ) from exc

    @contextmanager
    def isolated_workspace(self, source_dir: Path | None = None) -> Generator[Path, None, None]:
        """Context manager yielding an isolated workspace path and guaranteeing cleanup."""
        if source_dir is not None:
            ws = self.clone_workspace(source_dir)
        else:
            ws = self.create_workspace()
        try:
            yield ws
        finally:
            self.cleanup_workspace(ws)


workspace_manager = WorkspaceManager()
