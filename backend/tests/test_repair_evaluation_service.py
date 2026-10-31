import difflib
import hashlib
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import FaultlineException
from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.code_snapshot import CodeSnapshot
from app.models.execution_result import ExecutionResult
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.models.project import Project
from app.models.repair_evaluation import RepairEvaluation
from app.models.repository_connection import RepositoryConnection
from app.repositories.repair_candidate_repository import repair_candidate_repository
from app.schemas.repair_evaluation import ForgeFitScenarioRequest, RepairEvaluationRequest
from app.services.forgefit_adapter import ForgeFitOutcome
from app.services.repair_evaluation_service import (
    RepairEvaluationService,
    repair_evaluation_service,
)
from app.services.repair_service import RepairService
from app.services.sandbox.baseline_runner import BaselineRunOutput

_SOURCE = "def calculate(a, b):\n    return a - b\n"
_DIAGNOSED_TEST = "tests/test_math.py::test_calculate"
_FAILURE_OUTPUT = f"FAILED {_DIAGNOSED_TEST} - AssertionError: wrong result"


class StaticMaterializer:
    def __init__(self, workspace):
        self.workspace = workspace

    @contextmanager
    def materialized_workspace(self, repository_url, commit_hash):
        yield self.workspace


class FakeRunner:
    def __init__(
        self,
        *,
        status="passed",
        stdout="1 passed in 0.01s",
        failed_count=0,
        passed_count=1,
        timed_out=False,
        infrastructure_error=None,
    ):
        self.status = status
        self.stdout = stdout
        self.failed_count = failed_count
        self.passed_count = passed_count
        self.timed_out = timed_out
        self.infrastructure_error = infrastructure_error
        self.calls = []

    def run_baseline(self, workspace_path, *, custom_command=None, timeout_seconds=None):
        self.calls.append((workspace_path, custom_command, timeout_seconds))
        target = workspace_path / "package" / "math_ops.py"
        assert target.read_text(encoding="utf-8") == _SOURCE.replace("a - b", "a + b")
        return BaselineRunOutput(
            command=" ".join(custom_command or []),
            status=self.status,
            exit_code=0 if self.status == "passed" else 1,
            stdout=self.stdout,
            stderr="",
            duration_ms=25,
            framework="pytest",
            test_files_count=1,
            passed_count=self.passed_count,
            failed_count=self.failed_count,
            skipped_count=0,
            infrastructure_error=self.infrastructure_error,
            timed_out=self.timed_out,
        )


class FakeForgeFit:
    def run_scenario(self, scenario, *, candidate_id, evaluation_id):
        return ForgeFitOutcome(
            status="failed",
            run_id="forgefit-run-1",
            error_code="RUN_FAILED",
        )


def _create_evaluation_case(db_session, tmp_path):
    source_path = tmp_path / "package" / "math_ops.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(_SOURCE, encoding="utf-8")
    project = Project(name="Evaluation", slug=f"eval-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    db_session.flush()
    connection = RepositoryConnection(
        project_id=project.id,
        repository_url="https://example.invalid/evaluation.git",
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
    baseline = BaselineExecution(
        analysis_run_id=analysis.id,
        code_snapshot_id=snapshot.id,
        command="approved-test-runner",
        command_identifier="pytest",
        framework="pytest",
        test_files_count=1,
        status="passed",
        passed_count=1,
        failed_count=0,
        skipped_count=0,
        stdout="1 passed in 0.01s",
    )
    db_session.add(baseline)
    db_session.flush()
    mutation = MutationRecord(
        analysis_run_id=analysis.id,
        mutation_type="arithmetic_operator",
        target_file="package/math_ops.py",
        line_number=2,
        col_offset=11,
        source_sha256=hashlib.sha256(_SOURCE.encode("utf-8")).hexdigest(),
        original_code="a + b",
        mutated_code="a - b",
        status="applied",
    )
    db_session.add(mutation)
    db_session.flush()
    mutant_result = ExecutionResult(
        mutation_record_id=mutation.id,
        status="failed",
        stdout=_FAILURE_OUTPUT,
        stderr="",
        passed_count=0,
        failed_count=1,
        skipped_count=0,
    )
    db_session.add(mutant_result)
    db_session.flush()
    report = FailureReport(
        analysis_run_id=analysis.id,
        execution_result_id=mutant_result.id,
        baseline_execution_id=baseline.id,
        mutation_record_id=mutation.id,
        title="Introduced assertion failure",
        failure_type="AssertionError",
        category="introduced_failure",
        causal_attribution="inferred",
        confidence_score=0.8,
        affected_test=_DIAGNOSED_TEST,
        test_identifier=_DIAGNOSED_TEST,
        mutation_file=mutation.target_file,
        mutation_line=mutation.line_number,
        original_expression=mutation.original_code,
        mutated_expression=mutation.mutated_code,
        evidence=[{"kind": "baseline_comparison", "supports_cause": True}],
    )
    db_session.add(report)
    db_session.commit()
    generated = RepairService(materializer=StaticMaterializer(tmp_path)).generate_for_diagnosis(
        db_session,
        analysis.id,
        report.id,
    )
    return (
        repair_candidate_repository.get(db_session, generated.candidates[0].id),
        report,
        baseline,
        mutant_result,
    )


def test_evaluation_applies_patch_in_isolated_workspace_and_persists_evidence(
    db_session,
    tmp_path,
):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    runner = FakeRunner()
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(
        db_session,
        candidate.id,
        RepairEvaluationRequest(timeout_seconds=17),
    )

    assert result.status == "PASSED"
    assert result.passed_count == 1
    assert result.evidence["diagnosed_test_state"] == "not_observed"
    assert result.evidence["behavioral_correctness_proven"] is False
    assert runner.calls[0][1] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
    ]
    assert runner.calls[0][2] == 17
    assert (tmp_path / "package" / "math_ops.py").read_text(encoding="utf-8") == _SOURCE


def test_evaluation_classifies_timeout_and_infrastructure_error(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    timeout_runner = FakeRunner(status="timeout", timed_out=True, passed_count=0)
    service = RepairEvaluationService(
        runner=timeout_runner,
        materializer=StaticMaterializer(tmp_path),
    )

    timeout = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())
    assert timeout.status == "TIMEOUT"
    assert timeout.error_code == "TEST_EXECUTION_TIMEOUT"

    second_candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    error_runner = FakeRunner(
        status="error",
        passed_count=0,
        infrastructure_error="DOCKER_RUN_FAILED",
    )
    service = RepairEvaluationService(
        runner=error_runner,
        materializer=StaticMaterializer(tmp_path),
    )
    error = service.evaluate_candidate(
        db_session,
        second_candidate.id,
        RepairEvaluationRequest(),
    )
    assert error.status == "ERROR"
    assert error.error_code == "DOCKER_RUN_FAILED"


def test_evaluation_rejects_hash_mismatch_without_running_candidate(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    candidate.original_source_sha256 = "0" * 64
    db_session.commit()
    runner = FakeRunner()
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "INVALID"
    assert result.error_code == "ORIGINAL_SOURCE_HASH_MISMATCH"
    assert runner.calls == []


def test_evaluation_rejects_malformed_patch_without_running_candidate(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    candidate.patch_content = "not a unified diff"
    db_session.commit()
    runner = FakeRunner()
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "INVALID"
    assert result.error_code == "PATCH_MALFORMED"
    assert runner.calls == []


def test_evaluation_rejects_syntax_invalid_proposal_and_ast_mismatch(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    invalid_source = _SOURCE.replace("a - b", "a +")
    candidate.patch_content = (
        "\n".join(
            difflib.unified_diff(
                _SOURCE.splitlines(),
                invalid_source.splitlines(),
                fromfile=f"a/{candidate.target_file}",
                tofile=f"b/{candidate.target_file}",
                lineterm="",
            )
        )
        + "\n"
    )
    candidate.proposed_source_sha256 = hashlib.sha256(invalid_source.encode()).hexdigest()
    db_session.commit()
    runner = FakeRunner()
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    syntax_invalid = service.evaluate_candidate(
        db_session,
        candidate.id,
        RepairEvaluationRequest(),
    )
    assert syntax_invalid.status == "INVALID"
    assert syntax_invalid.error_code == "PATCH_SOURCE_SYNTAX_INVALID"
    assert runner.calls == []

    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    candidate.mutation_record.col_offset += 1
    db_session.commit()
    ast_mismatch = service.evaluate_candidate(
        db_session,
        candidate.id,
        RepairEvaluationRequest(),
    )
    assert ast_mismatch.status == "INVALID"
    assert ast_mismatch.error_code == "AST_TARGET_NOT_FOUND"
    assert runner.calls == []


def test_path_traversal_and_symlink_targets_are_rejected(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    candidate.target_file = "../outside.py"
    candidate.mutation_record.target_file = "../outside.py"
    db_session.commit()
    service = RepairEvaluationService(
        runner=FakeRunner(),
        materializer=StaticMaterializer(tmp_path),
    )

    traversal = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())
    assert traversal.status == "INVALID"
    assert traversal.error_code == "UNSAFE_PATCH_PATH"

    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    link = tmp_path / "package_link"
    try:
        link.symlink_to(tmp_path / "package", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlink creation is unavailable: {exc}")
    candidate.target_file = "package_link/math_ops.py"
    candidate.mutation_record.target_file = candidate.target_file
    db_session.commit()
    symlink = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())
    assert symlink.status == "INVALID"
    assert symlink.error_code == "SYMLINK_PATCH_PATH"


def test_baseline_failures_make_evaluation_invalid(db_session, tmp_path):
    candidate, report, baseline, _ = _create_evaluation_case(db_session, tmp_path)
    baseline.status = "failed"
    baseline.failed_count = 1
    baseline.stdout = _FAILURE_OUTPUT
    db_session.commit()
    runner = FakeRunner()
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "INVALID"
    assert result.error_code == "BASELINE_NOT_PASSED"
    assert result.evidence["diagnosis_category"] == report.category
    assert result.evidence["baseline_failure_ids"] == [_DIAGNOSED_TEST]
    assert runner.calls == []


def test_existing_mutant_failure_and_partial_recovery_are_reported(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    output = (
        f"{_DIAGNOSED_TEST} PASSED\n"
        "FAILED tests/test_other.py::test_other - AssertionError: other failure\n"
    )
    runner = FakeRunner(status="failed", stdout=output, failed_count=1, passed_count=1)
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "PARTIALLY_PASSED"
    assert result.evidence["diagnosed_test_state"] == "observed_passed"
    assert result.evidence["new_candidate_failure_ids"] == ["tests/test_other.py::test_other"]


def test_new_failure_is_not_misclassified_as_repair_success(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    runner = FakeRunner(
        status="failed",
        stdout="FAILED tests/test_other.py::test_other - AssertionError: unexpected",
        failed_count=1,
        passed_count=0,
    )
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "FAILED"
    assert result.evidence["new_candidate_failure_ids"] == ["tests/test_other.py::test_other"]


def test_candidate_with_fewer_test_results_is_only_partially_passed(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    runner = FakeRunner(passed_count=0)
    service = RepairEvaluationService(
        runner=runner,
        materializer=StaticMaterializer(tmp_path),
    )

    result = service.evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert result.status == "PARTIALLY_PASSED"


def test_forgefit_result_is_persisted_separately_from_repair_verdict(db_session, tmp_path):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    service = RepairEvaluationService(
        runner=FakeRunner(),
        materializer=StaticMaterializer(tmp_path),
        forgefit=FakeForgeFit(),
    )

    result = service.evaluate_candidate(
        db_session,
        candidate.id,
        RepairEvaluationRequest(
            forgefit_scenario=ForgeFitScenarioRequest(
                target_url="http://localhost:8000/health",
                request_count=2,
            )
        ),
    )

    assert result.status == "PASSED"
    assert result.forgefit_status == "failed"
    assert result.forgefit_run_id == "forgefit-run-1"
    assert result.forgefit_error_code == "RUN_FAILED"


def test_only_one_evaluation_can_run_for_a_candidate(db_session, tmp_path):
    candidate, report, baseline, mutant = _create_evaluation_case(db_session, tmp_path)
    db_session.add(
        RepairEvaluation(
            repair_candidate_id=candidate.id,
            analysis_run_id=candidate.analysis_run_id,
            failure_report_id=report.id,
            baseline_execution_id=baseline.id,
            mutant_execution_result_id=mutant.id,
            status="RUNNING",
            evidence={},
        )
    )
    db_session.commit()

    with pytest.raises(FaultlineException) as error:
        RepairEvaluationService(
            runner=FakeRunner(),
            materializer=StaticMaterializer(tmp_path),
        ).evaluate_candidate(db_session, candidate.id, RepairEvaluationRequest())

    assert error.value.status_code == 409
    assert error.value.error_code == "REPAIR_EVALUATION_IN_PROGRESS"


def test_database_rejects_concurrent_active_evaluations(db_session, tmp_path):
    candidate, report, baseline, mutant = _create_evaluation_case(db_session, tmp_path)
    common = {
        "repair_candidate_id": candidate.id,
        "analysis_run_id": candidate.analysis_run_id,
        "failure_report_id": report.id,
        "baseline_execution_id": baseline.id,
        "mutant_execution_result_id": mutant.id,
        "status": "RUNNING",
        "evidence": {},
    }
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(RepairEvaluation(**common))
            db_session.flush()
            db_session.add(RepairEvaluation(**common))
            db_session.flush()


def test_evaluation_api_persists_lists_and_validates_evaluation(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    candidate, _, _, _ = _create_evaluation_case(db_session, tmp_path)
    monkeypatch.setattr(repair_evaluation_service, "runner", FakeRunner())
    monkeypatch.setattr(
        repair_evaluation_service,
        "materializer",
        StaticMaterializer(tmp_path),
    )
    endpoint = f"/api/v1/repair-candidates/{candidate.id}/evaluations"

    created = client.post(endpoint, json={"timeout_seconds": 11})
    evaluation_id = created.json()["id"]
    listed = client.get(f"{endpoint}?page=1&page_size=1")
    retrieved = client.get(f"/api/v1/repair-evaluations/{evaluation_id}")
    invalid = client.post(endpoint, json={"timeout_seconds": 0})

    assert created.status_code == 200
    assert created.json()["status"] == "PASSED"
    assert "target_file" not in created.json()
    assert "patch_content" not in created.json()
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == evaluation_id
    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == evaluation_id
    assert invalid.status_code == 422
