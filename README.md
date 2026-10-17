# Bharat Sourcer

Bharat Sourcer turns maker project links into a reviewable bill of materials (BOM), then helps users find Indian seller offers and check declared-spec compatibility before selecting parts.

Live site: <https://bharatsourcer.web.app>

## How it works

1. **Paste a project link.** A YouTube video, GitHub repo, Instructables or Adafruit Learn
   guide, or a maker blog. Gemini reads every source in parallel, and the backend merges
   duplicate parts and drops lines that aren't purchases.
2. **Review the BOM.** Edit lines, answer open spec questions, and confirm the list. A
   project overview draws each part and its wiring; it is AI-inferred and labelled so.
3. **Source parts in India.** The backend searches Indian sellers, checks each listing's
   page for price, stock and declared specs, and grades compatibility (A drop-in to
   X don't use). When no listing fits, an AI buyer picks a substitute and says what to change.
4. **Buy and build.** Pick offers, see per-seller totals and add-to-cart links, get
   fabrication services for 3D-printed or PCB lines, a step-by-step build guide, and code
   changes for swapped parts (with an optional compile check).

## What is implemented

- FastAPI backend with asynchronous jobs, live progress streaming and a Cloud Tasks queue
- Multi-source intake: YouTube, GitHub (README and code), Instructables, Adafruit Learn and
  blogs, fused into one BOM with evidence and confidence
- BOM review, edits and confirmation, including edits after sourcing
- Seller search, page-checked offers, declared-spec compatibility grades, AI buyer
  substitutes, offer selection, costing and targeted refresh
- Project overview diagram, build guide, project chat that can propose BOM edits, and code
  patches for substitutes
- Share links and PDF export
- Google sign-in or guest sessions, per-user quotas, project retention (30 days for guests,
  365 for accounts) and **Delete my data**
- Demo mode on labelled fixture data, with no cloud credentials needed
- Firestore persistence, structured logs, monitoring and alerts as code, and backups

See the backend details and limits in [`backend/README.md`](backend/README.md) and the
implemented API contract in [`docs/contracts/README.md`](docs/contracts/README.md).

## Tech stack

- **Backend:** Python 3.12, FastAPI, Gemini (Vertex AI or API key), Firestore, WeasyPrint
- **Frontend:** React 19, TypeScript, Vite, Firebase Authentication, and a small Node
  server that serves the app and proxies `/api`
- **Google Cloud:** Cloud Run, Cloud Tasks, Firebase Hosting, Secret Manager, Cloud
  Monitoring

## Repository layout

- [`backend/`](backend/) — Python/FastAPI service, tests, scripts, runtime config and
  [operations docs](backend/infra/README.md)
- [`frontend/`](frontend/) — React/Vite client application and frontend deployment tooling
- [`docs/contracts/`](docs/contracts/) — source-of-truth contract for implemented API behavior
  and `openapi.json`
- [`docs/`](docs/) — architecture, delivery, and reference documentation
- [`roadmap.md`](roadmap.md) — planned work

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

Backend CI runs `pip-audit`, `ruff check`, `ruff format --check`, `mypy`, `pytest` and an
OpenAPI export drift check. Frontend CI runs `npm audit`, lint, format check, build,
`test:server` and `test:preview`; run `test:integration` locally.

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
- What the app stores and for how long is on the site's [privacy page](https://bharatsourcer.web.app/privacy).

## Security

Please report vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md), not in
public issues. Operations docs (runbooks, incident response, SLOs, data inventory, release
checklist, cost guardrails): [`backend/infra/README.md#operations`](backend/infra/README.md#operations).

## Additional reading

- Backend setup and operational detail: [`backend/README.md`](backend/README.md)
- Frontend setup and behavior: [`frontend/README.md`](frontend/README.md)
- Current implemented contract: [`docs/contracts/README.md`](docs/contracts/README.md)
- Full docs index: [`docs/00-index.md`](docs/00-index.md)
