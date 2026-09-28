from fastapi.testclient import TestClient

from contextplane.app import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_unsupported_method() -> None:
    response = client.post("/health")

    assert response.status_code == 405
