"""Automated test framework and suite discovery for target repositories."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("faultline.sandbox.test_discovery")


@dataclass
class TestDiscoveryResult:
    """Discovered test suite metadata and recommended execution command."""

    __test__ = False
    framework: str  # "pytest" or "unittest"
    test_files: list[str] = field(default_factory=list)
    recommended_command: list[str] = field(default_factory=list)
    has_tests: bool = False
    details: dict[str, str] = field(default_factory=dict)


class TestDiscoveryService:
    """Discovers test suites and execution commands in a workspace."""

    __test__ = False
    PYTEST_CONFIG_FILES = [
        "pytest.ini",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
    ]

    def discover(self, workspace_path: Path) -> TestDiscoveryResult:
        """Analyze workspace to determine test files and appropriate runner."""
        if not workspace_path.is_dir():
            return TestDiscoveryResult(
                framework="none",
                has_tests=False,
                details={"error": "Workspace directory not found"},
            )

        test_files = self._find_test_files(workspace_path)
        if not test_files:
            return TestDiscoveryResult(
                framework="none",
                has_tests=False,
                details={"info": "No test files matching test_*.py or *_test.py found"},
            )

        # Check for pytest configuration or indicators
        has_pytest_config = self._has_pytest_config(workspace_path)
        uses_pytest_imports = self._scan_for_pytest_imports(workspace_path, test_files)

        if has_pytest_config or uses_pytest_imports:
            framework = "pytest"
            cmd = [
                "python",
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ]
        else:
            # Fall back to Python unittest discovery
            framework = "unittest"
            cmd = ["python", "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"]

        return TestDiscoveryResult(
            framework=framework,
            test_files=test_files,
            recommended_command=cmd,
            has_tests=True,
            details={
                "has_pytest_config": str(has_pytest_config),
                "uses_pytest_imports": str(uses_pytest_imports),
                "total_test_files": str(len(test_files)),
            },
        )

    def _find_test_files(self, workspace_path: Path) -> list[str]:
        """Find relative paths of test files in workspace."""
        matches: list[str] = []
        for p in workspace_path.rglob("*.py"):
            name = p.name.lower()
            if (
                name.startswith("test_")
                or name.endswith("_test.py")
                or "/tests/" in p.as_posix().lower()
            ):
                # Filter out .git, venv, pycache
                posix = p.relative_to(workspace_path).as_posix()
                if any(
                    ignored in posix for ignored in [".git/", "venv/", ".venv/", "__pycache__/"]
                ):
                    continue
                matches.append(posix)
        return sorted(matches)

    def _has_pytest_config(self, workspace_path: Path) -> bool:
        """Check for pytest configuration files."""
        for config_name in self.PYTEST_CONFIG_FILES:
            cfg = workspace_path / config_name
            if cfg.is_file():
                try:
                    text = cfg.read_text(encoding="utf-8", errors="ignore")
                    if "pytest" in text or "[tool.pytest" in text:
                        return True
                except Exception:
                    continue
        return False

    def _scan_for_pytest_imports(self, workspace_path: Path, test_files: list[str]) -> bool:
        """Check if any test files explicitly import pytest."""
        for rel_path in test_files[:20]:  # Sample up to 20 files
            full_path = workspace_path / rel_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    if "import pytest" in content or "from pytest" in content:
                        return True
                except Exception:
                    continue
        return False


test_discovery_service = TestDiscoveryService()
