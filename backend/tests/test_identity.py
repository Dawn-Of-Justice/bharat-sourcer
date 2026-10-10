"""Account identities are synthetic; provider signature checking is tested through its adapter."""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.identity import FirebaseVerifier, GuestSessions, Principal
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import CreateJob
from bharat_sourcer.storage import MemoryJobStore


class Verifier:
    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise ValueError("Invalid mock signature")
        return Principal("user:" + token)


def setup(**overrides):
    settings = Settings(
        _env_file=None,
        **(
            {
                "auth_enabled": True,
                "gcp_project": "fixture-project",
                "guest_session_secret": "test-secret-only-not-production-123456",
            }
            | overrides
        ),
    )
    app = create_app(settings, identity_verifier=Verifier())
    client = TestClient(app, base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    return client, app


def create(client, user=None):
    return client.post(
        "/v1/jobs",
        json={"url": "https://example.com"},
        headers={"Authorization": "Bearer " + user} if user else {},
    )


def test_saved_project_reopens_with_identity_and_never_runs_extraction_again():
    client, app = setup()
    created = create(client, "alice").json()
    key = created["job_id"]
    headers = {"Authorization": "Bearer alice"}
    with patch.object(app.state.job_service, "extract", side_effect=AssertionError("No rerun")):
        listed = client.get("/v1/projects", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["projects"][0]["job_id"] == key
        loaded = client.get(f"/v1/jobs/{key}", headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["items"]
        assert "token_hash" not in loaded.text
        assert loaded.headers["cache-control"] == "no-store"
    assert (
        client.get("/v1/projects", headers={"Authorization": "Bearer bob"}).json()["projects"] == []
    )
    assert (
        client.get(
            f"/v1/jobs/{key}",
            headers={"Authorization": "Bearer bob", "X-Job-Token": created["job_token"]},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/v1/jobs/{key}", headers={"X-Job-Token": created["job_token"]}).status_code
        == 401
    )


def test_guest_cookie_is_named_for_firebase_hosting_and_the_old_name_still_works():
    client, _app = setup()
    session = client.post("/v1/session/guest")
    # Firebase Hosting forwards only `__session` to Cloud Run.
    assert session.headers["set-cookie"].startswith("__session=")
    value = client.cookies.get("__session")
    client.cookies.clear()
    client.cookies.set("bs_guest", value)
    assert client.get("/v1/session").json()["kind"] == "guest"
    assert client.post("/v1/session/guest").headers.get("set-cookie") is None


def test_guest_cookie_security_claim_and_old_guest_access_revoked():
    client, _app = setup()
    session = client.post("/v1/session/guest")
    cookie = session.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("httponly", "secure", "samesite=lax"))
    assert session.json()["kind"] == "guest"
    created = create(client).json()
    key = created["job_id"]
    assert client.get("/v1/projects").json()["projects"][0]["job_id"] == key
    assert client.post(f"/v1/projects/{key}/claim", json={}).status_code == 401
    assert (
        client.post(
            f"/v1/projects/{key}/claim", json={}, headers={"Authorization": "Bearer alice"}
        ).status_code
        == 200
    )
    assert client.get(f"/v1/jobs/{key}").status_code == 404
    assert client.get("/v1/projects").json()["projects"] == []
    assert (
        client.get(f"/v1/jobs/{key}", headers={"Authorization": "Bearer alice"}).status_code == 200
    )
    assert (
        client.post(
            f"/v1/projects/{key}/claim",
            json={"job_token": created["job_token"]},
            headers={"Authorization": "Bearer bob"},
        ).status_code
        == 404
    )


def test_legacy_claim_requires_old_token_and_is_atomic():
    client, app = setup()
    job, token = app.state.job_service.create(CreateJob(url="https://example.com"))
    path = f"/v1/projects/{job.job_id}/claim"
    assert client.post(path, json={}, headers={"Authorization": "Bearer alice"}).status_code == 404

    def claim(user):
        return client.post(
            path, json={"job_token": token}, headers={"Authorization": "Bearer " + user}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(claim, ["alice", "bob"]))
    assert sorted(codes) == [200, 404]


def test_invalid_account_token_never_falls_back_to_valid_guest():
    client, _app = setup()
    client.post("/v1/session/guest")
    assert client.get("/v1/session", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_daily_limit_does_not_block_saved_reads_and_cookie_reset_has_ip_limit():
    client, _app = setup(guest_daily_actions=1, ip_daily_actions=1)
    client.post("/v1/session/guest")
    created = create(client)
    assert created.status_code == 202
    assert create(client).status_code == 429
    assert client.get(f"/v1/jobs/{created.json()['job_id']}").status_code == 200
    client.cookies.clear()
    client.post("/v1/session/guest")
    assert create(client).status_code == 429


def test_global_limits_apply_across_accounts_and_atomic_counters():
    client, _app = setup(global_daily_actions=1)
    assert create(client, "alice").status_code == 202
    assert create(client, "bob").status_code == 429
    store = MemoryJobStore()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: store.consume({"fixture-global": 3}), range(20)))
    assert sum(results) == 3


def test_csrf_header_and_origin_checks():
    client, _app = setup()
    client.headers.pop("X-Requested-With")
    assert client.post("/v1/session/guest").status_code == 403
    client.headers["X-Requested-With"] = "BharatSourcer"
    assert (
        client.post("/v1/session/guest", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )


def test_guest_confirmation_part_limit_is_atomic():
    client, _app = setup(guest_part_limit=1)
    client.post("/v1/session/guest")
    key = create(client).json()["job_id"]
    assert client.post(f"/v1/jobs/{key}/confirm", json={"edits": []}).status_code == 422
    assert client.get(f"/v1/jobs/{key}").json()["status"] == "awaiting_confirmation"


def test_forged_and_expired_sessions_rejected():
    sessions = GuestSessions("fixture-secret", 60)
    token = sessions.issue()
    assert sessions.verify(token).guest
    with pytest.raises(ValueError):
        sessions.verify(token[:-1] + ("a" if token[-1] != "a" else "b"))
    with patch("time.time", return_value=time.time() + 120), pytest.raises(ValueError):
        sessions.verify(token)


def test_verifier_checks_issuer_project_provider_and_email():
    valid = {
        "sub": "alice",
        "iss": "https://securetoken.google.com/test",
        "firebase": {"sign_in_provider": "google.com"},
        "email_verified": True,
        "auth_time": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    verifier = FirebaseVerifier("test", account_lookup=lambda project, uid: {"localId": uid})
    with patch("google.oauth2.id_token.verify_firebase_token", return_value=valid) as verify:
        assert verifier.verify("fixture-token").owner == "user:alice"
        assert verify.call_args.kwargs["audience"] == "test"
    for change in [
        {"iss": "https://accounts.google.com"},
        {"email_verified": False},
        {"firebase": {"sign_in_provider": "anonymous"}},
        {"sub": ""},
    ]:
        with (
            patch("google.oauth2.id_token.verify_firebase_token", return_value=valid | change),
            pytest.raises(ValueError),
        ):
            verifier.verify("fixture-token")


def test_pagination_is_owner_scoped_and_cursor_validated():
    client, app = setup()
    service = app.state.job_service
    for _ in range(4):
        service.create(CreateJob(url="https://example.com"), Principal("user:alice"))
    service.create(CreateJob(url="https://example.com"), Principal("user:bob"))
    headers = {"Authorization": "Bearer alice"}
    first = client.get("/v1/projects?limit=2", headers=headers).json()
    second = client.get(
        "/v1/projects", headers=headers, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len({p["job_id"] for p in first["projects"] + second["projects"]}) == 4
    assert second["next_cursor"] is None
    assert client.get("/v1/projects?cursor=bad", headers=headers).status_code == 404


def test_proxy_ip_requires_trusted_integration_and_cannot_be_arbitrary_text():
    client, _app = setup(trusted_proxy_ip_header=True, integration_key="fixture-key")
    client.headers["X-Integration-Key"] = "fixture-key"
    assert client.post("/v1/session/guest").status_code == 400
    assert (
        client.post("/v1/session/guest", headers={"X-Client-IP": "203.0.113.10"}).status_code == 200
    )
    assert (
        client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer alice", "X-Client-IP": "spoof"},
            json={"url": "https://example.com"},
        ).status_code
        == 400
    )


def test_disabled_auth_preserves_legacy_job_access_and_blocks_identity_endpoints():
    app = create_app(Settings(_env_file=None))
    client = TestClient(app)
    result = create(client).json()
    assert (
        client.get(
            f"/v1/jobs/{result['job_id']}", headers={"X-Job-Token": result["job_token"]}
        ).status_code
        == 200
    )
    assert client.get("/v1/projects").status_code == 503


def test_usage_storage_outage_fails_closed_before_job_creation():
    from bharat_sourcer.storage import StorageError

    client, app = setup()
    with patch.object(app.state.job_service.store, "consume", side_effect=StorageError("test")):
        assert create(client, "alice").status_code == 503
    assert (
        client.get("/v1/projects", headers={"Authorization": "Bearer alice"}).json()["projects"]
        == []
    )


def test_pause_and_saved_reads_remain_available_after_quota_exhaustion():
    client, _app = setup(account_daily_actions=1)
    key = create(client, "alice").json()["job_id"]
    headers = {"Authorization": "Bearer alice"}
    assert client.post(f"/v1/jobs/{key}/confirm", headers=headers, json={}).status_code == 429
    # Draft jobs cannot pause, but the request reaches that state check, not the quota gate.
    assert client.post(f"/v1/jobs/{key}/pause", headers=headers).status_code == 409
    assert client.get(f"/v1/jobs/{key}", headers=headers).status_code == 200


def test_expired_principal_cannot_continue_reading_saved_project():
    from bharat_sourcer.jobs import JobError

    client, app = setup()
    key = create(client, "alice").json()["job_id"]
    expired = Principal("user:alice", expires_at=int(time.time()) - 1)
    with pytest.raises(JobError) as error:
        app.state.job_service.get(key, expired)
    assert error.value.code == "IDENTITY_EXPIRED"


def test_usage_is_private_read_only_and_resets_at_utc_boundary():
    client, _app = setup(account_daily_actions=2)
    headers = {"Authorization": "Bearer alice"}
    moment = 1750000020
    with patch("time.time", return_value=moment):
        assert create(client, "alice").status_code == 202
        usage = client.get("/v1/session/usage", headers=headers).json()
        assert usage["daily_actions"]["used"] == 1
        assert usage["daily_actions"]["remaining"] == 1
        assert usage["daily_projects"]["remaining"] == 4
        assert usage["daily_actions"]["resets_at"] == (moment // 86400 + 1) * 86400
        assert client.get("/v1/session/usage", headers=headers).json() == usage
        other = client.get("/v1/session/usage", headers={"Authorization": "Bearer bob"}).json()
        assert other["daily_actions"]["used"] == 0
        assert client.get("/v1/session/usage").status_code == 401
    with patch("time.time", return_value=(moment // 86400 + 1) * 86400):
        assert client.get("/v1/session/usage", headers=headers).json()["daily_actions"]["used"] == 0


def test_daily_quota_retry_after_waits_until_midnight():
    client, _app = setup(account_daily_actions=1)
    moment = 1750000020
    with patch("time.time", return_value=moment):
        assert create(client, "alice").status_code == 202
        rejected = create(client, "alice")
        assert rejected.status_code == 429
        assert int(rejected.headers["Retry-After"]) == (moment // 86400 + 1) * 86400 - moment


def test_burst_quota_retry_after_waits_only_until_next_minute():
    client, _app = setup()
    moment = 1750000020
    with patch("time.time", return_value=moment):
        key = create(client, "alice").json()["job_id"]
        headers = {"Authorization": "Bearer alice"}
        # Invalid-body attempts are charged, without starting model work.
        for _ in range(4):
            assert (
                client.post(f"/v1/jobs/{key}/messages", headers=headers, json={}).status_code == 422
            )
        response = client.post(f"/v1/jobs/{key}/messages", headers=headers, json={})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) == 60 - moment % 60
