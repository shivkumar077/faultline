import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.core.exceptions import FaultlineException, ValidationException
from app.core.git_environment import isolated_git_environment
from app.core.logging_config import safe_error_log

logger = logging.getLogger("faultline.ingestion")

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "vendor",
    ".next",
    "coverage",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pyc",
    ".wasm",
    ".ttf",
    ".woff",
    ".woff2",
    ".eot",
    ".mp3",
    ".mp4",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".xml": "XML",
}


class IngestionService:
    def __init__(
        self,
        clone_timeout_seconds: int = 60,
        max_repo_size_bytes: int = 100 * 1024 * 1024,
        max_file_size_bytes: int = 2 * 1024 * 1024,
        max_file_count: int = 5000,
    ):
        self.clone_timeout = clone_timeout_seconds
        self.max_repo_size = max_repo_size_bytes
        self.max_file_size = max_file_size_bytes
        self.max_file_count = max_file_count

    def clone_repository(self, repository_url: str, branch: str, target_dir: str) -> str:
        """Perform shallow, single-branch clone into target directory and return commit hash."""
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            branch,
            "--no-recurse-submodules",
            repository_url,
            target_dir,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
                shell=False,
                check=False,
                env=isolated_git_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise FaultlineException(
                status_code=504,
                detail=f"Repository clone timed out after {self.clone_timeout} seconds.",
                error_code="CLONE_TIMEOUT",
            ) from exc
        except FileNotFoundError as exc:
            raise FaultlineException(
                status_code=500,
                detail="Git executable not found in system PATH.",
                error_code="GIT_NOT_FOUND",
            ) from exc

        if result.returncode != 0:
            logger.warning("Git clone failed with exit code %d.", result.returncode)
            raise FaultlineException(
                status_code=400,
                detail="Failed to clone the configured public repository.",
                error_code="CLONE_FAILED",
            )

        # Retrieve commit hash
        rev_cmd = ["git", "rev-parse", "HEAD"]
        rev_res = subprocess.run(
            rev_cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
            env=isolated_git_environment(),
        )
        if rev_res.returncode != 0:
            raise FaultlineException(
                status_code=400,
                detail="Failed to resolve commit hash from cloned repository.",
                error_code="COMMIT_RESOLUTION_FAILED",
            )

        return rev_res.stdout.strip()

    def inspect_workspace(self, workspace_path: str) -> dict[str, Any]:
        """Walk workspace, validate safety limits, and generate source inventory."""
        root = Path(workspace_path).resolve()

        total_files = 0
        total_directories = 0
        total_size = 0
        extension_counts: dict[str, int] = {}
        language_bytes: dict[str, int] = {}
        file_entries: list[dict[str, Any]] = []

        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            # Prune ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRECTORIES]
            total_directories += len(dirnames)

            for filename in filenames:
                total_files += 1
                if total_files > self.max_file_count:
                    raise ValidationException(
                        f"Repository exceeds maximum allowed file count ({self.max_file_count})."
                    )

                file_path = Path(dirpath) / filename

                # Prevent symlink traversal outside workspace root
                try:
                    resolved_file = file_path.resolve()
                    if not resolved_file.is_relative_to(root):
                        logger.warning(
                            "Skipping repository symlink outside workspace: %s",
                            file_path.relative_to(root).as_posix(),
                        )
                        continue
                except (ValueError, RuntimeError):
                    continue

                if not file_path.is_file():
                    continue

                try:
                    file_size = file_path.stat().st_size
                except OSError:
                    continue

                total_size += file_size
                if total_size > self.max_repo_size:
                    raise ValidationException(
                        f"Repository exceeds maximum allowed size ({self.max_repo_size} bytes)."
                    )

                rel_path = file_path.relative_to(root).as_posix()
                ext = file_path.suffix.lower()

                extension_counts[ext] = extension_counts.get(ext, 0) + 1

                lang = LANGUAGE_MAP.get(ext)
                if lang:
                    language_bytes[lang] = language_bytes.get(lang, 0) + file_size

                is_binary = ext in BINARY_EXTENSIONS
                sha256_hash: str | None = None

                # Compute hash for eligible non-binary files within size limits
                if not is_binary and file_size <= self.max_file_size:
                    try:
                        content = file_path.read_bytes()
                        # Secondary binary check: null byte check
                        if b"\x00" in content[:1024]:
                            is_binary = True
                        else:
                            sha256_hash = hashlib.sha256(content).hexdigest()
                    except (OSError, MemoryError):
                        sha256_hash = None

                file_entries.append(
                    {
                        "path": rel_path,
                        "size_bytes": file_size,
                        "extension": ext,
                        "is_binary": is_binary,
                        "sha256": sha256_hash,
                    }
                )

        # Calculate approximate language percentages based on bytes
        total_lang_bytes = sum(language_bytes.values())
        language_distribution: dict[str, float] = {}
        if total_lang_bytes > 0:
            for lang, b in language_bytes.items():
                language_distribution[lang] = round((b / total_lang_bytes) * 100, 2)

        return {
            "total_files": total_files,
            "total_directories": total_directories,
            "total_size_bytes": total_size,
            "extension_counts": extension_counts,
            "language_distribution": language_distribution,
            "files": file_entries,
        }

    def ingest(self, repository_url: str, branch: str) -> tuple[str, dict[str, Any]]:
        """Clone repository safely into isolated temporary directory, inspect, and clean up."""
        temp_dir = tempfile.mkdtemp(prefix="faultline_repo_")
        try:
            commit_hash = self.clone_repository(repository_url, branch, temp_dir)
            inventory = self.inspect_workspace(temp_dir)
            return commit_hash, inventory
        finally:
            try:
                shutil.rmtree(temp_dir)
            except FileNotFoundError:
                pass
            except OSError as exc:
                safe_error_log(logger, "repository_workspace_cleanup_failed", exc)
                raise FaultlineException(
                    status_code=500,
                    detail="Repository workspace cleanup failed.",
                    error_code="WORKSPACE_CLEANUP_FAILED",
                ) from exc


ingestion_service = IngestionService()
