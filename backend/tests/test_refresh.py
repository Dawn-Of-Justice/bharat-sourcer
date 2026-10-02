from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    ErrorDetail,
    RefreshOffers,
    ReportLine,
    now,
)
from bharat_sourcer.storage import MemoryJobStore


class Extractor:
    calls = 0

    def extract(self, url):
        self.calls += 1
        return [BomItem(line_id=f"L0{i}", raw_name="Synthetic part") for i in [1, 2, 3]]


class Source:
    def __init__(self):
        self.calls = []

    def source(self, item):
        self.calls.append(item.line_id)
        return ReportLine(item=item, sourcing_status="no_verified_offers")


def setup():
    extractor, source, store = Extractor(), Source(), MemoryJobStore()
    service = JobService(extractor, store=store, sourcing=source)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    return service, extractor, source, job.job_id, token


def test_refresh_clears_target_selection_and_preserves_other_lines():
    service, extractor, source, job_id, token = setup()

    def selected(record):
        for line in record.job.report.lines:
            line.selected_offer_url = HttpUrl("https://seller.example/old")
            line.price_inr = "12.00"
            line.grade = "A"

    service.store.mutate(job_id, selected)
    before = service.get(job_id, token)
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L02"]))
    pending = service.get(job_id, token)
    assert pending.report.lines[1].selected_offer_url is None
    assert pending.report.parts_subtotal_inr is None
    assert pending.report.selected_parts_subtotal_inr == "24.00"
    assert pending.report.unselected_line_ids == ["L02"]
    assert pending.items == before.items
    service.finish(job_id)
    result = service.get(job_id, token)
    assert [line.item.line_id for line in result.report.lines] == ["L01", "L02", "L03"]
    assert result.report.lines[0].selected_offer_url is not None
    assert result.report.lines[1].selected_offer_url is None
    assert source.calls == ["L01", "L02", "L03", "L02"]
    assert extractor.calls == 1
    assert result.refresh_count == 1


@pytest.mark.parametrize("line_ids", [["bad"], ["L01", "L01"]])
def test_invalid_refresh_rolls_back(line_ids):
    service, _, _, job_id, token = setup()
    before = service.get(job_id, token)
    with pytest.raises(JobError) as error:
        service.refresh_offers(job_id, token, RefreshOffers(line_ids=line_ids))
    assert error.value.code == "INVALID_REFRESH"
    assert service.get(job_id, token) == before


def test_refresh_api_token_and_limit():
    service, _, source, job_id, token = setup()
    app = create_app(Settings(_env_file=None))
    # Route closures use the original service; share the test store and sourcing adapter.
    app.state.job_service.store = service.store
    app.state.job_service.sourcing = source
    client = TestClient(app)
    path = f"/v1/jobs/{job_id}/refresh"
    body = {"line_ids": ["L01"]}
    assert client.post(path, json=body).status_code == 404
    for _ in range(2):
        assert client.post(path, json=body, headers={"X-Job-Token": token}).status_code == 202
    response = client.post(path, json=body, headers={"X-Job-Token": token})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REFRESH_LIMIT"
    assert source.calls.count("L01") == 3


def test_concurrent_refresh_claims_once():
    service, _, _, job_id, token = setup()

    def submit(_):
        try:
            service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
            return 202
        except JobError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [202, 409]
    assert service.get(job_id, token).refresh_count == 1


def test_interrupted_refresh_resumes_only_requested_unfinished_lines():
    service, extractor, source, job_id, token = setup()
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01", "L03"]))

    def interrupted(record):
        record.job.status = "sourcing"
        record.run_id = "expired"
        record.lease_until = now() - timedelta(seconds=1)
        record.job.report.lines[0] = source.source(record.job.items[0])

    service.store.mutate(job_id, interrupted)
    restarted = JobService(extractor, store=service.store, sourcing=source)
    restarted.recover()
    restarted.recover()
    result = restarted.get(job_id, token)
    assert result.status == "done"
    assert source.calls == ["L01", "L02", "L03", "L01", "L03"]
    assert result.refresh_count == 1
    assert result.recovery_attempts == 1


def test_refresh_partial_failed_report_does_not_run_unrequested_lines():
    service, _, source, job_id, token = setup()

    def failed(record):
        record.job.status = "failed"
        record.job.error = ErrorDetail(code="SOURCING_INTERRUPTED", message="Test interruption")
        record.job.report.lines = record.job.report.lines[:1]

    service.store.mutate(job_id, failed)
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L02"]))
    service.finish(job_id)
    report = service.get(job_id, token).report
    assert source.calls == ["L01", "L02", "L03", "L02"]
    assert report.lines[2].sourcing_error.code == "SOURCING_INTERRUPTED"
    assert report.parts_subtotal_inr is None
