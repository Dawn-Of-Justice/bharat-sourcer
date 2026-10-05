"""Chat spec proposals use synthetic parts; requirement values are test data, not real specs."""

from uuid import uuid4

import pytest

from bharat_sourcer.conversation import ConversationService
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import (
    BomItem,
    ChatReply,
    ConfirmJob,
    CreateJob,
    ProposalDecision,
    ReportLine,
    SendMessage,
)

UPDATE = {"updates": [{"line_id": "L01", "specs": {"logic_v": 3.3}}]}


class Extractor:
    def extract(self, url):
        return [BomItem(line_id="L01", raw_name="Pro Micro board")]


class Source:
    def __init__(self):
        self.calls = 0

    def source(self, item):
        self.calls += 1
        return ReportLine(item=item, sourcing_status="no_verified_offers")


class Assistant:
    def __init__(self, reply):
        self.value = reply

    def reply(self, job):
        return self.value


def setup(reply):
    source = Source()
    jobs = JobService(Extractor(), sourcing=source)
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    jobs.confirm(job.job_id, token, ConfirmJob())
    jobs.finish(job.job_id)
    chat = ConversationService(jobs, Assistant(reply))
    chat.send(job.job_id, token, SendMessage(message_id=uuid4(), text="It must be 3.3 V logic"))
    chat.process(job.job_id)
    return jobs, chat, source, job.job_id, token


def test_spec_proposal_applies_only_after_acceptance():
    reply = ChatReply(text="Proposed 3.3 V logic for L01.", spec_update=UPDATE)
    jobs, chat, source, key, token = setup(reply)
    job = jobs.get(key, token)
    message = job.messages[-1]
    assert message.spec_proposal.status == "pending"
    assert job.items[0].specs.logic_v is None
    accepted = chat.decide(key, token, message.message_id, ProposalDecision(action="accept"))
    assert accepted.items[0].specs.logic_v == 3.3
    assert accepted.items[0].user_edited is True
    assert accepted.report.lines[0].resolution.specs.logic_v == 3.3
    assert accepted.messages[-1].spec_proposal.status == "accepted"
    assert source.calls == 1


def test_spec_proposal_reject_and_stale_report():
    reply = ChatReply(text="Proposed 3.3 V logic for L01.", spec_update=UPDATE)
    jobs, chat, _, key, token = setup(reply)
    message = jobs.get(key, token).messages[-1].message_id
    jobs.store.mutate(key, lambda record: setattr(record.job.report, "summary", "Changed"))
    with pytest.raises(JobError) as error:
        chat.decide(key, token, message, ProposalDecision(action="accept"))
    assert error.value.code == "PROPOSAL_STALE"
    rejected = chat.decide(key, token, message, ProposalDecision(action="reject"))
    assert rejected.items[0].specs.logic_v is None


def test_invalid_spec_proposal_is_not_offered():
    bad = {"updates": [{"line_id": "L99", "specs": {"logic_v": 3.3}}]}
    jobs, _, _, key, token = setup(ChatReply(text="Bad line", spec_update=bad))
    job = jobs.get(key, token)
    assert job.chat_error.code == "CHAT_FAILED"
    assert job.messages[-1].role == "user"


def test_reply_allows_only_one_action():
    with pytest.raises(ValueError):
        ChatReply(text="x", refresh={"line_ids": ["L01"]}, spec_update=UPDATE)
