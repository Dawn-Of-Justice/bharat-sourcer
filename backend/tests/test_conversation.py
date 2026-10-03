import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import ConversationService, GeminiAssistant
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ChatReply,
    ConfirmJob,
    CreateJob,
    ProposalDecision,
    SendMessage,
    now,
)
from bharat_sourcer.streaming import snapshots


class Extractor:
    def extract(self, url):
        return [BomItem(line_id="L01", raw_name="Pro Micro", qty=None)]


class Assistant:
    calls = 0

    def reply(self, job):
        self.calls += 1
        return ChatReply(
            text="Proposed marking your board as owned.",
            cited_line_ids=["L01"],
            edits=[{"op": "have_it", "line_id": "L01"}],
        )


def setup():
    jobs = JobService(Extractor())
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    assistant = Assistant()
    chat = ConversationService(jobs, assistant)
    return jobs, chat, assistant, job.job_id, token


def send(chat, job_id, token):
    request = SendMessage(message_id=uuid4(), text="I own the board; update it")
    chat.send(job_id, token, request)
    chat.process(job_id)
    return request


def test_proposal_requires_acceptance_and_does_not_confirm():
    jobs, chat, assistant, job_id, token = setup()
    request = send(chat, job_id, token)
    before = jobs.get(job_id, token)
    assert not before.items[0].user_has_it
    chat.send(job_id, token, request)
    chat.process(job_id)
    assert assistant.calls == 1
    msg = before.messages[-1]
    accepted = chat.decide(job_id, token, msg.message_id, ProposalDecision(action="accept"))
    assert accepted.items[0].user_has_it
    assert accepted.items[0].qty is None
    assert accepted.status == "awaiting_confirmation"
    assert accepted.report is None
    assert chat.decide(job_id, token, msg.message_id, ProposalDecision(action="accept")) == accepted
    with pytest.raises(JobError):
        jobs.confirm(job_id, token, ConfirmJob())


def test_stale_reject_and_conflicting_message():
    jobs, chat, _, job_id, token = setup()
    req = send(chat, job_id, token)
    msg = jobs.get(job_id, token).messages[-1]

    def changed(record):
        record.job.items[0].qty = 2

    jobs.store.mutate(job_id, changed)
    with pytest.raises(JobError) as error:
        chat.decide(job_id, token, msg.message_id, ProposalDecision(action="accept"))
    assert error.value.code == "PROPOSAL_STALE"
    rejected = chat.decide(job_id, token, msg.message_id, ProposalDecision(action="reject"))
    assert not rejected.items[0].user_has_it
    with pytest.raises(JobError) as error:
        chat.send(job_id, token, req.model_copy(update={"text": "Different"}))
    assert error.value.code == "MESSAGE_CONFLICT"


def test_busy_failure_recovery_and_late_response():
    jobs, chat, _, job_id, token = setup()
    chat.send(job_id, token, SendMessage(message_id=uuid4(), text="Question"))
    with pytest.raises(JobError) as error:
        chat.send(job_id, token, SendMessage(message_id=uuid4(), text="Another"))
    assert error.value.code == "CHAT_BUSY"

    class Expiring:
        def reply(self, job):
            def expire(record):
                record.chat_lease_until = now() - timedelta(seconds=1)

            jobs.store.mutate(job_id, expire)
            chat.recover()
            return ChatReply(text="Late")

    chat.assistant = Expiring()
    chat.process(job_id)
    result = jobs.get(job_id, token)
    assert result.chat_error.code == "CHAT_INTERRUPTED"
    assert len(result.messages) == 1
    assert result.status == "awaiting_confirmation"


@pytest.mark.parametrize(
    "reply",
    [
        ChatReply(text="Bad reference", cited_line_ids=["L99"]),
        ChatReply(text="Bad edit", edits=[{"op": "remove", "line_id": "L01"}]),
    ],
)
def test_invalid_reply_does_not_change_bom(reply):
    jobs, chat, _, job_id, token = setup()

    class Invalid:
        def reply(self, job):
            return reply

    chat.assistant = Invalid()
    send(chat, job_id, token)
    result = jobs.get(job_id, token)
    assert result.chat_state == "failed"
    assert result.chat_error.code == "CHAT_FAILED"
    assert len(result.items) == 1
    assert len(result.messages) == 1


def test_api_demo_auth_and_snapshot_stream():
    app = create_app(Settings(_env_file=None))
    client = TestClient(app)
    created = client.post("/v1/jobs", json={"url": "https://example.com"}).json()
    job_id, token = created["job_id"], created["job_token"]
    path = f"/v1/jobs/{job_id}/messages"
    body = {"message_id": str(uuid4()), "text": "Explain these parts"}
    assert client.post(path, json=body).status_code == 404
    response = client.post(path, json=body, headers={"X-Job-Token": token})
    assert response.status_code == 202
    job = client.get(f"/v1/jobs/{job_id}", headers={"X-Job-Token": token}).json()
    assert job["chat_state"] == "idle"
    assert job["messages"][-1]["text"].startswith("Demo:")
    assert client.get(f"/v1/jobs/{job_id}/stream").status_code == 404

    class Request:
        async def is_disconnected(self):
            return False

    async def read():
        stream = snapshots(app.state.job_service, job_id, token, Request(), duration=60, interval=0)
        try:
            return [await anext(stream), await anext(stream)]
        finally:
            await stream.aclose()

    chunks = asyncio.run(read())
    assert chunks[0].startswith("event: snapshot\n")
    assert json.loads(chunks[0].split("data: ")[1])["messages"] == job["messages"]
    assert token not in "".join(chunks)
    assert ": heartbeat\n\n" in chunks


def test_gemini_adapter_validates_structured_reply_and_omits_secrets():
    jobs, _, _, job_id, token = setup()

    def handler(request):
        payload = json.loads(request.content)
        assert token not in request.content.decode()
        assert "responseJsonSchema" in payload["generationConfig"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "text": "Review L01",
                                            "cited_line_ids": ["L01"],
                                            "edits": [],
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    adapter = GeminiAssistant(
        Settings(_env_file=None, gemini_api_key="test"), httpx.MockTransport(handler)
    )
    assert adapter.reply(jobs.get(job_id, token)).cited_line_ids == ["L01"]


def test_queued_chat_survives_new_service_and_limit():
    jobs, chat, assistant, job_id, token = setup()
    chat.send(job_id, token, SendMessage(message_id=uuid4(), text="Question"))
    ConversationService(jobs, assistant).recover()
    assert jobs.get(job_id, token).chat_state == "idle"
    for _ in range(19):
        send(chat, job_id, token)
    with pytest.raises(JobError) as error:
        chat.send(job_id, token, SendMessage(message_id=uuid4(), text="More"))
    assert error.value.code == "CHAT_LIMIT"


def test_concurrent_messages_allow_only_one_turn():
    _, chat, _, job_id, token = setup()

    def submit(_):
        try:
            chat.send(job_id, token, SendMessage(message_id=uuid4(), text="Question"))
            return 202
        except JobError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [202, 409]


def test_live_api_proposal_decision_and_no_automatic_search():
    app = create_app(
        Settings(_env_file=None, demo_mode=False, sourcing_enabled=False, gemini_api_key="test"),
        extractor=Extractor(),
        assistant=Assistant(),
    )
    client = TestClient(app)
    created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
    job_id = created["job_id"]
    headers = {"X-Job-Token": created["job_token"]}
    root = f"/v1/jobs/{job_id}"
    assert (
        client.post(
            root + "/messages",
            headers=headers,
            json={"message_id": str(uuid4()), "text": "I own the board"},
        ).status_code
        == 202
    )
    job = client.get(root, headers=headers).json()
    message_id = job["messages"][-1]["message_id"]
    path = root + f"/messages/{message_id}/decision"
    assert client.post(path, json={"action": "accept"}).status_code == 404
    accepted = client.post(path, headers=headers, json={"action": "accept"})
    assert accepted.status_code == 200
    assert accepted.json()["items"][0]["user_has_it"] is True
    assert accepted.json()["status"] == "awaiting_confirmation"
    assert accepted.json()["report"] is None
