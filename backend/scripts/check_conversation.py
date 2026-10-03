"""Live Gemini smoke test in an isolated memory job; writes a token-free local report."""

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import ConversationService, GeminiAssistant
from bharat_sourcer.extraction import GeminiExtractor
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import CreateJob, Job, ProposalDecision, SendMessage
from bharat_sourcer.storage import StoredJob
from bharat_sourcer.streaming import snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--resume", action="store_true", help="Reuse the saved extraction")
    parser.add_argument(
        "--resistor-question",
        action="store_true",
        help="Ask about resistor roles only; does not choose test component values",
    )
    args = parser.parse_args()
    settings = Settings()
    jobs = JobService(GeminiExtractor(settings), model=settings.gemini_model)
    chat = ConversationService(jobs, GeminiAssistant(settings))
    target = Path(".data/conversation-check.json")
    target.parent.mkdir(exist_ok=True)
    if args.resume:
        job = Job.model_validate_json(target.read_text(encoding="utf-8"))
        if str(job.input.url) != args.url:
            raise ValueError("Saved video differs from requested URL")
        token = str(uuid4())
        jobs.store.create(StoredJob(job=job, token_hash=sha256(token.encode()).hexdigest()))
    else:
        job, token = jobs.create(CreateJob(url=args.url))

    def save():
        current = jobs.get(job.job_id, token)
        target.write_text(current.model_dump_json(indent=2), encoding="utf-8")
        return current

    if not args.resume:
        print("Extracting video with live Gemini...", flush=True)
        jobs.extract(job.job_id)
    current = save()
    if current.status != "awaiting_confirmation":
        raise RuntimeError(
            f"Extraction failed: {current.error.code if current.error else current.status}"
        )
    print(
        json.dumps(
            [{"line_id": p.line_id, "name": p.raw_name, "qty": p.qty} for p in current.items]
        ),
        flush=True,
    )

    def ask(text):
        print("Asking: " + text, flush=True)
        chat.send(job.job_id, token, SendMessage(message_id=uuid4(), text=text))
        chat.process(job.job_id)
        result = save()
        if result.chat_state != "idle":
            raise RuntimeError(f"Chat failed: {result.chat_error.code}")
        reply = result.messages[-1]
        print(reply.model_dump_json(), flush=True)
        return reply

    first = current.items[0].line_id
    if args.resistor_question:
        before = [item.model_dump() for item in current.items]
        answer = ask(
            "Which resistor values should I use for this project? "
            "I don't know which resistor serves which role yet. "
            "Ask me what you need to know before calculating anything."
        )
        assert answer.resistor_question is not None
        assert answer.proposal is None
        assert [item.model_dump() for item in save().items] == before
        print("PASS: contextual resistor clarification; BOM unchanged.")
        return
    answer = (
        None
        if args.resume
        else ask(
            f"Explain {first} using the saved video evidence and timestamps. "
            "What is uncertain? Do not propose edits."
        )
    )
    if answer:
        assert answer.proposal is None and first in answer.cited_line_ids
    for decision in ["accept"] if args.resume else ["reject", "accept"]:
        reply = ask(
            f"For this smoke test only, propose marking {first} as already owned "
            "with have_it. Do not change anything else."
        )
        assert reply.proposal and len(reply.proposal.edits) == 1
        edit = reply.proposal.edits[0]
        assert edit.op == "have_it" and edit.line_id == first and edit.user_has_it
        chat.decide(job.job_id, token, reply.message_id, ProposalDecision(action=decision))
        current = save()
        assert current.items[0].user_has_it == (decision == "accept")
        assert current.status == "awaiting_confirmation" and current.report is None

    class Request:
        async def is_disconnected(self):
            return False

    async def check_stream():
        stream = snapshots(jobs, job.job_id, token, Request(), interval=0)
        try:
            event = await anext(stream)
            assert event.startswith("event: snapshot\n") and token not in event
            assert json.loads(event.split("data: ")[1])["items"][0]["user_has_it"]
            assert await anext(stream) == ": heartbeat\n\n"
        finally:
            await stream.aclose()

    asyncio.run(check_stream())
    print(
        "PASS: live extraction, evidence answer, reject/accept and snapshot generator. "
        f"Saved {target}"
    )


if __name__ == "__main__":
    main()
