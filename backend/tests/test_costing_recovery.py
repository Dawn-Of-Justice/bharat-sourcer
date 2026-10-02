from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.resilience import post_with_retry
from bharat_sourcer.schemas import (
    BomItem,
    Compatibility,
    ConfirmJob,
    CreateJob,
    Report,
    ReportLine,
    VerifiedOffer,
    now,
)
from bharat_sourcer.storage import MemoryJobStore

URL = "https://seller.example/part"


def client_report(grade="A", stock="in_stock", age=0):
    app = create_app(Settings(_env_file=None, demo_mode=True))
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://example.com"))
    offer = VerifiedOffer(
        url=URL,
        seller="seller.example",
        title="Synthetic test part",
        price_inr="0.10",
        stock=stock,
        checked_at=now() - timedelta(hours=age),
        compatibility=Compatibility(status="compatible", grade=grade),
    )

    def seed(record):
        record.job.demo = False
        record.job.status = "done"
        record.job.report = Report(
            demo=False,
            summary="Synthetic test report",
            lines=[
                ReportLine(
                    item=BomItem(line_id="L01", raw_name="Test part", qty=3),
                    sourcing_status="offers_found",
                    offers=[offer],
                ),
                ReportLine(
                    item=BomItem(line_id="L02", raw_name="Owned", user_has_it=True),
                    sourcing_status="already_owned",
                ),
            ],
        )

    service.store.mutate(job.job_id, seed)
    return TestClient(app), service, job.job_id, {"X-Job-Token": token}


def test_selection_decimal_totals_clear_and_token():
    client, service, job_id, headers = client_report()
    path = f"/v1/jobs/{job_id}/selections"
    body = {"selections": [{"line_id": "L01", "offer_url": URL}]}
    assert client.post(path, json=body).status_code == 404
    for _ in range(2):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200
        report = response.json()["report"]
        assert report["parts_subtotal_inr"] == "0.30"
        assert report["selected_parts_subtotal_inr"] == "0.30"
        assert report["total_inr"] is report["shipping_inr"] is report["tax_inr"] is None
        assert report["lines"][0]["price_inr"] == "0.10"
        assert report["lines"][1]["subtotal_inr"] == "0.00"
    result = client.post(path, json={"selections": [{"line_id": "L01"}]}, headers=headers)
    assert result.json()["report"]["parts_subtotal_inr"] is None
    assert result.json()["report"]["unselected_line_ids"] == ["L01"]


@pytest.mark.parametrize(
    "options,code",
    [
        ({"grade": None}, "COMPATIBILITY_UNRESOLVED"),
        ({"grade": "X"}, "COMPATIBILITY_UNRESOLVED"),
        ({"grade": "B"}, "CHANGES_REQUIRED"),
        ({"stock": "unknown"}, "OFFER_UNAVAILABLE"),
        ({"age": 25}, "OFFER_STALE"),
    ],
)
def test_selection_rejects_unusable_offer(options, code):
    client, _, job_id, headers = client_report(**options)
    response = client.post(
        f"/v1/jobs/{job_id}/selections",
        headers=headers,
        json={"selections": [{"line_id": "L01", "offer_url": URL}]},
    )
    assert response.json()["error"]["code"] == code


def test_selection_changes_and_atomic_rollback():
    client, service, job_id, headers = client_report(grade="B")
    selection = {"line_id": "L01", "offer_url": URL, "accept_changes": True}
    path = f"/v1/jobs/{job_id}/selections"
    response = client.post(
        path, headers=headers, json={"selections": [selection, {"line_id": "missing"}]}
    )
    assert response.status_code == 422
    assert service.store.get(job_id).job.report.lines[0].selected_offer_url is None
    response = client.post(path, headers=headers, json={"selections": [selection]})
    assert response.json()["report"]["lines"][0]["changes_accepted"] is True


@pytest.mark.parametrize("codes,count", [([503, 200], 2), ([429, 429, 429], 3), ([401], 1)])
def test_bounded_http_retries(codes, count):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(codes[len(calls) - 1])

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with patch("bharat_sourcer.resilience.time.sleep"):
            response = post_with_retry(client, URL, json={})
    assert len(calls) == count
    assert response.status_code == codes[-1]


def test_retry_after_budget_and_network_failure():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, headers={"Retry-After": "120"})
            )
        ) as client,
        patch("bharat_sourcer.resilience.time.sleep") as sleep,
    ):
        assert post_with_retry(client, URL).status_code == 429
        sleep.assert_not_called()
    with (
        httpx.Client() as client,
        patch.object(client, "post", side_effect=httpx.ConnectError("test")) as post,
        patch("bharat_sourcer.resilience.time.sleep"),
    ):
        with pytest.raises(httpx.ConnectError):
            post_with_retry(client, URL)
        assert post.call_count == 3


def test_recovery_resumes_checkpoint_without_repeating_completed_search():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id=f"L0{i}", raw_name="Test") for i in [1, 2]]

    class Source:
        calls = []

        def source(self, item):
            self.calls.append(item.line_id)
            return ReportLine(item=item, sourcing_status="no_verified_offers")

    source = Source()
    store = MemoryJobStore()
    first = JobService(Extractor(), store=store, sourcing=source)
    job, token = first.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    first.extract(job.job_id)
    first.confirm(job.job_id, token, ConfirmJob())

    def interrupt(record):
        record.job.status = "sourcing"
        record.run_id = "abandoned"
        record.lease_until = now() - timedelta(seconds=1)
        record.job.report = Report(
            demo=False,
            summary="Partial",
            lines=[ReportLine(item=record.job.items[0], sourcing_status="no_verified_offers")],
        )

    store.mutate(job.job_id, interrupt)
    restarted = JobService(Extractor(), store=store, sourcing=source)
    restarted.recover()
    assert restarted.get(job.job_id, token).status == "resolving"
    restarted.recover()
    result = restarted.get(job.job_id, token)
    assert result.status == "done"
    assert result.recovery_attempts == 1
    assert source.calls == ["L02"]
    assert len(result.report.lines) == 2


def test_extraction_recovery_budget_survives_restart():
    store = MemoryJobStore()
    service = JobService(store=store)
    job, token = service.create(CreateJob(url="https://example.com"))

    def interrupt(record):
        record.job.status = "extracting"
        record.lease_until = now() - timedelta(seconds=1)

    store.mutate(job.job_id, interrupt)
    service.recover()
    assert service.get(job.job_id, token).status == "queued"
    store.mutate(job.job_id, interrupt)
    JobService(store=store).recover()
    assert service.get(job.job_id, token).error.code == "EXTRACTION_INTERRUPTED"
