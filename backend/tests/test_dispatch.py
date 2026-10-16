from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import ConversationService
from bharat_sourcer.dispatch import CloudDispatcher, Work, work_once
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import BomItem, ConfirmJob, CreateJob, ReportLine, now
from bharat_sourcer.storage import MemoryJobStore


class Extractor:
    def extract(self, url):
        return [BomItem(line_id=f"L0{i}", raw_name="Synthetic") for i in range(1, 4)]


class Source:
    def __init__(self):
        self.calls = []

    def source(self, item):
        self.calls.append(item.line_id)
        return ReportLine(item=item, sourcing_status="no_verified_offers")


def test_each_delivery_saves_one_line_and_duplicates_after_done_do_nothing():
    source = Source()
    jobs = JobService(Extractor(), sourcing=source)
    chat = ConversationService(jobs)
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    work = Work(job_id=job.job_id, kind="workflow")
    assert work_once(jobs, chat, work)
    jobs.confirm(job.job_id, token, ConfirmJob())
    for count in range(1, 4):
        assert not work_once(jobs, chat, work)
        assert len(source.calls) == count
    assert work_once(jobs, chat, work)
    assert work_once(jobs, chat, work)
    assert source.calls == ["L01", "L02", "L03"]


def test_existing_lease_retries_then_expiry_is_recovered():
    jobs = JobService(Extractor())
    chat = ConversationService(jobs)
    job, _ = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))

    def claim(record):
        record.job.status = "extracting"
        record.run_id = "old"
        record.lease_until = now() + timedelta(minutes=5)

    jobs.store.mutate(job.job_id, claim)
    work = Work(job_id=job.job_id, kind="workflow")
    assert not work_once(jobs, chat, work)
    jobs.store.mutate(job.job_id, lambda r: setattr(r, "lease_until", now() - timedelta(seconds=1)))
    assert work_once(jobs, chat, work)
    assert jobs.store.get(job.job_id).job.recovery_attempts == 1


def test_enqueue_outage_retains_job_and_sweep_dispatches(monkeypatch):
    calls = []

    def enqueue(self, key, kind, **kwargs):
        if not kwargs.get("sweep"):
            raise RuntimeError("simulated queue outage")
        calls.append((key, kind))

    monkeypatch.setattr(CloudDispatcher, "enqueue", enqueue)
    monkeypatch.setattr(CloudDispatcher, "authorize", lambda self, header: header == "Bearer test")
    settings = Settings(
        _env_file=None,
        dispatch_backend="cloud_tasks",
        storage_backend="firestore",
        gcp_project="test",
        tasks_url="https://worker.example",
        tasks_service_account="worker@test",
    )
    store = MemoryJobStore()
    app = create_app(settings, store=store)
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": "https://example.com"}).json()
        key = created["job_id"]
        assert store.get(key).job.status == "queued"
        assert client.post("/internal/sweep").status_code == 401
        assert (
            client.post("/internal/work", json={"job_id": key, "kind": "workflow"}).status_code
            == 401
        )
        assert (
            client.post("/internal/sweep", headers={"Authorization": "Bearer test"}).status_code
            == 200
        )
        assert calls == [(key, "workflow")]
        assert (
            client.post(
                "/internal/work",
                headers={"Authorization": "Bearer test"},
                json={"job_id": key, "kind": "workflow"},
            ).status_code
            == 200
        )
        assert store.get(key).job.status == "awaiting_confirmation"


def test_oidc_requires_correct_identity_and_verified_email(monkeypatch):
    settings = Settings(
        _env_file=None, tasks_url="https://worker.example", tasks_service_account="worker@test"
    )
    dispatcher = CloudDispatcher(settings)
    verify = Mock(return_value={"email": "attacker@test", "email_verified": True})
    monkeypatch.setattr("bharat_sourcer.dispatch.id_token.verify_oauth2_token", verify)
    assert not dispatcher.authorize(None)
    assert not dispatcher.authorize("Bearer token")
    verify.return_value = {"email": "worker@test", "email_verified": False}
    assert not dispatcher.authorize("Bearer token")
    verify.return_value["email_verified"] = True
    assert dispatcher.authorize("Bearer token")
    assert verify.call_args.kwargs["audience"] == "https://worker.example"


def test_unknown_work_is_acknowledged():
    jobs = JobService()
    assert work_once(jobs, ConversationService(jobs), Work(job_id=uuid4(), kind="workflow"))


def sweep_app(monkeypatch, enqueue, **overrides):
    monkeypatch.setattr(CloudDispatcher, "enqueue", enqueue)
    monkeypatch.setattr(CloudDispatcher, "authorize", lambda self, header: header == "Bearer test")
    settings = Settings(
        _env_file=None,
        **{
            "dispatch_backend": "cloud_tasks",
            "storage_backend": "firestore",
            "gcp_project": "test",
            "tasks_url": "https://worker.example",
            "tasks_service_account": "worker@test",
        }
        | overrides,
    )
    store = MemoryJobStore()
    jobs = JobService(Extractor(), store=store)
    keys = [jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))[0].job_id for _ in range(3)]
    client = TestClient(create_app(settings, store=store))
    client.headers["Authorization"] = "Bearer test"
    return client, store, keys


def test_sweep_isolates_enqueue_failures_and_reports_counts(monkeypatch, caplog):
    calls = []

    def enqueue(self, key, kind, **kwargs):
        calls.append(key)
        if len(calls) == 1:
            raise RuntimeError("simulated queue outage")

    client, _, keys = sweep_app(monkeypatch, enqueue)
    body = client.post("/internal/sweep").json()
    assert sorted(calls) == sorted(keys)
    assert body.pop("retention")["deleted"] == 0
    assert body == {"status": "ok", "dispatched": 2, "failed": 1, "stale": 0, "truncated": False}
    assert "TASK_ENQUEUE_FAILED" in caplog.text


def test_sweep_is_bounded_and_flags_stale_work(monkeypatch, caplog):
    calls = []
    client, store, keys = sweep_app(
        monkeypatch, lambda self, key, kind, **kwargs: calls.append(key), sweep_limit=2
    )
    for key in keys:
        store.mutate(key, lambda r: setattr(r.job, "updated_at", now() - timedelta(hours=2)))
    body = client.post("/internal/sweep").json()
    assert len(calls) == 2
    assert body["truncated"] is True
    assert body["stale"] == 2
    assert "QUEUE_AGE_EXCEEDED" in caplog.text
    assert "SWEEP_TRUNCATED" in caplog.text
