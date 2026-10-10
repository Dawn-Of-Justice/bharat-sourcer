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

## Checks

Node 24 or newer (`.nvmrc`). CI runs lint, format check, build, `test:server` and `test:preview`.

| Command                                        | What it does                                                                          |
| ---------------------------------------------- | ------------------------------------------------------------------------------------- |
| `npm run lint` / `npm run lint:fix`            | ESLint (type-aware TypeScript, React hooks, React Refresh); fails on any warning      |
| `npm run format` / `npm run format:check`      | Prettier (`.prettierrc.json`: no semicolons, single quotes, 120 columns)              |
| `npm run typecheck`                            | `tsc --noEmit` (also part of `npm run build`)                                         |
| `npm run test:server` / `npm run test:preview` | Server proxy tests; preview modules with network access forbidden (no backend needed) |
| `npm run test:integration`                     | API client against a local identity-aware fixture                                     |

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

### Landing

- The landing page offers fields for YouTube, tutorial/blog pages, GitHub repositories and documents (PDF, DOC, DOCX). The Article tab accepts Instructables, Adafruit Learn and the maker blogs listed in [multi-source-intake.md](../docs/contracts/multi-source-intake.md); Hackster links get an explanation instead of a request because Hackster refuses automated access. "Add another source" adds up to 3 extra links, sent as `sources` on `POST /v1/jobs`; the form allows only one YouTube video per project. Documents are a visible planned input and are not uploaded. The form does not ask for a PIN code: parts are ordered online for delivery, so location is an account setting instead.
- The landing illustration changes with the selected YouTube, article/blog, GitHub or document tab. It is built with CSS/SVG, needs no image download, and respects reduced-motion settings. Planned sources are labelled as preview concepts.

### Project page

One column in the landing page's style (`App.tsx` `JobPage`, `ProjectFrame.tsx`). The job page keeps `X-Job-Token` in `sessionStorage` for legacy projects and reads `GET /v1/jobs/{id}` to reopen saved projects; live jobs receive fetch-based SSE snapshots.

- **Progress strip:** Review the parts → Find sellers → Order plan, with a live note for the current step and the Pause/Resume control. Finished steps can be revisited read-only: the confirmed list (changes after confirming go through chat suggestions) and how the seller search went per part. Content slides in the direction of travel; all motion stops under reduced motion.
- **Side panels:** the chat ("Ask about this build", with a badge for suggestions waiting for approval) and one part's details share `SidePanel`. On screens 1100 px and wider the page makes room for the panel; below that it is full screen. Only one is open at a time; Esc or Close returns focus to the opener.
- **Needs you** (`ReportSummary.tsx`): one list of decisions. Safety checks from `job.safety_flags` expand in place (mains open by default) and are labelled as automatic checks, not a guarantee. The review stage adds conflicting sources, unclear parts and the guest part limit; results add parts without a seller (`order_plan.unsourced`), selections waiting for confirmation (`selected: false` with `blocked_reason`) and chat suggestions waiting for approval.
- **Review:** rows with inline quantity and "I have it". The part panel holds the name, quantity (with the reason for a suggested quantity), build details (requirements with plain-language labels), the buying spec (category, mount, params, a **Needs value** prompt; edits are sent as `buyable_spec` in the confirm `update`), conflict values, look-alike warnings, evidence (Video, Page quote, Code `file:line`, Video description) with the confidence chip, and Remove/Undo. "Where these came from" holds the build overview and Sources read (`source_reports`, plus `video_meta.links`; store links are marked unverified and nothing is followed). The confirm button names how many parts will be searched; guests are held to their part limit.
- **Seller search:** one row per part with a single status and a progress bar.
- **Results:** a dark summary band with the parts price in whole rupees (`order_plan.costing`, else `report.costing`), how many parts it covers from how many sellers, what is still unknown (shipping, GST) and when prices were checked, plus Download PDF and Share. The parts list (`PartsList.tsx`) groups by seller (subtotal and one shipping line; then Not bought yet and You already have) or by part, with one status per row. Thumbnails (`PartThumb`) try `line_image`, seller photos and `image_candidates`, then the image endpoint; broken photos are reported for an optional generated illustration. Compare plans (`GET /plans`; Apply posts `/selections`) and seller refresh (up to 10 parts per batch, 2 batches) follow the list. Seller prices are snapshots; tax, shipping and the final payable total are not known, and demo data is labelled.
- **Part panel:** the chosen offer first (price, seller with trust label, listing title, stock and check time, match, grade and GST chips, Open seller page) or what is missing, then callouts for confirming a seller or adding a value, then sections: Seller offers (selection posts `/selections`; grade B picks need `accept_changes`, judge-confirmed offers are selectable, recommendation reasons under "Why this pick"), Code changes, Why this part is in the list, Specs and requirements (the buying spec used for seller search and requirement edits) and Research notes, with "Include in the next seller search".
- **Code changes:** a selected catalogue substitute shows code diffs, origin and compile labels (Not compiled / Compiles for <board> / Did not compile), and wiring/power/verification notes. AI drafts need explicit acceptance before ZIP download; shared and demo reports hide this control.
- **Compile check** (backend v0.29.0): when `GET /v1/compile/boards` reports `enabled`, a ready patch offers a board picker ("From the parts list" by default) and "Check it compiles". A queued check polls the job every 8 s until it settles, then shows the board, core and size ("compile only: not tested on hardware"), the compiler output, or the reason it could not compile. `FQBN_REQUIRED` highlights the board picker. After an AI repair round the panel asks for the revised draft to be accepted again.
- Seller quotes show the backend's optional seller name, domain and store type, plus trust labels and reasons. Marketplace trust does not verify the individual merchant.
- **Conversation:** messages are spaced apart and the history scrolls to new messages, respecting reduced motion. The composer accepts any file; small TXT/Markdown notes can be inserted into the draft as text, other files are marked as unsent because chat does not upload files. Questions are sent with client UUIDs, citations show saved line evidence and open the cited part, and proposed draft edits can be accepted or rejected (accepting does not confirm the BOM). Live updates reconnect with refreshed credentials and backoff.
- On completed reports the conversation also shows seller refresh proposals and spec/requirement proposals (`spec_proposal`) with Approve/Reject through the shared decision endpoint; approval re-checks saved quotes, clears those parts' selections and marks AI research stale. Stale (`PROPOSAL_STALE`) or already-decided (`PROPOSAL_DECIDED`) 409s show a message and reload the job. Refresh completion messages (`refresh_results`) show a per-part status, offer count and lowest price labelled "seller-listed, not a verified total". A collapsible "Action history" lists `job.actions` newest first.
- **Export and share** (`ReportActions.tsx`): "Download PDF" fetches `export.pdf` through the proxy and saves it as `<project>.pdf`. The share control creates, copies and revokes links; the token is shown once, and creating a new link replaces the old one. The server proxy forwards `DELETE`. The **public share page** `/shared/<token>` (`SharedReport.tsx`) uses the same frame and renders the report read-only (no chat, edit, select, refresh or image generation), with `notice` and the demo label, and handles 404 (revoked) and 429.
- Preview: `/job/ui-preview?preview=1` and the toolbar's stages show every state with labelled dummy data. In the order plan, open the sample sensor to see a sample diff and a dummy "Compiles" result; patch and compile actions are disabled in preview. The toolbar's "Shared link" opens the read-only share page.

The YouTube player and PWA share target remain future frontend work. The implemented API is documented in [docs/contracts](../docs/contracts/README.md); the broader [frontend architecture](../docs/02-architecture/09-frontend-and-ux.md) is a target design.

## Local UI preview without API calls

Run npm run dev and open http://localhost:5173/?preview=1. The preview toolbar switches between landing, review, parallel progress, and results. API actions use in-memory dummy responses; the sample image is a local labelled illustration. Preview mode is development-only and requires preview=1 in the URL. Normal URLs retain the configured backend connection.

## Responsive layout

Every screen is checked for zero horizontal scroll at 320, 375, 414, 768, 1024, 1280, 1440 and 1920px. Main breakpoints in `styles.css`: 1000px (chat panel moves below the report), 600px (phone layout: stacked cards, wrapping totals) and 380–420px (narrow phones: account dialog, review fields, hero chips). Single-column grids use `minmax(0, 1fr)` so long seller names and prices wrap instead of widening the page. On touch screens (`pointer: coarse`) buttons, form fields, disclosure summaries and plan action links get a 44px hit area; small report chips grow to about 30px. The account dialog's close button stays visible while a long panel scrolls on phones.

## Accounts and saved projects (5 October 2026)

- Google sign-in creates or reopens a Firebase account. The SDK refreshes ID tokens before API requests, including chat and fetch-based SSE reconnects. All browser requests include credentials; POSTs send `X-Requested-With: BharatSourcer`.
- Signed-in accounts choose a **Country** from a flag dropdown in the account panel (`CountryPicker.tsx`, exposed as `useAccount().country`). The list comes from `GET /v1/countries` and the choice is saved with `POST /v1/account/settings`; new projects default to it on the backend. Only India is supported today. Flags are inline SVGs keyed by country code; add one when the backend adds a country ([countries.md](../docs/contracts/countries.md)).
- **Shared page** (`SharedReport.tsx`) has "Copy to my projects": it asks for sign-in (or a guest session), calls `POST /v1/shared/{token}/copy` and opens the copy. Copied projects show a "Copied from a shared project" note under the title, and the sharer's picks are labelled "Copied choice" until the new owner chooses. Share links (`/shared/<id>.<secret>`) are served by `server.mjs` even though the token contains a dot.
- **My projects** cards (`ProjectCard.tsx`) show an icon for the source (YouTube, GitHub, article or link), a status badge with an icon (Reading the source, Review the parts, Finding sellers, Paused, Order plan ready, Needs attention), the source site instead of the raw URL, and an unambiguous date. The whole card opens the project. The bin button asks for confirmation on the card itself, then calls `DELETE /v1/projects/{id}` and removes the card. Preview mode lists four labelled sample projects and supports deleting them.
- The account panel also supports explicit guest entry and logout. `/projects` lists owner-only saved projects with pagination and opens their existing job IDs without creating another job. Guest-to-account saving is explicit after sign-in and does not rerun analysis.
- The proxy forwards Authorization, Cookie, Origin and X-Requested-With, preserves separate Set-Cookie headers, Retry-After and Cache-Control, and applies no-store if upstream has no cache policy. It deliberately does not trust browser-supplied client-IP headers.
- A 401 prompts sign-in recovery. Provider outages preserve the session. Quota errors show the retry time and leave saved work readable; the account panel reads personal usage when opened. Live sourcing can be paused/resumed.
- Backend authentication is enabled. Account and guest project access uses the deployed identity routes.

Copy `.env.example` to an ignored local env file and supply the four public Firebase web values from the project owner. The Cloud Run deployment script reads these public values and serves them at runtime. The frontend domain is authorized in Firebase and included in backend CORS. Google login requires a popup-capable browser. Guest cookies need HTTPS and a same-origin proxy, not direct cross-origin localhost requests.

Use `http://127.0.0.1:5173/?preview=1` for **no-API local testing**, even if `.env.local` points at a live backend. Firebase initialization is disabled and all API methods use local sample responses. Click Sign in → Try demo account → My projects → Open project. Also try Continue as guest → My projects → Save my projects → Try demo account → Save to my account. The demo account marker lasts for the current tab session; project contents are in-memory fixtures and reset on reload. No real account is created.

Validation: `npm run build`, `npm run test:server`, `npm run test:preview`, and `npm run test:integration`. The preview test executes the real preview/auth/API modules with network access forbidden. The integration test exercises the API client against a local identity-aware fixture. Real Google login, two-account isolation, revoked users and cookie expiry still require live browser checks. Local browser checks cover the wide desktop layout, 390px mobile layout, card expansion, inline editing, build details, and new-message scrolling. Older unowned jobs can be claimed using their original browser-session token.
