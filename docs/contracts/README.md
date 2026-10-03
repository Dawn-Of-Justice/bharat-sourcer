# Implemented API contract — v0.11

This directory is the handoff between backend and frontend. The architecture docs describe
the target system; this contract describes the runnable local milestone.

v0.11 adds [sourcing pause/resume](pause-resume.md), the `paused` status and
`Job.pause_requested`. Regenerate frontend types for the new status.

`openapi.json` is generated from backend Pydantic schemas and FastAPI routes. Do not edit
it manually. Backend CI checks that it matches the implementation. The frontend can
generate TypeScript types from it using its own tooling.

## Local workflow

For team cloud integration, see [deployment and access](../../backend/infra/cloud-run.md).
Base URL: `https://bharat-sourcer-integration-diahnrbuna-el.a.run.app`.
Cloud liveness endpoint: `/health`. Use `/docs` or `/openapi.json` for the deployed API.
When configured, send `X-Integration-Key` on **every** `/v1/` request (including streams),
in addition to `X-Job-Token` for the relevant job. Missing integration access returns 401
`INTEGRATION_KEY_REQUIRED`. Keep the shared key in local development configuration and
share it privately; do not bundle it in a public frontend release. `/healthz`, `/docs`
and `/openapi.json` are public. `/health` is the cloud-safe liveness path.
The API base URL has no `/api` suffix.

[Backend roadmap](backend-roadmap.md) tracks agreed features still to implement.
[Frontend quickstart](frontend-quickstart.md) includes local configuration, request code,
credentials guidance and the integration acceptance checklist.

**New: [conversation integration guide](conversation.md).** Add chat beside the BOM,
reviewable edit proposals and a live snapshot stream. Existing endpoints remain available.

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

2. Save `job_token` for this job. Send it as `X-Job-Token` on GET, confirm and selection calls.
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
   retain the transitions. Stop on 404 (memory-mode jobs disappear after a restart).

## Compatibility and clarification (v0.5)

Draft `items[]` includes `specs` (nullable typed fields) and `clarifications[]` with `field`
and `question`. Use the OpenAPI `PartSpecs` enums for answer controls. Example confirmation:

```json
{"edits":[{"op":"update","line_id":"L01","specs":{
  "family":"pro_micro","controller":"atmega32u4","logic_v":5.0,"clock_mhz":16,
  "pinout":"pro_micro_v13"
}}]}
```

`pinout` must describe an actual known ordered pin mapping; the example is a symbolic ID,
not evidence that a clone follows it. Spec updates merge; explicit null clears a saved
answer (literal part-name inference can still supply a value). User answers are assertions,
not independently verified facts. Missing answers may be skipped; unknown specs block a
positive compatibility grade, not sourcing. Conflicting specs return 422 `INVALID_SPECS`.

`resolution.specs`, `resolution.evidence` and `resolution.clarifications` show the required
part's fields and provenance. Offers include `specs`, `spec_evidence` and `compatibility`:

| Status | Grade | Display meaning |
|---|---|---|
| `unknown` | null | More specifications are needed, or family unsupported |
| `compatible` | A | Declared replacement specs match |
| `changes_required` | B | Same declared specs except I2C address; show the required change |
| `incompatible` | X | A known constraint fails; do not recommend |

Always display `scope: declared_specs_only`, reasons and missing fields. Do not turn A into
a whole-project safety claim. These checks do not verify current, mechanical fit, complete
circuit wiring, firmware or seller accuracy. No C/D adaptation rules exist yet. `references`
contains rule references and the checked seller page. Chip documentation is not module evidence.
Offer `compatibility_status` mirrors the assessment; old saved offers can remain `not_checked`.

## Answering specs after a report (v0.8)

For a completed live report, `POST /v1/jobs/{job_id}/specs` with `X-Job-Token`
updates required part specifications and returns the updated Job (200):

```json
{"updates":[{"line_id":"L01","specs":{"logic_v":5.0,"clock_mhz":16}}]}
```

Send 1–100 distinct existing lines, each with at least one spec field. Fields merge with
saved answers; omitted fields remain and explicit null clears an answer. Literal name
inference can still supply a cleared field. Invalid merged specs reject the entire batch.
Demo, active and failed jobs return 409 `INVALID_STATE`; use confirmation edits for drafts.

The backend updates BOM and report copies, clarification questions and user provenance,
then reassesses saved offers locally. It does not call Gemini, refresh prices, change seller
specs or consume refresh/recovery budgets. Original video evidence stays intact.
Missing seller specs still prevent a positive grade even after all required specs are answered.

Changed lines lose their selections and contribute nothing until selected again; other
selections survive. Exact repeated answers are a no-op and preserve selections. Offer age
still comes from its original `checked_at`; use `/refresh` to retrieve new seller quotes.
Errors: 422 `INVALID_EDIT` for unknown/repeated lines; `INVALID_SPECS` for merged conflicts;
`VALIDATION_ERROR` for malformed or empty updates; 404 for an invalid job/token.

## Sourcing

New live jobs record `sourcing_enabled: true` unless disabled in backend configuration.
After confirmation the job moves through `resolving` → `sourcing` → `done`.
Poll the same job endpoint; `report.lines` grows as each part finishes. `done` does not
mean every part has an offer. Render each line's `sourcing_status`:

| Status | Meaning |
|---|---|
| `offers_found` | At least one seller page passed structured-data verification |
| `no_verified_offers` | No candidate met verification requirements |
| `failed` | Search or sourcing failed; show `sourcing_error.message` |
| `already_owned` | User owns this part; no search was made |
| `not_run` | Demo/disabled sourcing, or the per-job limit was reached |

`resolution` provides a query and `missing_specs`. Each `offers[]` entry contains an HTTPS URL, seller
hostname, product title, decimal-string `price_inr`, stock status, and `checked_at`.
`verification: seller_structured_data` means the seller's Product/Offer JSON-LD was read
and title/currency/price checks passed. Label prices as seller-reported; tax and shipping
are unknown. `seller_trust` remains `unverified`; review the per-offer compatibility result.
Line price and grade are populated after selection, described below. The final payable
total remains null because shipping and tax are unknown.

`attribution` retains Google's `source_urls`, `search_queries`, and optional
`search_suggestions_html`. Render the Google-provided suggestions alongside search results
according to the [grounding display requirements](https://ai.google.dev/gemini-api/docs/generate-content/google-search).
Use an isolated, sandboxed rendering surface for this external HTML; do not inject it into
the main document or allow script execution. Source URLs may be Google redirect URLs;
offer URLs point to fetched seller pages. All other strings should render as plain text.

An interrupted sourcing lease requeues unfinished work once per job and preserves completed
lines. A second interruption sets `failed` / `SOURCING_INTERRUPTED`. Per-line codes include
`DISCOVERY_FAILED`, `SOURCING_FAILED`, and `SOURCING_LIMIT`.
Existing stored jobs without the new flag remain extraction-only.

## Offer selection and costing (v0.6)

`POST /v1/jobs/{job_id}/selections` requires `X-Job-Token` and returns the updated Job (200):

```json
{"selections":[{"line_id":"L01","offer_url":"https://seller.example/product",
"accept_changes":false}]}
```

Use an actual `offers[].url` from the report; the URL above is illustrative. Null or omitted
`offer_url` clears a selection. A batch must have 1–100 distinct existing unowned lines.
Selection is allowed only for completed live reports. Offers must be reported in stock,
checked within 24 hours, and graded A or B. B requires `accept_changes: true`; show its
required changes before asking for that acknowledgement. Unknown and X cannot be selected.
The batch is atomic; repeating the same request does not duplicate quantities or costs.

- `lines[].selected_offer_url`, `price_inr` (unit price), `grade`, `changes_accepted`:
  selected seller quote and compatibility result.
- `lines[].subtotal_inr`: unit price times quantity, or zero for owned parts.
- `selected_parts_subtotal_inr`: partial sum of selected lines, as a decimal string.
- `unselected_line_ids`: unowned lines without selections.
- `parts_subtotal_inr`: full parts sum once every unowned line is selected; otherwise null.
- `shipping_inr`, `tax_inr`, `total_inr`: null. Never label the parts sum as a delivered total.

Prices remain snapshots at the offer's `checked_at`; GET does not refresh seller data.
Selection does not purchase anything or verify delivery, seller trust or final checkout cost.

Selection errors: 409 `INVALID_STATE` / `OFFER_STALE`; 422 `INVALID_SELECTION`,
`OFFER_UNAVAILABLE`, `COMPATIBILITY_UNRESOLVED`, or `CHANGES_REQUIRED`.

## Targeted offer refresh (v0.7)

`POST /v1/jobs/{job_id}/refresh` requires `X-Job-Token`:

```json
{"line_ids":["L01","L03"]}
```

Returns 202 `{"status":"resolving"}`. Resume polling the job until `done` or `failed`.
Available for completed live sourcing reports and reports failed with `SOURCING_INTERRUPTED`.
Select 1–30 distinct unowned lines, within the server's per-batch sourcing limit (default 10).
Demo jobs, extraction-only jobs, and active jobs cannot be refreshed.

The confirmed BOM, evidence, quantities and specs stay unchanged. Selected lines immediately
lose old offers, attribution, errors and selections and become `not_run` while pending.
Other lines and selections are preserved. Refresh searches and checks seller pages again;
it does not extract the video again. New offers require explicit selection, even if the
same URL returns. Subtotals exclude cleared selections immediately.

`refresh_count` persists across restarts and limits the job to **two accepted batches**.
Concurrent requests while a refresh is pending return 409. Sending the request again after
completion starts another batch and consumes the limit; do not automatically replay POSTs
after a lost response. Check job status, events and `refresh_count` first.
Refresh can incur Gemini charges. The existing automatic recovery budget is not reset.
Interrupted refresh resumes only unfinished requested lines. Unrequested unfinished lines
in a partial failed report remain `not_run` with `SOURCING_INTERRUPTED`.

Errors: 404 `JOB_NOT_FOUND`; 409 `INVALID_STATE` or `REFRESH_LIMIT`; 422 `INVALID_REFRESH`
for unknown, repeated, owned or too many lines; 503 `SOURCING_UNAVAILABLE` if this worker
has no sourcing adapter. Invalid requests do not consume the refresh budget.

## Persistent storage

`/healthz.storage` is `memory` or `firestore`. Firestore mode preserves the same API
payloads and job tokens across restarts. Continue API polling; direct database listeners
are not enabled. The database collection contains private token hashes and worker metadata.

Queued jobs and confirmed jobs awaiting report creation are recovered automatically.
Expired extraction is automatically requeued once per job; another interruption becomes
`failed` with `EXTRACTION_INTERRUPTED`. `recovery_attempts` and events expose recovery.
Gemini transient failures have at most three HTTP attempts per operation. Permanent errors
and invalid output fail without retry. A surviving client must retain `X-Job-Token`.
The health endpoint reports configuration, not database readiness.

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
- `report.demo` reflects the mode. With sourcing disabled, lines are `not_run` or `already_owned`.
  With sourcing enabled, use the offer fields described above.

## Demo behavior and common limits

- In demo mode every URL produces the same fixture. No upstream requests run.
- Show a demo label when `demo` is true. Demo data has no offer grades; total costing remains unavailable.
- This version supports piece quantities as positive integers, four language codes
  (`en`, `hi`, `ta`, `ml`), and unlisted jobs. Text remains English in fixture mode.
- Firestore listeners, caching, conflict answers, exports and automatic purchase plans
  are not implemented. Unimplemented routes return 404.
- Memory-mode jobs disappear when the backend reloads; Firestore jobs persist. Tokens are returned only
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
| 422 | `INVALID_SPECS` | Merged specs or identity conflict |
| 422 | `EMPTY_BOM` | Confirmation removes every line |
| 422 | `UNKNOWN_QUANTITY` | A retained part still has null quantity |
| 422 | `BOM_TOO_LARGE` | More than 100 retained lines |
| 503 | `STORAGE_ERROR` | Storage unavailable or snapshot too large |

Background failures appear in the job snapshot (HTTP 200), with codes `UPSTREAM_QUOTA`,
`UPSTREAM_ERROR`, `UPSTREAM_TIMEOUT`, `INVALID_EXTRACTION`, `NO_BOM`, `EXTRACTION_FAILED`,
or `EXTRACTION_INTERRUPTED`.
No raw upstream errors or credentials are exposed.

Framework errors such as an unknown route retain FastAPI's default `detail` response.

## Implementation references

The local runner uses FastAPI's [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
The request schema uses Pydantic [discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
so each edit operation validates its own fields.
