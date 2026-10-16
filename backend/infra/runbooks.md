# Alert runbooks

One section per alert. Alert policies, the dashboard and SLOs are defined in
`backend/infra/monitoring.md` and `backend/scripts/setup_monitoring.py` (branch
`ops/monitoring`); event fields are defined in `backend/infra/observability.md` (branch
`obs/instrumentation`). If those disagree with this page, they win; fix this page.

Severity and communication: [incident response](incident-response.md). Budget policy:
[SLOs](slos.md).

## Setup for every runbook

Run in [Cloud Shell](https://console.cloud.google.com/cloudshell/editor?project=hackathon-510415)
or Git Bash. On Windows `gcloud.cmd`, avoid newlines and commas inside one argument
(`--format` tables included), or use Cloud Shell.

```sh
P=hackathon-510415; R=asia-south1
API=bharat-sourcer-integration; WEB=bharat-sourcer-web
APP='resource.type="cloud_run_revision" AND resource.labels.service_name="bharat-sourcer-integration"'
REQ='resource.type="cloud_run_revision" AND log_name="projects/hackathon-510415/logs/run.googleapis.com%2Frequests"'
```

Links:

| What | Link |
| --- | --- |
| Dashboards (pick the Bharat Sourcer one) | <https://console.cloud.google.com/monitoring/dashboards?project=hackathon-510415> |
| Alert incidents | <https://console.cloud.google.com/monitoring/alerting?project=hackathon-510415> |
| SLOs | <https://console.cloud.google.com/monitoring/services?project=hackathon-510415> |
| API service metrics | <https://console.cloud.google.com/run/detail/asia-south1/bharat-sourcer-integration/metrics?project=hackathon-510415> |
| Web service metrics | <https://console.cloud.google.com/run/detail/asia-south1/bharat-sourcer-web/metrics?project=hackathon-510415> |
| Logs Explorer | <https://console.cloud.google.com/logs/query?project=hackathon-510415> |
| Cloud Tasks queue | <https://console.cloud.google.com/cloudtasks/queue/asia-south1/bharat-sourcer/tasks?project=hackathon-510415> |
| Firestore | <https://console.cloud.google.com/firestore/databases/-default-/data?project=hackathon-510415> |
| Quotas (Vertex AI, Gemini API) | <https://console.cloud.google.com/iam-admin/quotas?project=hackathon-510415> |
| GitHub Actions deploys | <https://github.com/Dawn-Of-Justice/bharat-sourcer/actions> |
| Google Cloud status | <https://status.cloud.google.com/> |

Not on the user path, so excluded from user-facing checks: `/internal/work` answers 503 on
purpose so Cloud Tasks retries unfinished work, and `/v1/jobs/{id}/stream` (SSE) and
`/internal/work` (up to 1,800 s) are long by design.

## Common mitigations

### Roll back a Cloud Run revision

```sh
gcloud run revisions list --service=$API --region=$R --project=$P --limit=5
gcloud run services update-traffic $API --region=$R --project=$P --to-revisions=REVISION_NAME=100
# same for the web service: replace $API with $WEB
```

- Pick the newest revision that was healthy before the alert (its image tag is the merge
  commit SHA: `gcloud run revisions describe REVISION_NAME --region=$R --project=$P
  --format='value(spec.containers[0].image)'`).
- While traffic is pinned, new deploys from `main` create revisions that get **no**
  traffic, and the backend workflow's version check reads the pinned revision and fails.
  After the fix merges: `gcloud run services update-traffic $API --region=$R --project=$P
  --to-latest`.
- Revert the bad PR on `main` too (`git revert`, PR, merge); otherwise the next deploy
  ships it again.
- Pre-v0.13 revisions need minimum one instance and always-on CPU; do not roll back past
  the queued-dispatch migration (`docs/contracts/queued-dispatch.md`).

### Pause and resume queued dispatch

Stops new work (extraction, sourcing, chat) from running; saved jobs stay pending.

```sh
gcloud tasks queues pause bharat-sourcer --location=$R --project=$P
gcloud scheduler jobs pause bharat-sourcer-reconcile --location=$R --project=$P
# resume
gcloud tasks queues resume bharat-sourcer --location=$R --project=$P
gcloud scheduler jobs resume bharat-sourcer-reconcile --location=$R --project=$P
gcloud scheduler jobs run bharat-sourcer-reconcile --location=$R --project=$P   # redispatch now
```

Tasks keep up to 200 attempts over one day; work paused longer than that relies on the
scheduler sweep to redispatch. The sweep also runs the retention pass (v0.43.0+), so a
long scheduler pause delays project deletion.

### Raise limits

```sh
# Instances (integration was raised to 3 on 7 Oct 2026; web: check describe)
gcloud run services update $API --region=$R --project=$P --max-instances=5
# Queue throughput (set by scripts/enable_queued_dispatch.py: 2 concurrent, 2/s)
gcloud tasks queues update bharat-sourcer --location=$R --project=$P --max-concurrent-dispatches=4 --max-dispatches-per-second=4
# Env-driven limits (each update creates a new revision)
gcloud run services update $API --region=$R --project=$P --update-env-vars=BS_SWEEP_LIMIT=400
# Values containing commas need a custom delimiter
gcloud run services update $API --region=$R --project=$P '--update-env-vars=^@^BS_GEMINI_SITE_MODELS={"chat_scope":"gemini-3.1-flash-lite","judge":"gemini-3.1-flash-lite"}'
# Current values
gcloud run services describe $API --region=$R --project=$P --format='yaml(spec.template.spec.containerConcurrency,spec.template.metadata.annotations,spec.template.spec.containers[0].env)'
```

`scripts/deploy_integration.py` resets `--max-instances=1` and rewrites env vars other than
the auth and `BS_COMPILE_*` ones. Image deploys from GitHub Actions keep everything.
Raising limits raises cost; see [cost guardrails](cost-guardrails.md).

<a id="uptime-failure"></a>
## uptime-failure

**Means:** an uptime check could not load the site or API health.

**First 5 minutes**

```sh
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' https://bharatsourcer.web.app/
curl -sS -w '\n%{http_code} %{time_total}s\n' https://bharatsourcer.web.app/api/health
curl -sS -w '\n%{http_code} %{time_total}s\n' https://bharat-sourcer-integration-diahnrbuna-el.a.run.app/health
gcloud run services describe $API --region=$R --project=$P --format='yaml(status.conditions,status.traffic)'
gcloud run services describe $WEB --region=$R --project=$P --format='yaml(status.conditions,status.traffic)'
gcloud logging read "resource.type=\"cloud_run_revision\" AND severity>=ERROR" --project=$P --freshness=15m --limit=30 --format='table(timestamp,resource.labels.service_name,resource.labels.revision_name,textPayload,jsonPayload.message)'
```

Use `/health`, not `/healthz`, on the `run.app` URL: Google's edge intercepts paths ending
in `z` there. The web proxy maps `/api/health` and `/api/healthz` to backend `/health`.

**Likely causes**

- Bad deploy: new revision fails to start (look for `STARTUP` probe or import errors in the
  newest revision's logs; compare with the latest GitHub Actions run).
- Cold start after min instances went back to 0 (planned 7 Nov 2026) and a slow first
  request; repeats only on idle periods.
- Firebase Hosting rewrite to `bharat-sourcer-web` broken (site loads on the `run.app` URL
  but not on `bharatsourcer.web.app`).
- Google Cloud regional incident in `asia-south1`.

**Mitigate:** roll back the failing service ([above](#roll-back-a-cloud-run-revision)).
For hosting only, redeploy Firebase Hosting from the last good commit.

**Escalate:** down more than 10 minutes, or rollback does not restore it: SEV1, owner
paged. A Google incident: follow status.cloud.google.com and post status.

<a id="high-5xx"></a>
## high-5xx

**Means:** the share of 5xx responses on user-facing routes crossed the alert threshold.

**First 5 minutes**

```sh
# User-facing 5xx by service, route and revision
gcloud logging read "$REQ AND httpRequest.status>=500 AND NOT httpRequest.requestUrl:\"/internal/\"" --project=$P --freshness=30m --limit=50 --format='table(timestamp,resource.labels.service_name,resource.labels.revision_name,httpRequest.status,httpRequest.requestMethod,httpRequest.requestUrl)'
# App-side exceptions (route template, exception class)
gcloud logging read "$APP AND jsonPayload.event=\"UNHANDLED_ERROR\"" --project=$P --freshness=30m --limit=30 --format='table(timestamp,jsonPayload.route,jsonPayload.type)'
# Web proxy failures (backend unreachable or 502/503/504)
gcloud logging read 'resource.labels.service_name="bharat-sourcer-web" AND jsonPayload.event="PROXY_ERROR"' --project=$P --freshness=30m --limit=30 --format='table(timestamp,jsonPayload.route,jsonPayload.reason,jsonPayload.upstream_status,jsonPayload.error)'
```

Request URLs in Cloud Run's request log can contain share tokens; do not paste them into
tickets or chat.

**Likely causes**

- Bad deploy: errors start at the new revision (`revision_name` column).
- Firestore errors: `UNHANDLED_ERROR` with `google.api_core` types (`ServiceUnavailable`,
  `DeadlineExceeded`, `Aborted`), or `StorageError` (job over 800 KB).
- Instance saturation: Cloud Run 429/503 "no available instance" at max instances
  (concurrency 20).
- Web 502 with `reason=fetch_failed`: backend cold start or down; see
  [uptime-failure](#uptime-failure).

**Mitigate:** bad deploy: [roll back](#roll-back-a-cloud-run-revision). Saturation:
[raise max instances](#raise-limits). Firestore: check
[Firestore status](https://status.cloud.google.com/) and pause dispatch to cut load.

**Escalate:** above threshold for 15 minutes or most requests failing: SEV1/SEV2.

<a id="high-latency"></a>
## high-latency

**Means:** user-facing request latency is above target (SLO: 95% of requests under 1 s).

**First 5 minutes**

```sh
gcloud logging read "$REQ AND resource.labels.service_name=\"$API\" AND httpRequest.latency>\"1s\" AND NOT httpRequest.requestUrl:\"/internal/\" AND NOT httpRequest.requestUrl:\"/stream\"" --project=$P --freshness=30m --limit=50 --format='table(timestamp,resource.labels.revision_name,httpRequest.latency,httpRequest.status,httpRequest.requestUrl)'
# Slow Gemini calls (some routes call Gemini in the request)
gcloud logging read "$APP AND jsonPayload.event=\"GEMINI_CALL\" AND jsonPayload.duration_ms>20000" --project=$P --freshness=30m --limit=30 --format='table(timestamp,jsonPayload.site,jsonPayload.route,jsonPayload.duration_ms,jsonPayload.attempts,jsonPayload.outcome)'
gcloud run services describe $API --region=$R --project=$P --format='value(spec.template.metadata.annotations)'
```

Check the API metrics page: request latencies (p50/p95/p99), container instance count,
and startup latency.

**Likely causes**

- Cold starts: min instances reverted to 0 (planned 7 Nov 2026,
  [README](README.md#demo-and-judging-scaling-approved-7-october-2026)); slow requests
  cluster after idle periods.
- Saturation: instance count pinned at max instances, CPU high.
- Gemini slow or retrying (`attempts`>1) on routes that wait for it.
- Firestore latency (slow reads across all routes, not one route).
- Bad deploy adding work to a hot route.

**Mitigate:** cold starts: `gcloud run services update $API --region=$R --project=$P
--min-instances=1` (about $0.33/day per service; record it in
[cost guardrails](cost-guardrails.md)). Saturation: [raise limits](#raise-limits). Bad
deploy: [roll back](#roll-back-a-cloud-run-revision).

**Escalate:** p95 above 5 s for 30 minutes, or SLO burn alert also firing: SEV2.

<a id="slo-burn"></a>
## slo-burn

**Means:** an SLO's error budget is burning faster than allowed. The alert names the SLO.

**First 5 minutes**

- Open the [SLOs page](https://console.cloud.google.com/monitoring/services?project=hackathon-510415);
  note which SLO, burn rate and remaining budget.
- Go to the matching runbook: API or web availability: [high-5xx](#high-5xx) and
  [uptime-failure](#uptime-failure); API latency: [high-latency](#high-latency); job
  success: [job-failures](#job-failures).
- Check for a deploy in the last hour on
  [GitHub Actions](https://github.com/Dawn-Of-Justice/bharat-sourcer/actions).

**Likely causes:** as in the linked runbook. A fast burn right after a merge is almost
always the deploy.

**Mitigate:** as in the linked runbook. Apply the [error-budget policy](slos.md#error-budget-policy)
if the budget is spent.

**Escalate:** fast-burn (budget gone in under a day): SEV2. Budget spent: owner decides on
a deploy freeze.

<a id="job-failures"></a>
## job-failures

**Means:** the share of non-demo jobs ending `failed` is above threshold (SLO: 95% done).

**First 5 minutes**

```sh
# Failed jobs by error code
gcloud logging read "$APP AND jsonPayload.event=\"JOB_FINISHED\" AND jsonPayload.status=\"failed\" AND jsonPayload.demo=false" --project=$P --freshness=1h --limit=50 --format='table(timestamp,jsonPayload.job_id,jsonPayload.code,jsonPayload.part_count,jsonPayload.prior_finishes)'
# Failing stages
gcloud logging read "$APP AND jsonPayload.event=\"STAGE_FINISHED\" AND jsonPayload.outcome=\"failed\"" --project=$P --freshness=1h --limit=50 --format='table(timestamp,jsonPayload.stage,jsonPayload.kind,jsonPayload.code,jsonPayload.job_id)'
# Extraction attempts per route
gcloud logging read "$APP AND jsonPayload.event=\"EXTRACTION_ATTEMPT_FAILED\"" --project=$P --freshness=1h --limit=30 --format='table(timestamp,jsonPayload.noun,jsonPayload.route,jsonPayload.code)'
```

One job in detail, from `backend/`: `.venv/Scripts/python scripts/inspect_job.py JOB_ID`.

**Likely causes (by `code`)**

| Code | Usual cause |
| --- | --- |
| `EXTRACTION_FAILED`, `UPSTREAM_TIMEOUT` | Gemini quota, overload or timeout: see [gemini-errors](#gemini-errors) |
| `NO_BOM` | Source has no parts list; a spike means a source type broke (GitHub, Instructables, video) |
| `EXTRACTION_INTERRUPTED`, `SOURCING_INTERRUPTED` | Instance killed mid-work: deploy during jobs, OOM at 512 MiB, lease expiry |
| Sourcing lines `failed` | Seller sites blocking (see `SELLER_FETCH` below) or Gemini discovery errors |

```sh
gcloud logging read "$APP AND jsonPayload.event=\"SELLER_FETCH\" AND (jsonPayload.outcome=\"blocked\" OR jsonPayload.outcome=\"cooldown\" OR jsonPayload.outcome=\"http_error\" OR jsonPayload.outcome=\"timeout\")" --project=$P --freshness=1h --limit=50 --format='table(timestamp,jsonPayload.host,jsonPayload.outcome,jsonPayload.http_status)'
```

**Mitigate:** bad deploy: [roll back](#roll-back-a-cloud-run-revision). Gemini: see
[gemini-errors](#gemini-errors). OOM: `gcloud run services update $API --region=$R
--project=$P --memory=1Gi`. Seller blocking: nothing to force; the host cooldown
(`BS_SELLER_BLOCKED_COOLDOWN_S`, 1,800 s) applies; do not raise request rates.

**Escalate:** most new jobs failing for 30 minutes: SEV2. One source type or seller only:
SEV3, ticket.

<a id="gemini-errors"></a>
## gemini-errors

**Means:** Gemini calls ending `quota`, `timeout`, `error` or `invalid` crossed threshold.

**First 5 minutes**

```sh
gcloud logging read "$APP AND jsonPayload.event=\"GEMINI_CALL\" AND jsonPayload.outcome!=\"ok\"" --project=$P --freshness=30m --limit=100 --format='table(timestamp,jsonPayload.site,jsonPayload.model,jsonPayload.route,jsonPayload.outcome,jsonPayload.http_status,jsonPayload.attempts)'
```

Group by `route` (`vertex` or `api_key`), `http_status` and `model`. Check
[quotas](https://console.cloud.google.com/iam-admin/quotas?project=hackathon-510415)
(Vertex AI) and the Gemini API key's usage page in AI Studio.

**Likely causes**

- `429` / `quota`: per-minute or daily quota on the API key or Vertex pool.
- `503`, `timeout`: model overloaded (common on new models at peak).
- `404`: model id retired or renamed (`BS_GEMINI_MODEL`, `BS_GEMINI_SITE_MODELS`).
- `403`, `401`: key revoked, API disabled, or the runtime account lost
  `roles/aiplatform.user`.
- `invalid`: truncated (`MAX_TOKENS`) or blocked answers; usually one site.

**Mitigate**

- Quota on one route: move sites to the other pool. Vertex sites are
  `BS_GEMINI_VERTEX_SITES` (JSON list; use the `^@^` delimiter from
  [raise limits](#raise-limits)).
- Overload: route heavy sites to a lighter model with `BS_GEMINI_SITE_MODELS`.
- Retry storm: [pause dispatch](#pause-and-resume-queued-dispatch) until the provider recovers.
- Request a quota increase in the console.
- Retired model: set a current model id and redeploy env.

**Escalate:** all routes failing 15 minutes (jobs cannot complete): SEV2. Key or IAM
revoked: owner immediately.

<a id="gemini-spend"></a>
## gemini-spend

**Means:** estimated Gemini spend (`usd_est` from `GEMINI_USAGE`) crossed its threshold.
This is an estimate, not the bill; the [billing budget](cost-guardrails.md#billing-budget)
is the bill.

**First 5 minutes**

```sh
# from backend/: per-site and per-job totals from Cloud Logging
.venv/Scripts/python scripts/usage_report.py --days 1
gcloud logging read "$APP AND jsonPayload.message:\"GEMINI_USAGE\" AND jsonPayload.usd_est>0.02" --project=$P --freshness=6h --limit=50 --format='table(timestamp,jsonPayload.site,jsonPayload.model,jsonPayload.total,jsonPayload.search_queries,jsonPayload.usd_est,jsonPayload.job_id)'
# Job-level cost at finish
gcloud logging read "$APP AND jsonPayload.event=\"JOB_FINISHED\" AND jsonPayload.usd_est>0.2" --project=$P --freshness=24h --limit=30 --format='table(timestamp,jsonPayload.job_id,jsonPayload.usd_est,jsonPayload.prior_finishes)'
```

**Likely causes**

- Traffic spike within quotas (many jobs, one heavy user or IP at its cap).
- Repeated work: at-least-once redelivery repeating billed calls, a job finishing again and
  again (`prior_finishes` growing), refresh loops.
- Cache off or failing (`CACHE_READ_FAILED`, `BS_CACHE_ENABLED`).
- A model change to a pricier model, or the 2027-01-01 price change.

**Mitigate:** [cut cost fast](cost-guardrails.md#cut-cost-fast): lower
`BS_GLOBAL_DAILY_ACTIONS` and `BS_JOB_GEMINI_BUDGET_USD`, turn off optional stages, pause
dispatch.

**Escalate:** spend rate would exceed the monthly budget within days: owner, SEV2.

<a id="error-burst"></a>
## error-burst

**Means:** many `ERROR`-severity log lines in a short window.

**First 5 minutes**

```sh
gcloud logging read "resource.type=\"cloud_run_revision\" AND severity>=ERROR" --project=$P --freshness=15m --limit=100 --format='table(timestamp,resource.labels.service_name,resource.labels.revision_name,jsonPayload.event,jsonPayload.type,jsonPayload.route)'
```

| Event | Points at |
| --- | --- |
| `UNHANDLED_ERROR` | Bug or dependency error on a route: see [high-5xx](#high-5xx) |
| `TASK_ENQUEUE_FAILED` | Cloud Tasks unreachable, queue deleted, or `roles/cloudtasks.enqueuer` lost; jobs saved but wait for the sweep |
| `SWEEP_READ_FAILED` | Firestore reads failing |
| `PROXY_ERROR` | Web proxy cannot reach the backend |

**Likely causes:** bad deploy, Firestore incident, Cloud Tasks IAM or quota change.

**Mitigate:** bad deploy: [roll back](#roll-back-a-cloud-run-revision). IAM:
`gcloud tasks queues get-iam-policy bharat-sourcer --location=$R --project=$P` and re-run
`scripts/enable_queued_dispatch.py` to restore bindings (it redeploys the API with min 0,
max 1; raise max afterwards).

**Escalate:** burst continues 15 minutes with user impact: SEV2; no user impact: SEV3.

<a id="queue-stuck"></a>
## queue-stuck

**Means:** `QUEUE_AGE_EXCEEDED` (pending work older than `BS_QUEUE_AGE_ALERT_MINUTES`,
default 30) or `SWEEP_TRUNCATED` (sweep hit `BS_SWEEP_LIMIT`, default 200). Existing policy:
[queue-age-alert.json](queue-age-alert.json).

**First 5 minutes**

```sh
gcloud logging read "$APP AND (jsonPayload.event=\"QUEUE_AGE_EXCEEDED\" OR jsonPayload.event=\"SWEEP_TRUNCATED\")" --project=$P --freshness=1h --limit=50 --format='table(timestamp,jsonPayload.event,jsonPayload.job_id,jsonPayload.kinds,jsonPayload.age_s,jsonPayload.limit)'
gcloud tasks queues describe bharat-sourcer --location=$R --project=$P
gcloud tasks list --queue=bharat-sourcer --location=$R --project=$P --limit=20
gcloud scheduler jobs describe bharat-sourcer-reconcile --location=$R --project=$P --format='yaml(state,status,lastAttemptTime,schedule)'
# Worker deliveries and their status
gcloud logging read "$REQ AND resource.labels.service_name=\"$API\" AND httpRequest.requestUrl:\"/internal/\"" --project=$P --freshness=30m --limit=30 --format='table(timestamp,httpRequest.status,httpRequest.latency,httpRequest.requestUrl)'
```

One job: `.venv/Scripts/python scripts/inspect_job.py JOB_ID` from `backend/`.

**Likely causes**

- Queue or scheduler left paused (`state: PAUSED`).
- Backlog: queue throughput (2 concurrent) or max instances too low for the load.
- Worker always answering 503 for a job (lease never released) or 401/403 (OIDC identity
  `bharat-sourcer-tasks@` changed).
- Firestore errors (`SWEEP_READ_FAILED`).
- Scheduler failing (non-OK `status`), so lost enqueues are never redispatched.

**Mitigate:** resume and run the sweep ([commands](#pause-and-resume-queued-dispatch)).
Backlog: [raise queue throughput, max instances and `BS_SWEEP_LIMIT`](#raise-limits). One
job looping: inspect it; let its lease expire (recovery runs once per job) rather than
editing Firestore by hand.

**Escalate:** jobs older than 2 hours or growing backlog after resume: SEV2.
