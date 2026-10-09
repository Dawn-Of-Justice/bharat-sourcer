# Implemented API contract — v0.30.2

v0.30.2: a part whose only usable listing was an AI buyer pick is searched again on
refresh (the buyer decides again) instead of re-checking that listing with the strict
spec judge alone.

v0.30.1: a refresh re-checks a part's known listings only when one was usable (in stock,
judged exact or compatible, value known); otherwise it runs the full search with the AI
buyer. AI buyer substitutes keep grade B when offers are re-graded, and any buyer pick
that needs changes is grade B.

v0.30.0 adds the [AI buyer](ai-buyer.md): unstated part values are decided from the
circuit (with the reasoning) before searching, and when no listing is accepted the buyer
picks from every fetched listing (exact, kit, or a grade B substitute with the changes to
make) or searches again in Indian shop wording. New optional `report.lines[].buyer`
(`BuyerDecision`), `match.method: "llm_buyer"` and stages `buyer_value`, `buyer`,
`buyer_search`. Google grounding redirects are no longer marked blocked when one target
site blocks us. Frontend: the part panel shows the decided value and the buyer's reason.

v0.29.0 adds [compile checks for code patches](code-adapt.md#compile-check-v0290):
`GET /v1/compile/boards`, `POST …/code-patch/compile` (202, optional `fqbn`) and
`code_patch.compile` (`CompileCheck`); `code_patch.check` becomes `compiles` or
`compile_failed`. Compile only, in isolated runners; never uploaded or tested on hardware.
Answers 503 `COMPILE_UNAVAILABLE` until the runner is provisioned on a server.
Frontend: built (board picker, "Check it compiles", result badge, size or compiler output).

v0.28.0 adds [code patches for substituted parts](code-adapt.md): optional
`report.lines[].code_patch` (`CodePatch`), `POST …/lines/{line_id}/code-patch`,
`POST …/code-patch/accept` and `GET …/code-patch.zip`. Owner-only.
Frontend: built (code changes panel with diffs, labels, notes, Accept and Download).

v0.27.0 improves [seller query routing](seller-search.md) and structured offer parsing.
Offers add optional `seller_domain`, `seller_name` and `seller_kind`
(`direct`, `marketplace`, `platform_hosted`). Existing `seller` remains available.
Hosted stores do not inherit their platform's domain age; marketplace trust does not
verify the merchant. Free catalogue search continues after the paid AI budget is spent.
Search, judge and page-reading failures preserve earlier results where possible;
`DISCOVERY_FAILED` can accompany `no_verified_offers` when seller pages were retained.
See [seller trust](seller-trust.md) and [part matching](part-matching.md).

This directory is the handoff between backend and frontend. The architecture docs describe
the target system; this contract describes the runnable local milestone.

v0.26.0 replaces CSV with a downloadable PDF: `GET /v1/jobs/{job_id}/export.pdf` and
`GET /v1/shared/{share_token}/export.pdf` return the order plan as an A4 PDF; both
`export.csv` routes were removed. `export.html` remains and uses the same order-plan layout.
See [export-and-share](export-and-share.md#pdf-and-html-report).

v0.25.0 adds "Copy to my projects": `POST /v1/shared/{share_token}/copy` (account or guest,
counts as a new project) makes an editable copy of a shared project, adding
`job.copied_from` and `lines[].copied_choice`. See
[export-and-share](export-and-share.md#copy-to-my-projects).

v0.24.0 adds `DELETE /v1/projects/{job_id}` (owner only, 204): permanently deletes a saved
project with its parts list, offers, conversation and share link. See
[authentication](authentication.md).

v0.23.0 removes the PIN code and adds [countries](countries.md): `country` on
`POST /v1/jobs` (defaults to the account's saved country, else `IN`), `GET /v1/countries`,
`GET`/`POST /v1/account/settings`, and nearby markets by `city` instead of `pin`
(`CITY_NOT_SUPPORTED`, `LOCATION_OUTSIDE_COUNTRY`). Requests that still send `pin` are accepted
and the value is ignored. Only India is supported.

Released in v0.21.0: automatic [recommendations](recommendations.md). Adds optional `report.order_plan`, `lines[].selection_source`, `user_offer_url`, `recommended_offer_url`, `recommendation` and `line_image`; `GET /plans` adds a `recommended` plan and `seller_penalty_inr`. Completed live reports now arrive with default selections.

v0.22.0 adds `research_skipped` to `stages`, `part_name` to `BuyableSpec`, Shopify variant
offers (`verification: shopify_storefront_json` with `?variant=` URLs) and AI buying specs for
older jobs. See the [frontend quickstart](frontend-quickstart.md) for integration guidance.

v0.21.0 adds the sourcing engine: buyable specs, seller catalogue search, an LLM spec
judge (`offers[].match`), automatic recommendations and selections, a seller-grouped
`report.order_plan`, `line_image`, cost controls (`job.cost_estimate`), nearby markets and
YouTube description intake. All new fields are optional. See [seller search](seller-search.md)
and [recommendations](recommendations.md) for implemented behavior.

v0.20.0 adds safety flags, costing breakdowns and cart plans, multi-source intake with
conflicts, look-alikes and confidence, seller trust labels, export and share links, catalogue-backed
compatibility grades A–D/X, and disabled-by-default Gemini extras. All new fields are optional.
The feature contracts below describe implemented behavior.

Released in v0.21.0: [cost controls](cost-controls.md) add optional
`job.cost_estimate` and research status `skipped`. Older snapshots may contain line error
`JOB_BUDGET_REACHED`; v0.27.0 continues free searches and skips paid stages at the limit.

v0.19.2 adds internal Gemini usage logging only; no API changes.

v0.19.1 makes inferred requirements measurable specs; no schema changes.

v0.19.0 adds [project understanding](project-understanding.md): `job.project` with an
AI-written, editable title and description plus a summary; inferred quantities
(`qty_source`, `qty_reason`) and inferred requirements (`origin`, `reason`);
`POST /v1/jobs/{job_id}/project`; and title/description/summary on `GET /v1/projects`.
`UNKNOWN_QUANTITY` is no longer returned. Project-list cards and inline project editing are implemented.

v0.18.1: Instructables extraction reads the project JSON; Hackster pages that refuse
automated access fail with `SOURCE_UNAVAILABLE`. No schema changes.

v0.18.0 accepts Instructables, Hackster and GitHub repository URLs in live mode.
`items[].evidence[]` gains `source` (`video` default | `project_page`), optional `quote`
and `url`; `timestamp` is now null for page evidence. New failure code
`SOURCE_UNAVAILABLE`. Older snapshots stay valid.

v0.17.11 adds optional `job.actions`, `messages[].refresh_results`,
`messages[].completes_message_id` and `refresh_proposal.result_message_id`; see
[chat actions](chat-actions.md). Older snapshots stay valid.

v0.17.10 prefers Indian retail pages within the existing per-part fetch limit; no schema
changes.

v0.17.9 adds optional `messages[].spec_proposal` for reviewed chat spec changes; see
[chat actions](chat-actions.md). The frontend renders its Approve/Reject controls.

v0.17.8 returns real seller photos more often (placeholder rejection, `og:image` fallback);
no schema changes. The frontend also falls back to `report.lines[].image_candidates`
and the part image endpoint; see the [part image contract](part-images.md).

v0.17.7 adds optional `offers[].spec_conflicts` (field plus candidate `SpecEvidence`
entries) and the `seller_table` evidence source. Show conflicts as "sellers disagree";
the field remains unknown. Older snapshots stay valid.

v0.17.6 hardens the internal queue sweep; no public schema changes.

v0.17.5 uses category illustrations for plural part names; no schema changes.

v0.17.4 adds [part image fallbacks](part-images.md#response-fields-and-routes):
`report.lines[].image_candidates` and `GET`/`POST /v1/jobs/{job_id}/parts/{line_id}/image`.
All fields are optional; older snapshots stay valid. AI generation is disabled by default.

v0.17.3 fixes [discarded grounded sources on truncated discovery](sourcing-incident-2026-10-05.md).
No frontend schema changes are required.

v0.17 adds [authentication, saved projects and guest limits](authentication.md),
with account and guest access enabled on the integration backend as of 5 October 2026.
The frontend proxy forwards credentials and cookies; a live guest session check passed
through it. Existing legacy jobs require explicit claim with their original token;
authenticated browser acceptance checks remain.
v0.17.1 adds personal remaining usage and accurate quota reset delays and is deployed.
v0.17.2 deploys revoked-session and disabled-account checks with runtime Firebase
account-read permission configured. Authentication is enabled on the integration backend.
See the authentication handoff for error handling.

v0.16 adds [general part research, flexible requirements and reviewed AI assessments](part-research.md).
Render research candidates even when no verified offers exist. Existing chat receives
research evidence; frontend research cards and requirement controls are implemented.

v0.15 adds optional seller product image URLs to verified offers. v0.14 added
[project-only chat, parallel part sourcing and seller diagnostics](project-chat-and-sourcing.md).
See the [part image contract](part-images.md) for the current field behavior
and future fallback plan.
The deployed backend runs Cloud Tasks in request-billed mode; see [durable dispatch](queued-dispatch.md).

v0.13 uses [durable queued dispatch](queued-dispatch.md) in cloud mode. API shapes
are unchanged; expect cold starts and `resolving` between sourcing checkpoints.

v0.12 adds [reviewed chat refresh actions](chat-actions.md). Render
`ChatMessage.refresh_proposal` with approval controls before starting seller search.

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
[Export and share](export-and-share.md): PDF, printable HTML report and revocable read-only share links.
[Frontend quickstart](frontend-quickstart.md) includes local configuration, request code,
credentials guidance and the integration acceptance checklist.
[Gemini extras](gemini-extras.md): opt-in explain-aloud audio, clip zoom and parts-bin scan.
[Nearby markets](nearby-markets.md): `GET /v1/jobs/{job_id}/markets?city=` lists Maps-grounded electronics shops near the maker, with required Google Maps attribution.
[Seller trust labels and storefront JSON fast path](seller-trust.md): `offers[].trust` and new `verification` values.
[Safety flags](safety-flags.md): deterministic MAINS / LIPO / HIGH_CURRENT / LEVEL_SHIFT banners on `job.safety_flags`.

**New: [conversation integration guide](conversation.md).** Add chat beside the BOM,
reviewable edit proposals and a live snapshot stream. Existing endpoints remain available.

[Multi-source intake](multi-source-intake.md): Adafruit Learn and tutorial blog sources,
GitHub code evidence, extra `sources` per job, fused BOM lines with `conflicts`,
`lookalikes` and a `confidence` chip. YouTube description intake (§8): evidence
`source: "youtube_description"`, `job.video_meta` and 30-day retention.

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
and `question`. Use OpenAPI for typed-field answer controls; `family` is now free text.
Use [generic requirements and research](part-research.md) for arbitrary categories.
See [compatibility rules](compatibility-rules.md) for the part catalogue, resolver and A–X rules engine.
Example confirmation:

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

GST, shipping and import estimates, import reference prices and cart plans: see
[costing](costing.md).

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
Live mode accepts public YouTube video URLs and supported project pages: Instructables
(`instructables.com/<slug>/`, or legacy `/id/<slug>/`), Hackster (`hackster.io/<user>/<project>`)
and GitHub repository READMEs (`github.com/<owner>/<repo>`). Other sources, including
Instructables category or member paths, return 400 `UNSUPPORTED_URL`.
The same routes and job-token flow apply in both modes.

- `items[].qty` can now be **null**. Ask the user for a positive integer before confirming,
  or let them remove the line. Confirmation rejects remaining unknown quantities.
- `items[].evidence` entries are model-reported; display them for review. Branch on `source`:
  - `source: "video"`: `{timestamp: "01:12", observation, source, quote: null, url: null}`.
    Not independently verified. Older snapshots omit `source`; treat missing as `video`.
  - `source: "project_page"`: `{timestamp: null, observation, source, quote, url}`. `quote`
    was checked by the server to appear verbatim (whitespace-normalised) in the fetched
    document at `url` (for GitHub, the raw README; for Instructables, the project page, whose
    content the server reads from the page's own public JSON model). Show it as a page
    citation, not a video time. The quote proves the page says it, not that the identity
    or quantity is right.
  Parts whose quotes could not be found on the page are dropped before review.
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
| 400 | `UNSUPPORTED_URL` | Live mode requires a YouTube video, Instructables/Hackster project or GitHub repository URL |
| 404 | `JOB_NOT_FOUND` | Missing job or incorrect token |
| 409 | `INVALID_STATE` | Confirmation attempted in the wrong state |
| 422 | `VALIDATION_ERROR` | Invalid fields, types, URL, PIN or quantity |
| 422 | `INVALID_EDIT` | Edit references a missing line |
| 422 | `INVALID_SPECS` | Merged specs or identity conflict |
| 422 | `EMPTY_BOM` | Confirmation removes every line |
| 422 | `BOM_TOO_LARGE` | More than 100 retained lines |
| 503 | `STORAGE_ERROR` | Storage unavailable or snapshot too large |

Background failures appear in the job snapshot (HTTP 200), with codes `UPSTREAM_QUOTA`,
`UPSTREAM_ERROR`, `UPSTREAM_TIMEOUT`, `INVALID_EXTRACTION`, `NO_BOM`, `SOURCE_UNAVAILABLE`
(project page could not be fetched, blocked by robots.txt, refused automated access with
HTTP 401/403/429/451/503, had no README or no readable text; Hackster project pages returned
a Cloudflare 403 to the development sandbox on 5 Oct 2026, so expect this code for them
unless production egress is accepted),
`EXTRACTION_FAILED`,
or `EXTRACTION_INTERRUPTED`.
No raw upstream errors or credentials are exposed.

Framework errors such as an unknown route retain FastAPI's default `detail` response.

## Implementation references

The local runner uses FastAPI's [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
The request schema uses Pydantic [discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
so each edit operation validates its own fields.
