# Service level objectives

SLO resources and burn-rate alerts are created by `backend/scripts/setup_monitoring.py`
(documented in [monitoring.md](monitoring.md)). If the SLI filters
there differ from this page, the script is what runs; update this page.

## SLOs

| SLO | Target | Window | SLI (good / valid) |
| --- | --- | --- | --- |
| API availability | 99.5% | 28 days rolling | Non-5xx / all requests to `bharat-sourcer-integration` |
| Web availability | 99.5% | 28 days rolling | Non-5xx / all requests to `bharat-sourcer-web` (serves <https://bharatsourcer.web.app> through Firebase Hosting) |
| API latency | 95% of requests < 1 s | 28 days rolling | Requests under 1 s / all requests to `bharat-sourcer-integration`, excluding `/internal/*` and SSE `/stream` (`api_request_latency`, seconds) |
| Job success | 95% of non-demo jobs `done` | 28 days rolling | `JOB_FINISHED` with `status="done"` / `JOB_FINISHED` with `status` `done` or `failed`, `demo=false` |

Error budgets over 28 days: 99.5% allows about 3 h 22 min of full outage or 0.5% of
requests failing; latency allows 5% of requests over 1 s; job success allows 1 failed job
in 20.

### Rationale

- **99.5%, not higher.** Single region, scale-to-zero, a small team without on-call, and
  paid upstreams (Gemini, seller sites) we do not control. 99.5% catches real outages
  without paging on every cold start or provider blip.
- **Latency 1 s at p95.** Most API calls are Firestore reads and writes; heavy work
  (extraction, sourcing, chat) runs in Cloud Tasks, not in the user's request. A user
  request over 1 s usually means a cold start, saturation or a regression.
- **Job success 95%.** A job is the product's unit of value. Some failures are correct
  answers (`NO_BOM` for a page with no parts list), so 100% is not the goal. Demo jobs are
  fixtures and excluded. `paused` is a user action and excluded.

### Known measurement caveats

- `/internal/work` returns 503 on purpose so Cloud Tasks retries unfinished work, and runs
  up to 1,800 s. Cloud Run's built-in `request_count` and `request_latencies` metrics have
  no path label, so an SLI built on them counts these. Prefer a log-based SLI on the
  request log that excludes `httpRequest.requestUrl:"/internal/"`; otherwise expect noise.
- `/v1/jobs/{job_id}/stream` (SSE) stays open about 60 s by design; exclude it from latency.
- Job success counts every finish, including re-finishes after resume or refresh
  (`prior_finishes>0`). For a first-run view filter `prior_finishes=0`.
- Uptime checks measure reachability from Google's probes, not user experience.

## Error-budget policy

| Budget state (28 days) | Action |
| --- | --- |
| > 50% left | Normal releases. |
| 25–50% left | Each release needs the full [release checklist](release-checklist.md) and someone watching the 15-minute window. |
| < 25% left | Only fixes, reliability work and low-risk changes (docs, copy). No new Gemini call sites, scaling changes or dependency major bumps. |
| Spent (0%) | **Freeze risky deploys** until the budget is positive again or the owner grants an exception in writing (PR comment). Reliability work goes first in the next plan. A postmortem is required for the incident(s) that spent it. |
| One incident uses > 20% | Postmortem required, whatever the remaining budget. |

Security fixes and rollbacks are always allowed. The owner can override the freeze; record
the reason in the PR.

## Measuring p50, p95, p99

**Request latency (Cloud Run).** Metric `run.googleapis.com/request_latencies`
(distribution, milliseconds), per `service_name` and `revision_name`. In Metrics Explorer
pick the metric, filter the service, aligner "delta", reducer 50th / 95th / 99th
percentile. Same on the service's metrics page:
[API](https://console.cloud.google.com/run/detail/asia-south1/bharat-sourcer-integration/metrics?project=hackathon-510415),
[web](https://console.cloud.google.com/run/detail/asia-south1/bharat-sourcer-web/metrics?project=hackathon-510415).
Includes `/internal/work` and SSE, so p99 is inflated (see caveats).

MQL example (API p95, 5-minute windows):

```text
fetch cloud_run_revision
| metric 'run.googleapis.com/request_latencies'
| filter resource.service_name == 'bharat-sourcer-integration'
| align delta(5m)
| every 5m
| group_by [], [p95: percentile(value.request_latencies, 95)]
```

**Pipeline latency (log-based distributions).** Created from structured events
([observability.md](observability.md)):

| Distribution | Filter | Value field | Labels |
| --- | --- | --- | --- |
| Job time to finish | `jsonPayload.event="JOB_FINISHED" AND jsonPayload.demo=false AND jsonPayload.prior_finishes=0` | `jsonPayload.total_duration_ms` | `status`, `code` |
| Stage duration | `jsonPayload.event="STAGE_FINISHED"` | `jsonPayload.duration_ms` | `stage`, `outcome` |
| Gemini call latency | `jsonPayload.event="GEMINI_CALL"` | `jsonPayload.duration_ms` | `site`, `route`, `outcome` |
| Seller fetch latency | `jsonPayload.event="SELLER_FETCH" AND jsonPayload.outcome!="cache"` | `jsonPayload.duration_ms` | `host`, `outcome` |

Read percentiles in Metrics Explorer on `logging.googleapis.com/user/<metric name>` with a
percentile reducer. `total_duration_ms` includes time waiting for the user to confirm the
parts list, so it measures the user journey, not machine time.

Ad hoc, from logs:

```sh
gcloud logging read 'resource.labels.service_name="bharat-sourcer-integration" AND jsonPayload.event="STAGE_FINISHED" AND jsonPayload.stage="extraction"' --project=hackathon-510415 --freshness=1d --limit=1000 --format='value(jsonPayload.duration_ms)' | sort -n | awk '{a[NR]=$1} END {print "p50",a[int(NR*0.5)],"p95",a[int(NR*0.95)],"p99",a[int(NR*0.99)]}'
```

## Review cadence

- **Weekly (15 min):** budget remaining per SLO, alerts fired, top failure codes from
  `JOB_FINISHED`. Note it in the team channel.
- **Monthly:** check targets against reality; adjust thresholds that page without action.
- **Quarterly:** revisit targets and SLIs together with the backup restore drill
  (`backups.md`). Record changes in a PR to this file.
