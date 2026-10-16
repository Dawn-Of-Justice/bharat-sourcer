# Monitoring: metrics, SLOs, alerts, dashboard and budget

Monitoring for production is kept as code. The specs live in [`monitoring/`](monitoring/) and
`scripts/setup_monitoring.py` applies them to project `hackathon-510415`. Every notification goes
to the existing email channel `projects/hackathon-510415/notificationChannels/16148970600683421140`
("Bharat Sourcer owner"). Each alert's documentation links a section of
[`runbooks.md`](runbooks.md), which is maintained separately.

The app events these metrics read (`JOB_FINISHED`, `STAGE_FINISHED`, `GEMINI_CALL`,
`GEMINI_USAGE`, `SELLER_FETCH`, `PROXY_ERROR`, `UNHANDLED_ERROR`, ...) are defined in
[observability.md](observability.md).

| File | Contents |
| --- | --- |
| `monitoring/log-metrics.json` | 9 log-based metrics (Logging v2 `LogMetric` bodies) |
| `monitoring/uptime-checks.json` | 2 uptime checks |
| `monitoring/services.json` | 3 custom services, each with its SLOs |
| `monitoring/alerts/*.json` | 11 alert policies, one per file (`queue-age.json` is the former `infra/queue-age-alert.json`) |
| `monitoring/dashboard.json` | Dashboard "Bharat Sourcer — production" |
| `monitoring/budget.json` | Monthly billing budget. Its amount and project number are set by the script |

## Applying

From `backend/`, signed in with an owner gcloud account:

```powershell
.venv/Scripts/python scripts/setup_monitoring.py              # plan only: CREATE / UPDATE / OK per resource
.venv/Scripts/python scripts/setup_monitoring.py --validate   # plan plus read-only API checks of every spec
.venv/Scripts/python scripts/setup_monitoring.py --apply      # make the changes
.venv/Scripts/python scripts/setup_monitoring.py --apply --budget-inr 3000
```

The script is idempotent. It matches log metrics by name, services and SLOs by id, and uptime
checks, alert policies, the dashboard and the budget by displayName. It updates a match in place
and never creates a duplicate. For each UPDATE the plan lists the fields that differ. Edit the JSON
files, then run the script again. Resources are applied in dependency order: metrics, uptime
checks, services and SLOs, alerts, dashboard, then budget.

The script uses the REST APIs (Monitoring v3 and v1, Logging v2, Billing Budgets v1) with
`gcloud auth print-access-token`, so no `gcloud alpha` commands or comma-separated arguments are
needed.

Only dashboards have an API dry run, so `--validate` checks the rest by other read-only means:

- log filters through `entries.list`, which also shows sample matches from the last 24 h;
- PromQL queries through the Prometheus query API;
- monitoring filters through `timeSeries.list`;
- the dashboard through `dashboards.create?validateOnly=true`;
- the structure of every spec: required fields, label/extractor agreement, no `job_id`,
  `line_id` or `host` labels, at least 3 uptime regions, and a runbook link in every alert.

Filters on log metrics or SLOs that do not exist yet are reported as `PEND`, not as failures.

The budget step needs the Billing Budget API (`billingbudgets.googleapis.com`) enabled on the
project. When it is disabled, the plan says so and `--apply` enables it. Creating the budget also
needs Billing Account Administrator or Billing Account Costs Manager on billing account
`01E92D-DB8A9B-6BFD7E`, whose currency is INR. Without those rights the script prints a clear
SKIP line and finishes the other sections.

## Log-based metrics

All metrics read `resource.type="cloud_run_revision"`. Metric type in Monitoring:
`logging.googleapis.com/user/<name>`. In PromQL: `logging_googleapis_com:user_<name>`, with
`_bucket`, `_count` and `_sum` for distributions.

| Metric | Kind | Source | Labels | Meaning |
| --- | --- | --- | --- | --- |
| `job_duration_ms` | distribution, ms (1 s to about 37 min, ×1.5 buckets) | `JOB_FINISHED` with `prior_finishes=0` | `status`, `demo` | Time from job creation to its first finish. Includes the time the user took to confirm the parts list |
| `job_finished_count` | counter | every `JOB_FINISHED` | `status`, `code`, `demo` | Job outcomes. `code` is the failure code (`EXTRACTION_FAILED`, `NO_BOM`, `UPSTREAM_TIMEOUT`, `SOURCING_INTERRUPTED`, ...), a bounded set of about 20 values, and is empty when not failed |
| `gemini_call_duration_ms` | distribution, ms (100 ms to about 8 min) | `GEMINI_CALL` | `site`, `outcome` | Gemini latency per call site. `_count` by outcome gives the error rate |
| `gemini_cost_usd` | distribution, USD | `GEMINI_USAGE` `usd_est` | none | The app's cost estimate per call. `_sum` is spend. It is not Google's bill |
| `stage_duration_ms` | distribution, ms (10 ms to about 44 min) | `STAGE_FINISHED` | `stage`, `outcome` | Pipeline stage latency and outcomes |
| `seller_fetch_count` | counter | `SELLER_FETCH` | `outcome` | Seller page and search health (`blocked`, `timeout`, `cooldown`, ...) |
| `app_errors` | counter | app lines at `severity>=ERROR`, `UNHANDLED_ERROR` and `PROXY_ERROR` on both services | `service` | App error volume. Request-log lines are excluded because 5xx responses have their own alert |
| `api_request_count` | counter | Cloud Run request log (`run.googleapis.com/requests`) for the API, excluding `/internal/` and `/stream` | `status` (HTTP code) | Source for API availability and the API 5xx alert |
| `api_request_latency` | distribution, s (√2 buckets from 62.5 ms; 1 s, 2 s and 4 s are bucket bounds) | same request log and exclusions, from `httpRequest.latency` | none | Source for the API latency SLO, alerts and dashboard chart |

`host`, `job_id`, `line_id` and `route` are deliberately not labels. Search the logs for them.

### Why the API request metrics come from the request log

Cloud Run's built-in `run.googleapis.com/request_count` and `request_latencies` have no path
label, so they cannot exclude two kinds of requests:

- **`/internal/work`** answers **503 on purpose** to make Cloud Tasks retry unfinished work. From
  10 to 17 October 2026, all 77 sampled 5xx responses of `bharat-sourcer-integration` came from
  `/internal/work`. That was about 0.27% of all requests, more than half of a 99.5% error budget,
  with no user impact.
- **SSE streams** (`/v1/jobs/{id}/stream`) stay open for up to 60 s. They were about 1.7% of API
  requests, so with the built-in metric the API p99 sits at about 60 s all the time. Long
  `/internal/*` jobs add more slow requests.

The two `api_request_*` log metrics drop both kinds of request by `httpRequest.requestUrl`.
Request logs are already ingested, so these metrics add no log volume. Their samples are small and
low-cardinality.

## Uptime checks

| Check | Target | Pass condition |
| --- | --- | --- |
| Bharat Sourcer: web home | `https://bharatsourcer.web.app/` | HTTP 200 |
| Bharat Sourcer: API health via web | `https://bharatsourcer.web.app/api/healthz` (the web proxy forwards it to the API's `/health`) | HTTP 200 and the body contains `"status":"ok"` |

Both checks run every 5 min from `ASIA_PACIFIC`, `EUROPE` and `USA_VIRGINIA`, with a 30 s timeout
to allow for cold starts. That is about 52k executions a month, well inside the free 1M.

## SLOs (Service Monitoring)

Cloud Run services are not auto-detected as Monitoring services, so the script creates custom
services. All periods are rolling 28 days.

| Service / SLO id | Goal | Good / total |
| --- | --- | --- |
| `bharat-sourcer-api` / `api-availability` | 99.5% | `api_request_count` with status not 5xx, over all requests. Excludes `/internal/*` and SSE |
| `bharat-sourcer-api` / `api-latency` | 95% under 1 s | `api_request_latency` in [0, 1.0 s]. Excludes `/internal/*` and SSE |
| `bharat-sourcer-web` / `web-availability` | 99.5% | `run.googleapis.com/request_count` with `response_code_class` other than `5xx` on `bharat-sourcer-web` |
| `bharat-sourcer-jobs` / `job-success` | 95% | `job_finished_count`, `demo="false"`: `status="done"` over `status` in (`done`, `failed`) |

Latency threshold: in the week to 17 October 2026, 97.2% of all API requests finished under
1 s, SSE included. About 98.9% did once SSE is removed (the median is about 0.45 s), so
1 s at 95% leaves headroom without hiding regressions.

Job success excludes `paused`, which is a user action, not a failure. A resume, refresh or
re-confirm that finishes the job again counts as another finish.

## Alert policies

Every policy notifies the owner email channel and links its runbook section.

| Policy | Condition | Runbook |
| --- | --- | --- |
| uptime check failing | `check_passed` false from 2 or more locations for either check (20 min window) | `#uptime-failure` |
| API 5xx ratio high | `api_request_count` 5xx / all > 5% over 10 min, with at least 10 requests | `#high-5xx` |
| web 5xx ratio high | Cloud Run `request_count` 5xx / all > 5% over 10 min on `bharat-sourcer-web`, with at least 10 requests | `#high-5xx` |
| API latency high | `api_request_latency` p95 > 2 s **or** p99 > 5 s over 15 min, with at least 20 requests | `#high-latency` |
| API availability SLO burn | burn rate > 14.4 over 1 h (fast) or > 6 over 6 h (slow) | `#slo-burn` |
| job success SLO burn | same burn conditions on `job-success` | `#slo-burn` |
| job failure ratio high | non-demo `failed` / (`done`+`failed`) > 30% over 1 h, with at least 3 jobs | `#job-failures` |
| Gemini errors high | `GEMINI_CALL` outcome `error` or `timeout` > 20% of calls over 30 min, with at least 5 calls | `#gemini-errors` |
| Gemini spend high | `sum(increase(gemini_cost_usd_sum[1d]))` > $2 (rolling 24 h) | `#gemini-spend` |
| app error burst | `app_errors` > 10 in 5 min on one service | `#error-burst` |
| stuck sourcing queue | log match on `QUEUE_AGE_EXCEEDED` / `SWEEP_TRUNCATED`, at most 1 notification per hour (unchanged; runbook link added) | `#queue-stuck` |

Ratio, quantile and spend conditions use PromQL (`conditionPrometheusQueryLanguage`, with
`disableMetricValidation` so they can be created before the first log line arrives). The minimum
volume guards stop a single failed request or job from paging at night.

Burn rate is how fast the error budget is being spent compared with a steady pace. 14.4 over 1 h
uses 2% of the 28-day budget in an hour. 6 over 6 h uses about 5% in six hours.

The rolling 24 h sum on the cost distribution's `_sum` series works: it was checked with the same
query shape on `run.googleapis.com/request_latencies_sum`. The 1 h / $0.50 fallback in the brief
was therefore not needed.

## Dashboard: "Bharat Sourcer — production"

Ordered by importance:

1. **Health**: uptime check status, then compliance and error budget left for each SLO.
2. **API** and **Web**, each with:
   - requests/s by status class;
   - p50/p95/p99 latency in seconds (Cloud Run's `request_latencies`, which is in ms, divided by
     1000);
   - 5xx ratio;
   - instances (active and idle);
   - container CPU and memory utilization (p50 and p95).

   The API also has a latency chart that excludes SSE and `/internal/*`. That chart is the source
   for the latency alert.
3. **Jobs**:
   - jobs finished by status;
   - job duration p50/p95/p99 (non-demo, first finish);
   - stage p95 by stage;
   - Gemini p95 by site;
   - Gemini calls by outcome;
   - seller fetches by outcome;
   - app errors by service.
4. **Cost**: Gemini estimated cost, rolling 24 h and per hour.

### Reading p50, p95 and p99

- **p50** is the median: what a typical request or job feels like.
- **p95** is the time that 1 request in 20 exceeds. It is the best signal of a real slowdown, and
  the latency SLO and the 2 s alert use it.
- **p99** is the time that 1 request in 100 exceeds. It catches tail problems such as cold
  starts, retries and a slow seller or Gemini call. At low traffic a few requests can move it a
  lot, so treat a p99 spike without a p95 change as noise unless it persists.
- On the **Cloud Run latency charts of both services** (labelled "includes SSE streams"), p99 sits
  near 60 s, and sometimes p95 does too, because SSE streams stay open that long. That is
  expected. Use the API chart that excludes SSE for real latency.
- Job and stage durations measure the pipeline, not HTTP. Job duration also includes time the
  user spent confirming the parts list.

## Billing budget

The budget is "Bharat Sourcer: monthly cost guardrail" on billing account `01E92D-DB8A9B-6BFD7E`:

- scope: project `hackathon-510415` only, calendar month, credits included;
- amount: `--budget-inr`, default 2000 INR;
- thresholds: 50%, 90% and 100% of actual spend, and 100% of forecast spend;
- notifications: billing account admins by email (default IAM recipients), plus the monitoring
  email channel.

A budget only notifies. It does not stop spending.

## Cost of this setup

- **Uptime checks:** about 52k executions a month, inside the free tier.
- **Log-based metrics:** 9 metrics, all low-cardinality. The highest is `gemini_call_duration_ms`
  (site × outcome, a few dozen active series). Points are written only in minutes with traffic,
  so ingestion stays well under the free 150 MiB a month at current volume.
- **Alerting:** 14 conditions at $0.10 per condition per month (pricing from 1 May 2026) comes to
  about $1.40 a month. PromQL alerts also bill query execution, which is negligible at these
  evaluation intervals.
- **Dashboards, services and SLOs:** free.

## Known limitations

- **Event metrics need the instrumentation deployed.** On 17 October 2026 no lines with
  `jsonPayload.event` existed yet in production (the `obs/instrumentation` change was still
  merging), so the job, stage, Gemini, seller and app-error panels stay empty until it is
  deployed.
- **Log-based metrics do not backfill.** They count from the moment they are created, so SLOs and
  charts start empty and the 28-day windows fill over four weeks.
- **`api_request_latency` reads `httpRequest.latency` with
  `REGEXP_EXTRACT(httpRequest.latency, "([0-9.]+)")`.** The request log renders the field as a
  string such as `"0.152961420s"`, and Logging converts fields to strings before the regex.
  Confirm after `--apply` that the API latency chart shows data in seconds.
- **Path exclusion is a substring match.** Any URL containing `/stream` or `/internal/` is
  excluded from the API request metrics. Today only the SSE route and the worker routes match.
- **Web availability uses Cloud Run's metric**, so it includes the proxied SSE stream and passes
  backend 5xx responses through. `/internal/*` is never reached through the web service.
- **SLO burn alerts at low volume:** with few jobs, a single failure can exceed the job-success
  fast-burn threshold. The job failure ratio alert has a 3-job minimum. The burn alerts do not.
- **Gemini error alert:** it counts only `error` and `timeout`. `quota` and `invalid` are visible on
  the outcomes chart but do not page.
- **Gemini spend is an estimate** (see [gemini-cost.md](gemini-cost.md)), over a rolling 24 h rather
  than a calendar day. The billing budget covers the real bill.
- **No dry run** exists for log metrics, uptime checks, services, SLOs, alert policies or budgets.
  `--validate` checks them only through read APIs and structure checks. SLO and `select_slo_*`
  filters can be checked only after the first apply.
