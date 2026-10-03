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

Run `npm run build` before delivery. `npm run preview` serves the built frontend locally.

## Current behavior

- The landing page offers fields for YouTube, tutorial/blog pages, GitHub repositories and audio files. YouTube submits to the live or demo API. Article and GitHub links can preview the fixed fixture only when the backend reports demo mode; the live backend does not extract them yet. Audio is a visible planned input and is not uploaded.
- The job page keeps `X-Job-Token` in `sessionStorage` and polls `GET /v1/jobs/{id}` throughout the job's lifetime, including after extraction finishes. It lets users correct quantities/names and mark owned or removed parts, then explicitly confirms the BOM.
- The conversation panel renders persisted job messages beside the BOM, sends questions with client UUIDs, shows saved line evidence for citations, and lets users accept or reject proposed draft edits. Accepting does not confirm the BOM. Lost connections are retried with backoff; the UI uses polling, which the [conversation contract](../docs/contracts/conversation.md) permits in place of the SSE stream.
- Results show the backend's sourcing outcomes and checked seller offers. Demo data is conspicuously labelled. Seller prices are snapshots; tax, shipping and final payable total are not known.
- The landing illustration is built with CSS/SVG and needs no image download. Animations respect reduced-motion settings.

This is the first frontend slice. Offer selection, targeted refresh, the YouTube player, PWA share target, exports and public sharing are subsequent integration work. The implemented API is documented in [docs/contracts](../docs/contracts/README.md); the broader [frontend architecture](../docs/02-architecture/09-frontend-and-ux.md) is a target design.
