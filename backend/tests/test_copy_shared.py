"""Copying a shared project into your own projects. Identities and offers are synthetic."""

from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.identity import Principal
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ChatMessage,
    Compatibility,
    CostEstimate,
    Report,
    ReportLine,
    VerifiedOffer,
)
from bharat_sourcer.sharing import token_hash

SECRET = "s" * 32
BOARD_URL = "https://seller.example/pro-micro"


class Verifier:
    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise ValueError("Invalid mock signature")
        return Principal("user:" + token)


def setup(**overrides):
    settings = Settings(
        _env_file=None,
        **{
            "auth_enabled": True,
            "gcp_project": "fixture-project",
            "guest_session_secret": "test-secret-only-not-production-123456",
        }
        | overrides,
    )
    app = create_app(settings, identity_verifier=Verifier())
    client = TestClient(app, base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    return client, app


def auth(user):
    return {"Authorization": "Bearer " + user}


def report():
    offer = VerifiedOffer(
        url=BOARD_URL,
        seller="seller.example",
        title="Pro Micro 5V",
        price_inr="250.00",
        stock="in_stock",
        compatibility=Compatibility(status="compatible", grade="A"),
    )
    board = BomItem(line_id="L01", raw_name="Pro Micro", qty=1)
    owned = BomItem(line_id="L02", raw_name="USB cable", qty=1, user_has_it=True)
    return Report(
        demo=False,
        summary="Synthetic report.",
        lines=[
            ReportLine(
                item=board,
                sourcing_status="offers_found",
                offers=[offer],
                selected_offer_url=BOARD_URL,
                price_inr="250.00",
                grade="A",
                selection_source="user",
                user_offer_url=BOARD_URL,
            ),
            ReportLine(item=owned, sourcing_status="already_owned"),
        ],
    ), [board, owned]


def shared_project(client, app, status="done"):
    """Alice's project, rewritten to a synthetic live report and shared."""
    created = client.post("/v1/jobs", json={"url": "https://example.com"}, headers=auth("alice"))
    key = created.json()["job_id"]
    lines, items = report()

    def change(record):
        record.job.status = status
        record.job.demo = False
        record.job.items = items
        record.job.report = lines if status == "done" else None
        record.job.messages = [ChatMessage(message_id="m1", role="user", text="private note")]
        record.job.cost_estimate = CostEstimate(total_usd=0.1, run_usd=0.1, budget_usd=0.25)
        record.share_token_hash = token_hash(f"{key}.{SECRET}")

    app.state.job_service.store.mutate(key, change)
    return key, f"{key}.{SECRET}"


def test_copy_creates_an_owned_project_without_private_data():
    client, app = setup()
    source_id, token = shared_project(client, app)
    response = client.post(f"/v1/shared/{token}/copy", headers=auth("bob"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "done" and body["job_id"] != source_id

    copy = client.get(f"/v1/jobs/{body['job_id']}", headers=auth("bob")).json()
    assert copy["copied_from"]["copied_at"] and copy["copied_from"]["source_updated_at"]
    assert copy["messages"] == [] and copy["cost_estimate"] is None
    assert [event["message"] for event in copy["events"]] == [
        "Copied from a shared project. Seller prices are from the shared snapshot; "
        "refresh to update them."
    ]
    board, cable = copy["report"]["lines"]
    # The sharer's pick is kept and labelled as copied.
    assert board["selected_offer_url"] == BOARD_URL
    assert board["selection_source"] == "user" and board["copied_choice"] is True
    # The sharer owned the cable; the new owner still needs to buy it.
    assert cable["item"]["user_has_it"] is False and cable["sourcing_status"] == "not_run"
    assert not any(item["user_has_it"] for item in copy["items"])
    # The copy belongs to Bob only; the original is untouched and still Alice's.
    projects = client.get("/v1/projects", headers=auth("bob")).json()["projects"]
    assert [p["job_id"] for p in projects] == [body["job_id"]]
    assert client.get(f"/v1/jobs/{body['job_id']}", headers=auth("alice")).status_code == 404
    original = app.state.job_service.store.get(source_id)
    assert original.owner_id == "user:alice" and original.job.messages
    assert original.job.report.lines[1].item.user_has_it is True
    # The copy has no share link of its own.
    assert app.state.job_service.store.get(body["job_id"]).share_token_hash is None


def test_choosing_an_offer_clears_the_copied_label():
    client, app = setup()
    _, token = shared_project(client, app)
    copy_id = client.post(f"/v1/shared/{token}/copy", headers=auth("bob")).json()["job_id"]
    selected = client.post(
        f"/v1/jobs/{copy_id}/selections",
        json={"selections": [{"line_id": "L01", "offer_url": BOARD_URL}]},
        headers=auth("bob"),
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["report"]["lines"][0]["copied_choice"] is False


def test_draft_parts_lists_can_be_copied_but_running_projects_cannot():
    client, app = setup()
    _, draft = shared_project(client, app, status="awaiting_confirmation")
    response = client.post(f"/v1/shared/{draft}/copy", headers=auth("bob"))
    assert response.status_code == 201 and response.json()["status"] == "awaiting_confirmation"
    _, running = shared_project(client, app, status="sourcing")
    response = client.post(f"/v1/shared/{running}/copy", headers=auth("bob"))
    assert response.status_code == 409 and response.json()["error"]["code"] == "SHARE_NOT_READY"


def test_revoked_or_unknown_links_cannot_be_copied():
    client, app = setup()
    source_id, token = shared_project(client, app)
    app.state.job_service.store.mutate(
        source_id, lambda record: setattr(record, "share_token_hash", None)
    )
    assert client.post(f"/v1/shared/{token}/copy", headers=auth("bob")).status_code == 404
    assert client.post("/v1/shared/nope.nope/copy", headers=auth("bob")).status_code == 404


def test_copy_needs_an_identity_and_the_application_header():
    client, app = setup()
    _, token = shared_project(client, app)
    assert client.post(f"/v1/shared/{token}/copy").status_code == 401
    response = client.post(
        f"/v1/shared/{token}/copy", headers=auth("bob") | {"X-Requested-With": ""}
    )
    assert response.status_code == 403


def test_guests_copy_within_their_part_limit():
    client, app = setup(guest_part_limit=1)
    _, token = shared_project(client, app)  # two parts
    assert client.post("/v1/session/guest").status_code == 200
    response = client.post(f"/v1/shared/{token}/copy")
    assert response.status_code == 422 and response.json()["error"]["code"] == "PART_LIMIT"
    client, app = setup(guest_part_limit=3)
    _, token = shared_project(client, app)
    assert client.post("/v1/session/guest").status_code == 200
    assert client.post(f"/v1/shared/{token}/copy").status_code == 201


def test_copy_counts_as_a_new_project():
    client, app = setup()
    _, token = shared_project(client, app)
    # Accounts may create 5 projects a day; Bob has created none, so 5 copies succeed.
    for _ in range(5):
        assert client.post(f"/v1/shared/{token}/copy", headers=auth("bob")).status_code == 201
    response = client.post(f"/v1/shared/{token}/copy", headers=auth("bob"))
    assert response.status_code == 429
