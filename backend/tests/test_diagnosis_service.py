import uuid

from app.core.exceptions import FaultlineException
from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.code_snapshot import CodeSnapshot
from app.models.execution_result import ExecutionResult
from app.models.mutation_record import MutationRecord
from app.models.project import Project
from app.repositories.failure_report_repository import failure_report_repository
from app.services.diagnosis_service import FailureDiagnosisService

PYTEST_FAILURE = """___________________________ test_total ____________________________
/workspace/faultline/math_ops.py:12: in multiply
    return left + right
tests/test_math.py:8: in test_total
    assert multiply(2, 3) == 7
E   AssertionError: expected 7
E   assert 5 == 7
FAILED tests/test_math.py::test_total - AssertionError: expected 7
"""


def _persist_execution(
    db_session,
    *,
    baseline_status="passed",
    baseline_stdout="1 passed",
    result_status="KILLED",
    result_stdout=PYTEST_FAILURE,
    result_stderr="",
    infrastructure_error=None,
):
    project = Project(name="Diagnosis", slug=f"diagnosis-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    db_session.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        commit_hash=uuid.uuid4().hex * 2,
        branch="main",
    )
    db_session.add(snapshot)
    db_session.flush()
    analysis = AnalysisRun(
        project_id=project.id,
        code_snapshot_id=snapshot.id,
        status="failed" if baseline_status != "passed" else "completed",
        summary={},
    )
    db_session.add(analysis)
    db_session.flush()
    baseline = BaselineExecution(
        analysis_run_id=analysis.id,
        code_snapshot_id=snapshot.id,
        command="approved-test-runner",
        framework="pytest",
        status=baseline_status,
        exit_code=0 if baseline_status == "passed" else 1,
        stdout=baseline_stdout,
        stderr="",
        passed_count=1 if baseline_status == "passed" else 0,
    )
    mutation = MutationRecord(
        analysis_run_id=analysis.id,
        mutation_type="arithmetic_operator",
        target_file="faultline/math_ops.py",
        line_number=12,
        col_offset=11,
        source_sha256="a" * 64,
        original_code="left * right",
        mutated_code="left + right",
        status="applied",
    )
    db_session.add_all([baseline, mutation])
    db_session.flush()
    result = ExecutionResult(
        mutation_record_id=mutation.id,
        status=result_status,
        exit_code=1 if result_status == "KILLED" else None,
        failed_count=1 if result_status == "KILLED" else 0,
        timed_out=result_status == "TIMEOUT",
        infrastructure_error=infrastructure_error,
        mutation_application_status="applied",
        stdout=result_stdout,
        stderr=result_stderr,
    )
    db_session.add(result)
    db_session.commit()
    return analysis, baseline, mutation, result


def test_diagnose_new_failure_links_mutation_and_explains_confidence(db_session):
    analysis, baseline, mutation, result = _persist_execution(db_session)
    service = FailureDiagnosisService()

    diagnosed = service.diagnose_analysis(db_session, analysis.id)

    assert diagnosed.baseline_execution_id == baseline.id
    assert diagnosed.summary.introduced_failures == 1
    assert diagnosed.summary.baseline_failures == 0
    assert len(diagnosed.reports) == 1
    report = diagnosed.reports[0]
    assert report.category == "introduced_failure"
    assert report.execution_result_id == result.id
    assert report.mutation_record_id == mutation.id
    assert report.test_identifier == "tests/test_math.py::test_total"
    assert report.exception_type == "AssertionError"
    assert report.failure_summary == "AssertionError: expected 7"
    assert report.source_file == "/workspace/faultline/math_ops.py"
    assert report.source_line == 12
    assert report.mutation_file == "faultline/math_ops.py"
    assert report.mutation_line == 12
    assert report.original_expression == "left * right"
    assert report.mutated_expression == "left + right"
    assert report.causal_attribution == "inferred"
    assert report.confidence_score == 0.95
    assert any(item["kind"] == "mutation_line_in_traceback" for item in report.evidence)
    assert "not proof" in report.root_cause_analysis


def test_existing_baseline_failure_is_not_attributed_to_mutant(db_session):
    baseline_output = "FAILED tests/test_math.py::test_total - AssertionError: expected 7"
    analysis, _, _, _ = _persist_execution(
        db_session,
        baseline_status="failed",
        baseline_stdout=baseline_output,
        result_stdout=baseline_output,
    )

    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)

    assert diagnosed.summary.baseline_failures == 1
    assert diagnosed.summary.existing_failures == 1
    baseline_report = next(
        report for report in diagnosed.reports if report.category == "baseline_failure"
    )
    mutant_report = next(
        report for report in diagnosed.reports if report.category == "existing_baseline_failure"
    )
    assert baseline_report.mutation_record_id is None
    assert mutant_report.causal_attribution == "not_attributed"


def test_failure_signature_change_is_reported_as_inferred_not_new(db_session):
    analysis, _, _, _ = _persist_execution(
        db_session,
        baseline_status="failed",
        baseline_stdout="FAILED tests/test_math.py::test_total - AssertionError: expected 6",
        result_stdout="FAILED tests/test_math.py::test_total - AssertionError: expected 7",
    )

    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)

    comparison = next(item for item in diagnosed.comparisons if item.execution_result_id)
    assert comparison.category == "failure_changed"
    assert diagnosed.summary.changed_failures == 1
    assert comparison.confidence_score < 1.0
    assert "pre-existing" in comparison.explanation


def test_timeout_and_infrastructure_errors_are_classified(db_session):
    analysis, _, _, result = _persist_execution(
        db_session,
        result_status="TIMEOUT",
        result_stdout="",
    )
    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)
    assert diagnosed.summary.timed_out == 1
    assert diagnosed.reports[0].category == "timeout"

    result.status = "ERROR"
    result.timed_out = False
    result.infrastructure_error = "DOCKER_RUN_FAILED"
    db_session.commit()
    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)
    assert diagnosed.summary.infrastructure_errors == 1
    assert diagnosed.reports[0].category == "infrastructure_error"


def test_success_without_named_tests_is_reported_as_run_level_only(db_session):
    analysis, _, _, result = _persist_execution(
        db_session,
        result_status="SURVIVED",
        result_stdout="1 passed",
    )
    result.exit_code = 0
    result.failed_count = 0
    db_session.commit()

    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)

    assert diagnosed.summary.passed_both_tests_observed == 0
    assert diagnosed.summary.passing_runs_without_shared_test_ids == 1
    comparison = diagnosed.comparisons[0]
    assert comparison.category == "passed_both"
    assert comparison.test_identifier is None
    assert "run-level" in comparison.explanation
    assert diagnosed.reports == []


def test_same_passing_test_id_is_identified_as_passed_in_both_runs(db_session):
    analysis, baseline, _, result = _persist_execution(
        db_session,
        result_status="SURVIVED",
        result_stdout="tests/test_math.py::test_total PASSED",
    )
    baseline.stdout = "tests/test_math.py::test_total PASSED"
    result.exit_code = 0
    result.failed_count = 0
    db_session.commit()

    diagnosed = FailureDiagnosisService().diagnose_analysis(db_session, analysis.id)

    assert diagnosed.summary.passed_both_tests_observed == 1
    assert diagnosed.summary.passing_runs_without_shared_test_ids == 0
    assert diagnosed.comparisons[0].category == "passed_both"
    assert diagnosed.comparisons[0].test_identifier == "tests/test_math.py::test_total"


def test_repeated_diagnosis_upserts_instead_of_duplicating_reports(db_session):
    analysis, _, _, result = _persist_execution(db_session)
    service = FailureDiagnosisService()
    original_execution = (result.status, result.exit_code, result.stdout, result.stderr)

    first = service.diagnose_analysis(db_session, analysis.id)
    second = service.diagnose_analysis(db_session, analysis.id)
    reports, total = failure_report_repository.get_for_analysis(db_session, analysis.id)

    assert first.reports[0].id == second.reports[0].id
    assert total == 1
    assert len(reports) == 1
    assert (result.status, result.exit_code, result.stdout, result.stderr) == original_execution


def test_invalid_execution_ids_are_rejected(db_session):
    analysis, _, _, _ = _persist_execution(db_session)

    try:
        FailureDiagnosisService().diagnose_analysis(
            db_session,
            analysis.id,
            execution_ids=[uuid.uuid4()],
        )
    except FaultlineException as exc:
        assert exc.status_code == 422
        assert exc.error_code == "INVALID_EXECUTION_IDS"
    else:
        raise AssertionError("Expected an invalid execution ID to be rejected.")


def test_diagnosis_rejects_missing_baseline_or_incomplete_execution(db_session):
    analysis, baseline, _, result = _persist_execution(db_session)
    service = FailureDiagnosisService()

    baseline.status = "running"
    db_session.commit()
    try:
        service.diagnose_analysis(db_session, analysis.id)
    except FaultlineException as exc:
        assert exc.status_code == 409
        assert exc.error_code == "EXECUTION_IN_PROGRESS"
    else:
        raise AssertionError("Expected an incomplete baseline to be rejected.")

    baseline.status = "passed"
    result.status = "running"
    db_session.commit()
    try:
        service.diagnose_analysis(db_session, analysis.id)
    except FaultlineException as exc:
        assert exc.status_code == 409
        assert exc.error_code == "EXECUTION_IN_PROGRESS"
    else:
        raise AssertionError("Expected an incomplete mutant execution to be rejected.")

    db_session.delete(baseline)
    db_session.commit()
    try:
        service.diagnose_analysis(db_session, analysis.id)
    except FaultlineException as exc:
        assert exc.status_code == 409
        assert exc.error_code == "BASELINE_EXECUTION_REQUIRED"
    else:
        raise AssertionError("Expected a missing baseline to be rejected.")
