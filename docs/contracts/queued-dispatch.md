# Durable dispatch (v0.13)

The cloud backend uses Cloud Tasks. Public routes, job tokens, integration keys,
approval controls and SSE snapshots keep their existing shapes. The API can now
scale to zero, so the first request after idle may take longer to start.

## Execution

1. An API request commits a pending workflow or chat state to Firestore.
2. Before returning, it attempts to enqueue a task containing only the job ID and
   work kind. The user token and Gemini key are never placed in the task payload.
3. Cloud Tasks makes an authenticated HTTP request to `/internal/work`. The work
   runs inside that request so request-based Cloud Run billing keeps CPU available.
4. Extraction and chat each run as one operation. Sourcing saves one BOM line per
   delivery, releases its lease and returns to `resolving` between lines.
5. Unfinished work returns 503 so Cloud Tasks retries. Finished, paused, failed or
   awaiting-confirmation work returns 200. Existing leases prevent duplicate claims.

Keep showing sourcing progress across `resolving` and `sourcing`; intermediate
`resolving` snapshots now also mean a checkpoint was saved and work will continue.
Retries wait 10–60 seconds, so there can be a gap between sourced lines.

## Recovery

A Cloud Scheduler request checks pending Firestore states every five minutes and
redispatches workflow/chat tasks. This closes the gap when Firestore commits but
queue creation fails. The API logs `TASK_ENQUEUE_FAILED` and still returns the
saved job; recovery does not require the user to keep a browser open.

Each queue task has up to 200 attempts with a one-day retry duration. The scheduler
can create replacement tasks for still-pending work. Expired execution leases keep
the existing one automatic workflow recovery per job; expired chat calls fail
without automatic Gemini replay. Sourcing resumes saved lines, and late results
from replaced workers are rejected. A provider call whose result was never saved
may still be repeated and charged again. This is at-least-once delivery.

Paused jobs stay paused. No new seller search bypasses user approval. The scheduled
scan enqueues pending work only; it does not run Gemini inside the scheduler request.

## Sweep limits and stuck-work signals (v0.17.6)

Each scheduled sweep handles at most `BS_SWEEP_LIMIT` pending jobs (default 200);
jobs beyond the limit wait until earlier ones leave a pending state, so a sustained
`SWEEP_TRUNCATED` warning means the limit or capacity must be raised. A failed read or
enqueue for one job is
logged (`SWEEP_READ_FAILED`, `TASK_ENQUEUE_FAILED`) and no longer aborts the sweep.
The internal response reports `dispatched`, `failed`, `stale` and `truncated` counts.

Pending work whose `updated_at` is older than `BS_QUEUE_AGE_ALERT_MINUTES` (default 30)
logs `QUEUE_AGE_EXCEEDED job=<id> kinds=<workflow|chat> age_s=<seconds>`, and a capped
sweep logs `SWEEP_TRUNCATED`. These are warning-level Cloud Logging entries; on Cloud Run
they are structured JSON with the tag at the start of `jsonPayload.message` (and `job_id`,
`kinds`, `age_s` or `limit` as fields; see `backend/infra/observability.md`). To be paged,
use a log-based alert on `jsonPayload.message:"QUEUE_AGE_EXCEEDED" OR
jsonPayload.message:"SWEEP_TRUNCATED"` (plus the `textPayload` forms for older entries), as
`backend/infra/queue-age-alert.json` does.
Public API shapes are unchanged.

## Operations

Queue: `bharat-sourcer`, region `asia-south1`; max two concurrent deliveries and
two dispatches/second. Worker deadline and Cloud Run timeout are 1,800 seconds.
Service minimum instances is zero; maximum remains one. In-process recovery loops
are disabled in cloud mode. Local development keeps its existing background mode.

Internal endpoints verify Google-signed OIDC tokens, exact audience, verified email
and the dedicated `bharat-sourcer-tasks` service-account identity. They are omitted
from public OpenAPI. Integration keys alone cannot invoke worker endpoints.
The runtime can enqueue on this queue and act as the dispatch identity. Scheduler
uses the same dedicated identity. These routes use application authentication
because the public API service also accepts frontend requests.

Cloud Run now charges while handling requests, including worker calls and open SSE
streams, rather than continuously. Cloud Tasks, Scheduler, Firestore reads and
Gemini still have usage charges/free allowances. The five-minute scan wakes the
service briefly even when there are no jobs. Heavy concurrent use can queue because
the deployment still permits only one Cloud Run instance.

Re-run `backend/scripts/enable_queued_dispatch.py` to provision this setup. The
normal deployment script preserves queue settings after migration. Rollbacks must
pair an old background-only revision with its previous always-allocated CPU and
minimum-one configuration; do not deploy that code with minimum zero.

References: [Cloud Tasks with Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks),
[HTTP tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks),
[Cloud Run billing](https://docs.cloud.google.com/run/docs/configuring/billing-settings).
