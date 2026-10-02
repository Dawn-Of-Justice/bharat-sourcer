# Implemented API contract — v0.2

This directory is the handoff between backend and frontend. The architecture docs describe
the target system; this contract describes the runnable local milestone.

`openapi.json` is generated from backend Pydantic schemas and FastAPI routes. Do not edit
it manually. Backend CI checks that it matches the implementation. The frontend can
generate TypeScript types from it using its own tooling.

## Local workflow

Base URL: `http://127.0.0.1:8000` (no `/api` prefix locally).

1. Create a job:

   ```http
   POST /v1/jobs
   Content-Type: application/json

   {"url":"https://example.com/build","pin":"560001","lang":"en"}
   ```

   HTTP 202 returns `job_id`, `job_token`, `watch`, `status: "queued"`,
   `cached: false`, and `demo` (true for fixtures, false for live extraction).
   `watch` is the relative GET path.

2. Save `job_token` for this job. Send it as `X-Job-Token` on subsequent GET/confirm calls.
   Missing or incorrect tokens return 404 to avoid revealing job existence.
3. Poll `GET /v1/jobs/{job_id}` about once per second until `awaiting_confirmation`.
   The snapshot includes `items` and ordered `events` with timestamps and sequence numbers.
4. Submit confirmation (an empty object accepts the draft):

   ```json
   {"edits":[
     {"op":"update","line_id":"L03","qty":8},
     {"op":"have_it","line_id":"L01"},
     {"op":"add","raw_name":"Breadboard","qty":1}
   ]}
   ```

   `POST /v1/jobs/{job_id}/confirm` returns HTTP 202 and `status: "resolving"`.
   Supported edit operations: `add`, `update`, `remove`, `have_it`. Set
   `user_has_it: false` on `have_it` to clear it. Edits apply in order and atomically.
   At least one line must remain. Repeated confirmation returns 409.
5. Poll until `done` or `failed`, then stop. Pause polling while awaiting user confirmation.
   At `done`, render `report`. Intermediate states may finish between polls; `events`
   retain the transitions. Stop and offer a fresh run on 404 after a server restart.

## Live extraction (v0.2 additions)

The server defaults to demo mode. `/healthz` reports `mode: "demo" | "live"`.
Live mode accepts public YouTube video URLs only; unsupported sources return 400.
The same routes and job-token flow apply in both modes.

- `items[].qty` can now be **null**. Ask the user for a positive integer before confirming,
  or let them remove the line. Confirmation rejects remaining unknown quantities.
- `items[].evidence` contains `{timestamp: "01:12", observation: "..."}` entries reported
  by the model. Display them for review; they are not independently verified.
- `items[].user_edited` marks manually added or updated lines. Existing evidence describes
  the original extraction, and may not support the user's replacement name or quantity.
- Jobs include nullable `extraction_model` and `error: {code, message} | null`.
- Failed extraction sets status `failed`, with no fixture fallback. Stop polling and show
  the error. Retry by creating a new job.
- `report.demo` reflects the mode. In either mode, sourcing is `not_run` or `already_owned`,
  and prices, grades and totals remain null. A live report is extraction-only.

## Demo behavior and common limits

- In demo mode every URL produces the same fixture. No upstream requests run.
- Show a demo label when `demo` is true. Prices, grades and totals are unavailable in both modes.
- This version supports piece quantities as positive integers, four language codes
  (`en`, `hi`, `ta`, `ml`), and unlisted jobs. Text remains English in fixture mode.
- Firestore listeners, caching, sourcing, conflict answers, exports, and plan/candidate
  selection are not implemented. Unimplemented routes return 404.
- Jobs are in memory and disappear when the backend reloads. Tokens are returned only
  once, on job creation. There is no public job listing or sharing flow yet.
- Configurable CORS defaults to localhost/127.0.0.1 on port 5173.

## Errors

Implemented domain and request-validation errors use:

```json
{"error":{"code":"INVALID_STATE","message":"Job is not awaiting confirmation"}}
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `UNSUPPORTED_URL` | Live mode requires a supported YouTube video URL |
| 404 | `JOB_NOT_FOUND` | Missing job or incorrect token |
| 409 | `INVALID_STATE` | Confirmation attempted in the wrong state |
| 422 | `VALIDATION_ERROR` | Invalid fields, types, URL, PIN or quantity |
| 422 | `INVALID_EDIT` | Edit references a missing line |
| 422 | `EMPTY_BOM` | Confirmation removes every line |
| 422 | `UNKNOWN_QUANTITY` | A retained part still has null quantity |

Background failures appear in the job snapshot (HTTP 200), with codes `UPSTREAM_QUOTA`,
`UPSTREAM_ERROR`, `UPSTREAM_TIMEOUT`, `INVALID_EXTRACTION`, `NO_BOM`, or `EXTRACTION_FAILED`.
No raw upstream errors or credentials are exposed.

Framework errors such as an unknown route retain FastAPI's default `detail` response.

## Implementation references

The local runner uses FastAPI's [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
The request schema uses Pydantic [discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
so each edit operation validates its own fields.
