# Backend

The integration deployment was observed on 5 October 2026 with Firebase account and
guest authentication enabled. The frontend origin is included in CORS. The
`BS_AUTH_ENABLED=false` setting shown below remains the default for a fresh local setup.

v0.17.9 lets chat propose spec/requirement changes for completed reports; they apply only
after approval. See [chat actions](../docs/contracts/chat-actions.md).

v0.17.8 fixes missing seller images: storefront placeholder images (such as Shopify's
`no-image` asset, returned for every Robocraze product) are rejected, and a verified
single-product page falls back to its `og:image`/`twitter:image` metadata (same-host
`http` is upgraded to `https`). Offers saved before v0.15 have no `image_url`; refresh
those parts to collect images.

v0.17.7 reads seller specification tables and common JSON-LD property labels, and reports
seller-source disagreements as `spec_conflicts` instead of silently dropping them.

v0.17.6 bounds the scheduled queue sweep, isolates per-job enqueue failures and logs
`QUEUE_AGE_EXCEEDED` for stuck work. See [durable dispatch](../docs/contracts/queued-dispatch.md).

v0.17.5 matches plural part names ("Resistors", "Jumper wires") to category
illustrations. Merges to `main` now deploy to Cloud Run automatically.

v0.17.4 adds part image fallbacks: matching page product photos, labelled SVG category
illustrations and opt-in AI illustrations with separate daily quotas. Image requests do not
consume the project action quota. See the [image handoff](../docs/contracts/frontend-image-handoff.md).

v0.17.3 preserves grounded discovery URLs when Gemini ends with MAX_TOKENS,
while keeping downstream evidence verification and blocked-response rejection.
See [the sourcing investigation](../docs/contracts/sourcing-incident-2026-10-05.md).

v0.17.2 checks Firebase account status for disabled/deleted users and revoked
sessions on each authenticated request. Provider outages fail closed with 503.
The runtime identity needs `firebaseauth.users.get`; see the auth rollout guide.

v0.17.1 adds `GET /v1/session/usage` for remaining personal quotas and reset times,
and returns the applicable quota reset delay in `Retry-After` on usage rejection.

v0.17.0 adds optional Firebase Google authentication, signed guest sessions,
owner-scoped saved projects, guest-to-account claims and shared usage limits.
Authentication defaults to disabled until the frontend proxy and Firebase setup
are ready. See [authentication and rollout](../docs/contracts/authentication.md).

v0.16.1 adds one bounded alternative-source search when no verified offer or research
evidence is available. Unreadable pages no longer consume the document-review budget.
See the [research limits and cost controls](../docs/contracts/part-research.md).

v0.16 adds [general part research](../docs/contracts/part-research.md): arbitrary
categories, source-linked facts, AI suitability assessments, flexible user requirements,
and deterministic comparisons. Research candidates survive missing structured offers.
Chat can answer from these results. The frontend needs the documented research cards
and requirement controls; research candidates are separate from verified price offers.

v0.15 adds optional seller product image URLs to verified offers. The frontend can
display these directly; image metadata is optional and never affects offer verification.

v0.14 adds a project-scope chat gate, three concurrent sourcing lines per batch,
explicit seller variant verification and useful no-offer diagnostics.
See [behavior and limits](../docs/contracts/project-chat-and-sourcing.md).

GitHub Actions checks backend changes and deploys successful `main` builds to
Cloud Run. See [CI/CD setup and first run](infra/github-actions.md).

v0.13 supports [Cloud Tasks dispatch and scale to zero](../docs/contracts/queued-dispatch.md).
Local development retains background tasks; cloud execution uses authenticated HTTP workers.

v0.12 adds [user-approved chat refresh proposals](../docs/contracts/chat-actions.md).
Approval atomically queues a scoped refresh with existing limits and stale-report checks.

v0.11 adds persisted sourcing pause/resume at part checkpoints. Chat remains available;
see [frontend controls and limitations](../docs/contracts/pause-resume.md).

Python + FastAPI, with an isolated package, virtual environment, tests and configuration.

## Run locally (PowerShell)

From the repository root, using Python 3.12 or newer:

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.venv/Scripts/python -m uvicorn bharat_sourcer.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux use `.venv/bin/python` in place of `.venv/Scripts/python`.

Open `http://127.0.0.1:8000/docs` for interactive requests, or `/healthz` for health.
Demo mode needs no credentials or cloud services. Environment variables use the `BS_` prefix;
`.env` is loaded from the working directory (`backend/`).

`requirements-dev.lock` pins the tested runtime and development dependencies. Update it
deliberately when upgrading dependencies, then rerun checks and regenerate OpenAPI.

## Implemented workflow

1. `POST /v1/jobs` accepts an HTTP(S) project URL and returns a job ID and secret job token.
2. A background task loads a fixed BOM in demo mode, or extracts a public YouTube video in live mode.
3. `POST /v1/jobs/{id}/confirm` applies all edits atomically.
4. In live mode, grounded search discovers seller pages and the verifier reads product offers.
5. `GET /v1/jobs/{id}` returns state, errors, events and the incremental report.

Send `X-Job-Token` on reads and confirmations. Keep that token in the client session and
out of URLs/logs. It is a local capability token, separate from the planned Firebase Auth.

In demo mode, all URLs receive the same fixture. URLs are validated but never fetched.
`demo: true` marks the response; prices, totals and compatibility grades are `null`.
`done` means processing finished. Inspect each report line for sourcing success or failure.

## Live YouTube extraction

In `backend/.env`, set:

```dotenv
BS_DEMO_MODE=false
BS_GEMINI_API_KEY=your-key-here
BS_GEMINI_MODEL=gemini-3.8-flash
BS_EXTRACTION_TIMEOUT_S=120
```

Keep the real key in the ignored `.env` file. Restart the server, then submit a public
YouTube `watch`, `youtu.be`, `shorts`, or `embed` URL. Other sources return HTTP 400 in
live mode. The backend sends a canonical YouTube URL to Gemini; it does not fetch arbitrary
URLs or download video locally. Live requests can incur Gemini usage charges.

The adapter uses `generateContent`, structured JSON output, and local Pydantic validation.
The default model appears in Google's [model catalog](https://ai.google.dev/gemini-api/docs/models).
Google documents direct YouTube input as a preview feature in its
[video guide](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding).
The [REST reference](https://ai.google.dev/api/generate-content) documents the request fields.
This first adapter does not yet use ADK or agentic video processing.

Live responses have `demo: false` and `extraction_model`. Each extracted line carries
model-reported `evidence` (timestamp and observation), which must be reviewed rather than
treated as independently verified. Unknown quantities are `null`; confirmation requires
the user to set a positive integer or remove the line. User edits retain the original
evidence and set `user_edited: true` so the UI can distinguish them.

Errors transition the job to `failed` with a sanitized `error.code` and message. There
are bounded transient retries as described below, with no demo fallbacks. HTTP read timeout
is configurable; output is limited to 8,192 tokens and validated to at most 100 parts.
Compatibility is limited to declared-spec comparisons described below. Parts costing is available
after offer selection; shipping, tax and the final payable total remain unknown.

Automated tests use a mocked HTTP transport. A credentialed smoke test on 2 Oct 2026
successfully extracted four parts from YouTube Short `qSRrq_VZ4Fw` and reached
`awaiting_confirmation` in about eight seconds. This validates connectivity and response
parsing, not the accuracy or completeness of the BOM.

The live endpoint rejected the full Pydantic generation schema with HTTP 400. The adapter
now sends an inline schema without bounds or string constraints, then applies the full
Pydantic validator locally. Invalid quantities, timestamps, oversized results and extra
fields are still rejected. Public API schemas retain their validation constraints.

Jobs use memory storage by default, disappear on reload/restart, and require **one worker**
in that mode. For persistence, follow [Firestore setup](infra/README.md) for project
`hackathon-510415`, then select `BS_STORAGE_BACKEND=firestore`. Firestore stores jobs,
events, parts, reports and token hashes in private snapshots. Existing API routes still
work; the frontend does not need direct Firestore access.

A startup/periodic sweep resumes queued work and report creation. Expired work gets one
automatic recovery attempt per job, which can repeat a billed API request. Use this
server locally until durable task dispatch, retention, rate limits and Firebase
Auth/App Check are ready for public deployment. Firestore cloud access was verified on
2 Oct 2026 against `hackathon-510415` in Mumbai. Other developer machines need Application
Default Credentials; see the setup guide.
Live mode fails startup if `BS_GEMINI_API_KEY` is missing or empty.

## Seller sourcing

New live jobs source confirmed parts by default. Set `BS_SOURCING_ENABLED=false` to keep
new jobs extraction-only. Existing jobs retain the sourcing flag recorded at creation.
Demo jobs never call search or fetch sellers. Up to ten unowned parts are searched per
job (`BS_SOURCING_MAX_PARTS`), with five candidate pages per part by default.

Discovery uses Gemini Google Search grounding without a seller allow-list. Candidate
URLs come from grounding metadata, never generated prose. The verifier follows HTTPS
redirects, rejects non-public IPs at every hop, pins the checked address for TLS requests,
respects robots.txt, and limits response sizes. Pages with missing/blocked robots data,
long crawl delays, compression or unsupported product data can be skipped.

Only a single Product with a single Offer in seller JSON-LD qualifies. Its title must
match the query, currency must be INR, and price must be a positive decimal. Stock is
copied from explicit availability or marked unknown. Aggregate prices and unresolved
variant URLs are rejected. This verifies seller-published data, not merchant honesty,
delivery to the PIN, tax inclusion, electrical suitability or an independent stock check.
If the verified Product JSON-LD includes an HTTPS image URL, it is returned as optional
`image_url` for the frontend to display. The backend does not download or proxy seller
images; missing or invalid image metadata does not affect the offer. Placeholder assets are rejected; when the Product JSON-LD has no real
image, the page's `og:image` is used only for single-product pages. All sellers are
labelled `unverified`; no offer is selected automatically.

Seller specifications come from three sources on the verified page, each recorded in
`spec_evidence` with its `source`: the product title (`seller_title`), JSON-LD
`additionalProperty` (`seller_property`) and two-cell spec table rows or `dt`/`dd` pairs
(`seller_table`). Properties may use internal field names or a narrow set of common labels
(for example "Operating Voltage", "Interface", "Driver IC", "Resolution", "I2C Address").
Generic labels such as "Voltage" or "Frequency", alternatives such as "I2C / SPI",
single supply voltages and anything inside scripts are ignored. When sources disagree,
or an explicit property value is invalid, the field stays unknown and the offer lists a
`spec_conflicts` entry with every candidate value and source. Tables are read from the
whole verified page, so a related-product table can create a conflict, never a value.

## Part image fallbacks

Images are presentation only; they never establish specifications, compatibility or
identity. Each report line can carry up to ten `image_candidates`: Product JSON-LD photos
from fetched seller pages whose product title matches the query, even when price/stock
could not be verified. `GET /v1/jobs/{job_id}/parts/{line_id}/image` returns, in order,
offer seller images, then those page references, deduplicated by URL, plus a `fallback`
code-authored SVG (a category diagram for resistors, capacitors, LEDs, wires and LDRs,
otherwise a generic placeholder), labelled "Illustration · not a product photo".

`POST` on the same path accepts `{"failed_urls": [...]}` (max 10) for images the browser
could not load and, when nothing else applies, may generate one AI illustration. Generation
requires `BS_IMAGE_GENERATION_ENABLED=true`, `BS_GEMINI_API_KEY`, and a non-demo job.
Results are 384px JPEG data URLs (≤150 KB) cached per owner, part name and model in
memory or the Firestore `<collection>_images` collection. Limits: `BS_IMAGE_DAILY_LIMIT`
(default 30) globally and 10 per owner per UTC day. A failure is cached for one hour;
an atomic lease prevents duplicate concurrent generation. `GET` never generates.
`generation_status` is `not_needed`, `not_requested`, `ready`, `pending` or `unavailable`.
With authentication enabled, image requests still require identity, CSRF header and job
ownership, but are exempt from the per-account action quota so broken-image retries
cannot block project actions.

General research accepts any part category, reads source text and text PDFs, and
extracts quoted specifications and candidate assessments. Discovery searches globally
for technical documentation and Indian sellers. Missing or blocked sources stay visible.
The original deterministic compatibility grades still cover Pro Micro, OLED, TTP223
and USB cables; other categories use the separate AI assessment and generic requirement
checks. No category needs a new enum or parser before it can be researched.

Lines are checkpointed in Firestore as sourcing progresses. An expired sourcing lease
queues unfinished work once, preserving completed lines and the sourcing limit. A second
interruption fails with `SOURCING_INTERRUPTED`. Per-line errors remain explicit in the report.

## Offer selection and costs

`POST /v1/jobs/{job_id}/selections` accepts a batch of `{line_id, offer_url, accept_changes}`
with the job token. Use null `offer_url` to clear a selection. Changes apply atomically.
Only completed live reports support selection. Offers must be in stock, checked within
24 hours, and graded A or B; B requires `accept_changes: true`. Nothing is purchased.
Unknown compatibility requires explicit research review as described below. Seller
adapters can lack sufficient specification evidence; gaps remain visible for review.

For v0.16, a verified quote with a current AI `potential_match` assessment can also be
selected with explicit `accept_research_assessment: true`. Generic requirements must
pass, known incompatibility blocks selection, and the report records research approval
without assigning an A/B grade. See the research contract for stale-assessment handling.

The line `price_inr` is the selected unit price; `subtotal_inr` multiplies it by quantity
using decimal arithmetic. Owned items contribute zero. `selected_parts_subtotal_inr`
contains the partial sum; `parts_subtotal_inr` is available only once all unowned lines
have selections. `unselected_line_ids` identifies gaps. Shipping, tax and `total_inr`
stay null. Costs are snapshots of seller quotes, not checkout totals or live guarantees.

## Refresh stale or failed offers

Send `POST /v1/jobs/{job_id}/refresh` with the job token and `{"line_ids":["L01"]}`.
The backend returns 202 and searches only those parts, without extracting the video again.
Completed live sourcing reports and interrupted sourcing reports support refresh.
Requested lines lose their old offers and selections immediately; other selections survive.
New quotes must be selected again. Confirmed parts, specs and evidence remain unchanged.

Each job supports two accepted refresh batches, each within the configured sourcing part
limit. The counter and requested scope persist in Firestore. Invalid or concurrent requests
do not consume the budget. A repeated POST after completion starts a new batch, so clients
must check job status and `refresh_count` before retrying a lost response. Refresh can incur
paid search calls. It does not reset the automatic recovery budget. Interrupted refresh
reuses completed lines and resumes only unfinished requested lines.

## Automatic recovery

Gemini extraction and discovery retry timeouts, network errors and HTTP 429/500/502/503/504
up to three total attempts, with exponential delays and jitter. Numeric Retry-After is
honored up to ten seconds; longer or unsupported values stop retries. Authentication,
invalid requests and malformed output are not retried. Retry counts are logged without
request bodies or credentials. Repeated generation can incur additional charges.

The job's persisted `recovery_attempts` limits interrupted-worker recovery to one per job.
The periodic sweep requeues expired extraction or sourcing; a subsequent sweep claims it.
Completed sourcing lines are reused, including failed lines, so only unfinished lines run.
Worker IDs prevent late results from overwriting a recovered job. Extraction leases allow
at least three configured request timeouts plus 60 seconds. Exhausted recovery becomes a
visible failure; there is no automatic code editing, fabricated fallback, or infrastructure
repair. Firestore is required to retain progress across process restarts.

Run a targeted live check from `backend/` (uses paid search if your plan charges for it):

```powershell
.venv/Scripts/python scripts/check_sourcing.py --part "TTP223 touch sensor module"
```

A live check on 2 Oct 2026 returned two structured-data offers from five candidates:
Robocraze INR 9.00 and FlyRobo INR 18.00, both seller-reported in stock. This is historical
test evidence, not a price guarantee. The ignored `.data/sourcing-check.json` stores the
full local response. See the shared contract for attribution rendering requirements.

## Compatibility and clarification

Draft BOM items carry `specs` and `clarifications`. Answer questions using the `specs`
field of an existing confirmation `update` edit. Answers merge with saved specs; omitted
fields remain unchanged. Unknown answers can stay empty and the offer stays ungraded.
The backend distinguishes user assertions from literal name tokens and seller properties.
No model-generated electrical specifications are used by the rules engine.

Seller specs currently come from unambiguous title tokens and JSON-LD `additionalProperty`
entries whose names exactly match `PartSpecs` fields. Most seller pages will not provide
enough data for a positive grade. Generic voltage text is not assumed to describe logic
levels. Contradictory seller fields are discarded. Chip datasheets are rule references,
not a source of assumed module/clone wiring, regulators or voltage tolerance.

Every offer contains a `compatibility` assessment, with reasons, missing fields,
changes and reference links. This milestone implements:

- **A:** all required declared replacement specs match.
- **B:** the only mismatch is OLED I2C address; change the configured address.
- **X:** a known constraint differs or required supply range is not covered.
- **Unknown / null grade:** unsupported family or incomplete specs.

Grades have `scope: declared_specs_only`. They do not certify the complete circuit,
physical fit, current draw, firmware, seller claims, clone quality or every used MCU pin
function. `pinout` must identify the same ordered pin mapping; different strings block
approval. Controller swaps and rewiring are blocked until safe adapters exist. C/D grades
are reserved for future rules. Line-level grades appear after selection; payable totals stay null.

Rule references: [SparkFun Pro Micro guide](https://learn.sparkfun.com/tutorials/pro-micro--fio-v3-hookup-guide/all),
[Adafruit OLED guide](https://learn.adafruit.com/monochrome-oled-breakouts?view=all),
[Tontek TTP223-HA6 datasheet](https://www.tontek.com.tw/uploads/product/245/TTP223-HA6_V1.1_EN.pdf).
For TTP223, supply and output-mode rules are based on the exact declared module; the cited
chip datasheet is background and does not establish which chip revision a seller ships.

## Correct required specs after sourcing

`POST /v1/jobs/{job_id}/specs` accepts `{"updates":[{"line_id":"L01","specs":{"logic_v":5.0}}]}`
with the job token and returns the updated Job. It supports completed live reports only.
Saved answers merge atomically; explicit null clears an answer, though name inference can
still supply it. Invalid merged specs or repeated/unknown lines roll back the whole batch.

This updates required specs and reassesses saved offers without network calls or changes
to seller specs, prices, check times or video evidence. Changed lines lose selections;
other selections remain. Exact repeated answers are a no-op. Missing seller specifications
remain unknown, and stale quotes still need refresh before selection.

## Project conversation (v0.9)

Live smoke test on 3 Oct 2026 used YouTube Short `En4KD0c3XXs`: Gemini returned
five BOM lines, answered a question with a saved timestamp and line citation, and
produced ownership proposals that were rejected and accepted in an isolated memory job.
Acceptance left the job awaiting confirmation. The snapshot generator emitted the changed
state and heartbeat. One chat turn returned `CHAT_FAILED`; a new turn using the saved
extraction succeeded. The underlying failure cause was not captured. This validates live
adapter connectivity, not BOM accuracy or a deployed browser-to-server SSE connection.

Repeat from `backend/` with configured Gemini credentials (billable calls may occur):

```powershell
.venv/Scripts/python scripts/check_conversation.py --url https://www.youtube.com/shorts/En4KD0c3XXs
```

The test uses isolated memory storage, performs no sourcing, and saves a token-free
snapshot in ignored `.data/conversation-check.json`. Its ownership edit is test data.
Use `--resume` to reuse that snapshot and retry the acceptance step without re-extraction.

Users can ask questions alongside the BOM using persistent job chat. The live Gemini
adapter receives saved parts, evidence, offer assessments and the last 12 messages.
It can answer in every job state and propose draft BOM edits while awaiting confirmation.
Proposals require explicit acceptance; acceptance does not start sourcing. Stale proposals
are rejected, and existing deterministic edit validation applies atomically.

`POST /v1/jobs/{id}/messages` queues a turn using a client UUID for deduplication.
`POST /v1/jobs/{id}/messages/{message_id}/decision` accepts or rejects a proposal.
`GET /v1/jobs/{id}/stream` sends full job snapshots over SSE with token authentication.
Streams check saved state about once a second and close after about 60 seconds; reconnect
while the project is open. Each subscriber causes storage reads, including Firestore reads.
Replies appear once validated, rather than token by token. Polling GET remains supported.

Chat has separate queued/thinking/idle/failed state, a 20-turn limit and one active turn.
Queued turns resume after restart. Expired reply leases fail visibly without an automatic
generation replay; send a new message UUID to retry. Model HTTP calls use bounded transient
retries and may incur costs. Demo chat returns a labelled static response without Gemini.
Chat does not yet execute search tools, pause/cancel jobs, or edit completed reports;
the existing spec/refresh endpoints still serve those report updates. Model answers are
not independently verified; only line-reference existence and proposal validity are checked.

Frontend implementation details and a fetch/SSE client are in
[the conversation integration guide](../docs/contracts/conversation.md).

## Package layout

### Deterministic resistor advice (v0.10)

Chat may ask a contextual resistor-role question. Confirmed low-voltage single-LED
series-resistor inputs can be submitted to `/v1/jobs/{id}/resistor-advice`; see the
[frontend guide](../docs/contracts/conversation.md#contextual-resistor-suggestions-v010).
Decimal arithmetic selects the next E24 value considering 5% negative tolerance and
the smaller of desired current and driver design current. Power uses maximum voltage
drop and minimum resistance, with a 2x rated-power margin. Advice is saved separately
from extracted parts and never automatically changes quantities or selections.

Reference formula: [DigiKey LED series resistor calculator](https://www.digikey.ie/en/resources/conversion-calculators/conversion-calculator-led-series-resistor).
No board-specific GPIO current or LED forward voltage is inferred from the video.

Rule self-checks and an independent selection check detect exceptions or incorrect
standard values. A failing primary selector is quarantined for the worker process;
a bundled tested fallback is used for later calls, with its own output validation.
Both failing produces an unavailable result. Events `RULE_QUARANTINED` and
`RULE_UNAVAILABLE` provide diagnostic signals; advice stores version and fallback status.
This is bounded recovery, not autonomous source-code repair. A permanent correction
requires a regression case, a new version, checks and deployment. Restarted workers
repeat self-checks; quarantines are not synchronized across workers. Arbitrary formula,
hardware or shared-data defects are not guaranteed to be detected by these checks.

Run `python scripts/check_rules.py` from the installed backend development environment
before shipping a rule change. This runs the electrical reference examples, bounds,
injected selector failures, fallback checks and API isolation checks, with a nonzero exit
on failure. The existing CI `pytest` step includes this same test file. Add a failing
regression case for each discovered defect before changing a rule; bump its version when
behavior changes. Passing this suite alone does not prove every possible circuit safe.

On 3 Oct 2026, live Gemini was asked about the two unspecified resistors in the saved
`En4KD0c3XXs` BOM. It returned a structured question about each resistor's role and the
four LED-rule input bounds, without suggesting a value or changing the BOM. Reproduce with:

```powershell
.venv/Scripts/python scripts/check_conversation.py --url https://www.youtube.com/shorts/En4KD0c3XXs --resume --resistor-question
```

This command needs the earlier saved extraction and makes one billable chat operation
(with bounded HTTP retries). It validates the live clarification path, not the video's
actual circuit connections or component values.

```text
backend/
  src/bharat_sourcer/
    config.py       environment settings
    schemas.py      validated request/response models
    jobs.py         job state, atomic edits, fixture workflow
    storage.py      memory and transactional Firestore stores
    extraction.py   Gemini adapter, YouTube normalization, structured extraction
    compat.py       declared-spec resolution, clarification and deterministic comparison
    sourcing/       grounded discovery, safe page fetching and JSON-LD verification
    main.py         API routes, errors, CORS
  scripts/          OpenAPI export/check
  tests/            API and job concurrency tests
  pyproject.toml    backend dependencies and tooling
```

Frontend code belongs in `../frontend/`. Shared contracts belong in `../docs/contracts/`.

## Checks (from backend/)

```powershell
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python scripts/export_openapi.py --check
```

After changing public routes or schemas, regenerate and commit the shared contract:

```powershell
.venv/Scripts/python scripts/export_openapi.py
```

## Next backend milestones

See the [agreed feature roadmap](../docs/contracts/backend-roadmap.md) for priorities and
the [Cloud Run guide](infra/cloud-run.md) for the shared frontend integration environment.

- Validate extraction against real videos and a labelled BOM evaluation set.
- Add project page/code extraction and evidence fusion.
- Add durable queue dispatch and broaden seller format support.
- Add seller trust checks, broader compatibility rules with module data, and shipping/tax costing.
- Extend the shared contract with the frontend teammate as those features become available.
