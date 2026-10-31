import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.code_snapshot import CodeSnapshot
from app.models.execution_result import ExecutionResult
from app.models.mutation_record import MutationRecord
from app.models.project import Project


def _create_diagnosable_analysis(db: Session) -> tuple[AnalysisRun, ExecutionResult]:
    project = Project(name="Diagnosis API", slug=f"diagnosis-api-{uuid.uuid4().hex[:8]}")
    db.add(project)
    db.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        commit_hash=uuid.uuid4().hex * 2,
        branch="main",
    )
    db.add(snapshot)
    db.flush()
    analysis = AnalysisRun(
        project_id=project.id,
        code_snapshot_id=snapshot.id,
        status="completed",
        summary={},
    )
    db.add(analysis)
    db.flush()
    baseline = BaselineExecution(
        analysis_run_id=analysis.id,
        code_snapshot_id=snapshot.id,
        command="approved-test-runner",
        framework="pytest",
        status="passed",
        exit_code=0,
        stdout="1 passed",
        stderr="",
    )
    mutation = MutationRecord(
        analysis_run_id=analysis.id,
        mutation_type="operator",
        target_file="app/module.py",
        line_number=2,
        original_code="x + y",
        mutated_code="x - y",
        status="applied",
    )
    db.add_all([baseline, mutation])
    db.flush()
    result = ExecutionResult(
        mutation_record_id=mutation.id,
        status="KILLED",
        exit_code=1,
        stdout="FAILED tests/test_module.py::test_sum - AssertionError: mismatch",
        stderr="",
        mutation_application_status="applied",
    )
    db.add(result)
    db.commit()
    return analysis, result


def test_diagnosis_endpoints_validate_and_paginate(
    client: TestClient,
    db_session: Session,
):
    analysis, result = _create_diagnosable_analysis(db_session)

    diagnosed = client.post(
        f"/api/v1/analyses/{analysis.id}/diagnose",
        json={"execution_ids": [str(result.id)]},
    )
    assert diagnosed.status_code == 200
    body = diagnosed.json()
    assert body["analysis_run_id"] == str(analysis.id)
    assert body["summary"]["introduced_failures"] == 1
    assert body["reports"][0]["execution_result_id"] == str(result.id)
    assert body["reports"][0]["confidence_score"] == 0.7
    assert body["reports"][0]["evidence"]

    listed = client.get(f"/api/v1/analyses/{analysis.id}/diagnoses?page=1&page_size=1")
    detail = client.get(f"/api/v1/diagnoses/{body['reports'][0]['id']}")

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert len(listed.json()["items"]) == 1
    assert detail.status_code == 200
    assert detail.json()["id"] == body["reports"][0]["id"]


def test_diagnosis_endpoints_return_consistent_errors(client: TestClient):
    missing_analysis = uuid.uuid4()
    missing_report = uuid.uuid4()

    invalid_id = client.post("/api/v1/analyses/not-a-uuid/diagnose", json={})
    missing_execution = client.post(
        f"/api/v1/analyses/{missing_analysis}/diagnose",
        json={},
    )
    missing_list = client.get(f"/api/v1/analyses/{missing_analysis}/diagnoses")
    missing_detail = client.get(f"/api/v1/diagnoses/{missing_report}")
    bad_page = client.get(f"/api/v1/analyses/{missing_analysis}/diagnoses?page=0")

    assert invalid_id.status_code == 422
    assert missing_execution.status_code == 404
    assert missing_list.status_code == 404
    assert missing_detail.status_code == 404
    assert bad_page.status_code == 422
