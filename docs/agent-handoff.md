# Agent handoff (backend work, 5–7 October 2026)

This file is for the next agent continuing backend work on Bharat Sourcer. Read it with
`AGENTS.md`, `backend/README.md` (implemented behaviour), `docs/contracts/README.md`
(API contract) and `docs/contracts/backend-roadmap.md`.

Production state at handoff (7 October 2026): backend **v0.21.0** live on Cloud Run
(`bharat-sourcer-integration`, revision 00048 with `BS_YOUTUBE_API_KEY` mounted, max 3
instances); frontend on Cloud Run (`bharat-sourcer-web`) has **not** been updated for v0.20
or v0.21 (see the frontend handoffs). Everything is merged to `main` (PRs #9–#29).

**Read first for v0.20–v0.21:** `docs/contracts/frontend-handoff-v0.20.md`,
`docs/contracts/frontend-handoff-v0.21.md`, `roadmap.md` (owner-approval proposals) and
`backend/infra/README.md` (TTL policies, alert, scaling runbook).

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

## What was done (v0.20.0 → v0.21.0, 6–7 October 2026)

- **v0.20.0:** safety flags, costing (GST/shipping/import, cart plans), multi-source intake
  with fusion/look-alikes/confidence, seller trust labels, CSV/HTML export and share links,
  disabled-by-default Gemini extras, catalogue-backed compatibility grades A–D/X, a draft
  (unreviewed) eval gold set.
- **v0.21.0 sourcing engine:** buyable spec per line, seller catalogue search first (free),
  LLM spec judge with server-verified quotes, paid grounded discovery only when needed,
  automatic recommendations and selections (judge-confirmed offers included),
  seller-grouped `order_plan`, `line_image`, shared cache + per-job budget, nearby markets
  (Maps grounding), YouTube description intake.
- **Infra (owner-approved 7 Oct):** Firestore TTL on `_cache`/`_audio`; queue-age alert
  policy emailing the owner; API max instances 3; YouTube Data API key in Secret Manager.
- **Live check** of the failed job `e5c272c4…` (~$0.12): 5 of 6 parts auto-selected in 3
  seller groups. Two judge errors (blue LED for "clear LED", 4 mm rod for bare wire) were
  fixed by giving the judge the part name and stricter rules; **not yet re-verified live**
  (`backend/scripts/check_job_sourcing.py <job.json>`, needs owner OK: it costs money).

## Pending, in suggested order

1. **Re-verify the judge fix live** on the failed job with the script above (owner OK).
2. **Frontend:** build the v0.20 and v0.21 handoffs. Item 1 of each (code and YouTube
   description evidence render as `null — …`) is needed now; the order plan should be
   the main view after sourcing.
3. **Min instances 15 Oct – 6 Nov** and the revert on 7 Nov (`backend/infra/README.md`).
4. **Gemini cost:** after a few days of traffic run
   `cd backend && python scripts/usage_report.py --days 7`, compare with the estimates in
   `backend/infra/gemini-cost.md` and `job.cost_estimate`, then A/B low thinking for
   research and the Flex tier. Budget for the `gemini-3.8-flash` price doubling on
   2027-01-01.
5. **Accuracy:** two people review the draft gold set (`backend/evaluation/gold/`) and
   label the 5 candidate videos; no accuracy claim until then.
6. **Owner decisions still open:** grade B auto-apply, the ₹60 per-extra-seller penalty,
   IGST rate for imports and the courier placeholder, ElectronicsComp/FlyRobo in
   `known_sellers.json`, safety-flag false positives, whether description links should
   cost extra extraction calls, and the remaining `roadmap.md` proposals (M9 compile,
   Web Risk, distributor APIs, headless renderer §15).

## How to start

1. `git checkout main && git pull`, create the session's designated branch.
2. Backend setup: `python3.12 -m venv .venv && .venv/bin/pip install -r
   requirements-dev.lock -e ".[dev]"` inside `backend/`; run the checks above.
3. Confirm production versions: `curl $BS_BACKEND_URL/openapi.json` (version field).
4. Pick the next item from "Pending"; for anything major, write `roadmap.md` and ask.
