import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.code_snapshot import CodeSnapshot
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.services.execution_service import execution_service


def _create_analysis(db_session: Session) -> AnalysisRun:
    project = Project(name="API execution", slug=f"api-exec-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    db_session.flush()
    connection = RepositoryConnection(
        project_id=project.id,
        repository_url="https://github.com/example/api-execution",
        branch="main",
    )
    db_session.add(connection)
    db_session.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        repository_connection_id=connection.id,
        commit_hash="b" * 40,
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
    db_session.commit()
    return analysis


def test_execution_endpoints_validate_ids_and_not_found(client: TestClient):
    invalid_id = client.post("/api/v1/analyses/not-a-uuid/execute", json={})
    missing = client.get(f"/api/v1/executions/{uuid.uuid4()}")
    missing_list = client.get(f"/api/v1/analyses/{uuid.uuid4()}/executions")

    assert invalid_id.status_code == 422
    assert missing.status_code == 404
    assert missing_list.status_code == 404


def test_execute_endpoint_response_has_no_host_paths(
    client: TestClient, db_session: Session, monkeypatch
):
    analysis = _create_analysis(db_session)
    fake_response = {
        "analysis_run_id": str(analysis.id),
        "status": "completed",
        "baseline": {
            "id": str(uuid.uuid4()),
            "analysis_run_id": str(analysis.id),
            "code_snapshot_id": str(analysis.code_snapshot_id),
            "command": "approved-test-runner",
            "command_identifier": "pytest",
            "framework": "pytest",
            "test_files_count": 1,
            "status": "passed",
            "exit_code": 0,
            "passed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "timed_out": False,
            "infrastructure_error": None,
            "stdout": "1 passed",
            "stderr": "",
            "duration_ms": 10,
            "created_at": "2026-10-31T00:00:00Z",
        },
        "execution_results": [],
        "summary": {"mutation_score": None},
    }

    def fake_execute(db, analysis_id, *, timeout_seconds=None):
        assert analysis_id == analysis.id
        return fake_response

    monkeypatch.setattr(execution_service, "execute_analysis", fake_execute)
    response = client.post(f"/api/v1/analyses/{analysis.id}/execute", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "C:\\" not in response.text


def test_execution_list_and_detail_endpoints(client: TestClient, db_session: Session):
    analysis = _create_analysis(db_session)
    baseline = BaselineExecution(
        analysis_run_id=analysis.id,
        code_snapshot_id=analysis.code_snapshot_id,
        command="approved-test-runner",
        command_identifier="pytest",
        framework="pytest",
        status="passed",
        exit_code=0,
    )
    db_session.add(baseline)
    db_session.commit()
    db_session.refresh(baseline)

    listed = client.get(f"/api/v1/analyses/{analysis.id}/executions")
    detail = client.get(f"/api/v1/executions/{baseline.id}")

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["kind"] == "baseline"
    assert detail.status_code == 200
    assert detail.json()["id"] == str(baseline.id)
    assert detail.json()["analysis_run_id"] == str(analysis.id)
    duplicate = client.post(f"/api/v1/analyses/{analysis.id}/execute", json={})
    assert duplicate.status_code == 409
