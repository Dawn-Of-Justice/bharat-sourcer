from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import ConversationService
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ChatReply,
    ConfirmJob,
    CreateJob,
    ProposalDecision,
    ReportLine,
    SendMessage,
)


class Extractor:
    def extract(self, url):
        return [BomItem(line_id="L01", raw_name="Synthetic board")]


class Source:
    def __init__(self):
        self.calls = 0

    def source(self, item):
        self.calls += 1
        return ReportLine(item=item, sourcing_status="no_verified_offers")


class Assistant:
    def reply(self, job):
        return ChatReply(text="Approve a new search for L01?", refresh={"line_ids": ["L01"]})


def setup():
    source = Source()
    jobs = JobService(Extractor(), sourcing=source)
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    jobs.confirm(job.job_id, token, ConfirmJob())
    jobs.finish(job.job_id)
    chat = ConversationService(jobs, Assistant())
    chat.send(job.job_id, token, SendMessage(message_id=uuid4(), text="Search again for L01"))
    chat.process(job.job_id)
    message = jobs.get(job.job_id, token).messages[-1]
    return jobs, chat, source, job.job_id, token, message.message_id


def test_concurrent_acceptance_queues_once_and_recovery_runs_it():
    jobs, chat, source, key, token, message = setup()
    assert source.calls == 1
    assert jobs.get(key, token).refresh_count == 0
    with ThreadPoolExecutor() as pool:
        list(
            pool.map(
                lambda _: chat.decide(key, token, message, ProposalDecision(action="accept")),
                range(4),
            )
        )
    job = jobs.get(key, token)
    assert job.status == "resolving"
    assert job.refresh_count == 1
    assert job.messages[-1].refresh_proposal.refresh_count == 1
    jobs.recover()
    chat.decide(key, token, message, ProposalDecision(action="accept"))
    assert source.calls == 2
    assert jobs.get(key, token).refresh_count == 1


def test_stale_report_reject_and_no_search():
    jobs, chat, source, key, token, message = setup()
    jobs.store.mutate(key, lambda record: setattr(record.job.report, "summary", "Changed report"))
    with pytest.raises(JobError) as error:
        chat.decide(key, token, message, ProposalDecision(action="accept"))
    assert error.value.code == "PROPOSAL_STALE"
    chat.decide(key, token, message, ProposalDecision(action="reject"))
    assert source.calls == 1
    assert jobs.get(key, token).refresh_count == 0


def test_limit_rechecked_atomically():
    jobs, chat, _, key, token, message = setup()
    jobs.sourcing_max_parts = 0
    with pytest.raises(JobError):
        chat.decide(key, token, message, ProposalDecision(action="accept"))
    job = jobs.get(key, token)
    assert job.messages[-1].refresh_proposal.status == "pending"
    assert job.refresh_count == 0


def test_api_accept_schedules_worker_and_requires_token():
    jobs, _, source, key, token, message = setup()
    app = create_app(Settings(_env_file=None))
    service = app.state.job_service
    service.store, service.sourcing = jobs.store, source
    app.state.conversation_service.store = jobs.store
    client = TestClient(app)
    path = f"/v1/jobs/{key}/messages/{message}/decision"
    assert client.post(path, json={"action": "accept"}).status_code == 404
    response = client.post(path, headers={"X-Job-Token": token}, json={"action": "accept"})
    assert response.status_code == 200
    assert response.json()["status"] == "resolving"
    assert jobs.get(key, token).status == "done"
    assert source.calls == 2


def test_invalid_proposal_fails_without_mutation():
    jobs, chat, source, key, token, _ = setup()

    class Invalid:
        def reply(self, job):
            return ChatReply(text="Bad scope", refresh={"line_ids": ["L99"]})

    chat.assistant = Invalid()
    chat.send(key, token, SendMessage(message_id=uuid4(), text="Search"))
    chat.process(key)
    job = jobs.get(key, token)
    assert job.chat_error.code == "CHAT_FAILED"
    assert job.refresh_count == 0
    assert source.calls == 1
