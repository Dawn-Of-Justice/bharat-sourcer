"""Synthetic large-report regressions; no seller claims or network calls."""

import base64
import zlib

import pytest

from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import BomItem, CreateJob, Report, ReportLine, VerifiedOffer
from bharat_sourcer.storage import (
    FirestoreJobStore,
    StorageError,
    check_size,
    parse_document,
    storage_document,
)


def large_record():
    service = JobService()
    job, _ = service.create(CreateJob(url="https://example.com"))
    record = service.store.get(job.job_id)
    record.job.report = Report(
        demo=True,
        summary="Synthetic storage fixture",
        lines=[
            ReportLine(
                item=BomItem(line_id=f"L{i:02}", raw_name=f"Synthetic component {i}"),
                sourcing_status="offers_found",
                offers=[
                    VerifiedOffer(
                        url=f"https://seller.example/{i}/{n}",
                        seller="Synthetic fixture",
                        title="Synthetic offer description " * 8,
                        price_inr="1.00",
                    )
                    for n in range(20)
                ],
                selected_offer_url=f"https://seller.example/{i}/0",
                selection_source="user",
            )
            for i in range(1, 38)
        ],
    )
    return record


def test_large_report_lossless_roundtrip_preserves_all_quotes_and_query_fields():
    record = large_record()
    assert len(record.model_dump_json().encode()) > 800_000
    check_size(record)
    document = storage_document(record)
    assert "report_zlib_b64" in document
    assert document["job"]["status"] == record.job.status
    assert document["owner_id"] == record.owner_id
    assert parse_document(document) == record
    # Decoding must not mutate a snapshot shared by a caller.
    assert document["job"]["report"] is None
    store = FirestoreJobStore.__new__(FirestoreJobStore)
    assert parse_document(store._document(record)) == record


def test_legacy_document_still_reads_and_compression_is_removed_when_report_shrinks():
    record = large_record()
    assert parse_document(record.model_dump(mode="json")) == record
    record.job.report.lines = record.job.report.lines[:1]
    document = storage_document(record)
    assert "report_zlib_b64" not in document
    assert parse_document(document) == record


@pytest.mark.parametrize(
    "payload", ["invalid!", base64.b64encode(zlib.compress(b"x")[:-1]).decode()]
)
def test_corrupt_compressed_report_fails_closed(payload):
    record = large_record()
    document = storage_document(record)
    document["report_zlib_b64"] = payload
    with pytest.raises(StorageError):
        parse_document(document)


def test_expanded_report_limit_is_enforced(monkeypatch):
    from bharat_sourcer import storage

    record = large_record()
    document = storage_document(record)
    monkeypatch.setattr(storage, "MAX_REPORT_BYTES", 100)
    with pytest.raises(StorageError):
        parse_document(document)
    with pytest.raises(StorageError):
        check_size(record)
