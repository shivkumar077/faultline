from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """Verify application root endpoint metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "FAULTLINE"
    assert "version" in data
    assert data["health"] == "/health"
    assert "/docs" in data["docs"]


def test_root_health_endpoint(client: TestClient) -> None:
    """Verify root /health endpoint used for container health checking."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "faultline-api"
    assert "version" in data
    assert "environment" in data


def test_api_v1_health_endpoint(client: TestClient) -> None:
    """Verify versioned /api/v1/health endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "faultline-api"


def test_readiness_endpoint_checks_database_and_reports_runner(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "available"
    assert data["execution_runner"] in {"available", "unavailable"}
    assert data["status"] in {"ready", "degraded"}

    versioned = client.get("/api/v1/health/ready")
    assert versioned.status_code == 200
