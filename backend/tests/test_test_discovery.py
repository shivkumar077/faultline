"""Unit tests for the test discovery service."""

from pathlib import Path

from app.services.sandbox.test_discovery import TestDiscoveryService


def test_test_discovery_empty_dir(tmp_path: Path):
    service = TestDiscoveryService()
    result = service.discover(tmp_path)
    assert not result.has_tests
    assert result.framework == "none"
    assert result.test_files == []


def test_test_discovery_invalid_dir():
    service = TestDiscoveryService()
    result = service.discover(Path("/nonexistent/directory/path/54321"))
    assert not result.has_tests
    assert result.framework == "none"


def test_test_discovery_unittest_fallback(tmp_path: Path):
    service = TestDiscoveryService()
    test_file = tmp_path / "test_example.py"
    test_file.write_text(
        "import unittest\nclass TestSample(unittest.TestCase):\n    def test_pass(self): pass\n",
        encoding="utf-8",
    )
    result = service.discover(tmp_path)
    assert result.has_tests
    assert result.framework == "unittest"
    assert "test_example.py" in result.test_files
    assert result.recommended_command[:4] == ["python", "-m", "unittest", "discover"]


def test_test_discovery_pytest_by_import(tmp_path: Path):
    service = TestDiscoveryService()
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "import pytest\ndef test_feature():\n    assert True\n",
        encoding="utf-8",
    )
    result = service.discover(tmp_path)
    assert result.has_tests
    assert result.framework == "pytest"
    assert result.recommended_command[:4] == ["python", "-m", "pytest", "-q"]


def test_test_discovery_pytest_by_config(tmp_path: Path):
    service = TestDiscoveryService()
    ini_file = tmp_path / "pytest.ini"
    ini_file.write_text("[pytest]\npython_files = test_*.py\n", encoding="utf-8")
    test_file = tmp_path / "test_app.py"
    test_file.write_text("def test_ok(): pass\n", encoding="utf-8")

    result = service.discover(tmp_path)
    assert result.has_tests
    assert result.framework == "pytest"
    assert result.details["has_pytest_config"] == "True"


def test_test_discovery_ignores_venv_and_git(tmp_path: Path):
    service = TestDiscoveryService()
    git_dir = tmp_path / ".git" / "tests"
    git_dir.mkdir(parents=True)
    (git_dir / "test_ignored.py").write_text("pass", encoding="utf-8")

    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "test_venv.py").write_text("pass", encoding="utf-8")

    valid_test = tmp_path / "tests"
    valid_test.mkdir()
    (valid_test / "test_valid.py").write_text("import pytest\n", encoding="utf-8")

    result = service.discover(tmp_path)
    assert result.has_tests
    assert len(result.test_files) == 1
    assert result.test_files[0] == "tests/test_valid.py"
