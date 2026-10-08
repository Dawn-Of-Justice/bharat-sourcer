"""Deleting saved projects. Identities are synthetic."""

from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.identity import Principal
from bharat_sourcer.main import create_app
from bharat_sourcer.sharing import token_hash


class Verifier:
    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise ValueError("Invalid mock signature")
        return Principal("user:" + token)


def setup():
    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        gcp_project="fixture-project",
        guest_session_secret="test-secret-only-not-production-123456",
    )
    app = create_app(settings, identity_verifier=Verifier())
    client = TestClient(app, base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    return client, app


def auth(user):
    return {"Authorization": "Bearer " + user}


def create(client, user=None):
    headers = auth(user) if user else {}
    return client.post("/v1/jobs", json={"url": "https://example.com"}, headers=headers).json()


def test_owner_deletes_project_and_it_is_gone_everywhere():
    client, app = setup()
    key = create(client, "alice")["job_id"]
    kept = create(client, "alice")["job_id"]
    # A live share link dies with the project.
    secret = "s" * 32
    app.state.job_service.store.mutate(
        key, lambda record: setattr(record, "share_token_hash", token_hash(f"{key}.{secret}"))
    )
    assert client.get(f"/v1/shared/{key}.{secret}").status_code == 200

    assert client.delete(f"/v1/projects/{key}", headers=auth("alice")).status_code == 204
    listed = client.get("/v1/projects", headers=auth("alice")).json()["projects"]
    assert [project["job_id"] for project in listed] == [kept]
    assert client.get(f"/v1/jobs/{key}", headers=auth("alice")).status_code == 404
    assert client.get(f"/v1/shared/{key}.{secret}").status_code == 404
    # Deleting again is a plain 404.
    assert client.delete(f"/v1/projects/{key}", headers=auth("alice")).status_code == 404


def test_only_the_owner_can_delete():
    client, app = setup()
    key = create(client, "alice")["job_id"]
    response = client.delete(f"/v1/projects/{key}", headers=auth("bob"))
    assert response.status_code == 404 and response.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert client.delete(f"/v1/projects/{key}").status_code == 401
    assert client.delete("/v1/projects/not-a-job", headers=auth("alice")).status_code in {404, 422}
    assert app.state.job_service.store.get(key) is not None


def test_delete_needs_the_application_header():
    client, app = setup()
    key = create(client, "alice")["job_id"]
    response = client.delete(
        f"/v1/projects/{key}", headers=auth("alice") | {"X-Requested-With": ""}
    )
    assert response.status_code == 403
    assert app.state.job_service.store.get(key) is not None


def test_guest_deletes_own_project():
    client, _ = setup()
    assert client.post("/v1/session/guest").status_code == 200
    key = create(client)["job_id"]
    assert client.delete(f"/v1/projects/{key}").status_code == 204
    assert client.get("/v1/projects").json()["projects"] == []


def test_work_for_a_deleted_project_does_nothing():
    client, app = setup()
    key = create(client, "alice")["job_id"]
    assert client.delete(f"/v1/projects/{key}", headers=auth("alice")).status_code == 204
    service = app.state.job_service
    # A queued task that fires after deletion must not recreate or crash on the job.
    service.extract(key)
    assert service.store.get(key) is None
