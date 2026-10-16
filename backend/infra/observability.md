# Observability: structured logs and app events

This is the contract for log-based metrics on the two Cloud Run services,
`bharat-sourcer-integration` (backend) and `bharat-sourcer-web` (web server and API proxy).
Event names, field names, types and units below are stable: change them only together with
any metric or alert built on them.

Cost: no new service, agent or exporter. Lines go to stdout, which Cloud Run already ships to
Cloud Logging; log-based metrics and the Logs Explorer read them. Cloud Run's own request log
and built-in metrics keep covering request count and latency, so the app adds only what Cloud
Run cannot see: job, stage, Gemini and seller-fetch outcomes and durations. The added volume
is a few lines per pipeline stage and one per Gemini call or seller fetch.

## Log line format (backend)

`bharat_sourcer/observability.py` formats every app line. On Cloud Run (`K_SERVICE` is set)
or with `BS_LOG_FORMAT=json`, each line is one JSON object; otherwise lines stay plain text
(`LEVEL logger message`, and usage lines as `GEMINI_USAGE {json}`). `BS_LOG_FORMAT=text`
forces plain text on Cloud Run.

| Field | Type | Meaning |
| --- | --- | --- |
| `severity` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `message` | string | The event tag first, then details: `GEMINI_CALL {json}`, `QUEUE_AGE_EXCEEDED job=... age_s=...`. A traceback, when logged, follows on new lines. Existing filters such as `jsonPayload.message:"QUEUE_AGE_EXCEEDED"` (`infra/queue-age-alert.json`) keep matching. |
| `event` | string | The event name: set by the event helpers, or taken from a leading `UPPER_SNAKE` tag of a legacy line. Absent on untagged lines. |
| `time` | string | RFC 3339 UTC timestamp with microseconds |
| `logger` | string | Python logger name (`bharat_sourcer.events` for the events below) |
| `logging.googleapis.com/trace` | string | `projects/<project>/traces/<32-hex trace id>` of the request being served |
| `logging.googleapis.com/spanId` | string | 16 hex characters, when the header carried a span |
| `logging.googleapis.com/trace_sampled` | boolean | The header's sampled flag, when present |
| event fields | various | Every field listed for an event below, as top-level keys of `jsonPayload` |

The trace is read from `X-Cloud-Trace-Context` (`TRACE_ID/SPAN_ID;o=1`, decimal span id
converted to hex; preferred because Cloud Run's request log uses it) or, failing that, W3C
`traceparent`. Malformed values are ignored. It is kept in a context variable for the whole
request, including sync routes, background tasks and the extraction, sourcing and seller-search
thread pools. Cloud Tasks deliveries (`/internal/work`) arrive with their own trace. The
project comes from `BS_GCP_PROJECT` (set on the service), else `GOOGLE_CLOUD_PROJECT`; without
one the trace fields are omitted.

Uvicorn's error logger uses the same formatter on Cloud Run and its access log is off there,
since Cloud Run's request log already records every request and access lines would carry raw
paths (share tokens). Locally uvicorn keeps its usual output.

Redaction runs on every message and string field, in both formats: `Bearer` tokens, Google
API keys (`AIza...`), JWTs, `name=value` / `"name": "value"` pairs whose name ends in token,
secret, password, api key, authorization or cookie, and email addresses are replaced; URLs
keep scheme, host and path and lose their query string and fragment.

## Events

Durations are integer milliseconds from `time.perf_counter()` (monotonic). `null` means not
known or not applicable. All events log at `INFO` from logger `bharat_sourcer.events`.

### JOB_FINISHED

One line each time a job moves into `done`, `failed` or `paused`, logged after the change is
saved (a Firestore transaction may run the change twice; the line is logged once). Not logged
when a finished job is saved again with the same status.

| Field | Type | Unit / values |
| --- | --- | --- |
| `job_id` | string | job UUID |
| `status` | string | `done`, `failed`, `paused` |
| `code` | string or null | error code when `failed` (for example `EXTRACTION_FAILED`, `UPSTREAM_TIMEOUT`, `NO_BOM`, `EXTRACTION_INTERRUPTED`, `SOURCING_INTERRUPTED`); null otherwise |
| `total_duration_ms` | integer | ms from the job's `created_at` to now. Includes time the job waited for the user to confirm the parts list |
| `part_count` | integer | BOM lines on the job |
| `demo` | boolean | fixture job (`BS_DEMO_MODE`); its results are labelled demo data |
| `prior_finishes` | integer | earlier `done`/`failed`/`paused` transitions of this job. `0` is the first finish; a resume, refresh or re-confirm finishes again with a larger value |
| `usd_est` | number or null | USD, the job's running Gemini cost estimate (`cost_estimate.total_usd`); an estimate, not Google's bill |

### STAGE_FINISHED

One line per pipeline stage run.

| Field | Type | Unit / values |
| --- | --- | --- |
| `job_id` | string or null | job UUID |
| `stage` | string | `extraction`, `reconcile`, `spec_fill`, `sourcing`, `overview`, `build_guide`, `chat` |
| `duration_ms` | integer | ms the stage took |
| `outcome` | string | see below |
| `kind` | string | `extraction` only: the source report kind (`video`, `instructables`, `github`, `adafruit`, `blog`, ...) |
| `line_id` | string | `sourcing` only: the BOM line |
| `code` | string or null | `extraction`: the `ExtractionError` code (or exception type) when failed; `sourcing`: the line's `sourcing_error.code`; `chat`: `CHAT_FAILED`; null otherwise |
| `changes` | integer | `reconcile` only: lines merged or removed |

Outcomes per stage:

| Stage | Where | `outcome` |
| --- | --- | --- |
| `extraction` | `intake._attempt`, one line per source read | `ok`, `failed` |
| `reconcile` | `JobService.extract`, when a reconciler is configured | `ok` (the stage never fails the job; a failed review logs `RECONCILE_FAILED` and keeps the list) |
| `spec_fill` | `JobService.extract`, when a spec filler is configured | `ok` (a failed fill logs `SPEC_FILL_FAILED` and keeps the questions) |
| `sourcing` | `JobService._source`, one line per sourced BOM line | the line's `sourcing_status`: `offers_found`, `no_verified_offers`, `failed`, `fabrication_service`, `already_owned` |
| `overview` | `OverviewService.generate` | the drawing's status before it is saved: `ready`, `failed` |
| `build_guide` | `BuildGuideService.generate` | the guide's status before it is saved: `ready`, `failed` |
| `chat` | `ConversationService.process` | `ok`, `failed` |

Lines skipped by the per-job part limit are not sourced and log no `sourcing` stage.

### GEMINI_CALL

One line per routed generateContent call, logged by `resilience.post_with_retry` (used by
every Gemini call site, directly or through `gemini_api.post_generate`). Retries on the same
route count as one call (`attempts`); a Vertex AI call that falls back to the API key logs
one line per route. Unlike `GEMINI_USAGE`, it is also logged for timeouts, quota and HTTP
errors, so latency and outcome metrics use this event alone.

| Field | Type | Unit / values |
| --- | --- | --- |
| `site` | string | call site, as in `BS_GEMINI_VERTEX_SITES` and the site model settings: `discovery`, `research`, `judge`, `spec`, `buyer`, `cart_recipe`, `fabrication`, `spec_fill`, `reconcile`, `extraction`, `overview`, `overview_wiring`, `overview_judge`, `build_guide`, `chat_scope`, `chat_reply`, `code_adapt`, `image`, `markets` and the Gemini extras sites. Extraction calls use `extraction` here; `GEMINI_USAGE` names them `extraction_<source>` |
| `model` | string | model id from the request URL |
| `route` | string | `vertex` (Vertex AI), `api_key` (Gemini API), `other` |
| `duration_ms` | integer | ms for the whole call, retries and their waits included |
| `outcome` | string | `ok` (2xx with a complete answer), `invalid` (2xx with no candidate, a finish reason other than `STOP`, or a body that is not JSON), `timeout` (the last attempt timed out), `quota` (final HTTP 429), `error` (other HTTP status of 400 or above, or a network error) |
| `http_status` | integer or null | final HTTP status; null when no response arrived |
| `attempts` | integer | HTTP attempts made on this route |
| `tokens` | integer or null | `usageMetadata.totalTokenCount`; null without a 2xx JSON answer |
| `usd_est` | number or null | USD estimate from tokens and web-search queries (dated price table in `config.py`). Excludes Google Maps grounding queries (site `markets`). `GEMINI_USAGE` remains the cost record; do not add the two together |
| `job_id` | string or null | attributed job (`usage.attribute`); null for chat, extras and unattributed calls |
| `line_id` | string or null | attributed BOM line |

### SELLER_FETCH

One line per seller page or seller search fetch through `sourcing/politeness.py` (product
pages, seller search pages, seller-trust pages, fabrication pages, Robu API reads). The URL is
never logged, only the host.

| Field | Type | Unit / values |
| --- | --- | --- |
| `host` | string | final host after redirects (request host when no page arrived) |
| `kind` | string | `page`, `search` |
| `duration_ms` | integer | ms including per-host pacing waits and 429/503 retries |
| `outcome` | string | `ok` (2xx), `http_error` (other final status), `cache` (served from the page cache, no request), `cooldown` (host blocked after an earlier challenge, no request), `blocked` (bot-protection challenge), `robots` (robots.txt disallows), `timeout`, `api_route` (redirected to a seller read through its API), `error` |
| `http_status` | integer or null | final HTTP status; the cached status for `cache` |
| `attempts` | integer | requests made (0 for `cache` and `cooldown`) |

### GEMINI_USAGE and GEMINI_CACHE_HIT

Unchanged messages (`GEMINI_USAGE {json}`, `GEMINI_CACHE_HIT {json}`); on Cloud Run their JSON
fields are also top-level keys. Fields are documented in [gemini-cost.md](gemini-cost.md):
`site`, `model`, `prompt`, `output`, `thoughts`, `cached`, `tool_prompt`, `total`,
`grounded`, `search_queries`, `by_modality`, `usd_est`, `job_id`, `line_id`; and for cache
hits `namespace`, `job_id`, `line_id`. `scripts/usage_report.py` reads both formats.

### Existing operational tags with structured fields

Messages are unchanged (alerts match them); these fields are added as top-level keys.

| Event | Severity | Fields |
| --- | --- | --- |
| `QUEUE_AGE_EXCEEDED` | WARNING | `job_id` (string), `kinds` (list of `workflow`/`chat`), `age_s` (integer, seconds since the job's last update) |
| `SWEEP_TRUNCATED` | WARNING | `limit` (integer, jobs per sweep) |
| `TASK_ENQUEUE_FAILED` | ERROR | `job_id` (string), `kind` (`workflow`, `chat`, `overview`, `build_guide`), `type` (exception class) |
| `SWEEP_READ_FAILED` | ERROR | `job_id` (string), `type` (exception class) |
| `UNHANDLED_ERROR` | ERROR | `route` (route template, never the raw path), `type` (exception class) |
| `EXTRACTION_ATTEMPT_FAILED` | WARNING | `noun` (source noun), `route` (`vertex_first`, `api_key`), `code` (`ExtractionError` code) |

Other tagged lines (`SOURCING_LINE`, `SELLER_SEARCH`, `RECONCILE_APPLIED`, ...) carry `event`
but keep their details in `message` only.

## Web server (`frontend/server.mjs`)

The proxy forwards well-formed `X-Cloud-Trace-Context` and `traceparent` headers to the
backend, so a browser request keeps one trace id across both services. It logs nothing for
successful requests (Cloud Run's request log covers them) and one JSON line on stdout per
proxy failure:

| Field | Type | Unit / values |
| --- | --- | --- |
| `severity` | string | `ERROR` |
| `message` | string | `PROXY_ERROR <method> <route> status=<status> reason=<reason>` |
| `event` | string | `PROXY_ERROR` |
| `method` | string | `GET`, `POST`, `DELETE` |
| `route` | string | upstream path with share tokens as `:token` and UUIDs as `:id`; never a query string |
| `status` | integer or null | status sent to the browser (502 when the backend was unreachable) |
| `upstream_status` | integer or null | backend status; null when no response arrived |
| `reason` | string | `fetch_failed` (no response), `upstream_status` (backend answered 502, 503 or 504; passed through unchanged), `stream_failed` (the response broke while streaming) |
| `error` | string or null | error class name only |
| `duration_ms` | integer | ms from the upstream request to the failure |
| `logging.googleapis.com/trace`, `logging.googleapis.com/spanId` | string | as for the backend; the project is `GOOGLE_CLOUD_PROJECT`, else `FIREBASE_PROJECT_ID` (the deploy script requires it to be the deployment project) |

## Example log-based metric filters

```text
# Job outcomes (counter, labels status and code)
resource.type="cloud_run_revision" AND resource.labels.service_name="bharat-sourcer-integration"
AND jsonPayload.event="JOB_FINISHED"

# First-run time to a finished job (distribution of jsonPayload.total_duration_ms)
... AND jsonPayload.event="JOB_FINISHED" AND jsonPayload.prior_finishes=0 AND jsonPayload.demo=false

# Stage latency (distribution of jsonPayload.duration_ms, labels stage and outcome)
... AND jsonPayload.event="STAGE_FINISHED"

# Gemini latency and failure rate (distribution of jsonPayload.duration_ms, labels site, route, outcome)
... AND jsonPayload.event="GEMINI_CALL"

# Seller fetch health (labels host, outcome)
... AND jsonPayload.event="SELLER_FETCH" AND jsonPayload.outcome!="cache"

# Proxy failures on the web service
resource.labels.service_name="bharat-sourcer-web" AND jsonPayload.event="PROXY_ERROR"
```

Keep metric labels to low-cardinality fields (`status`, `code`, `stage`, `outcome`, `site`,
`route`, `kind`, `host`); `job_id` and `line_id` are for searching logs, not labels.

## Known limits

- Thread pools that do not copy the request context (the overview drawing pool, the shared
  seller-trust executor and the fabrication page reads) log without a trace; Gemini events
  from them still carry `job_id` where the call is attributed.
- `GEMINI_CALL` counts a complete answer that later fails the site's schema check as `ok`;
  the site's own `*_FAILED` warning records that rejection.
- Cloud Run's own request log still records full request URLs; that is platform behaviour.
