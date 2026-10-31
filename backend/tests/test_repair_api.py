import hashlib
import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.code_snapshot import CodeSnapshot
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.services.repair_service import repair_service


class StaticMaterializer:
    def __init__(self, workspace):
        self.workspace = workspace

    @contextmanager
    def materialized_workspace(self, repository_url, commit_hash):
        yield self.workspace


def _create_diagnosis(db: Session, workspace):
    source = "def calculate(a, b):\n    return a - b\n"
    target = workspace / "math_ops.py"
    target.write_text(source, encoding="utf-8")
    project = Project(name="Repair API", slug=f"repair-api-{uuid.uuid4().hex[:8]}")
    db.add(project)
    db.flush()
    connection = RepositoryConnection(
        project_id=project.id,
        repository_url="https://example.invalid/repository.git",
    )
    db.add(connection)
    db.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        repository_connection_id=connection.id,
        commit_hash=uuid.uuid4().hex + uuid.uuid4().hex[:8],
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
    mutation = MutationRecord(
        analysis_run_id=analysis.id,
        mutation_type="arithmetic_operator",
        target_file="math_ops.py",
        line_number=2,
        col_offset=11,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        original_code="a + b",
        mutated_code="a - b",
        status="applied",
    )
    db.add(mutation)
    db.flush()
    report = FailureReport(
        analysis_run_id=analysis.id,
        mutation_record_id=mutation.id,
        title="Failure",
        failure_type="AssertionError",
        category="introduced_failure",
        causal_attribution="inferred",
        confidence_score=0.8,
        mutation_file="math_ops.py",
        mutation_line=2,
        original_expression="a + b",
        mutated_expression="a - b",
        evidence=[{"supports_cause": True, "kind": "baseline_comparison"}],
    )
    db.add(report)
    db.commit()
    return analysis, report


def test_repair_api_generation_listing_patch_and_review(
    client: TestClient,
    db_session: Session,
    tmp_path,
    monkeypatch,
):
    analysis, report = _create_diagnosis(db_session, tmp_path)
    monkeypatch.setattr(repair_service, "materializer", StaticMaterializer(tmp_path))

    generated = client.post(
        f"/api/v1/analyses/{analysis.id}/diagnoses/{report.id}/repair-candidates"
    )
    assert generated.status_code == 200
    body = generated.json()
    candidate_id = body["candidates"][0]["id"]
    assert body["candidates"][0]["validation_status"] == "syntax_valid"

    listed = client.get(f"/api/v1/analyses/{analysis.id}/repair-candidates?page_size=1")
    detail = client.get(f"/api/v1/repair-candidates/{candidate_id}")
    patch = client.get(f"/api/v1/repair-candidates/{candidate_id}/diff")
    reviewed = client.patch(
        f"/api/v1/repair-candidates/{candidate_id}/review",
        json={"decision": "reviewed"},
    )
    conflicting_review = client.patch(
        f"/api/v1/repair-candidates/{candidate_id}/review",
        json={"decision": "rejected"},
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert detail.status_code == 200
    assert "patch_content" not in detail.json()
    assert patch.status_code == 200
    assert "+    return a + b" in patch.json()["patch_content"]
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "reviewed"
    assert conflicting_review.status_code == 409


def test_generate_analysis_repairs_with_report_filter_and_rejection(
    client: TestClient,
    db_session: Session,
    tmp_path,
    monkeypatch,
):
    analysis, report = _create_diagnosis(db_session, tmp_path)
    monkeypatch.setattr(repair_service, "materializer", StaticMaterializer(tmp_path))

    generated = client.post(
        f"/api/v1/analyses/{analysis.id}/repair-candidates",
        json={"failure_report_ids": [str(report.id)]},
    )
    candidate_id = generated.json()["candidates"][0]["id"]
    rejected = client.patch(
        f"/api/v1/repair-candidates/{candidate_id}/review",
        json={"decision": "rejected"},
    )

    assert generated.status_code == 200
    assert len(generated.json()["candidates"]) == 1
    assert rejected.status_code == 200
    assert rejected.json()["review_status"] == "rejected"


def test_repair_api_rejects_invalid_ids_and_decisions(client: TestClient):
    missing_analysis = uuid.uuid4()
    missing_report = uuid.uuid4()
    invalid_body = client.post(
        f"/api/v1/analyses/{missing_analysis}/repair-candidates",
        json={"failure_report_ids": ["not-a-uuid"]},
    )
    missing_diagnosis = client.post(
        f"/api/v1/analyses/{missing_analysis}/diagnoses/{missing_report}/repair-candidates"
    )
    invalid_review = client.patch(
        f"/api/v1/repair-candidates/{uuid.uuid4()}/review",
        json={"decision": "accepted"},
    )
    missing_list = client.get(f"/api/v1/analyses/{missing_analysis}/repair-candidates")

    assert invalid_body.status_code == 422
    assert missing_diagnosis.status_code == 404
    assert invalid_review.status_code == 422
    assert missing_list.status_code == 404


def test_repair_generation_skips_unsupported_reports(
    client: TestClient,
    db_session: Session,
    tmp_path,
    monkeypatch,
):
    analysis, report = _create_diagnosis(db_session, tmp_path)
    report.category = "existing_baseline_failure"
    db_session.commit()
    materializer = StaticMaterializer(tmp_path)
    monkeypatch.setattr(repair_service, "materializer", materializer)

    response = client.post(f"/api/v1/analyses/{analysis.id}/repair-candidates", json={})

    assert response.status_code == 200
    assert response.json()["candidates"] == []
    assert response.json()["skipped"][0]["reason"] == "unsupported_diagnosis"
