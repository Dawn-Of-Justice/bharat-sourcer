"""Exports and share links use demo fixtures and synthetic offers; no model calls."""

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer import sharing
from bharat_sourcer.config import Settings
from bharat_sourcer.export import PdfUnavailable, redact, to_html, to_pdf
from bharat_sourcer.identity import Principal
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    Compatibility,
    CreateJob,
    Evidence,
    Job,
    Report,
    ReportLine,
    VerifiedOffer,
)

INJECTION = '=HYPERLINK("https://evil.example","x")'
SCRIPT = "<script>alert(1)</script>"


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, demo_mode=True))) as client:
        yield client


def create_done_job(client, headers=None, edits=None):
    response = client.post("/v1/jobs", json={"url": "https://example.com/build"}, headers=headers)
    assert response.status_code == 202
    created = response.json()
    auth = headers or {"X-Job-Token": created["job_token"]}
    path = created["watch"]
    assert client.post(f"{path}/confirm", headers=auth, json={"edits": edits or []}).status_code
    assert client.get(path, headers=auth).json()["status"] == "done"
    return path, auth, created


def pdf_available():
    try:
        to_pdf(redact(live_job()))
    except PdfUnavailable:
        return False
    return True


needs_pdf = pytest.mark.skipif(
    "not pdf_available()", reason="WeasyPrint system libraries (Pango) not installed"
)


def test_owner_exports_and_others_cannot(client):
    path, headers, created = create_done_job(client)
    _, other, _ = create_done_job(client)
    html = client.get(f"{path}/export.html", headers=headers)
    assert html.status_code == 200
    assert "default-src 'none'" in html.headers["content-security-policy"]
    assert "DEMO JOB" in html.text and "<script" not in html.text
    for bad in ({}, other):
        for suffix in ("export.pdf", "export.html", "share"):
            assert client.get(f"{path}/{suffix}", headers=bad).status_code == 404
        assert client.post(f"{path}/share", headers=bad).status_code == 404
        assert client.delete(f"{path}/share", headers=bad).status_code == 404
    assert created["job_token"] not in html.text


def test_share_is_redacted_rotates_and_revokes(client):
    path, headers, created = create_done_job(client)
    assert client.get(f"{path}/share", headers=headers).json() == {
        "active": False,
        "created_at": None,
    }
    link = client.post(f"{path}/share", headers=headers)
    assert link.status_code == 201
    token = link.json()["share_token"]
    assert link.json()["path"] == f"/v1/shared/{token}"
    assert client.get(f"{path}/share", headers=headers).json()["active"] is True
    shared = client.get(f"/v1/shared/{token}")
    assert shared.status_code == 200
    assert shared.headers["referrer-policy"] == "no-referrer"
    body = shared.json()
    assert body["shared"] is True and body["demo"] is True
    for key in ("job_id", "messages", "events", "actions", "chat_state", "input"):
        assert key not in body
    for secret in (created["job_token"], "token_hash", "560001", "owner_id"):
        assert secret not in shared.text
    record = client.app.state.job_service.store.get(created["job_id"])
    assert token not in record.model_dump_json()
    assert record.share_token_hash == sharing.token_hash(token)
    assert client.get(f"/v1/shared/{token}/export.html").status_code == 200

    rotated = client.post(f"{path}/share", headers=headers).json()["share_token"]
    assert client.get(f"/v1/shared/{token}").status_code == 404
    assert client.get(f"/v1/shared/{rotated}").status_code == 200
    assert client.delete(f"{path}/share", headers=headers).status_code == 204
    for value in (rotated, token, "nonsense", f"{created['job_id']}.guess", "x" * 200):
        response = client.get(f"/v1/shared/{value}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SHARE_NOT_FOUND"
    for suffix in ("export.html", "export.pdf"):
        assert client.get(f"/v1/shared/{rotated}/{suffix}").status_code == 404


def test_shared_reads_are_rate_limited(client, monkeypatch):
    path, headers, _ = create_done_job(client)
    token = client.post(f"{path}/share", headers=headers).json()["share_token"]
    monkeypatch.setattr(sharing, "SHARED_MINUTE_READS", 2)
    assert [client.get(f"/v1/shared/{token}").status_code for _ in range(3)] == [200, 200, 429]


def test_html_escapes_part_names(client):
    edits = [
        {"op": "add", "raw_name": INJECTION, "qty": 1},
        {"op": "add", "raw_name": SCRIPT, "qty": 1},
        {"op": "add", "raw_name": "@SUM(1)", "qty": 1},
        {"op": "add", "raw_name": "-2+3", "qty": 1},
    ]
    path, headers, _ = create_done_job(client, edits=edits)
    html = client.get(f"{path}/export.html", headers=headers).text
    assert SCRIPT not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def live_job():
    offer = VerifiedOffer(
        url="https://seller.example/p?a=1&b=<x>",
        seller="=Seller",
        title="Pro Micro 5V",
        price_inr="250.00",
        stock="in_stock",
        compatibility=Compatibility(status="compatible", grade="A"),
    )
    item = BomItem(
        line_id="L01",
        raw_name="Pro Micro",
        qty=2,
        evidence=[
            Evidence(timestamp="01:05", observation="Board shown"),
            Evidence(
                source="project_page",
                observation="Parts list",
                quote="uses a Pro Micro",
                url="https://example.com/build",
            ),
        ],
    )
    line = ReportLine(
        item=item,
        sourcing_status="offers_found",
        offers=[offer],
        selected_offer_url=offer.url,
        price_inr="250.00",
        subtotal_inr="500.00",
        grade="A",
    )
    return Job(
        job_id="00000000-0000-4000-8000-000000000000",
        status="done",
        demo=False,
        input=CreateJob(url="https://example.com/build"),
        items=[item],
        report=Report(
            demo=False, summary="Sourced.", lines=[line], selected_parts_subtotal_inr="500.00"
        ),
    )


def test_selected_offer_and_evidence_in_html():
    view = redact(live_job())
    html = to_html(view)
    assert "Pro Micro 5V" in html and "₹250.00" in html and "₹500.00" in html
    assert "01:05" in html and "Board shown" in html and "uses a Pro Micro" in html
    assert "DEMO JOB" not in html
    assert "<x>" not in html and "&amp;b=" in html and "560001" not in html


def test_auth_mode_share_is_public_and_free(monkeypatch):
    class Verifier:
        def verify(self, token):
            if token not in {"alice", "bob"}:
                raise ValueError("Invalid mock signature")
            return Principal("user:" + token)

    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        gcp_project="fixture-project",
        guest_session_secret="test-secret-only-not-production-123456",
    )
    app = create_app(settings, identity_verifier=Verifier())
    client = TestClient(app, base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    alice = {"Authorization": "Bearer alice"}
    path, _, created = create_done_job(client, headers=alice)
    bob = {"Authorization": "Bearer bob"}
    assert client.get(f"{path}/export.pdf", headers=bob).status_code == 404
    assert client.post(f"{path}/share", headers=bob).status_code == 404
    assert client.delete(f"{path}/share", headers=bob).status_code == 404
    assert (
        client.delete(f"{path}/share", headers=alice | {"X-Requested-With": ""}).status_code == 403
    )
    before = client.get("/v1/session/usage", headers=alice).json()["daily_actions"]["used"]
    token = client.post(f"{path}/share", headers=alice).json()["share_token"]
    public = TestClient(app, base_url="https://testserver")
    for _ in range(3):
        response = public.get(f"/v1/shared/{token}")
        assert response.status_code == 200
    assert "user:alice" not in response.text
    after = client.get("/v1/session/usage", headers=alice).json()["daily_actions"]["used"]
    assert after == before
    assert client.delete(f"{path}/share", headers=alice).status_code == 204
    assert public.get(f"/v1/shared/{token}").status_code == 404


def test_printable_report_uses_plain_words_and_indian_rupees():
    from bharat_sourcer.export import inr

    assert inr("12.00") == "₹12.00"
    assert inr("123456.5") == "₹1,23,456.50"
    assert inr("1234567") == "₹12,34,567.00"
    item = BomItem(line_id="L01", raw_name="LDR", qty=2, user_has_it=True)
    job = Job(
        job_id="00000000-0000-0000-0000-000000000001",
        status="done",
        demo=False,
        input=CreateJob(url="https://www.youtube.com/watch?v=abc"),
        items=[item],
        report=Report(
            demo=False,
            summary="Synthetic.",
            lines=[ReportLine(item=item, sourcing_status="already_owned")],
        ),
    )
    html = to_html(redact(job))
    assert "Source: <a" in html and ">YouTube video</a>" in html
    assert "You have it" in html and "already_owned" not in html
    assert "Already have" in html and "Order plan ready" in html


@needs_pdf
def test_pdf_downloads_for_owner_and_share_link(client):
    path, headers, _ = create_done_job(client)
    response = client.get(f"{path}/export.pdf", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert ".pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    token = client.post(f"{path}/share", headers=headers).json()["share_token"]
    shared = client.get(f"/v1/shared/{token}/export.pdf")
    assert shared.status_code == 200 and shared.content.startswith(b"%PDF")
    assert shared.headers["referrer-policy"] == "no-referrer"


def test_pdf_unavailable_is_a_clear_503(client, monkeypatch):
    def missing(view):
        raise PdfUnavailable("no pango")

    monkeypatch.setattr(sharing, "to_pdf", missing)
    path, headers, _ = create_done_job(client)
    response = client.get(f"{path}/export.pdf", headers=headers)
    assert response.status_code == 503 and response.json()["error"]["code"] == "PDF_UNAVAILABLE"
