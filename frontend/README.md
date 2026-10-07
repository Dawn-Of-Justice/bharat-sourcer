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
INTEGRATION_KEY=<privately-shared-team-key>
```

Restart Vite after editing this file. Vite's development proxy injects `X-Integration-Key` server-side. Browser requests use same-origin `/api` and include cookies; do not use a `VITE_` prefix for the team key.

Run `npm run build` before delivery. `npm run preview` serves the built frontend locally.

## Cloud Run team preview

The production build sends same-origin requests to `/api`. The Node server in
`server.mjs` serves the built app and forwards those requests to the deployed backend,
adding the team key from Cloud Run Secret Manager. The key is absent from the production
JavaScript bundle. `/api/healthz` maps to the backend's Cloud Run-safe `/health` route.
The backend requires either a Firebase Google account or a guest session. The
integration key is used only by the server to authenticate requests to the backend.

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

Google sign-in, guest sessions and saved-project UI are implemented. The deployed
backend has authentication enabled. Real Google account and guest-claim browser checks
remain outstanding. For local checks without a live backend, use `?preview=1`; its
API replies are labelled dummy data.

## Current behavior

Project titles and descriptions appear on the job page and saved-project cards. Hover or focus a title or description to reveal its pencil control; touch screens show the controls directly. Each field saves independently. Older projects retain host and URL fallbacks.

Part images use the backend's labelled category or placeholder fallback when photos are unavailable. Broken photo URLs are reported to the image endpoint for an optional generated illustration. Conflicting seller specs show the reported values while leaving the field unknown.

- The landing page offers fields for YouTube, tutorial/blog pages, GitHub repositories and audio files. The Article tab accepts Instructables, Adafruit Learn and the maker blogs listed in [multi-source-intake.md](../docs/contracts/multi-source-intake.md); Hackster links get an explanation instead of a request because Hackster refuses automated access. "Add another source" adds up to 3 extra links, sent as `sources` on `POST /v1/jobs`; the form allows only one YouTube video per project. Audio is a visible planned input and is not uploaded. The form does not ask for a PIN code: parts are ordered online for delivery, so location is an account setting instead.
- Review screen (backend v0.20/v0.21): safety banners from `job.safety_flags` above the BOM (`SafetyBanners.tsx`, reusable, labelled "Automatic safety check, not a guarantee", MAINS never collapsed, guidance as a checklist, per-row code badges); a "Sources read" card from `source_reports` with failed extra sources and their errors, plus `video_meta.links` as "Links in the video description" (store links marked as not verified, nothing followed by the frontend); a conflict banner linking to lines, per-line conflict values with source and locator links; look-alike warnings (AI-suggested marked); confidence chips (✓ Verified / ◐ Likely / ⚠ Check) with the reason; evidence labelled Video, Page quote, Code (`file:line`) or Video description, linking to `url`; and a buying spec panel per line (category, mount and reason, params with inferred labels, a **Needs value** prompt with the project's assumed range) whose edits are sent as `buyable_spec` in the confirm `update`. `?preview=1` shows all of these with dummy fixtures from `previewReview.ts`.
- The job page keeps `X-Job-Token` in `sessionStorage` for legacy projects and reads `GET /v1/jobs/{id}` to reopen saved projects. It lets users correct quantities/names and mark owned or removed parts, then explicitly confirms the BOM. Live jobs receive fetch-based SSE snapshots.
- Build overview is a collapsed summary of the project, power, controller, interfaces and assumptions to check. Suggested quantities retain their explanations. Each part has a Build details button that opens optional requirements with plain-language labels and an example. Suggested details retain origin/reason metadata until edited.
- The wider conversation panel spaces messages apart and scrolls its own history to new messages, respecting reduced-motion settings. It renders persisted job messages beside the BOM, sends questions with client UUIDs, shows saved line evidence for citations, and lets users accept or reject proposed draft edits. Accepting does not confirm the BOM. Live updates reconnect with refreshed credentials and backoff.
- On completed reports the conversation also shows reviewed seller refresh proposals and spec/requirement proposals (`spec_proposal`) with Approve/Reject through the shared decision endpoint. The spec card lists each part and its proposed values and explains that approval re-checks saved quotes, clears those parts' selections and marks AI research stale. Stale (`PROPOSAL_STALE`) or already-decided (`PROPOSAL_DECIDED`) 409s show a message and reload the job.
- Refresh completion messages (`refresh_results`) show a per-part status, offer count and lowest price labelled "seller-listed, not a verified total", with links between the completion message and its original proposal. A collapsible "Action history" lists `job.actions` newest first. The `?preview=1&stage=done` preview shows these states with dummy messages.
- Results start with expandable part cards showing a photo, name, quantity and quote status. Opening a card reveals build details, seller quotes, research and source notes. Demo data is conspicuously labelled. Seller prices are snapshots; tax, shipping and final payable total are not known.
- Each part image uses the first loadable seller offer photo, then the backend's labelled page reference images (`image_candidates`), so parts without a verified offer can still show a reference photo. A broken image falls through to the next one; the visible label always states the image source.
- The landing illustration changes with the selected YouTube, article/blog, GitHub or audio tab. It is built with CSS/SVG, needs no image download, and respects reduced-motion settings. Planned sources are labelled as preview concepts.

### Report (backend v0.20–v0.21)

- **Order plan** (`OrderPlan.tsx`) is the default report view when `report.order_plan` exists; "All parts and offers" shows the per-line list. One card per seller: line image with its label, quantity and pack rounding, unit and line price, subtotal, GST, shipping and seller estimate each with a ✓ Known / ≈ Estimated / ? Unknown chip, the free-shipping gap, the dated shipping policy (unverified policies marked), and product links in new tabs. Lines with `selected: false` show `blocked_reason`. The plan disclaimer and plan estimate are always shown, never as a payable total.
- **Recommendations:** ★ Recommended with a "why?" popover (`recommendation.reasons`), ✓ Your choice for user picks, and **Change**, which opens the offer picker and posts `/selections`. Grade B picks need the changes acknowledged (`accept_changes`). Judge-confirmed offers (`match` exact or compatible, no grade) can be selected.
- **Offers:** match chips (Exact / Compatible / Partial, "AI match" or "Spec match", with reasons and quotes), pack size and variant, GST chips (`tax_included`), seller trust badges with a "Why?" list, and compatibility grade chips (A–X, or "Not enough information") with a "what changes" drawer, safety items first.
- **Backend v0.22:** report parts show the buying spec actually used during sourcing, including specs written for older jobs. A missing value is called out before manual selection, which asks for acknowledgement. A skipped extra research review is labelled as skipped; Shopify variant offers continue to use their own product URLs and variant names.
- **Unsourced group** with `message`, `next_steps`, research leads and a jump to the part's details and refresh. Lines without offers show `sourcing_error.message` and `seller_search.candidate_urls` as unverified leads.
- **Costing footer** (`report.costing`) with assumptions, `at least ₹X + unknown` for unknown totals and per-seller policies. Also a **plan comparison** (Cheapest / Fewest sellers / Recommended, from `GET /plans`; Apply posts `/selections`) and an **import card** (shown only when `import_baseline` exists) with a US reference price form (`POST /import-references`, which counts toward the action budget).
- **Nearby markets** (`Markets.tsx`): a city from the project country's `market_cities` (`GET /v1/countries`) or "use my location" (rounded to 2 decimals). Google Maps sources come straight after the summary and places, in order, as links, and are always visible. "Google Maps" is never altered or line-broken. Demo results are labelled as a fictional sample.
- **Export and share** (`ReportActions.tsx`): Download CSV and Print / PDF fetch through the proxy and save or open the blob. The share control creates, copies and revokes links; the token is shown once, and creating a new link replaces the old one. The server proxy now forwards `DELETE`. **Public share page** `/shared/<token>` (`SharedReport.tsx`) renders the report read-only (no chat, edit, select, refresh or image generation), with `notice` and the demo label, and handles 404 (revoked) and 429.
- **Explain aloud** appears only when `GET /extras` reports it as enabled. Zoom and parts-bin scan are not built on the report.
- The estimated AI cost (`job.cost_estimate.total_usd`) is labelled as an estimate, not a charge.
- Preview: `?preview=1&stage=plan` shows a dummy non-demo order plan (invented sellers, prices, grades and shops, all labelled "dummy"). The toolbar's "Shared link" opens the read-only share page. In nearby markets, Bengaluru shows a dummy grounded layout with sources; other cities show the demo sample.

The YouTube player and PWA share target remain future frontend work. The implemented API is documented in [docs/contracts](../docs/contracts/README.md); the broader [frontend architecture](../docs/02-architecture/09-frontend-and-ux.md) is a target design.

## Local UI preview without API calls

Run npm run dev and open http://localhost:5173/?preview=1. The preview toolbar switches between landing, review, parallel progress, and results. API actions use in-memory dummy responses; the sample image is a local labelled illustration. Preview mode is development-only and requires preview=1 in the URL. Normal URLs retain the configured backend connection.

## Responsive layout

Every screen is checked for zero horizontal scroll at 320, 375, 414, 768, 1024, 1280, 1440 and 1920px. Main breakpoints in `styles.css`: 1000px (chat panel moves below the report), 600px (phone layout: stacked cards, wrapping totals) and 380–420px (narrow phones: account dialog, review fields, hero chips). Single-column grids use `minmax(0, 1fr)` so long seller names and prices wrap instead of widening the page. On touch screens (`pointer: coarse`) buttons, form fields, disclosure summaries and plan action links get a 44px hit area; small report chips grow to about 30px. The account dialog's close button stays visible while a long panel scrolls on phones.


## Accounts and saved projects (5 October 2026)

- Google sign-in creates or reopens a Firebase account. The SDK refreshes ID tokens before API requests, including chat and fetch-based SSE reconnects. All browser requests include credentials; POSTs send `X-Requested-With: BharatSourcer`.
- Signed-in accounts choose a **Country** from a flag dropdown in the account panel (`CountryPicker.tsx`, exposed as `useAccount().country`). The list comes from `GET /v1/countries` and the choice is saved with `POST /v1/account/settings`; new projects default to it on the backend. Only India is supported today. Flags are inline SVGs keyed by country code; add one when the backend adds a country ([countries.md](../docs/contracts/countries.md)).
- The account panel also supports explicit guest entry and logout. `/projects` lists owner-only saved projects with pagination and opens their existing job IDs without creating another job. Guest-to-account saving is explicit after sign-in and does not rerun analysis.
- The proxy forwards Authorization, Cookie, Origin and X-Requested-With, preserves separate Set-Cookie headers, Retry-After and Cache-Control, and applies no-store if upstream has no cache policy. It deliberately does not trust browser-supplied client-IP headers.
- A 401 prompts sign-in recovery. Provider outages preserve the session. Quota errors show the retry time and leave saved work readable; the account panel reads personal usage when opened. Live sourcing can be paused/resumed.
- Backend authentication is enabled. Account and guest project access uses the deployed identity routes.

Copy `.env.example` to an ignored local env file and supply the four public Firebase web values from the project owner. The Cloud Run deployment script reads these public values and serves them at runtime. The frontend domain is authorized in Firebase and included in backend CORS. Google login requires a popup-capable browser. Guest cookies need HTTPS and a same-origin proxy, not direct cross-origin localhost requests.

Use `http://127.0.0.1:5173/?preview=1` for **no-API local testing**, even if `.env.local` points at a live backend. Firebase initialization is disabled and all API methods use local sample responses. Click Sign in → Try demo account → My projects → Open project. Also try Continue as guest → My projects → Save my projects → Try demo account → Save to my account. The demo account marker lasts for the current tab session; project contents are in-memory fixtures and reset on reload. No real account is created.

Validation: `npm run build`, `npm run test:server`, `npm run test:preview`, and `npm run test:integration`. The preview test executes the real preview/auth/API modules with network access forbidden. The integration test exercises the API client against a local identity-aware fixture. Real Google login, two-account isolation, revoked users and cookie expiry still require live browser checks. Local browser checks cover the wide desktop layout, 390px mobile layout, card expansion, inline editing, build details, and new-message scrolling. Older unowned jobs can be claimed using their original browser-session token.
