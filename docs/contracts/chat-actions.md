# Reviewed chat actions (v0.12, spec proposals v0.17.9)

## Spec and requirement proposals (v0.17.9)

When a user states a required spec or requirement in chat for parts of a completed live
report, the assistant message can contain `spec_proposal` (separate from `proposal` and
`refresh_proposal`; a reply carries at most one of the three):

```json
{
  "request": {"updates": [{"line_id": "L01", "specs": {"logic_v": 3.3}}]},
  "status": "pending",
  "base_fingerprint": "opaque report fingerprint"
}
```

`request` has the same shape as the body of `POST /v1/jobs/{job_id}/specs`
(`UpdateJobSpecs`). Show the parts and values with Approve/Reject, and explain that
approval re-checks saved quotes against the new specs, clears those parts' selections
and marks AI research assessments stale. Decide with the existing
`POST /v1/jobs/{job_id}/messages/{message_id}/decision`. Acceptance applies exactly the
same validation and changes as the specs endpoint; nothing is searched or charged.
A changed report returns 409 `PROPOSAL_STALE`; invalid line IDs or specs are rejected
before the proposal is shown (`CHAT_FAILED`). Values come only from what the user said;
the assistant is instructed never to infer electrical specs.

## Seller refresh proposals (v0.12)

The tracked frontend (`frontend/src/ChatPanel.tsx`) renders `refresh_proposal`,
`spec_proposal`, refresh completion messages (`refresh_results`) and a collapsible
`job.actions` history.

The agent can propose a targeted seller refresh from a completed live report.
Sending a chat message never starts that search. The returned assistant message
contains `refresh_proposal`, separate from the existing draft BOM `proposal`:

```json
{
  "request": {"line_ids": ["L01"]},
  "status": "pending",
  "base_fingerprint": "opaque report fingerprint",
  "refresh_count": null
}
```

Display the selected parts and a confirmation explaining that approval starts
potentially paid search, clears those parts' prior quotes/selections and consumes
one of the existing two refresh batches per job. Provide Approve and Reject.
Use `POST /v1/jobs/{job_id}/messages/{message_id}/decision` with
`{"action":"accept"}` or `{"action":"reject"}` and both access headers.

Approval returns 200 with a Job in `resolving`. The worker then sources the
approved lines; use existing SSE snapshots, events and report lines for progress
and results. The proposal becomes `accepted` and records the batch number in
`refresh_count`. Accepted means authorized/queued, not successfully sourced.

### Refresh completion message

When the approved batch ends, the worker appends one assistant message. It is
generated deterministically from saved report lines; no model is called:

```json
{
  "message_id": "derived from the proposal message_id",
  "role": "assistant",
  "text": "The approved seller refresh has finished. L01: 2 seller offers found; lowest seller-listed price INR 99.50 (stock: in_stock). L02: search failed. ...",
  "cited_line_ids": ["L01", "L02"],
  "completes_message_id": "<proposal message_id>",
  "refresh_results": [
    {"line_id": "L01", "sourcing_status": "offers_found", "offer_count": 2,
     "lowest_listed_price_inr": "99.50", "lowest_listed_stock": "in_stock",
     "price_source": "seller_published", "error_code": null}
  ]
}
```

The proposal's `refresh_proposal.result_message_id` then names this message. If the
batch is interrupted and the job fails with `SOURCING_INTERRUPTED`, the message starts
"The approved seller refresh was interrupted" instead. A paused batch produces no message
until it resumes and finishes. Prices are seller-published snapshots, not verified or
delivered totals; select offers in the report as usual. The message is written in the
same transaction as the `done`/`failed` transition and its ID is derived from the
proposal, so redelivered worker tasks never append it twice. `refresh_results` is a
snapshot when the batch ended; later refreshes change the report but not this message.
Refreshes started directly with `POST /v1/jobs/{job_id}/refresh` produce no message.

### Action history

`job.actions` is an append-only list (newest 50 kept) recording each decision and
outcome: `kind` (`edit`, `refresh`, `spec_update`), proposal `message_id`, `status`,
`created_at`, `line_ids`, a short `summary`, and for refreshes `refresh_count` and
`result_message_id`. Statuses:

- `rejected`: the user rejected the proposal; nothing changed.
- `completed` for `edit`/`spec_update`: applied in the acceptance transaction.
- `accepted` for `refresh`: queued; followed later by `completed` or `failed` when the
  batch ends.

Repeated identical decisions add no entries. Snapshots saved before this field existed
load with an empty list. The history summarizes decisions; the report remains the
source of current quotes.

Approval and queuing are atomic. Repeated acceptance does not consume another
batch. Recovery dispatches queued work if the HTTP background task is interrupted.
Rejection starts no work. Opposite decisions return 409 `PROPOSAL_DECIDED`.
Changed BOM, workflow status, report (including selections), or refresh count
returns 409 `PROPOSAL_STALE`; ask for a fresh proposal. Limits and valid unowned
line IDs are validated before showing a proposal and again during approval.

Draft edits and refresh cannot be proposed together. Unknown/invalid model
actions produce `CHAT_FAILED` without changing sourcing. Existing pause/resume
controls apply once approved sourcing begins. Proposals for paused-plan
changes and other tools remain future work.
