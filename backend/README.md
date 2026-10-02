# Backend

Python + FastAPI, with an isolated package, virtual environment, tests and configuration.

## Run locally (PowerShell)

From the repository root, using Python 3.12 or newer:

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock -e ".[dev]"
Copy-Item .env.example .env
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
4. A background task creates a report. `GET /v1/jobs/{id}` returns state, errors and events.

Send `X-Job-Token` on reads and confirmations. Keep that token in the client session and
out of URLs/logs. It is a local capability token, separate from the planned Firebase Auth.

In demo mode, all URLs receive the same fixture. URLs are validated but never fetched.
`demo: true` marks the response; prices, totals and compatibility grades are `null`.
`done` means the implemented flow finished; sourcing has not run in either mode.

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
Seller search, prices and compatibility remain unavailable in live mode.

Automated tests use a mocked HTTP transport. A credentialed smoke test on 2 Oct 2026
successfully extracted four parts from YouTube Short `qSRrq_VZ4Fw` and reached
`awaiting_confirmation` in about eight seconds. This validates connectivity and response
parsing, not the accuracy or completeness of the BOM.

The live endpoint rejected the full Pydantic generation schema with HTTP 400. The adapter
now sends an inline schema without bounds or string constraints, then applies the full
Pydantic validator locally. Invalid quantities, timestamps, oversized results and extra
fields are still rejected. Public API schemas retain their validation constraints.

Jobs live in process memory, disappear on reload/restart, and require **one worker**.
Use this server locally; durable execution, retention limits, rate limiting, Firebase
Auth/App Check and Firestore security rules are still needed before a public deployment.
Live mode fails startup if `BS_GEMINI_API_KEY` is missing or empty.

## Layout

```text
backend/
  src/bharat_sourcer/
    config.py       environment settings
    schemas.py      validated request/response models
    jobs.py         job state, atomic edits, fixture workflow
    extraction.py   Gemini adapter, YouTube normalization, structured extraction
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
- Introduce Firestore storage and durable execution, keeping job transitions explicit.
- Implement seller verification, deterministic compatibility rules, and costing.
- Extend the shared contract with the frontend teammate as those features become available.
