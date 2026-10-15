# Bharat Sourcer

Bharat Sourcer turns maker project links into a reviewable bill of materials (BOM), then helps users find Indian seller offers and check declared-spec compatibility before selecting parts.

## What is implemented

- Backend API for asynchronous job-based workflows
- Demo mode (fixture data) and live mode (public YouTube extraction)
- BOM review and confirmation with edit operations
- Seller discovery and structured offer verification
- Compatibility assessment (declared-spec scope), offer selection, and partial costing
- Targeted refresh for stale/failed sourcing lines
- Optional Firestore-backed persistence and recovery

See the backend details and limits in [`backend/README.md`](backend/README.md) and the implemented API contract in [`docs/contracts/README.md`](docs/contracts/README.md).

## Repository layout

- [`backend/`](backend/) — Python/FastAPI service, tests, scripts, runtime config
- [`frontend/`](frontend/) — React/Vite client application and frontend deployment tooling
- [`docs/contracts/`](docs/contracts/) — source-of-truth contract for implemented API behavior
- [`docs/`](docs/) — architecture, delivery, and reference documentation
- [`research/`](research/) — cited background research

## Quick start

### 1) Run backend locally

Use Python 3.12+:

```bash
cd backend
python -m venv .venv
# macOS/Linux
.venv/bin/python -m pip install -r requirements-dev.lock -e ".[dev]"
# Windows PowerShell
# .venv/Scripts/python -m pip install -r requirements-dev.lock -e ".[dev]"
cp .env.example .env  # create only if missing
.venv/bin/python -m uvicorn bharat_sourcer.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/healthz>

By default, backend runs in demo mode and does not require cloud credentials.
[`backend/.env.example`](backend/.env.example) lists the common `BS_*` settings (the full set
is in [`config.py`](backend/src/bharat_sourcer/config.py)).
For live extraction, set `BS_DEMO_MODE=false` and your own `BS_GEMINI_API_KEY` in the
ignored `backend/.env` (see
[Live YouTube extraction](backend/README.md#live-youtube-extraction)).

### 2) Run frontend locally

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The frontend defaults to backend origin `http://127.0.0.1:8000`.
Google sign-in and other backends need an ignored `frontend/.env.local` based on
[`frontend/.env.example`](frontend/.env.example); <http://127.0.0.1:5173/?preview=1>
runs the UI on local sample data with no backend or Firebase project. See
[`frontend/README.md`](frontend/README.md) for details.

## Development checks

Backend CI runs:

- `ruff check`
- `ruff format --check`
- `pytest`
- OpenAPI export drift check (`python scripts/export_openapi.py --check`)

Equivalent local run (from `backend/`):

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
python scripts/export_openapi.py --check
python -m mypy
```

Frontend (from `frontend/`):

```bash
npm run lint
npm run format:check
npm run build
npm run test:server && npm run test:preview && npm run test:integration
```

Run all hooks automatically on commit with [pre-commit](https://pre-commit.com/)
(backend venv and frontend `node_modules` must be installed):

```bash
pre-commit install
pre-commit run --all-files
```

To hide the bulk formatting commit from `git blame`:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## Important notes

- Demo data is sample data and must be treated as labelled fixture output.
- Seller prices are snapshots from checked pages; tax, shipping, and final payable totals are not guaranteed.
- Compatibility grades are limited to declared-spec checks and are not full electrical/mechanical validation.
- Keep secrets in ignored local env files (`.env`, `.env.local`), never in source control.

## Security

Please report vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md), not in
public issues.

## Additional reading

- Backend setup and operational detail: [`backend/README.md`](backend/README.md)
- Frontend setup and behavior: [`frontend/README.md`](frontend/README.md)
- Current implemented contract: [`docs/contracts/README.md`](docs/contracts/README.md)
- Full docs index: [`docs/00-index.md`](docs/00-index.md)
