from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.main import SECURITY_HEADERS, create_app

EXPECTED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
}


def test_security_headers_on_every_response():
    assert {name.lower(): value for name, value in SECURITY_HEADERS.items()} == EXPECTED
    client = TestClient(create_app(Settings(_env_file=None, integration_key="test-team-key")))
    responses = [
        client.get("/healthz"),
        client.get("/no-such-route"),
        # Rejected by the integration-key check before reaching a route.
        client.post("/v1/jobs", json={"url": "https://example.com"}),
        # Validation error.
        client.post("/v1/jobs", headers={"X-Integration-Key": "test-team-key"}, json={}),
        client.options(
            "/v1/jobs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        ),
    ]
    assert [response.status_code for response in responses] == [200, 404, 401, 422, 200]
    for response in responses:
        for name, value in EXPECTED.items():
            assert response.headers.get(name) == value, (response.request.url, name)
