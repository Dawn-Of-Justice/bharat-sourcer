# Pause and resume sourcing (v0.11)

Both endpoints require `X-Job-Token` and the deployment's `X-Integration-Key`.
They accept no request body and return a complete Job snapshot.

| Request | Result |
| --- | --- |
| `POST /v1/jobs/{job_id}/pause` | 200; persists pause intent |
| `POST /v1/jobs/{job_id}/resume` | 202; queues remaining sourcing |

Show Pause during live `resolving` or `sourcing`. After requesting pause, show
“Pausing after current part…” when `pause_requested: true` and status is still
`sourcing`. Show Resume only once status is `paused`. Use the existing SSE
snapshot stream to watch these transitions.

Queued sourcing pauses immediately. An active line can finish its discovery and
seller checks before the worker saves it and acknowledges pause. HTTP calls are
not cancelled; this may take multiple request timeouts/retries. A request racing
with a new line may allow that line to finish. Pause leaves chat active.

Repeated pause calls are no-ops while requested/paused. Resume while the pause is
still pending returns 409 `INVALID_STATE`. Repeated resume during resolving or
sourcing with no pause intent is a no-op; worker claims prevent duplicate work.
These are state-based semantics: resume after completion returns 409.

Resume preserves saved lines, refresh scope, refresh count and sourcing limits.
Completed lines are skipped, including failed lines; retrying failed lines uses
the existing refresh endpoint after completion. If the worker dies before saving
the current line, that line may run again on resume. An expired worker's late
result is rejected. Recovery acknowledges persisted pause intent without
automatically restarting sourcing or consuming the automatic recovery attempt.

Extraction, draft review, completed/failed reports and demo jobs cannot be paused.
Wrong/missing job tokens return 404. Paused snapshots persist in Firestore across
restarts; default `pause_requested: false` keeps older snapshots readable.

Chat can answer questions about saved results while paused. BOM edit proposals
still apply only during `awaiting_confirmation`; changing a paused sourcing plan
and agent-proposed search actions remain future work. Partial reports may contain
only completed lines. A final-line pause can preserve all results while still
requiring Resume to finalize the report.
