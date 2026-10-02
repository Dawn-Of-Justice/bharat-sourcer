"""Run against a local emulator only; never implicitly touch a cloud project."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import ConfirmJob, CreateJob
from bharat_sourcer.storage import FirestoreJobStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="Firestore emulator not running"
)


def test_firestore_persists_and_serializes_confirmation():
    collection = "test_jobs_" + uuid4().hex
    store = FirestoreJobStore("demo-bharat-sourcer", collection=collection)
    other = FirestoreJobStore("demo-bharat-sourcer", collection=collection)
    first, second = JobService(store=store), JobService(store=other)
    job, token = first.create(CreateJob(url="https://example.com"))
    try:
        second.recover()
        assert first.get(job.job_id, token).status == "awaiting_confirmation"

        def confirm(service):
            try:
                service.confirm(job.job_id, token, ConfirmJob())
                return 202
            except JobError as exc:
                return exc.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(confirm, [first, second])) == [202, 409]
        second.recover()
        assert first.get(job.job_id, token).status == "done"
        assert token not in store.get(job.job_id).model_dump_json()
    finally:
        store.collection.document(job.job_id).delete()
