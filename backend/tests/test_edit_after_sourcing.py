"""Editing the parts list after sellers were found searches only new or changed parts.

Every part and seller result here is SYNTHETIC test data; no network call runs.
"""

import pytest
from pydantic import HttpUrl

from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import (
    AddLine,
    BomItem,
    ConfirmJob,
    CreateJob,
    HaveLine,
    RemoveLine,
    ReportLine,
    UpdateLine,
)


class Extractor:
    def extract(self, url):
        names = ["ESP32 board", "BME280 sensor", "OLED display"]
        return [BomItem(line_id=f"L0{i}", raw_name=name) for i, name in enumerate(names, 1)]


class Source:
    def __init__(self):
        self.calls = []

    def source(self, item):
        self.calls.append(item.line_id)
        return ReportLine(item=item, sourcing_status="no_verified_offers")


def finished():
    source = Source()
    service = JobService(Extractor(), sourcing=source)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)

    def picked(record):
        for line in record.job.report.lines:
            line.selected_offer_url = HttpUrl(f"https://seller.example/{line.item.line_id}")

    service.store.mutate(job.job_id, picked)
    source.calls.clear()
    return service, source, job.job_id, token


def test_adding_a_part_searches_only_that_part():
    service, source, job_id, token = finished()
    edits = ConfirmJob(edits=[AddLine(op="add", raw_name="TP4056 charger", qty=2)])
    service.confirm(job_id, token, edits)
    assert service.get(job_id, token).status == "resolving"
    service.finish(job_id)
    job = service.get(job_id, token)
    assert job.status == "done"
    assert source.calls == ["L04"]
    assert [line.item.line_id for line in job.report.lines] == ["L01", "L02", "L03", "L04"]
    # Earlier picks survive.
    assert str(job.report.lines[0].selected_offer_url) == "https://seller.example/L01"


def test_renamed_and_unowned_parts_are_searched_again_and_removals_drop():
    service, source, job_id, token = finished()
    service.confirm(
        job_id,
        token,
        ConfirmJob(
            edits=[
                UpdateLine(op="update", line_id="L02", raw_name="BMP280 sensor"),
                UpdateLine(op="update", line_id="L01", qty=3),
                RemoveLine(op="remove", line_id="L03"),
            ]
        ),
    )
    service.finish(job_id)
    job = service.get(job_id, token)
    assert source.calls == ["L02"]
    assert [line.item.line_id for line in job.report.lines] == ["L01", "L02"]
    # A quantity change keeps the seller results and updates the line.
    assert job.report.lines[0].item.qty == 3
    assert str(job.report.lines[0].selected_offer_url) == "https://seller.example/L01"


def test_no_new_parts_saves_without_searching():
    service, source, job_id, token = finished()
    service.confirm(
        job_id, token, ConfirmJob(edits=[HaveLine(op="have_it", line_id="L03", user_has_it=True)])
    )
    job = service.get(job_id, token)
    assert job.status == "done"
    assert job.report.lines[2].sourcing_status == "already_owned"
    service.finish(job_id)
    assert source.calls == []


def test_edits_wait_while_sellers_are_searched():
    service, _, job_id, token = finished()
    service.confirm(job_id, token, ConfirmJob(edits=[AddLine(op="add", raw_name="Slide switch")]))
    with pytest.raises(JobError) as error:
        service.confirm(job_id, token, ConfirmJob())
    assert error.value.code == "INVALID_STATE"
