from fastapi.testclient import TestClient

from app.main import app


def test_live_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": "InsightTrace"}
    assert response.headers["X-Request-ID"]
