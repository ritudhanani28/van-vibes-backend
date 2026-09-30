from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["statusCode"] == 200
    assert "service" in body["data"]
    assert body["data"]["status"] == "running"
    assert "X-Request-ID" in response.headers


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code in [200, 503]
    body = response.json()
    assert "status" in body["data"]
    assert "environment" in body["data"]
    assert "X-Request-ID" in response.headers


def test_v1_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code in [200, 503]
    body = response.json()
    assert "status" in body["data"]
    assert "X-Request-ID" in response.headers
