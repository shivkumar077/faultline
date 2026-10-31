import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import FaultlineException, ValidationException
from app.core.validators import validate_and_normalize_github_url
from app.services.ingestion_service import IngestionService


def test_url_validation_valid_cases() -> None:
    """Verify various valid GitHub URL formats normalize correctly."""
    assert (
        validate_and_normalize_github_url("https://github.com/octocat/Hello-World")
        == "https://github.com/octocat/Hello-World"
    )
    assert (
        validate_and_normalize_github_url("https://github.com/octocat/Hello-World.git")
        == "https://github.com/octocat/Hello-World"
    )
    assert (
        validate_and_normalize_github_url("https://www.github.com/octocat/Hello-World/")
        == "https://github.com/octocat/Hello-World"
    )


def test_url_validation_invalid_cases() -> None:
    """Verify that unsupported hosts, insecure schemes, credentials, and queries are rejected."""
    invalid_urls = [
        "http://github.com/octocat/Hello-World",  # Not HTTPS
        "https://gitlab.com/octocat/Hello-World",  # Unsupported host
        "https://user:pass@github.com/octocat/Hello-World",  # Embedded credentials
        "https://github.com/octocat/Hello-World?ref=main",  # Query params
        "https://github.com/octocat/Hello-World#readme",  # URL fragment
        "https://github.com/octocat/Hello-World/tree/main",  # Subpath
        "https://github.com/octocat/../malicious",  # Path traversal
        "",  # Empty string
        "not-a-url",
    ]
    for bad_url in invalid_urls:
        with pytest.raises(ValidationException):
            validate_and_normalize_github_url(bad_url)


def test_inspect_workspace_inventory_and_security() -> None:
    """Verify workspace inspection, language distribution, file hashing, and directory pruning."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # Create source files
        (root / "main.py").write_text("print('hello world')", encoding="utf-8")
        (root / "config.json").write_text('{"debug": true}', encoding="utf-8")

        # Create ignored directory with files that must be pruned
        ignored_dir = root / "node_modules" / "express"
        ignored_dir.mkdir(parents=True)
        (ignored_dir / "index.js").write_text("module.exports = {}", encoding="utf-8")

        # Create nested valid directory
        sub_dir = root / "src"
        sub_dir.mkdir()
        (sub_dir / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")

        # Create a binary file
        (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        service = IngestionService()
        inventory = service.inspect_workspace(tmp_dir)

        assert inventory["total_files"] == 4  # main.py, config.json, utils.py, logo.png
        assert "Python" in inventory["language_distribution"]

        # Check file list
        files_by_path = {f["path"]: f for f in inventory["files"]}
        assert "main.py" in files_by_path
        assert files_by_path["main.py"]["is_binary"] is False
        assert files_by_path["main.py"]["sha256"] is not None

        # Binary file check
        assert "logo.png" in files_by_path
        assert files_by_path["logo.png"]["is_binary"] is True
        assert files_by_path["logo.png"]["sha256"] is None

        # Ignored directory check
        assert "node_modules/express/index.js" not in files_by_path


def test_repository_registration_flow(client: TestClient) -> None:
    """Verify project repository connection registration."""
    proj = client.post("/api/v1/projects", json={"name": "Ingestion Target"}).json()
    proj_id = proj["id"]

    # Register valid repo
    res = client.post(
        f"/api/v1/projects/{proj_id}/repositories",
        json={"repository_url": "https://github.com/pallets/flask", "branch": "main"},
    )
    assert res.status_code == 201
    conn_data = res.json()
    assert conn_data["repository_url"] == "https://github.com/pallets/flask"
    assert conn_data["status"] == "connected"
    assert conn_data["project_id"] == proj_id
    repo_id = conn_data["id"]

    # List project repositories
    list_res = client.get(f"/api/v1/projects/{proj_id}/repositories")
    assert list_res.status_code == 200
    repos = list_res.json()
    assert len(repos) == 1
    assert repos[0]["id"] == repo_id

    # Get single repository
    get_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == repo_id

    # Duplicate registration returns 409
    dup_res = client.post(
        f"/api/v1/projects/{proj_id}/repositories",
        json={"repository_url": "https://github.com/pallets/flask.git"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error_code"] == "REPOSITORYCONNECTION_ALREADY_EXISTS"


def test_register_repository_missing_project(client: TestClient) -> None:
    """Verify 404 when registering a repository for a nonexistent project."""
    res = client.post(
        f"/api/v1/projects/{uuid.uuid4()}/repositories",
        json={"repository_url": "https://github.com/octocat/Hello-World"},
    )
    assert res.status_code == 404
    assert res.json()["error_code"] == "PROJECT_NOT_FOUND"


def test_sync_repository_and_duplicate_prevention(client: TestClient) -> None:
    """Verify repository sync, snapshot persistence, and duplicate snapshot prevention."""
    proj = client.post(
        "/api/v1/projects", json={"name": f"Sync Project {uuid.uuid4().hex[:6]}"}
    ).json()
    repo = client.post(
        f"/api/v1/projects/{proj['id']}/repositories",
        json={"repository_url": "https://github.com/octocat/Spoon-Knife"},
    ).json()
    repo_id = repo["id"]

    mock_inventory = {
        "total_files": 2,
        "total_directories": 0,
        "total_size_bytes": 128,
        "extension_counts": {".md": 1, ".txt": 1},
        "language_distribution": {"Markdown": 100.0},
        "files": [{"path": "README.md", "size_bytes": 128, "sha256": "abc123hash"}],
    }
    commit_1 = "1111222233334444555566667777888899990000"

    with patch(
        "app.services.ingestion_service.IngestionService.ingest",
        return_value=(commit_1, mock_inventory),
    ):
        # First sync: creates new snapshot
        res1 = client.post(f"/api/v1/repositories/{repo_id}/sync")
        assert res1.status_code == 200
        snap1 = res1.json()
        assert snap1["commit_hash"] == commit_1
        assert snap1["status"] == "captured"
        assert snap1["file_tree_summary"]["total_files"] == 2
        snap_id = snap1["id"]

        # Second sync with same commit: prevents duplicate and returns existing snapshot
        res2 = client.post(f"/api/v1/repositories/{repo_id}/sync")
        assert res2.status_code == 200
        snap2 = res2.json()
        assert snap2["id"] == snap_id  # Same snapshot ID returned

    # Verify repository snapshots list contains exactly 1 snapshot
    snaps_res = client.get(f"/api/v1/repositories/{repo_id}/snapshots")
    assert snaps_res.status_code == 200
    assert len(snaps_res.json()) == 1
    assert snaps_res.json()[0]["id"] == snap_id

    # Retrieve snapshot directly by ID
    get_snap_res = client.get(f"/api/v1/snapshots/{snap_id}")
    assert get_snap_res.status_code == 200
    assert get_snap_res.json()["commit_hash"] == commit_1


def test_sync_failure_updates_repository_status(client: TestClient) -> None:
    """Verify that a clone failure sets repository status to 'error' and returns error response."""
    proj = client.post(
        "/api/v1/projects", json={"name": f"Fail Project {uuid.uuid4().hex[:6]}"}
    ).json()
    repo = client.post(
        f"/api/v1/projects/{proj['id']}/repositories",
        json={"repository_url": "https://github.com/octocat/Fail-Repo"},
    ).json()
    repo_id = repo["id"]

    with patch(
        "app.services.ingestion_service.IngestionService.ingest",
        side_effect=FaultlineException(
            status_code=400,
            detail="Repository not found",
            error_code="CLONE_FAILED",
        ),
    ):
        res = client.post(f"/api/v1/repositories/{repo_id}/sync")
        assert res.status_code == 400
        assert res.json()["error_code"] == "CLONE_FAILED"

    # Verify repository status is set to error
    repo_check = client.get(f"/api/v1/repositories/{repo_id}").json()
    assert repo_check["status"] == "error"


def test_missing_repository_and_snapshot_404s(client: TestClient) -> None:
    """Verify 404 responses for missing repository and snapshot UUIDs."""
    random_id = uuid.uuid4()
    assert client.get(f"/api/v1/repositories/{random_id}").status_code == 404
    assert client.post(f"/api/v1/repositories/{random_id}/sync").status_code == 404
    assert client.get(f"/api/v1/repositories/{random_id}/snapshots").status_code == 404
    assert client.get(f"/api/v1/snapshots/{random_id}").status_code == 404
