from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_openapi_contract() -> None:
    client = TestClient(create_app())
    health = client.get("/api/v1/health")
    schema = client.get("/api/v1/openapi.json")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "Omni CRM API"

