from uuid import uuid4

from app.core.config import settings
from app.schemas.repair_evaluation import ForgeFitScenarioRequest
from app.services.forgefit_adapter import ForgeFitAdapter


def test_forgefit_adapter_uses_existing_async_api_and_bounds_report(monkeypatch):
    monkeypatch.setattr(settings, "FORGEFIT_BASE_URL", "https://forgefit.example")
    monkeypatch.setattr(settings, "FORGEFIT_API_KEY", "test-secret")
    adapter = ForgeFitAdapter()
    calls = []

    def request_json(method, url, headers, *, payload=None):
        calls.append((method, url, headers, payload))
        if url.endswith("/api/status"):
            return {"status": "ok", "api_key_required": True}
        if url.endswith("/api/runs"):
            return {"run_id": "run/with space"}
        return {
            "status": "completed",
            "report": {
                "total_requests": 2,
                "successful_requests": 2,
                "failed_requests": 0,
                "outcomes": [{"error_message": "must not be persisted"}],
                "metadata": {"secret": "must not be persisted"},
            },
        }

    monkeypatch.setattr(adapter, "_request_json", request_json)
    outcome = adapter.run_scenario(
        ForgeFitScenarioRequest(
            target_url="http://127.0.0.1:8000/health",
            request_count=2,
        ),
        candidate_id=uuid4(),
        evaluation_id=uuid4(),
    )

    assert outcome.status == "completed"
    assert outcome.run_id == "run/with space"
    assert outcome.result == {
        "total_requests": 2,
        "successful_requests": 2,
        "failed_requests": 0,
    }
    assert "X-ForgeFit-API-Key" not in calls[0][2]
    assert calls[1][3]["save_report"] is False
    assert "Faultline evaluation" in calls[1][3]["scenario"]["name"]
    assert calls[1][2]["X-ForgeFit-API-Key"] == "test-secret"
    assert calls[2][1].endswith("/api/runs/run%2Fwith%20space")


def test_forgefit_adapter_fails_closed_for_unauthorized_external_target(monkeypatch):
    monkeypatch.setattr(settings, "FORGEFIT_BASE_URL", "https://forgefit.example")
    adapter = ForgeFitAdapter()
    calls = []
    monkeypatch.setattr(
        adapter,
        "_request_json",
        lambda *args, **kwargs: calls.append(args),
    )

    outcome = adapter.run_scenario(
        ForgeFitScenarioRequest(target_url="https://example.com/health"),
        candidate_id=uuid4(),
        evaluation_id=uuid4(),
    )

    assert outcome.status == "error"
    assert outcome.error_code == "EXTERNAL_TARGET_NOT_AUTHORIZED"
    assert calls == []


def test_forgefit_adapter_reports_missing_optional_configuration(monkeypatch):
    monkeypatch.setattr(settings, "FORGEFIT_BASE_URL", None)
    outcome = ForgeFitAdapter().run_scenario(
        ForgeFitScenarioRequest(target_url="http://localhost:8000/health"),
        candidate_id=uuid4(),
        evaluation_id=uuid4(),
    )

    assert outcome.status == "not_configured"
    assert outcome.error_code == "NOT_CONFIGURED"


def test_forgefit_adapter_requires_tls_for_remote_base_url(monkeypatch):
    monkeypatch.setattr(settings, "FORGEFIT_BASE_URL", "http://forgefit.example")
    adapter = ForgeFitAdapter()
    calls = []
    monkeypatch.setattr(
        adapter,
        "_request_json",
        lambda *args, **kwargs: calls.append(args),
    )

    outcome = adapter.run_scenario(
        ForgeFitScenarioRequest(target_url="http://localhost:8000/health"),
        candidate_id=uuid4(),
        evaluation_id=uuid4(),
    )

    assert outcome.status == "error"
    assert outcome.error_code == "INSECURE_BASE_URL"
    assert calls == []
