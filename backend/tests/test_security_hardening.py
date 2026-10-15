"""Security hardening: route-wide auth sweeps, body caps, generic errors, SSRF and inputs.

Everything here is synthetic: mock identities, demo jobs and patched network calls.
"""

import hashlib
import hmac
import io
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_code_patches import path as patch_path
from test_code_patches import setup as patch_setup
from test_identity import create
from test_identity import setup as auth_setup

from bharat_sourcer import access as access_module
from bharat_sourcer.code_patches import archive_name, source_files
from bharat_sourcer.compile_check import runner_identity
from bharat_sourcer.config import Settings
from bharat_sourcer.dispatch import CloudDispatcher
from bharat_sourcer.identity import GuestSessions
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    BuyableSpec,
    ConfirmJob,
    CreateJob,
    Evidence,
    Job,
    UpdateLine,
)
from bharat_sourcer.sourcing.fetch import (
    FetchError,
    Page,
    SafeFetcher,
    is_public,
    public_addresses,
    validate_url,
)


def demo_client(**overrides):
    app = create_app(Settings(_env_file=None, demo_mode=True, **overrides))
    return TestClient(app), app


def demo_job(client):
    created = client.post("/v1/jobs", json={"url": "https://example.com/build"}).json()
    return created["job_id"], {"X-Job-Token": created["job_token"]}


# --- server-side auth on every route ---------------------------------------------------------

# Public by design: reference data, starting a guest session, clearing its cookie. Share
# routes (/v1/shared/...) authorise by their own token and are tested in test_export_share.
PUBLIC = {
    ("GET", "/v1/countries"),
    ("GET", "/v1/compile/boards"),
    ("POST", "/v1/session/guest"),
    ("POST", "/v1/session/logout"),
}
BODIES = {"/v1/account/settings": {"country": "IN"}}


def v1_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/v1/"):
            if route.path.startswith("/v1/shared/"):
                continue
            for method in sorted(route.methods):
                if (method, route.path) not in PUBLIC:
                    yield method, route.path


def fill(path, job_id):
    return path.format(job_id=job_id, line_id="L01", message_id=str(uuid4()))


def test_every_v1_route_requires_an_identity_when_auth_is_enabled():
    client, app = auth_setup()
    job_id = create(client, "alice").json()["job_id"]
    checked = 0
    for method, path in v1_routes(app):
        response = client.request(method, fill(path, job_id), json=BODIES.get(path, {}))
        assert response.status_code == 401, (method, path, response.status_code, response.text)
        checked += 1
    assert checked > 40


def test_another_identity_never_reaches_a_project_by_its_id():
    client, app = auth_setup()
    job_id = create(client, "alice").json()["job_id"]
    bob = {"Authorization": "Bearer bob"}
    for method, path in v1_routes(app):
        if "{job_id}" not in path:
            continue
        response = client.request(method, fill(path, job_id), json={}, headers=bob)
        assert response.status_code == 404, (method, path, response.status_code, response.text)
    # Alice still has her project, untouched by Bob's attempts.
    alice = client.get(f"/v1/jobs/{job_id}", headers={"Authorization": "Bearer alice"})
    assert alice.status_code == 200 and alice.json()["status"] == "awaiting_confirmation"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/internal/work", {"job_id": str(uuid4()), "kind": "workflow"}),
        ("POST", "/internal/sweep", None),
        ("GET", "/internal/compile/run", None),
        ("POST", "/internal/compile/run/result", {"status": "error"}),
    ],
)
def test_internal_routes_refuse_callers_without_a_verified_identity(method, path, body):
    client, _ = demo_client()
    for headers in ({}, {"Authorization": "Bearer forged"}, {"Authorization": "Basic x"}):
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401, (path, headers, response.text)


def test_worker_auth_fails_closed_without_audience_or_service_account(monkeypatch):
    # A token without an email claim must not match an unset service account (None == None).
    verify = Mock(return_value={"email": None, "email_verified": True})
    monkeypatch.setattr("bharat_sourcer.dispatch.id_token.verify_oauth2_token", verify)
    assert not CloudDispatcher(Settings(_env_file=None)).authorize("Bearer forged")
    only_url = Settings(_env_file=None, tasks_url="https://api.example")
    assert not CloudDispatcher(only_url).authorize("Bearer forged")
    verify.assert_not_called()


def test_runner_auth_fails_closed_without_a_runner_service_account(monkeypatch):
    verify = Mock(return_value={"email": None, "email_verified": True})
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", verify)
    settings = Settings(_env_file=None, compile_audience="https://api.example")
    assert not runner_identity(settings, "Bearer forged")
    verify.assert_not_called()


def test_share_token_is_not_a_job_token_and_reaches_no_other_job():
    client, _ = demo_client()
    job_id, owner = demo_job(client)
    other_id, _ = demo_job(client)
    share = client.post(f"/v1/jobs/{job_id}/share", headers=owner).json()["share_token"]
    as_token = {"X-Job-Token": share}
    assert client.get(f"/v1/jobs/{job_id}", headers=as_token).status_code == 404
    assert client.get(f"/v1/jobs/{other_id}", headers=as_token).status_code == 404
    edits = {"edits": []}
    assert (
        client.post(f"/v1/jobs/{job_id}/confirm", headers=as_token, json=edits).status_code == 404
    )
    assert client.delete(f"/v1/jobs/{job_id}/share", headers=as_token).status_code == 404
    assert client.post(f"/v1/jobs/{job_id}/share", headers=as_token).status_code == 404
    # The link itself keeps working read-only; the refused revoke changed nothing.
    assert client.get(f"/v1/shared/{share}").status_code == 200
    _, secret = share.split(".", 1)
    assert client.get(f"/v1/shared/{other_id}.{secret}").status_code == 404


# --- rate limits -----------------------------------------------------------------------------


def test_claims_are_limited_per_account_per_minute(monkeypatch):
    clock = SimpleNamespace(time=lambda: 1_800_000_000.0)
    monkeypatch.setattr(access_module, "time", clock)
    client, _ = auth_setup()
    alice = {"Authorization": "Bearer alice"}
    for _ in range(access_module.CLAIMS_PER_MINUTE):
        response = client.post(f"/v1/projects/{uuid4()}/claim", json={}, headers=alice)
        assert response.status_code == 404
    limited = client.post(f"/v1/projects/{uuid4()}/claim", json={}, headers=alice)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "USAGE_LIMIT"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    # Another account has its own budget.
    bob = client.post(
        f"/v1/projects/{uuid4()}/claim", json={}, headers={"Authorization": "Bearer bob"}
    )
    assert bob.status_code == 404


# --- identity and integration-key comparisons -------------------------------------------------


def test_non_ascii_integration_key_is_a_plain_mismatch():
    client, _ = demo_client(integration_key="k" * 32)
    bad = client.get("/v1/countries", headers={"X-Integration-Key": "\xe9".encode("latin-1")})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INTEGRATION_KEY_REQUIRED"
    assert client.get("/v1/countries", headers={"X-Integration-Key": "k" * 32}).status_code == 200


def test_malformed_guest_cookies_get_a_new_session_not_a_500():
    client, _ = auth_setup()
    expiry = int(time.time()) + 600
    for cookie in (
        f"{'a' * 48}.{expiry}.\xe9",
        f"{'a' * 48}.{expiry}",
        "a.b.c.d",
        f"{'a' * 48}.-1.x",
    ):
        header = {"Cookie": ("__session=" + cookie).encode("latin-1")}
        response = client.post("/v1/session/guest", headers=header)
        assert response.status_code == 200, (cookie, response.text)
        assert "__session=" in response.headers["set-cookie"]
        claim = client.post(
            f"/v1/projects/{uuid4()}/claim",
            json={},
            headers=header | {"Authorization": "Bearer alice"},
        )
        assert claim.status_code == 404


def test_guest_sessions_refuse_an_empty_secret():
    sessions = GuestSessions("", 60)
    key, expiry = "a" * 48, str(int(time.time()) + 60)
    forged = hmac.new(b"", f"{key}.{expiry}".encode(), hashlib.sha256).hexdigest()
    with pytest.raises(ValueError):
        sessions.verify(f"{key}.{expiry}.{forged}")
    with pytest.raises(RuntimeError):
        sessions.issue()


def test_authentication_refuses_wildcard_cors_origins():
    with pytest.raises(ValueError, match="explicit CORS"):
        Settings(
            _env_file=None,
            auth_enabled=True,
            gcp_project="fixture-project",
            guest_session_secret="s" * 32,
            cors_origins=["*"],
        )


# --- request size, validation and generic errors ----------------------------------------------


def test_declared_oversized_bodies_are_refused_before_parsing():
    client, app = demo_client(max_body_bytes=65_536)
    body = b'{"url": "https://example.com", "pad": "' + b"x" * 70_000 + b'"}'
    response = client.post("/v1/jobs", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {
        "error": {"code": "BODY_TOO_LARGE", "message": "Request body is too large"}
    }
    assert app.state.job_service.store._records == {}


def test_streamed_oversized_bodies_are_refused():
    client, app = demo_client(max_body_bytes=65_536)

    def chunks():
        yield b'{"url": "https://example.com", "pad": "'
        for _ in range(10):
            yield b"x" * 10_000
        yield b'"}'

    response = client.post(
        "/v1/jobs", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "BODY_TOO_LARGE"
    assert app.state.job_service.store._records == {}


def test_normal_bodies_and_the_scan_photo_still_pass_the_cap():
    client, _ = demo_client()
    job_id, owner = demo_job(client)
    assert client.get(f"/v1/jobs/{job_id}", headers=owner).status_code == 200
    # A 2 MB photo is over the default cap but within the scan route's own limit: it reaches
    # the route, which answers as before (scan is off by default).
    photo = {"image_base64": "A" * 2_000_000}
    response = client.post(f"/v1/jobs/{job_id}/scan", headers=owner, json=photo)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FEATURE_DISABLED"
    over = client.post(f"/v1/jobs/{job_id}/confirm", headers=owner, json={"pad": "x" * 1_100_000})
    assert over.status_code == 413


def test_unexpected_errors_return_a_generic_500_without_details(monkeypatch):
    app = create_app(Settings(_env_file=None, demo_mode=True))
    client = TestClient(app, raise_server_exceptions=False)
    detail = "Traceback /srv/app/secret.py internal detail"
    monkeypatch.setattr(app.state.job_service, "get", Mock(side_effect=RuntimeError(detail)))
    response = client.get(f"/v1/jobs/{uuid4()}", headers={"X-Job-Token": "t"})
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    }
    assert "secret" not in response.text and "Traceback" not in response.text


@pytest.mark.parametrize(
    ("suffix", "body"),
    [
        ("refresh", {"line_ids": ["L" * 65]}),
        ("selections", {"selections": [{"line_id": "L" * 65}]}),
        ("specs", {"updates": [{"line_id": "L" * 65, "requirements": []}]}),
        ("confirm", {"edits": [{"op": "remove", "line_id": "L" * 65}]}),
        ("parts/L01/image", {"failed_urls": ["https://cdn.example/" + "x" * 5000]}),
        ("messages", {"message_id": str(uuid4()), "text": "x" * 4001}),
    ],
)
def test_client_strings_are_bounded(suffix, body):
    client, _ = demo_client()
    job_id, owner = demo_job(client)
    response = client.post(f"/v1/jobs/{job_id}/{suffix}", headers=owner, json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_buying_spec_lists_are_bounded_and_marked_user():
    service = JobService()
    job = Job(
        job_id=str(uuid4()),
        input=CreateJob(url="https://example.com"),
        status="awaiting_confirmation",
        items=[BomItem(line_id="L01", raw_name="10k resistor")],
    )
    spec = BuyableSpec(origin="ai_inferred", reasons=["r" * 5000], must=["m" * 500])
    edit = UpdateLine(op="update", line_id="L01", buyable_spec=spec)
    service.edit_draft(job, ConfirmJob(edits=[edit]))
    saved = job.items[0].buyable_spec
    assert saved.origin == "user"
    assert saved.reasons == ["r" * 300] and saved.must == ["m" * 60]


# --- SSRF -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "169.254.169.254",
        "10.0.0.1",
        "::ffff:169.254.169.254",  # IPv4-mapped
        "64:ff9b::a9fe:a9fe",  # NAT64 of the metadata address
        "::7f00:1",  # IPv4-compatible loopback
        "fe80::1%eth0",  # scoped link-local
        "not-an-address",
    ],
)
def test_private_and_embedded_private_addresses_are_not_public(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111", "64:ff9b::808:808"])
def test_global_addresses_stay_public(address):
    assert is_public(address)


@pytest.mark.parametrize(
    "url",
    [
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://METADATA.google.internal./computeMetadata/v1/",
        "https://metadata/computeMetadata/v1/",
        "https://metadata.goog/",
        "https://service.internal/",
        "https://localhost/",
        "https://printer.local/",
    ],
)
def test_metadata_and_internal_names_are_refused_before_dns(url):
    with patch("socket.getaddrinfo", side_effect=AssertionError("no DNS lookup")):
        with pytest.raises(FetchError):
            validate_url(url)
        with pytest.raises(FetchError):
            SafeFetcher().get(url, robots=False)


def test_dns_answers_with_embedded_private_addresses_are_refused():
    answer = [(0, 0, 0, "", ("64:ff9b::7f00:1", 443, 0, 0))]
    with patch("socket.getaddrinfo", return_value=answer), pytest.raises(FetchError):
        public_addresses("seller.example")


def test_each_redirect_hop_is_revalidated(monkeypatch):
    fetcher = SafeFetcher()
    requested = []

    def request(url, max_bytes):
        requested.append(url)
        location = "https://metadata.google.internal/computeMetadata/v1/"
        return Page(url, 302, {"location": location}, b"")

    monkeypatch.setattr(fetcher, "_request", request)
    with pytest.raises(FetchError):
        fetcher.get("https://seller.example/item", robots=False)
    assert requested == ["https://seller.example/item"]


# --- zip export -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../x.ino",
        "src/../../x.ino",
        "src//x.ino",
        "./x.ino",
        "C:/x.ino",
        "a\\b.ino",
        "",
    ],
)
def test_traversal_and_absolute_archive_names_are_refused(path):
    assert archive_name(path) is None


def test_ordinary_repository_paths_are_archive_names():
    assert archive_name("src/main.ino") == "src/main.ino"
    assert archive_name("My Sketch/display-v1.2.cpp") == "My Sketch/display-v1.2.cpp"


def test_code_evidence_with_an_absolute_path_is_never_read():
    evidence = Evidence(
        source="code",
        observation="synthetic",
        quote="#include <Wire.h>",
        url="https://github.com/maker/repo/blob/main//etc/passwd.ino#L1",
        file="etc/passwd.ino",
        line=1,
    )
    job = Job(
        job_id=str(uuid4()),
        input=CreateJob(url="https://github.com/maker/repo"),
        items=[BomItem(line_id="L01", raw_name="OLED", evidence=[evidence])],
    )
    assert source_files(job) == {}


def test_download_refuses_a_stored_patch_with_an_unsafe_path():
    client, app, job_id, _ = patch_setup()
    assert client.post(patch_path(job_id), json={}).json()["status"] == "ready"
    good = client.get(patch_path(job_id) + ".zip")
    assert good.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(good.content)).namelist()[0] == "src/main.ino"

    def tamper(record):
        record.job.report.lines[0].code_patch.files[0].path = "../../evil.ino"

    app.state.job_service.store.mutate(job_id, tamper)
    refused = client.get(patch_path(job_id) + ".zip")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PATCH_UNSAFE"
