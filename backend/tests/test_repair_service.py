import hashlib
import uuid
from contextlib import contextmanager

import pytest

from app.core.exceptions import FaultlineException
from app.models.analysis_run import AnalysisRun
from app.models.code_snapshot import CodeSnapshot
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.repositories.repair_candidate_repository import repair_candidate_repository
from app.services.repair_service import RepairService


class StaticMaterializer:
    def __init__(self, workspace):
        self.workspace = workspace
        self.calls = 0

    @contextmanager
    def materialized_workspace(self, repository_url, commit_hash):
        self.calls += 1
        yield self.workspace


def _create_repair_case(
    db_session,
    workspace,
    *,
    source="def calculate(a, b):\n    return a - b\n",
    target_file="package/math_ops.py",
    line=2,
    col=11,
    original="a + b",
    mutated="a - b",
    mutation_type="arithmetic_operator",
    category="introduced_failure",
    confidence=0.8,
    evidence=None,
    source_hash=None,
):
    target = workspace.joinpath(*target_file.replace("\\", "/").split("/"))
    try:
        target.relative_to(workspace)
    except ValueError:
        pass
    else:
        if not target.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
    digest = source_hash or hashlib.sha256(source.encode("utf-8")).hexdigest()

    project = Project(name="Repair", slug=f"repair-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    db_session.flush()
    connection = RepositoryConnection(
        project_id=project.id,
        repository_url="https://example.invalid/repository.git",
        branch="main",
    )
    db_session.add(connection)
    db_session.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        repository_connection_id=connection.id,
        commit_hash=uuid.uuid4().hex + uuid.uuid4().hex[:8],
        branch="main",
    )
    db_session.add(snapshot)
    db_session.flush()
    analysis = AnalysisRun(
        project_id=project.id,
        code_snapshot_id=snapshot.id,
        status="completed",
        summary={},
    )
    db_session.add(analysis)
    db_session.flush()
    mutation = MutationRecord(
        analysis_run_id=analysis.id,
        mutation_type=mutation_type,
        target_file=target_file,
        line_number=line,
        col_offset=col,
        source_sha256=digest,
        original_code=original,
        mutated_code=mutated,
        status="applied",
    )
    db_session.add(mutation)
    db_session.flush()
    report = FailureReport(
        analysis_run_id=analysis.id,
        mutation_record_id=mutation.id,
        title="Introduced assertion failure",
        failure_type="AssertionError",
        category=category,
        causal_attribution="inferred",
        confidence_score=confidence,
        mutation_file=target_file,
        mutation_line=line,
        original_expression=original,
        mutated_expression=mutated,
        evidence=evidence
        if evidence is not None
        else [{"kind": "baseline_comparison", "supports_cause": True}],
    )
    db_session.add(report)
    db_session.commit()
    return analysis, snapshot, mutation, report


def test_exact_mutation_reversal_generates_reviewable_diff(db_session, tmp_path):
    analysis, _, _, report = _create_repair_case(db_session, tmp_path)
    service = RepairService(materializer=StaticMaterializer(tmp_path))

    result = service.generate_for_diagnosis(db_session, analysis.id, report.id)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.failure_report_id == report.id
    assert candidate.repair_strategy == "exact_mutation_reversal"
    assert candidate.original_expression == "a - b"
    assert candidate.replacement_expression == "a + b"
    assert candidate.validation_status == "syntax_valid"
    assert candidate.review_status == "pending"
    assert (
        candidate.original_source_sha256
        == hashlib.sha256(b"def calculate(a, b):\n    return a - b\n").hexdigest()
    )
    assert (
        candidate.proposed_source_sha256
        == hashlib.sha256(b"def calculate(a, b):\n    return a + b\n").hexdigest()
    )
    patch = service.get_patch(db_session, candidate.id).patch_content
    assert "--- a/package/math_ops.py" in patch
    assert "+++ b/package/math_ops.py" in patch
    assert "-    return a - b" in patch
    assert "+    return a + b" in patch
    assert "not evaluated" in candidate.explanation
    assert (tmp_path / "package" / "math_ops.py").read_text(encoding="utf-8") == (
        "def calculate(a, b):\n    return a - b\n"
    )


@pytest.mark.parametrize(
    ("source", "original", "mutated", "mutation_type"),
    [
        ("def f(a, b):\n    return a != b\n", "a == b", "a != b", "comparison_operator"),
        ("def f(a, b):\n    return a or b\n", "a and b", "a or b", "boolean_operator"),
        ("def f(x):\n    return x > 11\n", "x > 10", "x > 11", "numeric_boundary"),
    ],
)
def test_supported_mutator_strategies_restore_recorded_expression(
    db_session,
    tmp_path,
    source,
    original,
    mutated,
    mutation_type,
):
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        source=source,
        original=original,
        mutated=mutated,
        mutation_type=mutation_type,
    )

    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].validation_status == "syntax_valid"


def test_ast_expression_restoration_preserves_other_matching_expression(db_session, tmp_path):
    source = "def calculate(a, b):\n    return (a - b) + (a-b)\n"
    second_expression_col = source.splitlines()[1].rfind("a-b")
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        source=source,
        col=second_expression_col,
    )

    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.repair_strategy == "ast_expression_restoration"
    patch = (
        RepairService(materializer=StaticMaterializer(tmp_path))
        .get_patch(
            db_session,
            candidate.id,
        )
        .patch_content
    )
    assert "-    return (a - b) + (a-b)" in patch
    assert "+    return (a - b) + (a + b)" in patch


@pytest.mark.parametrize(
    ("target_file", "expected_reason"),
    [
        ("../outside.py", "unsafe_source_path"),
        ("missing.py", "source_file_missing_or_outside_snapshot"),
    ],
)
def test_unsafe_or_missing_paths_are_rejected(db_session, tmp_path, target_file, expected_reason):
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        target_file=target_file,
    )
    if expected_reason == "source_file_missing_or_outside_snapshot":
        (tmp_path / target_file).unlink()
    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )
    assert result.candidates == []
    assert result.skipped[0].reason == expected_reason


def test_symlink_escape_is_rejected(db_session, tmp_path):
    outside = tmp_path.parent / f"{uuid.uuid4().hex}.py"
    outside.write_text("def calculate(a, b):\n    return a - b\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError:
        outside.unlink(missing_ok=True)
        pytest.skip("Symlink creation is unavailable on this Windows host.")
    source_hash = hashlib.sha256(outside.read_text(encoding="utf-8").encode()).hexdigest()
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        target_file="linked.py",
        source_hash=source_hash,
    )

    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )

    assert result.candidates == []
    assert result.skipped[0].reason == "symlink_source_path"
    outside.unlink(missing_ok=True)


def test_source_hash_mismatch_is_rejected(db_session, tmp_path):
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        source_hash="0" * 64,
    )
    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )
    assert result.candidates == []
    assert result.skipped[0].reason == "source_hash_mismatch"


def test_materialization_error_is_returned_without_internal_details(db_session, tmp_path):
    analysis, _, _, report = _create_repair_case(db_session, tmp_path)

    class FailedMaterializer:
        @contextmanager
        def materialized_workspace(self, repository_url, commit_hash):
            raise FaultlineException(
                status_code=500,
                detail="private https://user:secret@example.invalid/repo",
                error_code="FETCH_FAILED",
            )
            yield

    with pytest.raises(FaultlineException) as error:
        RepairService(materializer=FailedMaterializer()).generate_for_diagnosis(
            db_session,
            analysis.id,
            report.id,
        )

    assert error.value.status_code == 503
    assert error.value.detail == (
        "The analysis snapshot could not be materialized for repair generation."
    )
    assert "secret" not in error.value.detail


def test_syntax_invalid_snapshot_is_rejected(db_session, tmp_path):
    source = "def calculate(a, b):\n    return a +\n"
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        source=source,
    )

    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )

    assert result.candidates == []
    assert result.skipped[0].reason == "source_syntax_invalid"


def test_invalid_expression_and_unsupported_diagnosis_are_rejected(db_session, tmp_path):
    analysis, _, _, report = _create_repair_case(db_session, tmp_path, original="a +")
    service = RepairService(materializer=StaticMaterializer(tmp_path))
    invalid_expression = service.generate_for_diagnosis(db_session, analysis.id, report.id)
    assert invalid_expression.candidates == []
    assert invalid_expression.skipped[0].reason == "mutation_expression_invalid"

    report.category = "existing_baseline_failure"
    db_session.commit()
    unsupported = service.generate_for_diagnosis(db_session, analysis.id, report.id)
    assert unsupported.candidates == []
    assert unsupported.skipped[0].reason == "unsupported_diagnosis"


def test_duplicate_generation_is_idempotent_and_patch_is_deterministic(db_session, tmp_path):
    analysis, _, _, report = _create_repair_case(db_session, tmp_path)
    materializer = StaticMaterializer(tmp_path)
    service = RepairService(materializer=materializer)

    first = service.generate_for_diagnosis(db_session, analysis.id, report.id).candidates[0]
    second = service.generate_for_diagnosis(db_session, analysis.id, report.id).candidates[0]

    assert first.id == second.id
    assert (
        service.get_patch(db_session, first.id).patch_content
        == service.get_patch(db_session, second.id).patch_content
    )
    assert materializer.calls == 1
    assert repair_candidate_repository.get(db_session, first.id) is not None


def test_identical_inputs_generate_identical_patch_content(db_session, tmp_path):
    analysis_a, _, _, report_a = _create_repair_case(db_session, tmp_path)
    analysis_b, _, _, report_b = _create_repair_case(db_session, tmp_path)
    service = RepairService(materializer=StaticMaterializer(tmp_path))

    candidate_a = service.generate_for_diagnosis(db_session, analysis_a.id, report_a.id).candidates[
        0
    ]
    candidate_b = service.generate_for_diagnosis(db_session, analysis_b.id, report_b.id).candidates[
        0
    ]

    patch_a = service.get_patch(db_session, candidate_a.id).patch_content
    patch_b = service.get_patch(db_session, candidate_b.id).patch_content
    assert patch_a == patch_b


def test_multiple_matching_nodes_at_distinct_ast_positions_are_not_ambiguous(db_session, tmp_path):
    source = "def calculate(a, b):\n    return (a - b) + (a - b)\n"
    second_binop_col = source.splitlines()[1].rfind("a - b")
    analysis, _, _, report = _create_repair_case(
        db_session,
        tmp_path,
        source=source,
        col=second_binop_col,
    )

    result = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )

    assert len(result.candidates) == 1
    patch = (
        RepairService(materializer=StaticMaterializer(tmp_path))
        .get_patch(
            db_session,
            result.candidates[0].id,
        )
        .patch_content
    )
    assert "+    return (a - b) + (a + b)" in patch
