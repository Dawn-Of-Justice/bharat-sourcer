from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import BomItem, ConfirmJob, CreateJob, RefreshOffers, ReportLine, now


class Extractor:
    def extract(self, url):
        return [BomItem(line_id=f"L0{i}", raw_name="Synthetic part") for i in range(1, 4)]


class Source:
    def __init__(self):
        self.calls = []
        self.started = Event()
        self.release = Event()

    def source(self, item):
        self.calls.append(item.line_id)
        self.started.set()
        assert self.release.wait(5)
        return ReportLine(item=item, sourcing_status="no_verified_offers")


def setup():
    source = Source()
    service = JobService(Extractor(), sourcing=source)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    return service, source, job.job_id, token


def test_active_pause_preserves_checkpoint_and_resume_skips_saved_lines():
    service, source, key, token = setup()
    with ThreadPoolExecutor() as pool:
        running = pool.submit(service.finish, key)
        assert source.started.wait(3)
        pending = service.pause(key, token)
        assert pending.status == "sourcing" and pending.pause_requested
        assert service.pause(key, token) == pending
        with pytest.raises(JobError):
            service.resume(key, token)
        source.release.set()
        running.result(timeout=5)
    paused = service.get(key, token)
    assert paused.status == "paused"
    assert [line.item.line_id for line in paused.report.lines] == ["L01"]
    service.recover()
    assert source.calls == ["L01"]
    assert service.resume(key, token).status == "resolving"
    service.resume(key, token)
    with ThreadPoolExecutor() as pool:
        list(pool.map(lambda _: service.finish(key), range(3)))
    assert source.calls == ["L01", "L02", "L03"]
    assert service.get(key, token).status == "done"


def test_pause_before_claim_api_and_authorization():
    service, source, key, token = setup()
    app = create_app(Settings(_env_file=None))
    app.state.job_service.store = service.store
    app.state.job_service.sourcing = source
    client = TestClient(app)
    path = f"/v1/jobs/{key}"
    assert client.post(path + "/pause").status_code == 404
    headers = {"X-Job-Token": token}
    assert client.post(path + "/pause", headers=headers).json()["status"] == "paused"
    service.finish(key)
    service.recover()
    assert source.calls == []
    source.release.set()
    assert client.post(path + "/resume", headers=headers).status_code == 202
    assert service.get(key, token).status == "done"
    assert client.post(path + "/pause", headers=headers).status_code == 409
    assert client.post(path + "/resume", headers=headers).status_code == 409


def test_expired_pausing_worker_is_fenced_and_does_not_auto_resume():
    service, source, key, token = setup()
    with ThreadPoolExecutor() as pool:
        running = pool.submit(service.finish, key)
        assert source.started.wait(3)
        service.pause(key, token)

        def expire(record):
            record.lease_until = now() - timedelta(seconds=1)

        service.store.mutate(key, expire)
        service.recover()
        assert service.get(key, token).status == "paused"
        source.release.set()
        running.result(timeout=5)
    job = service.get(key, token)
    assert job.report.lines == []
    assert job.recovery_attempts == 0
    service.recover()
    assert source.calls == ["L01"]


def test_pause_refresh_last_line_preserves_scope_and_budget():
    service, source, key, token = setup()
    source.release.set()
    service.finish(key)
    service.refresh_offers(key, token, RefreshOffers(line_ids=["L02"]))
    source.started.clear()
    source.release.clear()
    with ThreadPoolExecutor() as pool:
        running = pool.submit(service.finish, key)
        assert source.started.wait(3)
        service.pause(key, token)
        source.release.set()
        running.result(timeout=5)
    assert service.get(key, token).status == "paused"
    service.resume(key, token)
    service.finish(key)
    result = service.get(key, token)
    assert result.status == "done"
    assert result.refresh_count == 1
    assert source.calls == ["L01", "L02", "L03", "L02"]
