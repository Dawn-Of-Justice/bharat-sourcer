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
No credentials or cloud services are needed. Environment variables use the `BS_` prefix;
`.env` is loaded from the working directory (`backend/`).

`requirements-dev.lock` pins the tested runtime and development dependencies. Update it
deliberately when upgrading dependencies, then rerun checks and regenerate OpenAPI.

## Implemented milestone

1. `POST /v1/jobs` accepts an HTTP(S) project URL and returns a job ID and secret job token.
2. A background task loads a fixed weather-station BOM and waits for confirmation.
3. `POST /v1/jobs/{id}/confirm` applies all edits atomically.
4. A background task creates a demo report. `GET /v1/jobs/{id}` returns state and events.

Send `X-Job-Token` on reads and confirmations. Keep that token in the client session and
out of URLs/logs. It is a local capability token, separate from the planned Firebase Auth.

All URLs currently receive the same fixture. URLs are validated but never fetched.
`demo: true` marks the response; prices, totals and compatibility grades are `null`.
`done` means the demo flow finished, not that real sourcing ran.

Jobs live in process memory, disappear on reload/restart, and require **one worker**.
Use this server locally; durable execution, retention limits, rate limiting, Firebase
Auth/App Check and Firestore security rules are still needed before a public deployment.
`BS_DEMO_MODE=false` deliberately fails startup until a live implementation exists.

## Layout

```text
backend/
  src/bharat_sourcer/
    config.py       environment settings
    schemas.py      validated request/response models
    jobs.py         job state, atomic edits, fixture workflow
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

- Add real extraction behind the workflow interface after verifying Gemini capabilities.
- Introduce Firestore storage and durable execution, keeping job transitions explicit.
- Implement seller verification, deterministic compatibility rules, and costing.
- Extend the shared contract with the frontend teammate as those features become available.
