import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.code_snapshot import CodeSnapshot
from app.models.project import Project


def test_list_analyses_empty(client: TestClient) -> None:
    """Verify listing analyses returns an empty paginated collection when none exist."""
    response = client.get("/api/v1/analyses")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["page"] == 1


def test_get_missing_analysis_returns_404(client: TestClient) -> None:
    """Verify that requesting a nonexistent analysis UUID returns 404 Not Found."""
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/analyses/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "ANALYSISRUN_NOT_FOUND"


def test_get_analysis_with_counts(client: TestClient, db_session: Session) -> None:
    """Verify analysis retrieval with relationships and counts."""
    # Seed Project
    project = Project(
        name="Target Service",
        slug=f"target-service-{uuid.uuid4().hex[:6]}",
        status="active",
    )
    db_session.add(project)
    db_session.flush()

    # Seed CodeSnapshot
    snapshot = CodeSnapshot(
        project_id=project.id,
        commit_hash="abcdef0123456789",
        branch="main",
        status="captured",
    )
    db_session.add(snapshot)
    db_session.flush()

    # Seed AnalysisRun
    analysis = AnalysisRun(
        project_id=project.id,
        code_snapshot_id=snapshot.id,
        name="Full Regression Analysis",
        status="running",
        summary={"total_mutations": 10},
    )
    db_session.add(analysis)
    db_session.flush()

    # Seed BaselineExecution
    baseline = BaselineExecution(
        analysis_run_id=analysis.id,
        code_snapshot_id=snapshot.id,
        command="pytest tests/",
        status="completed",
        exit_code=0,
        duration_ms=450,
    )
    db_session.add(baseline)
    db_session.commit()

    # Retrieve via API
    response = client.get(f"/api/v1/analyses/{analysis.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(analysis.id)
    assert data["name"] == "Full Regression Analysis"
    assert data["status"] == "running"
    assert data["summary"]["total_mutations"] == 10
    assert data["baseline_executions_count"] == 1
    assert data["mutation_records_count"] == 0
    assert data["failure_reports_count"] == 0
