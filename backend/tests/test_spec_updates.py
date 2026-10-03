"""Synthetic offers exercise required-spec edits without network access."""

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.compat import assess, resolve_part
from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Evidence,
    PartSpecs,
    ReportLine,
    SelectOffers,
    VerifiedOffer,
)


def setup():
    app = create_app(Settings(_env_file=None))
    service = app.state.job_service
    complete = PartSpecs(
        family="pro_micro",
        controller="atmega32u4",
        logic_v=5.0,
        clock_mhz=16,
        pinout="test_mapping",
    )

    class Extractor:
        def extract(self, url):
            return [
                BomItem(
                    line_id=f"L0{i}",
                    raw_name="Pro Micro board",
                    specs=complete if i == 2 else PartSpecs(),
                    evidence=[Evidence(timestamp="00:01", observation="Test fixture")],
                )
                for i in [1, 2]
            ]

    class Source:
        def source(self, item):
            resolution = resolve_part(item)
            compatibility = assess(resolution.specs, complete)
            return ReportLine(
                item=item,
                sourcing_status="offers_found",
                resolution=resolution,
                offers=[
                    VerifiedOffer(
                        url="https://seller.example/board",
                        seller="seller.example",
                        title="Synthetic Pro Micro",
                        price_inr="10.00",
                        stock="in_stock",
                        specs=complete,
                        compatibility=compatibility,
                        compatibility_status=compatibility.status,
                    )
                ],
            )

    service.extractor = Extractor()
    service.sourcing = Source()
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    service.select_offers(
        job.job_id,
        token,
        SelectOffers.model_validate(
            {"selections": [{"line_id": "L02", "offer_url": "https://seller.example/board"}]}
        ),
    )
    return TestClient(app), service, job.job_id, token, complete


def test_answer_required_specs_reassesses_and_preserves_evidence():
    client, service, job_id, token, complete = setup()
    before = service.get(job_id, token)
    assert before.report.lines[0].offers[0].compatibility.grade is None
    response = client.post(
        f"/v1/jobs/{job_id}/specs",
        headers={"X-Job-Token": token},
        json={"updates": [{"line_id": "L01", "specs": complete.model_dump(exclude_none=True)}]},
    )
    assert response.status_code == 200
    result = service.get(job_id, token)
    assert result.report.lines[0].offers[0].compatibility.grade == "A"
    assert result.items[0].clarifications == []
    assert result.items[0].evidence == before.items[0].evidence
    assert (
        result.report.lines[0].offers[0].checked_at == before.report.lines[0].offers[0].checked_at
    )
    assert result.report.lines[0].offers[0].specs == before.report.lines[0].offers[0].specs
    assert result.report.lines[1] == before.report.lines[1]
    assert result.report.selected_parts_subtotal_inr == "10.00"
    assert result.report.parts_subtotal_inr is None
    assert all(e.source == "user" for e in result.report.lines[0].resolution.evidence)
    assert result.refresh_count == result.recovery_attempts == 0


def test_changed_specs_clear_selection_replay_is_noop_and_null_clears():
    client, service, job_id, token, _ = setup()
    path, headers = f"/v1/jobs/{job_id}/specs", {"X-Job-Token": token}
    body = {"updates": [{"line_id": "L02", "specs": {"pinout": "different_mapping"}}]}
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 200
    first = service.get(job_id, token)
    line = first.report.lines[1]
    assert line.offers[0].compatibility.grade == "X"
    assert line.selected_offer_url is line.price_inr is line.grade is None
    assert first.report.selected_parts_subtotal_inr == "0.00"
    assert client.post(path, headers=headers, json=body).status_code == 200
    assert service.get(job_id, token) == first
    response = client.post(
        path, headers=headers, json={"updates": [{"line_id": "L02", "specs": {"pinout": None}}]}
    )
    assert response.json()["report"]["lines"][1]["offers"][0]["compatibility"]["grade"] is None
    assert service.get(job_id, token).items[1].specs.logic_v == 5.0


@pytest.mark.parametrize(
    "second",
    [
        {"line_id": "missing", "specs": {"logic_v": 3.3}},
        {"line_id": "L01", "specs": {"logic_v": 3.3}},
        {"line_id": "L02", "specs": {"logic_v": 3.3}},
    ],
)
def test_batch_rollback_for_invalid_line_duplicate_or_merged_specs(second):
    client, service, job_id, token, _ = setup()
    before = service.get(job_id, token)
    response = client.post(
        f"/v1/jobs/{job_id}/specs",
        headers={"X-Job-Token": token},
        json={"updates": [{"line_id": "L01", "specs": {"pinout": "new"}}, second]},
    )
    assert response.status_code == 422
    assert service.get(job_id, token) == before


def test_token_state_and_empty_specs_validation():
    client, service, job_id, token, _ = setup()
    path = f"/v1/jobs/{job_id}/specs"
    body = {"updates": [{"line_id": "L01", "specs": {"logic_v": 5.0}}]}
    assert client.post(path, json=body).status_code == 404
    assert (
        client.post(
            path,
            headers={"X-Job-Token": token},
            json={"updates": [{"line_id": "L01", "specs": {}}]},
        ).status_code
        == 422
    )

    def active(record):
        record.job.status = "sourcing"

    service.store.mutate(job_id, active)
    assert client.post(path, headers={"X-Job-Token": token}, json=body).status_code == 409


def test_missing_seller_specs_stay_unknown_after_user_answers():
    client, service, job_id, token, complete = setup()

    def incomplete(record):
        record.job.report.lines[0].offers[0].specs = PartSpecs(family="pro_micro")

    service.store.mutate(job_id, incomplete)
    response = client.post(
        f"/v1/jobs/{job_id}/specs",
        headers={"X-Job-Token": token},
        json={"updates": [{"line_id": "L01", "specs": complete.model_dump(exclude_none=True)}]},
    )
    offer = response.json()["report"]["lines"][0]["offers"][0]
    assert offer["compatibility"]["grade"] is None
    assert "offered.logic_v" in offer["compatibility"]["missing_fields"]
