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

The current tracked frontend has not yet added a `refresh_proposal` type/card. Its
chat currently shows assistant text and BOM edit proposals only. Update the chat UI
before expecting users to approve seller refresh proposals.

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
No separate assistant completion message is generated. Later refreshes can
replace results, so this is not an immutable per-action result archive.

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
