# Backend

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
are no automatic retries or demo fallbacks. Start a new job to retry. HTTP read timeout
is configurable; output is limited to 8,192 tokens and validated to at most 100 parts.
Compatibility is limited to declared-spec comparisons described below. Total costing remains unavailable.

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

A startup/periodic sweep resumes queued work and report creation. Expired extraction
is marked failed rather than automatically repeating a billed API request. Use this
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
All sellers are labelled `unverified`; no offer is selected automatically.

Part resolution supports Pro Micro, OLED, TTP223 and USB cable families. It is not a
general knowledge graph or automatic datasheet resolver; other families stay unknown.
Missing specifications do not prevent discovery and remain visible for review.

Lines are checkpointed in Firestore as sourcing progresses. An expired sourcing lease
marks the job failed with `SOURCING_INTERRUPTED` while retaining saved lines. No automatic
paid retry occurs. Per-line search errors and the part limit are explicit in the report.

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
are reserved for future rules. Line-level selected grade and total remain null.

Rule references: [SparkFun Pro Micro guide](https://learn.sparkfun.com/tutorials/pro-micro--fio-v3-hookup-guide/all),
[Adafruit OLED guide](https://learn.adafruit.com/monochrome-oled-breakouts?view=all),
[Tontek TTP223-HA6 datasheet](https://www.tontek.com.tw/uploads/product/245/TTP223-HA6_V1.1_EN.pdf).
For TTP223, supply and output-mode rules are based on the exact declared module; the cited
chip datasheet is background and does not establish which chip revision a seller ships.

## Package layout

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

- Validate extraction against real videos and a labelled BOM evaluation set.
- Add project page/code extraction and evidence fusion.
- Add durable queue dispatch and broaden seller format support.
- Add seller trust checks, broader compatibility rules with module data, and costing.
- Extend the shared contract with the frontend teammate as those features become available.
