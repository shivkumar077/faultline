import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.code_snapshot import CodeSnapshot
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.services.mutation.ast_mutator import PythonAstMutator
from app.services.snapshot_materializer import SnapshotMaterializer


def test_comparison_operator_mutations() -> None:
    """Verify Operator A: Comparison operators (==, !=, >, >=, <, <=)."""
    mutator = PythonAstMutator()
    source = "def check(x):\n    return x == 10 and x > 5 and x <= 2\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        py_file = root / "sample.py"
        py_file.write_text(source, encoding="utf-8")

        plan = mutator.generate_mutations(root, commit_hash="c1", seed=42)
        types = {m.mutation_type for m in plan.mutations}
        assert "comparison_operator" in types

        cmp_ops = [
            m.operator_name for m in plan.mutations if m.mutation_type == "comparison_operator"
        ]
        assert "Eq_to_NotEq" in cmp_ops
        assert "Gt_to_GtE" in cmp_ops
        assert "LtE_to_Lt" in cmp_ops


def test_boolean_operator_mutations() -> None:
    """Verify Operator B: Boolean operators (and <-> or)."""
    mutator = PythonAstMutator()
    source = "def logic(a, b, c):\n    return a and b or c\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        py_file = root / "sample.py"
        py_file.write_text(source, encoding="utf-8")

        plan = mutator.generate_mutations(root, commit_hash="c1", seed=42)
        bool_ops = [
            m.operator_name for m in plan.mutations if m.mutation_type == "boolean_operator"
        ]
        assert "And_to_Or" in bool_ops
        assert "Or_to_And" in bool_ops


def test_numeric_boundary_mutations() -> None:
    """Verify Operator C: Numeric boundaries only in comparison expressions."""
    mutator = PythonAstMutator()
    source = (
        "TIMEOUT = 5000\n"  # Unrelated config constant - should NOT be mutated!
        "def validate(age):\n"
        "    return age >= 18\n"  # 18 in comparison should produce 17 and 19!
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        py_file = root / "sample.py"
        py_file.write_text(source, encoding="utf-8")

        plan = mutator.generate_mutations(root, commit_hash="c1", seed=42)
        boundary_mutations = [m for m in plan.mutations if m.mutation_type == "numeric_boundary"]
        assert len(boundary_mutations) >= 2
        mutated_snippets = [m.mutated_code for m in boundary_mutations]
        assert any("17" in snip for snip in mutated_snippets)
        assert any("19" in snip for snip in mutated_snippets)
        # Verify 5000 was NOT mutated
        assert not any("4999" in snip for snip in mutated_snippets)
        assert not any("5001" in snip for snip in mutated_snippets)


def test_invalid_python_file_handling() -> None:
    """Verify invalid Python files are skipped safely and reported in summary."""
    mutator = PythonAstMutator()
    valid_code = "x = 1 == 2\n"
    invalid_code = "def broken(\n  # incomplete syntax\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "valid.py").write_text(valid_code, encoding="utf-8")
        (root / "broken.py").write_text(invalid_code, encoding="utf-8")

        plan = mutator.generate_mutations(root, commit_hash="c1")
        assert len(plan.mutations) > 0
        assert len(plan.skipped_files) == 1
        assert plan.skipped_files[0]["file"] == "broken.py"
        assert "SyntaxError" in plan.skipped_files[0]["reason"]


def test_deterministic_output_with_same_and_different_seeds() -> None:
    """Verify determinism with identical seeds and variation with differing seeds."""
    mutator = PythonAstMutator()
    # Generate source with many candidate mutations
    source_lines = ["def compute(a, b):", "    return ("]
    for i in range(25):
        source_lines.append(f"        (a == {i} and b > {i}) or")
    source_lines.append("        False\n    )")
    source = "\n".join(source_lines)

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "test.py").write_text(source, encoding="utf-8")

        plan1 = mutator.generate_mutations(root, commit_hash="c1", seed=101, max_mutations=5)
        plan2 = mutator.generate_mutations(root, commit_hash="c1", seed=101, max_mutations=5)
        plan3 = mutator.generate_mutations(root, commit_hash="c1", seed=999, max_mutations=5)

        # Same seed yields byte-identical mutation IDs and ordering
        ids1 = [m.mutation_id for m in plan1.mutations]
        ids2 = [m.mutation_id for m in plan2.mutations]
        ids3 = [m.mutation_id for m in plan3.mutations]

        assert ids1 == ids2
        assert len(ids1) == 5
        # Different seeds select different sampled subsets
        assert ids1 != ids3


def test_original_source_preservation() -> None:
    """Verify mutation generation does not touch original files on disk."""
    mutator = PythonAstMutator()
    source = "def original():\n    return 1 == 1\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        target = root / "script.py"
        target.write_text(source, encoding="utf-8")

        mutator.generate_mutations(root, commit_hash="c1")
        # Ensure disk file is untouched
        assert target.read_text(encoding="utf-8") == source


def test_snapshot_materializer_lifecycle() -> None:
    """Verify materializer initializes workspace, executes git commands, and cleans up."""
    materializer = SnapshotMaterializer(timeout_seconds=5)

    with patch("subprocess.run") as mock_run:
        # 1. git init, 2. git remote add, 3. git fetch, 4. git checkout, 5. git rev-parse HEAD
        mock_init = MagicMock(returncode=0)
        mock_remote = MagicMock(returncode=0)
        mock_fetch = MagicMock(returncode=0)
        mock_checkout = MagicMock(returncode=0)
        mock_rev = MagicMock(returncode=0, stdout="deadbeef001122334455\n")

        mock_run.side_effect = [mock_init, mock_remote, mock_fetch, mock_checkout, mock_rev]

        temp_path_captured: Path | None = None
        with materializer.materialized_workspace(
            "https://github.com/octocat/Hello-World", "deadbeef001122334455"
        ) as ws:
            temp_path_captured = ws
            assert ws.exists()

        # Temporary workspace must be cleaned up on context manager exit
        assert temp_path_captured is not None
        assert not temp_path_captured.exists()


def test_generate_mutations_api_flow(client: TestClient, db_session: Session) -> None:
    """Verify POST /snapshots/{id}/mutations and GET /analyses/{id}/mutations."""
    # 1. Setup project, connection, and snapshot
    project = Project(name="Mutation Project", slug=f"mut-proj-{uuid.uuid4().hex[:6]}")
    db_session.add(project)
    db_session.flush()

    repo = RepositoryConnection(
        project_id=project.id,
        repository_url="https://github.com/octocat/Test-Repo",
        branch="main",
        status="connected",
    )
    db_session.add(repo)
    db_session.flush()

    snapshot = CodeSnapshot(
        project_id=project.id,
        repository_connection_id=repo.id,
        commit_hash="abcdef0123456789abcdef0123456789abcdef01",
        branch="main",
        status="captured",
    )
    db_session.add(snapshot)
    db_session.commit()

    # 2. Mock materializer to provide synthetic python code
    sample_code = "def is_active(val):\n    return val == True and val > 0\n"

    def mock_materialize(repo_url, commit_hash, target_dir):
        p = Path(target_dir) / "app.py"
        p.write_text(sample_code, encoding="utf-8")
        return commit_hash

    with patch.object(SnapshotMaterializer, "materialize_commit", side_effect=mock_materialize):
        res = client.post(
            f"/api/v1/snapshots/{snapshot.id}/mutations",
            json={"seed": 42, "max_mutations": 10},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert data["code_snapshot_id"] == str(snapshot.id)
        assert data["project_id"] == str(project.id)
        assert data["mutation_records_count"] >= 2
        analysis_id = data["id"]

        # Check summary manifest
        summary = data["summary"]
        assert summary["snapshot_commit"] == snapshot.commit_hash
        assert summary["random_seed"] == 42
        assert "manifest" in summary
        assert len(summary["manifest"]) == data["mutation_records_count"]

    # 3. Retrieve mutation records via GET /analyses/{analysis_id}/mutations
    list_res = client.get(f"/api/v1/analyses/{analysis_id}/mutations?page=1&page_size=10")
    assert list_res.status_code == 200
    mutations_page = list_res.json()
    assert "items" in mutations_page
    assert len(mutations_page["items"]) == data["mutation_records_count"]
    first_m = mutations_page["items"][0]
    assert first_m["analysis_run_id"] == analysis_id
    assert first_m["target_file"] == "app.py"
    assert first_m["status"] == "applied"


def test_generate_mutations_missing_snapshot(client: TestClient) -> None:
    """Verify 404 returned for nonexistent snapshot ID."""
    res = client.post(f"/api/v1/snapshots/{uuid.uuid4()}/mutations", json={})
    assert res.status_code == 404
    assert res.json()["error_code"] == "CODESNAPSHOT_NOT_FOUND"


def test_list_mutations_missing_analysis(client: TestClient) -> None:
    """Verify 404 returned for nonexistent analysis ID."""
    res = client.get(f"/api/v1/analyses/{uuid.uuid4()}/mutations")
    assert res.status_code == 404
    assert res.json()["error_code"] == "ANALYSISRUN_NOT_FOUND"
