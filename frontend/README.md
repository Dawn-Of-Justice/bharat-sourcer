# Bharat Sourcer frontend

React + TypeScript + Vite app for the landing page and the first local job flow. This workspace owns its own dependencies and commands.

## Run locally

Start the backend as described in [backend/README.md](../backend/README.md), then in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. To use a backend at another origin, create an ignored `frontend/.env` with `VITE_API_BASE_URL=https://your-api-origin` (origin only, without `/v1`). The default is `http://127.0.0.1:8000`.

For the shared integration backend, create ignored `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=https://bharat-sourcer-integration-diahnrbuna-el.a.run.app
VITE_INTEGRATION_KEY=<privately-shared-team-key>
```

Restart Vite after editing this file. The key is sent as `X-Integration-Key` on API calls. Vite exposes `VITE_` values to the browser, so use this only for team integration, not a public release.

Run `npm run build` before delivery. `npm run preview` serves the built frontend locally.

## Cloud Run team preview

The production build sends same-origin requests to `/api`. The Node server in
`server.mjs` serves the built app and forwards those requests to the deployed backend,
adding the team key from Cloud Run Secret Manager. The key is absent from the production
JavaScript bundle. `/api/healthz` maps to the backend's Cloud Run-safe `/health` route.
The frontend pages and API proxy do not require an application login. The integration
key is used only by the server to authenticate requests to the backend.

`scripts/deploy_cloud_run.ps1` targets project `hackathon-510415`, region `asia-south1`,
and service `bharat-sourcer-web`. Sign in with a project-authorized account, then
run the script from `frontend/`:

```powershell
gcloud auth login
.\scripts\deploy_cloud_run.ps1
```

An IAM administrator must grant the dedicated frontend service account
`roles/secretmanager.secretAccessor` on the existing `bharat-sourcer-integration-key`
secret before deployment. The script creates the service account if needed and deploys
the Dockerfile. It uploads only files
listed by `.gcloudignore`, excluding `.env.local`, dependencies, caches and built output.
An IAM administrator must enable direct browser access once:

```powershell
gcloud run services update bharat-sourcer-web --project=hackathon-510415 --region=asia-south1 --no-invoker-iam-check
```

Google sign-in and saved-project UI are implemented; real Firebase configuration and auth-enabled staging verification are still required before activation.
For local checks without a live backend, run `npm run test:server`; its API replies are
labelled dummy data.

## Current behavior

- The landing page offers fields for YouTube, tutorial/blog pages, GitHub repositories and audio files. YouTube submits to the live or demo API. Article and GitHub links can preview the fixed fixture only when the backend reports demo mode; the live backend does not extract them yet. Audio is a visible planned input and is not uploaded.
- The job page keeps `X-Job-Token` in `sessionStorage` and polls `GET /v1/jobs/{id}` throughout the job's lifetime, including after extraction finishes. It lets users correct quantities/names and mark owned or removed parts, then explicitly confirms the BOM.
- The conversation panel renders persisted job messages beside the BOM, sends questions with client UUIDs, shows saved line evidence for citations, and lets users accept or reject proposed draft edits. Accepting does not confirm the BOM. Lost connections are retried with backoff; the UI uses polling, which the [conversation contract](../docs/contracts/conversation.md) permits in place of the SSE stream.
- Results show the backend's sourcing outcomes and checked seller offers. Demo data is conspicuously labelled. Seller prices are snapshots; tax, shipping and final payable total are not known.
- The landing illustration changes with the selected YouTube, article/blog, GitHub or audio tab. It is built with CSS/SVG, needs no image download, and respects reduced-motion settings. Planned sources are labelled as preview concepts.

This is the first frontend slice. Offer selection, targeted refresh, the YouTube player, PWA share target, exports and public sharing are subsequent integration work. The implemented API is documented in [docs/contracts](../docs/contracts/README.md); the broader [frontend architecture](../docs/02-architecture/09-frontend-and-ux.md) is a target design.

## Local UI preview without API calls

Run npm run dev and open http://localhost:5173/?preview=1. The preview toolbar switches between landing, review, parallel progress, and results. API actions use in-memory dummy responses; the sample image is a local labelled illustration. Preview mode is development-only and requires preview=1 in the URL. Normal URLs retain the configured backend connection.


## Accounts and saved projects (5 October 2026)

- Google sign-in creates or reopens a Firebase account. The SDK refreshes ID tokens before API requests, including chat and polling. All browser requests include credentials; POSTs send `X-Requested-With: BharatSourcer`.
- The account panel also supports explicit guest entry and logout. `/projects` lists owner-only saved projects with pagination and opens their existing job IDs without creating another job. Guest-to-account saving is explicit after sign-in and does not rerun analysis.
- The proxy forwards Authorization, Cookie, Origin and X-Requested-With, preserves separate Set-Cookie headers and Retry-After, and forces no-store. It deliberately does not trust browser-supplied client-IP headers.
- A 401 prompts sign-in recovery. Provider outages preserve the session. Quota errors show the retry time and leave saved work readable; the account panel reads personal usage when opened. Live sourcing can be paused/resumed.
- AUTH_DISABLED keeps the previous job-token flow available and labels account saving as unavailable. Do not enable backend authentication until the staging checklist in `docs/contracts/authentication.md` passes.

Copy `.env.example` to an ignored local env file and supply the four public Firebase web values from the project owner. These are Vite build-time values; the current Cloud Run deployment script does not yet supply them. Production deployment/configuration is not part of this local UI change. Authorize the frontend domain in Firebase and configure backend CORS before live testing. Google login requires a popup-capable browser. Guest cookies need HTTPS and a same-origin proxy, not direct cross-origin localhost requests.

Use `http://127.0.0.1:5173/?preview=1` for **no-API local testing**, even if `.env.local` points at a live backend. Firebase initialization is disabled and all API methods use local sample responses. Click Sign in → Try demo account → My projects → Open project. Also try Continue as guest → My projects → Save my projects → Try demo account → Save to my account. The demo account marker lasts for the current tab session; project contents are in-memory fixtures and reset on reload. No real account is created.

Validation: `npm run build`, `npm run test:server`, and `npm run test:preview`. The preview test executes the real preview/auth/API modules with network access forbidden. Real Google login, two-account isolation, revoked users, cookie expiry and responsive visual QA remain staging/browser checks. Existing legacy jobs still require their original token; a dedicated legacy-project migration UI is not yet provided.
