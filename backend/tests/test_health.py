from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "equipsure-api"}


def test_cors_allows_local_dev_origins() -> None:
    for origin in ("http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"):
        response = client.get("/api/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin

