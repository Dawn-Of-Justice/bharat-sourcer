from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app


def test_integration_key_and_cors_preflight():
    client = TestClient(create_app(Settings(_env_file=None, integration_key="test-team-key")))
    assert client.get("/healthz").status_code == 200
    assert client.get("/health").json() == client.get("/healthz").json()
    assert client.post("/v1/jobs", json={"url": "https://example.com"}).status_code == 401
    response = client.options(
        "/v1/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Integration-Key,X-Job-Token,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.post(
        "/v1/jobs",
        headers={"X-Integration-Key": "test-team-key"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 202
    root = f"/v1/jobs/{response.json()['job_id']}"
    assert client.get(root, headers={"X-Integration-Key": "test-team-key"}).status_code == 404
    assert (
        client.get(
            root,
            headers={
                "X-Integration-Key": "test-team-key",
                "X-Job-Token": response.json()["job_token"],
            },
        ).status_code
        == 200
    )
