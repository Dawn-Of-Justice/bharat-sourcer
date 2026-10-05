from datetime import timedelta
from uuid import uuid4

from bharat_sourcer.actions import MAX_ACTIONS, complete_refresh, record_action
from bharat_sourcer.conversation import ConversationService
from bharat_sourcer.dispatch import Work, work_once
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    ChatReply,
    ConfirmJob,
    CreateJob,
    ProposalDecision,
    RefreshOffers,
    ReportLine,
    SendMessage,
    VerifiedOffer,
    now,
)
from bharat_sourcer.storage import StoredJob, check_size


class Extractor:
    def extract(self, url):
        return [
            BomItem(line_id="L01", raw_name="Synthetic board"),
            BomItem(line_id="L02", raw_name="Synthetic sensor"),
            BomItem(line_id="L03", raw_name="Synthetic cable"),
        ]


def offer(path, price, stock="in_stock"):
    return VerifiedOffer(
        url=f"https://seller.example/{path}",
        seller="Example seller",
        title="Synthetic listing",
        price_inr=price,
        stock=stock,
    )


class Source:
    def __init__(self):
        self.calls = 0
        self.refreshed = False

    def source(self, item):
        self.calls += 1
        if not self.refreshed:
            return ReportLine(item=item, sourcing_status="no_verified_offers")
        if item.line_id == "L01":
            return ReportLine(
                item=item,
                sourcing_status="offers_found",
                offers=[offer("a", "250.00", "out_of_stock"), offer("b", "99.50")],
            )
        if item.line_id == "L02":
            raise RuntimeError("synthetic seller outage")
        return ReportLine(item=item, sourcing_status="no_verified_offers")


class Assistant:
    def __init__(self, reply):
        self.value = reply

    def reply(self, job):
        return self.value


REFRESH = ChatReply(text="Approve a new search?", refresh={"line_ids": ["L01", "L02", "L03"]})


def setup(reply=REFRESH, *, finish=True):
    source = Source()
    jobs = JobService(Extractor(), sourcing=source)
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    if finish:
        jobs.confirm(job.job_id, token, ConfirmJob())
        jobs.finish(job.job_id)
    chat = ConversationService(jobs, Assistant(reply))
    chat.send(job.job_id, token, SendMessage(message_id=uuid4(), text="Please do it"))
    chat.process(job.job_id)
    message = jobs.get(job.job_id, token).messages[-1].message_id
    source.refreshed = True
    return jobs, chat, source, job.job_id, token, message


def accept(chat, key, token, message, action="accept"):
    return chat.decide(key, token, message, ProposalDecision(action=action))


def results(job, message):
    return [m for m in job.messages if m.completes_message_id == message]


def test_refresh_completion_message_summarizes_outcome_once():
    jobs, chat, source, key, token, message = setup()
    accept(chat, key, token, message)
    jobs.finish(key)
    job = jobs.get(key, token)
    assert job.status == "done"
    [reply] = results(job, message)
    assert job.messages[-1] == reply
    assert reply.role == "assistant"
    assert reply.cited_line_ids == ["L01", "L02", "L03"]
    assert "L01: 2 seller offers found; lowest seller-listed price INR 99.50" in reply.text
    assert "L02: search failed." in reply.text
    assert "L03: no verified offers." in reply.text
    assert "not verified totals" in reply.text
    by_line = {r.line_id: r for r in reply.refresh_results}
    assert by_line["L01"].offer_count == 2
    assert by_line["L01"].lowest_listed_price_inr == "99.50"
    assert by_line["L01"].lowest_listed_stock == "in_stock"
    assert by_line["L01"].price_source == "seller_published"
    assert by_line["L02"].sourcing_status == "failed"
    assert by_line["L02"].error_code == "SOURCING_FAILED"
    proposal = next(m for m in job.messages if m.message_id == message).refresh_proposal
    assert proposal.status == "accepted"
    assert proposal.result_message_id == reply.message_id
    assert [(a.kind, a.status) for a in job.actions] == [
        ("refresh", "accepted"),
        ("refresh", "completed"),
    ]
    assert job.actions[-1].message_id == message
    assert job.actions[-1].result_message_id == reply.message_id
    assert job.actions[-1].summary == "Finished; 1 of 3 parts have seller offers."

    # Duplicate completion attempts and redelivered tasks never append again.
    jobs.store.mutate(key, lambda record: complete_refresh(record.job))
    jobs.finish(key)
    assert work_once(jobs, chat, Work(job_id=key, kind="workflow"))
    accept(chat, key, token, message)
    again = jobs.get(key, token)
    assert len(results(again, message)) == 1
    assert len(again.actions) == 2
    assert again.messages == job.messages


def test_redelivered_one_line_work_completes_once():
    jobs, chat, source, key, token, message = setup()
    accept(chat, key, token, message)
    work = Work(job_id=key, kind="workflow")
    deliveries = 0
    while not work_once(jobs, chat, work):
        work_once(jobs, chat, work)  # at-least-once: every task is delivered twice
        deliveries += 1
    for _ in range(3):
        assert work_once(jobs, chat, work)
    job = jobs.get(key, token)
    assert deliveries >= 2
    assert job.status == "done"
    assert len(results(job, message)) == 1
    assert [a.status for a in job.actions] == ["accepted", "completed"]


def test_duplicate_result_message_is_linked_not_repeated():
    jobs, chat, _, key, token, message = setup()
    accept(chat, key, token, message)
    jobs.finish(key)

    def lose_link(record):
        proposal = next(m for m in record.job.messages if m.message_id == message)
        proposal.refresh_proposal.result_message_id = None

    jobs.store.mutate(key, lose_link)
    jobs.store.mutate(key, lambda record: complete_refresh(record.job))
    job = jobs.get(key, token)
    assert len(results(job, message)) == 1
    assert len(job.actions) == 2


def test_interrupted_refresh_records_failure_message():
    jobs, chat, source, key, token, message = setup()
    accept(chat, key, token, message)

    def interrupt(record):
        record.job.status = "sourcing"
        record.job.recovery_attempts = 1
        record.run_id = "lost-worker"
        record.lease_until = now() - timedelta(seconds=1)

    jobs.store.mutate(key, interrupt)
    jobs.recover(key, execute=False)
    job = jobs.get(key, token)
    assert job.status == "failed"
    [reply] = results(job, message)
    assert reply.text.startswith("The approved seller refresh was interrupted")
    assert job.actions[-1].status == "failed"
    jobs.recover(key, execute=False)
    assert len(results(jobs.get(key, token), message)) == 1


def test_direct_refresh_does_not_complete_old_proposal():
    jobs, chat, source, key, token, message = setup()
    accept(chat, key, token, message)
    jobs.finish(key)
    jobs.refresh_offers(key, token, RefreshOffers(line_ids=["L03"]))
    jobs.finish(key)
    job = jobs.get(key, token)
    assert job.refresh_count == 2
    assert sum(m.completes_message_id is not None for m in job.messages) == 1
    assert len(job.actions) == 2


def test_rejected_refresh_history():
    jobs, chat, source, key, token, message = setup()
    accept(chat, key, token, message, "reject")
    accept(chat, key, token, message, "reject")
    job = jobs.get(key, token)
    [entry] = job.actions
    assert (entry.kind, entry.status, entry.message_id) == ("refresh", "rejected", message)
    assert entry.line_ids == ["L01", "L02", "L03"]
    assert not results(job, message)
    assert source.calls == 3


def test_spec_update_history_accept_and_reject():
    update = {"updates": [{"line_id": "L01", "specs": {"logic_v": 3.3}}]}
    reply = ChatReply(text="Proposed 3.3 V logic.", spec_update=update)
    jobs, chat, _, key, token, message = setup(reply)
    accept(chat, key, token, message)
    accept(chat, key, token, message)
    chat.send(key, token, SendMessage(message_id=uuid4(), text="Again"))
    chat.process(key)
    second = jobs.get(key, token).messages[-1].message_id
    accept(chat, key, token, second, "reject")
    job = jobs.get(key, token)
    assert [(a.kind, a.status, a.message_id) for a in job.actions] == [
        ("spec_update", "completed", message),
        ("spec_update", "rejected", second),
    ]
    assert job.actions[0].line_ids == ["L01"]
    assert job.actions[0].summary == "Updated required specs for L01"
    assert all(m.completes_message_id is None for m in job.messages)


def test_draft_edit_history_accept_and_reject():
    reply = ChatReply(text="Mark L03 as owned?", edits=[{"op": "have_it", "line_id": "L03"}])
    jobs, chat, _, key, token, message = setup(reply, finish=False)
    accept(chat, key, token, message, "reject")
    chat.send(key, token, SendMessage(message_id=uuid4(), text="Yes, mark it"))
    chat.process(key)
    second = jobs.get(key, token).messages[-1].message_id
    accept(chat, key, token, second)
    job = jobs.get(key, token)
    assert [(a.kind, a.status) for a in job.actions] == [
        ("edit", "rejected"),
        ("edit", "completed"),
    ]
    assert job.actions[1].line_ids == ["L03"]
    assert job.items[2].user_has_it


def test_history_is_bounded_and_fits_storage():
    jobs, chat, _, key, token, _ = setup()

    def flood(record):
        for index in range(MAX_ACTIONS + 10):
            record_action(
                record.job,
                "refresh",
                f"m{index}",
                "rejected",
                [f"L{n:02d}" for n in range(1, 101)],
                "x" * 2000,
            )

    jobs.store.mutate(key, flood)
    job = jobs.get(key, token)
    assert len(job.actions) == MAX_ACTIONS
    assert job.actions[0].message_id == "m10"
    assert len(job.actions[-1].summary) == 500
    check_size(jobs.store.get(key))


def test_old_snapshot_without_action_fields_validates():
    jobs, chat, _, key, token, message = setup()
    accept(chat, key, token, message)
    jobs.finish(key)
    data = jobs.store.get(key).model_dump(mode="json")
    del data["job"]["actions"]
    for item in data["job"]["messages"]:
        item.pop("completes_message_id")
        item.pop("refresh_results")
        if item["refresh_proposal"]:
            item["refresh_proposal"].pop("result_message_id")
    old = StoredJob.model_validate(data)
    assert old.job.actions == []
    assert old.job.messages[0].completes_message_id is None
