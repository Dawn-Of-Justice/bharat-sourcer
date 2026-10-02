# Implemented API contract — v0.5

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
The line-level selected price, grade and report total remain null. No offer selection
endpoint exists yet.

`attribution` retains Google's `source_urls`, `search_queries`, and optional
`search_suggestions_html`. Render the Google-provided suggestions alongside search results
according to the [grounding display requirements](https://ai.google.dev/gemini-api/docs/generate-content/google-search).
Use an isolated, sandboxed rendering surface for this external HTML; do not inject it into
the main document or allow script execution. Source URLs may be Google redirect URLs;
offer URLs point to fetched seller pages. All other strings should render as plain text.

An interrupted sourcing lease sets `failed` / `SOURCING_INTERRUPTED` and preserves completed
lines. Per-line codes include `DISCOVERY_FAILED`, `SOURCING_FAILED`, and `SOURCING_LIMIT`.
Existing stored jobs without the new flag remain extraction-only.

## Persistent storage

`/healthz.storage` is `memory` or `firestore`. Firestore mode preserves the same API
payloads and job tokens across restarts. Continue API polling; direct database listeners
are not enabled. The database collection contains private token hashes and worker metadata.

Queued jobs and confirmed jobs awaiting report creation are recovered automatically.
Extraction interrupted past its lease becomes `failed` with `EXTRACTION_INTERRUPTED`;
the user can create a new job to retry. A surviving client must retain `X-Job-Token`.
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
- Firestore listeners, caching, conflict answers, exports, and plan/candidate
  selection are not implemented. Unimplemented routes return 404.
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
