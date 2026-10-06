# Agent handoff (backend work, 5–6 October 2026)

This file is for the next agent continuing backend work on Bharat Sourcer. Read it with
`AGENTS.md`, `backend/README.md` (implemented behaviour), `docs/contracts/README.md`
(API contract) and `docs/contracts/backend-roadmap.md`.

Production state at handoff: backend **v0.19.3** live on Cloud Run
(`bharat-sourcer-integration`); frontend on Cloud Run (`bharat-sourcer-web`). Everything
is merged to `main` (PRs #9–#24); no open PRs.

## Standing instructions from the owner

These came from the project owner during the session and should be followed unless they
say otherwise:

1. **Scope:** work on the backend. Small frontend changes are allowed only when the
   frontend blocks a backend feature ("nothing huge"); larger frontend work belongs to a
   teammate, so document it in `docs/contracts/` instead.
2. **Merging:** the agent may merge its own PRs once CI is green ("do the merge, don't
   wait for me"). Never merge red CI or with open review threads.
3. **Major changes need approval:** anything needing architectural or infrastructure
   change (new services, databases, schedulers, paid third-party APIs, IAM) goes into a
   `roadmap.md` proposal first; wait for the owner to confirm.
4. **Save money:** do not call paid APIs (Gemini) during development. Build with mocks,
   fixtures and offline tests; make one live smoke call only once a change is stable, and
   ask before running it.
5. **Parallelise:** use subagents for independent work whenever possible (isolated
   worktrees; the main agent integrates, bumps versions, regenerates OpenAPI, opens PRs).
6. **Document everything:** every change updates the READMEs/contracts; every new Gemini
   cost finding goes into `backend/infra/gemini-cost.md` with a dated entry and source.
7. **Product direction:** the backend must understand the project from the video or
   page and decide quantities and specs itself; never expect the maker to supply them.
   Inferred values are labelled with a reason and stay editable.

## Repository rules (from AGENTS.md, plus practice)

- Backend lives in `backend/`; frontend in `frontend/`; contracts in `docs/contracts/`.
- After changing public schemas or routes: `cd backend && python scripts/export_openapi.py`.
- Each release bumps the version in three places: `backend/pyproject.toml`,
  `backend/src/bharat_sourcer/main.py` (`FastAPI(version=...)`) and
  `backend/scripts/check_deployed.py`; then add a top note to `backend/README.md` and
  `docs/contracts/README.md`.
- Demo/fixture data must be labelled; never present fixture prices, compatibility or
  evidence as verified.
- Checks before every push (CI runs the same):
  `ruff check .`, `ruff format --check .`, `pytest`, `python scripts/export_openapi.py --check`
  (backend, Python ≥ 3.12); `npm run build`, `npm run test:server`, `npm run test:preview`
  (frontend).
- `backend/tests/conftest.py` strips `BS_*` env vars, so exported real keys do not break
  tests.

## Environment notes

- **Deploys:** merges to `main` deploy both services via GitHub Actions to Cloud Run
  (image-only update; env vars, secrets, runtime identity and scaling are preserved).
  During the 5 October GitHub Actions incident the owner deployed manually from the repo
  root: `gcloud run deploy bharat-sourcer-integration --source backend --region
  asia-south1 --project hackathon-510415 --quiet` (and `bharat-sourcer-web --source
  frontend`). Do not run from inside `backend/`.
- **Agent credentials** (session env vars, set by the owner): `BS_GEMINI_API_KEY`,
  `BS_INTEGRATION_KEY`, `BS_BACKEND_URL`, `GCP_SA_KEY_JSON` (read-only service account
  `claude-readonly@hackathon-510415`: logs, Cloud Run, Firestore read). The agent cannot
  deploy or change IAM; ask the owner.
- **Production data:** Firestore collection `backend_integration_jobs` (not the default
  `backend_jobs`).
- **Live API checks:** production has auth enabled. Start a guest session
  (`POST /v1/session/guest` with `X-Integration-Key`, `X-Requested-With: BharatSourcer`
  and the web origin), then create jobs.
- **Sandbox limits:** `SafeFetcher` uses pinned direct connections that the agent sandbox
  blocks (HTTP 403 from the proxy); use `curl`/`httpx` through the proxy for offline
  investigation. robu.in and hackster.io block automated access (Cloudflare).
- **Pitfall:** an interrupted turn can kill background subagents silently. Check a
  subagent's transcript timestamp before reporting it as "still running".

## What was done (v0.17.4 → v0.19.3)

| Area | Change |
| --- | --- |
| CI/CD | Fixed red CI; backend and frontend workflows deploy to Cloud Run instead of a nonexistent GKE cluster; deploy identity extended for the web service |
| Images | Placeholder seller images rejected, `og:image` fallback, plural category illustrations, frontend falls back to `image_candidates`; default image model `gemini-3.1-flash-lite-image` (generation disabled in production) |
| Sourcing | Indian retailers ranked first in grounded discovery; seller spec tables and labelled JSON-LD properties with `spec_conflicts`; 17 real seller-page fixtures (verification 20/20, images 15/15, specs 27/27); inch notation, label-unit ranges, URL escape fixes |
| Inputs | Instructables (reads the project JSON the page loads) and GitHub README extraction with server-checked quotes; Hackster returns `SOURCE_UNAVAILABLE`; strict robots.txt parser |
| Project understanding | `job.project` with AI-written editable title/description, summary, power/controller/interfaces/assumptions; inferred quantities (`qty_source`, `qty_reason`); inferred measurable requirements (`origin`, `reason`); `POST /v1/jobs/{id}/project`; titles on `GET /v1/projects` |
| Chat | Reviewed spec proposals; refresh completion messages; `job.actions` history |
| Ops | Bounded, failure-isolated queue sweep with `QUEUE_AGE_EXCEEDED` logs; Gemini usage logging per call (`GEMINI_USAGE`, `scripts/usage_report.py`) |
| Quality | Offline extraction evaluation harness (`scripts/evaluate_extraction.py`) |

Live checks (one Gemini call each): GitHub smartknob README → 21 quoted parts in 10 s;
Instructables obstacle robot → 13 quoted parts in 7 s; YouTube Short (ESP32-S3 piezo drum
trigger) → correct title/summary and, after v0.19.1, measurable requirements
(1 MΩ, 3.3 V, USB-C…). One run omitted jumper wires: outputs vary between runs.

## Pending, in suggested order

1. **Frontend teammate (documented, not built):** project cards should show
   `title`/`description` and offer an edit control
   (`docs/contracts/project-understanding.md`).
2. **Gemini cost:** after a few days of traffic run
   `cd backend && python scripts/usage_report.py --days 7` and record numbers in
   `backend/infra/gemini-cost.md`. Then A/B, one at a time, with the evaluation harness:
   skip discovery for refreshes of known offer URLs; fewer/consolidated search queries
   per part; cache discovery per part name; `thinkingLevel: low` for `chat_scope` and
   `discovery`; Flex tier for Cloud-Tasks research; stable-prefix prompt ordering for
   implicit caching; video `fps`/agentic mode for long videos. Budget for the
   `gemini-3.8-flash` price doubling on 2027-01-01.
3. **Accuracy:** label 5–10 real videos in the harness format (see `backend/README.md`)
   and run it; needed before any accuracy claim and to judge inference quality.
4. **Coverage:** many parts still end with no verified offer (sellers without JSON-LD,
   Cloudflare blocks). Seller APIs/feeds or affiliate programmes would be **major**
   (paid third-party/infra) and need a `roadmap.md` proposal and owner approval.
5. **Smaller items:** completion messages only for chat-approved refreshes (not
   `POST /refresh`); one source per job (video and project page not combined); relaxing
   the strict title match using spec-table evidence (needs a decision, see
   `backend/infra/seller-page-evaluation.md`); Hackster unsupported; image generation on
   the new model untested live.
6. **Research not yet done:** shipping/GST and HSN codes, competitor tools and Indian
   seller APIs were scoped out of the last research run; rerun when the owner asks.

## How to start

1. `git checkout main && git pull`, create the session's designated branch.
2. Backend setup: `python3.12 -m venv .venv && .venv/bin/pip install -r
   requirements-dev.lock -e ".[dev]"` inside `backend/`; run the checks above.
3. Confirm production versions: `curl $BS_BACKEND_URL/openapi.json` (version field).
4. Pick the next item from "Pending"; for anything major, write `roadmap.md` and ask.
