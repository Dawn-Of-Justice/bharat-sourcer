# Connect the local frontend

The frontend implements account/guest access, saved projects, editable project details,
BOM review, sourcing progress, part cards, research, images, requirements and chat actions.
The API reference is in [README](README.md) and the topic contracts linked there.

## Local configuration

From `frontend/`, install dependencies and run `npm run dev`. Keep configuration
in the ignored `frontend/.env.local`:

- `VITE_API_BASE_URL`: backend origin, without a `/v1` suffix.
- `INTEGRATION_KEY`: privately shared key. No `VITE_` prefix; the proxy holds it.
- The four public Firebase web values from `frontend/.env.example`.

The integration backend is
`https://bharat-sourcer-integration-diahnrbuna-el.a.run.app`.
The frontend uses same-origin `/api` requests. The proxy injects the integration key,
forwards bearer tokens and cookies, and preserves response cookies separately.
New jobs require an account or guest identity; legacy jobs can be claimed with their
original job token. See [authentication](authentication.md).

## Preview and checks

Open `http://127.0.0.1:5173/?preview=1` for labelled local fixtures with no API or
Firebase calls. The toolbar switches between review, progress and results. Inline
project editing, build details and chat work against in-memory preview responses.

Run `npm run build`, `npm run test:preview`, `npm run test:integration` and
`npm run test:server` from the frontend directory. Current local UI behavior and
browser verification are documented in [frontend/README](../../frontend/README.md).

Real Google login, guest claim, account isolation, revocation and cookie expiry still
need live browser acceptance checks. The completed proxy and UI implementation does
not replace those checks. Do not automatically replay mutations after a lost response;
quota attempts and explicit refreshes can have side effects.
