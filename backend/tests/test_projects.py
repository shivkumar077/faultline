import uuid

from fastapi.testclient import TestClient


def test_create_project_with_explicit_slug(client: TestClient) -> None:
    """Verify creating a project with a custom explicit slug."""
    payload = {
        "name": "Auth Service",
        "slug": "auth-service",
        "description": "Authentication microservice",
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Auth Service"
    assert data["slug"] == "auth-service"
    assert data["description"] == "Authentication microservice"
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data


def test_create_project_auto_slug(client: TestClient) -> None:
    """Verify automatic slug generation from the project name."""
    payload = {
        "name": "Billing Engine Core",
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "billing-engine-core"


def test_create_duplicate_slug_conflict(client: TestClient) -> None:
    """Verify that creating a project with an existing slug returns 409 Conflict."""
    payload = {
        "name": "Inventory API",
        "slug": "inventory-api",
    }
    res1 = client.post("/api/v1/projects", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/projects", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error_code"] == "PROJECT_ALREADY_EXISTS"
    assert "already exists" in data["detail"]


def test_get_project_by_id(client: TestClient) -> None:
    """Verify project retrieval with relationship counts."""
    payload = {
        "name": "Checkout Flow",
        "slug": "checkout-flow",
    }
    created = client.post("/api/v1/projects", json=payload).json()
    project_id = created["id"]

    response = client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == "Checkout Flow"
    assert data["repository_connections_count"] == 0
    assert data["code_snapshots_count"] == 0
    assert data["analysis_runs_count"] == 0


def test_get_missing_project_returns_404(client: TestClient) -> None:
    """Verify that requesting a nonexistent project UUID returns 404 Not Found."""
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/projects/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "PROJECT_NOT_FOUND"


def test_list_projects_pagination(client: TestClient) -> None:
    """Verify paginated listing of projects."""
    for i in range(3):
        client.post(
            "/api/v1/projects",
            json={
                "name": f"Paginated App {i}",
                "slug": f"paginated-app-{i}-{uuid.uuid4().hex[:6]}",
            },
        )

    response = client.get("/api/v1/projects?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 3
    assert data["total_pages"] >= 2


def test_delete_project(client: TestClient) -> None:
    """Verify project deletion."""
    created = client.post(
        "/api/v1/projects",
        json={"name": "Temporary Project", "slug": f"temp-proj-{uuid.uuid4().hex[:6]}"},
    ).json()
    project_id = created["id"]

    del_res = client.delete(f"/api/v1/projects/{project_id}")
    assert del_res.status_code == 200

    get_res = client.get(f"/api/v1/projects/{project_id}")
    assert get_res.status_code == 404
