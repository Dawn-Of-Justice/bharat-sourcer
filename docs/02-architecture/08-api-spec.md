# API specification

> **In one minute.** The API is a small REST surface on Cloud Run under `/v1`. You create a job, confirm the parts, and read the results from Firestore. Only short calls go through the Firebase Hosting rewrite (`/api/**`), which has a 60 s limit. There is optional local-dev SSE, an optional MCP server for other agents, and an internal endpoint for durable execution.

Base URL: `https://<site>.web.app/api` (Hosting rewrite) → `bs-api` Cloud Run.

---

## 1. Endpoints

### `POST /v1/jobs`

Create an analysis.

```json
// request
{"url": "https://youtu.be/abc123", "pin": "560001", "lang": "en", "user_level": "beginner", "visibility": "unlisted"}
// 202 response
{"job_id": "7f0c…", "status": "queued", "cached": false, "watch": "firestore:jobs/7f0c…"}
```

- If a public BOM exists for the same `source_key` and is less than 7 days old, the response is `200` with `cached: true` and the existing `job_id`. Prices are re-verified in the background.
- Validation errors:

  | Code | Meaning |
  |---|---|
  | 400 `UNSUPPORTED_URL` | URL type not handled |
  | 422 `PRIVATE_VIDEO` | Gemini can only watch public videos |
  | 422 `NOT_A_PROJECT` | classifier says the page isn't a build |

### `GET /v1/jobs/{id}`

Snapshot of the job. The frontend normally reads Firestore directly; this endpoint is for tests and integrations.

### `POST /v1/jobs/{id}/confirm`

Resume after the human-in-the-loop step.

```json
{"edits": [
  {"line_id": "L03", "op": "update", "qty": 2},
  {"line_id": "L09", "op": "remove"},
  {"line_id": "L11", "op": "have_it"},
  {"op": "add", "raw_name": "10k resistor", "qty": 4}
 ],
 "answers": [{"question_id": "Q1", "value": "12V"}]}
```

Response: `202 {"status": "resolving"}`. Returns 409 if the job isn't in `awaiting_confirmation`.

### `POST /v1/jobs/{id}/lines/{lineId}/choose`

The user picks a different candidate. Costing is recomputed synchronously (under 1 s).

```json
{"listing_id": "lst_…"}
```

### `POST /v1/jobs/{id}/plan`

Switch the costing plan.

```json
{"plan": "fewest_sellers"}
```

### `POST /v1/jobs/{id}/narrate`

Generate or return the TTS audio (S1).

```json
{"lang": "ml"}
```

Response: `{"audio_url": "<signed url>", "duration_s": 94}`.

### `GET /v1/jobs/{id}/markets?lat=&lng=`

Maps-grounded nearby markets (S2). The response includes an `attribution_html` field, which must be rendered.

### `GET /v1/jobs/{id}/export.{csv|pdf}`

Download the BOM.

### `POST /v1/library/{sourceKey}/vote`

Requires Firebase Auth ID token.

```json
{"line_id": "L07", "value": 1, "reason": "worked"}
```

### `POST /v1/scan-bin` (S3)

Multipart upload with an image and a `job_id`. Returns detected modules with `box_2d` and the matched line ids.

### `GET /healthz`

Liveness check. It also reports the configured model IDs and feature flags.

## 2. Internal endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /internal/run/{jobId}` | OIDC (Cloud Tasks service account) | Durable execution path |
| `POST /internal/compile` | OIDC | Callback from the compile job (or the API polls the job execution) |

## 3. Local-dev streaming

`GET /v1/jobs/{id}/stream` (SSE) mirrors Firestore events. It's only enabled when `ENABLE_SSE=1`, and is useful for testing with `curl` without Firestore. ADK's own `/run_sse` is also available in dev.

## 4. MCP server (S12)

Exposed at `/mcp` (streamable HTTP):

| Tool | Input | Output |
|---|---|---|
| `source_bom` | `{url, pin?}` | `DesiBom` (waits up to 5 min, otherwise returns the `job_id`) |
| `find_indian_equivalent` | `{part, specs?, project_context?}` | top 3 `{listing, grade, summary}` |
| `get_job` | `{job_id}` | status + report |

## 5. Errors

Uniform body:

```json
{"error": {"code": "RATE_LIMITED", "message": "Too many analyses from this IP; try again in 60s", "retry_after_s": 60}}
```

| Code | HTTP | Meaning |
|---|---|---|
| `UNSUPPORTED_URL` | 400 | URL type not supported |
| `PRIVATE_VIDEO` | 422 | Gemini can only watch public YouTube videos |
| `NOT_A_PROJECT` | 422 | The page doesn't describe a build |
| `INVALID_STATE` | 409 | Wrong job status for this action |
| `RATE_LIMITED` | 429 | Per-IP limit: 5 jobs / 10 min (demo protection) |
| `UPSTREAM_QUOTA` | 503 | Gemini or grounding quota hit; the job is marked `partial` |
| `INTERNAL` | 500 | Logged with `job_id` |

## 6. Auth and abuse protection

- Anonymous by default. An optional Firebase Auth ID token (`Authorization: Bearer …`) attaches jobs to a user.
- **Firebase App Check** (reCAPTCHA Enterprise) on `POST /v1/jobs` to stop scripted abuse of our Gemini budget.
- Per-IP and per-user rate limits (in-memory token bucket + Firestore counter).
- CORS: Hosting origin only (plus localhost in dev).
