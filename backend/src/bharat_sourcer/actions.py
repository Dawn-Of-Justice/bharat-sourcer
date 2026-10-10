"""Deterministic chat-action bookkeeping: bounded history and refresh completion messages.

Everything here runs inside storage transactions, so it performs no external I/O and
never calls a model.
"""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from bharat_sourcer.schemas import (
    ActionKind,
    ActionRecord,
    ActionStatus,
    ChatMessage,
    Job,
    RefreshLineResult,
)

MAX_ACTIONS = 50


def record_action(
    job: Job,
    kind: ActionKind,
    message_id: str,
    status: ActionStatus,
    line_ids: list[str],
    summary: str,
    *,
    refresh_count: int | None = None,
    result_message_id: str | None = None,
) -> None:
    """Append one history entry, keeping only the most recent MAX_ACTIONS."""
    job.actions.append(
        ActionRecord(
            kind=kind,
            message_id=message_id,
            status=status,
            line_ids=list(dict.fromkeys(line_ids))[:100],
            summary=summary[:500],
            refresh_count=refresh_count,
            result_message_id=result_message_id,
        )
    )
    del job.actions[:-MAX_ACTIONS]


def result_message_id(proposal_message_id: str) -> str:
    # Stable per proposal, so a duplicate completion can never mint a second message.
    return str(uuid5(NAMESPACE_URL, f"bharat-sourcer:refresh-result:{proposal_message_id}"))


def _line_results(job: Job, line_ids: list[str]) -> list[RefreshLineResult]:
    lines = {line.item.line_id: line for line in job.report.lines} if job.report else {}
    results = []
    for key in line_ids:
        line = lines.get(key)
        if line is None:
            results.append(RefreshLineResult(line_id=key, sourcing_status="failed"))
            continue
        cheapest = min(line.offers, key=lambda offer: Decimal(offer.price_inr), default=None)
        results.append(
            RefreshLineResult(
                line_id=key,
                sourcing_status=line.sourcing_status,
                offer_count=len(line.offers),
                lowest_listed_price_inr=cheapest.price_inr if cheapest else None,
                lowest_listed_stock=cheapest.stock if cheapest else None,
                error_code=line.sourcing_error.code if line.sourcing_error else None,
            )
        )
    return results


def _describe(result: RefreshLineResult) -> str:
    if result.sourcing_status == "offers_found" and result.offer_count:
        noun = "offer" if result.offer_count == 1 else "offers"
        return (
            f"{result.line_id}: {result.offer_count} seller {noun} found; lowest "
            f"seller-listed price INR {result.lowest_listed_price_inr} "
            f"(stock: {result.lowest_listed_stock})."
        )
    if result.sourcing_status in {"offers_found", "no_verified_offers"}:
        return f"{result.line_id}: no verified offers."
    if result.sourcing_status == "already_owned":
        return f"{result.line_id}: marked as already owned; not searched."
    if result.error_code == "SOURCING_LIMIT":
        return f"{result.line_id}: not searched; the sourcing limit was reached."
    return f"{result.line_id}: search failed."


def complete_refresh(job: Job, *, failed: bool = False) -> None:
    """Close the chat-approved refresh batch currently on the job, at most once.

    Call inside the same transaction that ends the batch. A redelivered task or a
    repeated call is a no-op because the proposal then already names its result message.
    """
    message = next(
        (
            m
            for m in reversed(job.messages)
            if m.refresh_proposal
            and m.refresh_proposal.status == "accepted"
            and m.refresh_proposal.refresh_count == job.refresh_count
        ),
        None,
    )
    if message is None or message.refresh_proposal.result_message_id is not None:
        return
    proposal = message.refresh_proposal
    reply_id = result_message_id(message.message_id)
    if any(m.message_id == reply_id for m in job.messages):
        proposal.result_message_id = reply_id
        return
    line_ids = proposal.request.line_ids
    results = _line_results(job, line_ids)
    found = sum(r.sourcing_status == "offers_found" and r.offer_count > 0 for r in results)
    if failed:
        heading = "The approved seller refresh was interrupted before it finished."
        summary = f"Interrupted; {found} of {len(results)} parts had offers saved."
    else:
        heading = "The approved seller refresh has finished."
        summary = f"Finished; {found} of {len(results)} parts have seller offers."
    text = " ".join(
        [
            heading,
            *(_describe(r) for r in results),
            "Prices are published by sellers, not verified totals; tax, shipping and seller "
            "trust are unverified. Review and select offers in the report.",
        ]
    )
    job.messages.append(
        ChatMessage(
            message_id=reply_id,
            role="assistant",
            text=text,
            cited_line_ids=list(line_ids),
            completes_message_id=message.message_id,
            refresh_results=results,
        )
    )
    proposal.result_message_id = reply_id
    record_action(
        job,
        "refresh",
        message.message_id,
        "failed" if failed else "completed",
        line_ids,
        summary,
        refresh_count=proposal.refresh_count,
        result_message_id=reply_id,
    )
