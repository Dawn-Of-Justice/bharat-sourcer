from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest

from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import BomItem, ConfirmJob, CreateJob, now
from bharat_sourcer.storage import FirestoreJobStore, MemoryJobStore, StoredJob


def test_new_service_can_read_and_confirm_existing_job():
    store = MemoryJobStore()
    first = JobService(store=store)
    job, token = first.create(CreateJob(url="https://example.com"))
    first.extract(job.job_id)
    second = JobService(store=store)
    assert second.get(job.job_id, token).status == "awaiting_confirmation"
    second.confirm(job.job_id, token, ConfirmJob())
    second.finish(job.job_id)
    assert first.get(job.job_id, token).status == "done"
    assert token not in store.get(job.job_id).model_dump_json()


def test_job_reads_never_alias_stored_state():
    # JobService.get relies on store.get returning a private copy instead of copying again.
    store = MemoryJobStore()
    service = JobService(store=store)
    job, token = service.create(CreateJob(url="https://example.com"))
    service.extract(job.job_id)
    read = service.get(job.job_id, token)
    read.items.clear()
    read.status = "failed"
    again = service.get(job.job_id, token)
    assert again.status == "awaiting_confirmation"
    assert again.items


def test_transaction_rollback():
    store = MemoryJobStore()
    service = JobService(store=store)
    job, token = service.create(CreateJob(url="https://example.com"))

    def failing(record):
        record.job.status = "done"
        raise ValueError("rollback")

    with pytest.raises(ValueError):
        store.mutate(job.job_id, failing)
    assert service.get(job.job_id, token).status == "queued"


def test_recovery_resumes_queued_and_confirmed_jobs():
    store = MemoryJobStore()
    first = JobService(store=store)
    job, token = first.create(CreateJob(url="https://example.com"))
    recovered = JobService(store=store)
    recovered.recover()
    assert recovered.get(job.job_id, token).status == "awaiting_confirmation"
    recovered.confirm(job.job_id, token, ConfirmJob())
    JobService(store=store).recover()
    assert recovered.get(job.job_id, token).report is not None
    count = len(recovered.get(job.job_id, token).events)
    recovered.recover()
    assert len(recovered.get(job.job_id, token).events) == count


def test_two_services_confirm_atomically():
    store = MemoryJobStore()
    services = [JobService(store=store), JobService(store=store)]
    job, token = services[0].create(CreateJob(url="https://example.com"))
    services[0].extract(job.job_id)

    def confirm(service):
        try:
            service.confirm(job.job_id, token, ConfirmJob())
            return 202
        except JobError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirm, services)) == [202, 409]


def test_expired_extraction_is_failed_and_late_result_cannot_overwrite():
    started, release = Event(), Event()

    class SlowExtractor:
        calls = 0

        def extract(self, url):
            self.calls += 1
            started.set()
            assert release.wait(5)
            return [BomItem(line_id="L01", raw_name="Board")]

    provider = SlowExtractor()
    store = MemoryJobStore()
    first = JobService(provider, store=store)
    second = JobService(provider, store=store)
    job, token = first.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(first.extract, job.job_id)
        try:
            assert started.wait(5)
            second.extract(job.job_id)
            second.recover()
            assert second.get(job.job_id, token).status == "extracting"

            def expire(record: StoredJob):
                record.job.recovery_attempts = 1
                record.lease_until = now() - timedelta(seconds=1)

            store.mutate(job.job_id, expire)
            second.recover()
            assert second.get(job.job_id, token).error.code == "EXTRACTION_INTERRUPTED"
        finally:
            release.set()
        running.result(timeout=5)
    assert second.get(job.job_id, token).status == "failed"
    assert second.get(job.job_id, token).items == []
    assert provider.calls == 1


def test_demo_worker_does_not_claim_live_job():
    class Provider:
        def extract(self, url):
            return []

    store = MemoryJobStore()
    job, token = JobService(Provider(), store=store).create(
        CreateJob(url="https://youtu.be/abcdefghijk")
    )
    demo = JobService(store=store)
    demo.recover()
    assert demo.get(job.job_id, token).status == "queued"


def test_requeued_extraction_rejects_old_worker_and_recovers():
    started, release = Event(), Event()

    class Provider:
        calls = 0

        def extract(self, url):
            self.calls += 1
            if self.calls == 1:
                started.set()
                assert release.wait(5)
                return [BomItem(line_id="L01", raw_name="Old result")]
            return [BomItem(line_id="L01", raw_name="Recovered result")]

    provider = Provider()
    store = MemoryJobStore()
    first = JobService(provider, store=store)
    second = JobService(provider, store=store)
    job, token = first.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(first.extract, job.job_id)
        try:
            assert started.wait(5)

            def expire(record):
                record.lease_until = now() - timedelta(seconds=1)

            store.mutate(job.job_id, expire)
            second.recover()
            assert second.get(job.job_id, token).status == "queued"
            second.recover()
        finally:
            release.set()
        running.result(timeout=5)
    result = second.get(job.job_id, token)
    assert result.status == "awaiting_confirmation"
    assert result.items[0].raw_name == "Recovered result"
    assert result.recovery_attempts == 1
    assert provider.calls == 2


class UsageRef:
    def __init__(self, key):
        self.id = key

    def get(self, **kwargs):
        raise AssertionError("usage counters are read in one batch, not one by one")


class UsageSnapshot:
    def __init__(self, key, data):
        self.id, self.data = key, data

    def to_dict(self):
        return self.data


class UsageTransaction:
    def __init__(self, counts):
        self.counts, self.batches, self.writes = counts, [], {}

    def get_all(self, refs):
        self.batches.append([ref.id for ref in refs])
        # Firestore may answer in any order; a missing counter has no data.
        for ref in reversed(refs):
            count = self.counts.get(ref.id)
            yield UsageSnapshot(ref.id, None if count is None else {"count": count})

    def set(self, ref, data):
        self.writes[ref.id] = data["count"]


def usage_store(monkeypatch, counts):
    import google.cloud.firestore

    monkeypatch.setattr(google.cloud.firestore, "transactional", lambda apply: apply)
    transaction = UsageTransaction(counts)
    store = FirestoreJobStore.__new__(FirestoreJobStore)
    store.usage = type("Usage", (), {"document": staticmethod(UsageRef)})()
    store.client = type("Client", (), {"transaction": staticmethod(lambda: transaction)})()
    return store, transaction


def test_firestore_usage_charge_reads_every_counter_in_one_batch(monkeypatch):
    store, transaction = usage_store(monkeypatch, {"day": 2, "burst": 4})
    assert store.consume({"day": 5, "burst": 5, "global": 100}) is True
    assert transaction.batches == [["day", "burst", "global"]]
    assert transaction.writes == {"day": 3, "burst": 5, "global": 1}


def test_firestore_usage_charge_at_a_cap_writes_nothing(monkeypatch):
    store, transaction = usage_store(monkeypatch, {"day": 2, "burst": 5})
    assert store.consume({"day": 5, "burst": 5}) is False
    assert len(transaction.batches) == 1
    assert transaction.writes == {}
