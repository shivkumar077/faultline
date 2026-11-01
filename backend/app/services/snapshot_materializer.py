import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.exceptions import FaultlineException, ValidationException
from app.core.git_environment import isolated_git_environment
from app.core.logging_config import safe_error_log
from app.core.validators import validate_and_normalize_github_url

logger = logging.getLogger("faultline.materializer")


class SnapshotMaterializer:
    def __init__(self, timeout_seconds: int = 60, max_repo_size_bytes: int = 100 * 1024 * 1024):
        self.timeout = timeout_seconds
        self.max_repo_size = max_repo_size_bytes

    def materialize_commit(self, repository_url: str, commit_hash: str, target_dir: str) -> str:
        """Clone and checkout an exact commit hash in target_dir using secure subprocess."""
        repository_url = validate_and_normalize_github_url(repository_url)
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit_hash or ""):
            raise ValidationException("Commit hash must be a hexadecimal Git object identifier.")

        try:
            # 1. Initialize git repo in target directory
            init_res = subprocess.run(
                ["git", "init", target_dir],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )
            if init_res.returncode != 0:
                raise FaultlineException(
                    status_code=500,
                    detail="Failed to initialize the snapshot repository.",
                    error_code="GIT_INIT_FAILED",
                )

            # 2. Add remote origin
            remote_res = subprocess.run(
                ["git", "-C", target_dir, "remote", "add", "origin", repository_url],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )
            if remote_res.returncode != 0:
                raise FaultlineException(
                    status_code=500,
                    detail="Failed to configure the snapshot repository.",
                    error_code="GIT_REMOTE_FAILED",
                )

            # 3. Fetch specific commit hash with shallow depth
            fetch_res = subprocess.run(
                [
                    "git",
                    "-C",
                    target_dir,
                    "fetch",
                    "--depth",
                    "1",
                    "--no-recurse-submodules",
                    "origin",
                    commit_hash,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )

            # If shallow fetch by SHA failed (some remotes disallow direct SHA fetch),
            # try fallback shallow fetch
            if fetch_res.returncode != 0:
                logger.info("Direct commit fetch failed; trying the bounded fallback fetch.")
                fallback_fetch = subprocess.run(
                    [
                        "git",
                        "-C",
                        target_dir,
                        "fetch",
                        "--depth",
                        "10",
                        "--no-recurse-submodules",
                        "origin",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    shell=False,
                    check=False,
                    env=isolated_git_environment(),
                )
                if fallback_fetch.returncode != 0:
                    raise FaultlineException(
                        status_code=400,
                        detail="Failed to fetch the requested snapshot commit.",
                        error_code="FETCH_COMMIT_FAILED",
                    )

            # 4. Checkout exact commit
            checkout_res = subprocess.run(
                ["git", "-C", target_dir, "checkout", "--force", commit_hash],
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )
            if checkout_res.returncode != 0:
                raise FaultlineException(
                    status_code=400,
                    detail="Failed to check out the requested snapshot commit.",
                    error_code="CHECKOUT_COMMIT_FAILED",
                )

            # 5. Verify HEAD matches expected commit
            rev_res = subprocess.run(
                ["git", "-C", target_dir, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )
            actual_head = rev_res.stdout.strip()
            if not actual_head.startswith(commit_hash) and not commit_hash.startswith(actual_head):
                raise FaultlineException(
                    status_code=400,
                    detail=f"Materialized {actual_head} does not match {commit_hash}.",
                    error_code="COMMIT_MISMATCH",
                )

            return actual_head

        except subprocess.TimeoutExpired as exc:
            raise FaultlineException(
                status_code=504,
                detail=f"Repository materialization timed out after {self.timeout}s.",
                error_code="MATERIALIZATION_TIMEOUT",
            ) from exc

    @contextmanager
    def materialized_workspace(
        self, repository_url: str, commit_hash: str
    ) -> Generator[Path, None, None]:
        """Isolated workspace context manager with the exact materialized commit."""
        temp_dir = tempfile.mkdtemp(prefix="faultline_materialize_")
        try:
            self.materialize_commit(repository_url, commit_hash, temp_dir)
            yield Path(temp_dir)
        finally:
            try:
                shutil.rmtree(temp_dir)
            except FileNotFoundError:
                pass
            except OSError as exc:
                safe_error_log(logger, "snapshot_workspace_cleanup_failed", exc)
                raise FaultlineException(
                    status_code=500,
                    detail="Snapshot workspace cleanup failed.",
                    error_code="WORKSPACE_CLEANUP_FAILED",
                ) from exc


snapshot_materializer = SnapshotMaterializer()
