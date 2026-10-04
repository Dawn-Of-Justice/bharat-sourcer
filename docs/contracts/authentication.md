# Authentication and saved projects — v0.17

Deployed in API v0.17.0 behind `BS_AUTH_ENABLED=false`. Authentication is not yet enabled in
production. The existing frontend proxy needs the changes below before rollout.

## Team handoff — 4 October 2026

Frontend implementation belongs to the frontend teammate. No frontend files were
changed for this handoff. Backend infrastructure preparation uses
`backend/scripts/prepare_auth.py`; it preserves the auth flag and existing guest
secret, and requests TTL cleanup for the actual deployed usage collection
(`backend_integration_jobs_usage`). Source deployments preserve live auth settings
and existing secret bindings.

The live Firestore smoke check passed owner-only pagination and concurrent quota
admission across separate clients, using synthetic records that were removed.
Real Firebase login still needs the Firebase project/provider configuration and
frontend integration described below. Keep `BS_AUTH_ENABLED=false` until both are
verified together. The public frontend continues using the existing token flow.

### Frontend teammate acceptance checklist

- [ ] Configure Firebase Google login for project `hackathon-510415` and register
  `bharat-sourcer-web-diahnrbuna-el.a.run.app` as an authorized domain.
- [ ] Implement Google login, guest entry and logout; refresh Firebase ID tokens.
- [ ] Forward credentials and each response cookie through the server proxy.
- [ ] Add the saved-project list and reopen by ID without creating another job.
- [ ] Offer explicit guest-to-account claim after login, preserving the guest cookie.
- [ ] Attach Authorization to chat and fetch-based streaming requests too.
- [ ] Show quota errors while keeping saved projects and pause available.
- [ ] Verify two-account isolation, guest claim, expiry and a returning-user visit
  on an auth-enabled staging backend before coordinating production activation.

Backend activation must add the production frontend Origin to `BS_CORS_ORIGINS`.
Trusted IP forwarding remains disabled until the teammate confirms the proxy
overwrites caller input using its verified platform client-IP chain.

## User flow

1. Offer Google sign-in through Firebase Authentication, or Continue as guest.
2. For sign-in, obtain a Firebase **ID token** and send `Authorization: Bearer <token>`.
   The backend accepts verified Google-provider accounts for `BS_GCP_PROJECT`.
   Refresh the token with the Firebase SDK when it expires; never send a Google
   OAuth access token in its place.
3. For guests, call `POST /v1/session/guest`. This sets `bs_guest`, a signed,
   Secure, HttpOnly, SameSite=Lax cookie lasting 14 days by default. JavaScript
   does not read this cookie. Use HTTPS and a same-origin proxy.
4. Create a project through the existing `POST /v1/jobs`. Its owner is recorded
   server-side. All existing job, chat, proposal and streaming routes use that owner.
5. On a later visit, call `GET /v1/projects`, then `GET /v1/jobs/{job_id}` to reopen.
   These reads do not trigger extraction, sourcing or LLM calls. Render the saved
   BOM, conversation, offers and research. Refreshing offers remains explicit.
6. After a guest signs in, call `POST /v1/projects/{job_id}/claim` with `{}` while
   sending both the account token and the existing guest cookie. Claim each desired
   project; claiming does not rerun it. The old guest immediately loses access.

An invalid bearer token returns 401 even if a valid guest cookie exists. Display
sign-in recovery rather than silently creating another guest identity.

## Routes

| Route | Behavior |
| --- | --- |
| `POST /v1/session/guest` | Create or reuse guest cookie; returns session info |
| `GET /v1/session` | Returns `kind`, `expires_at` (Unix seconds), `daily_action_limit`, `part_limit` |
| `POST /v1/session/logout` | Clears guest cookie, 204; frontend must also call Firebase sign-out |
| `GET /v1/projects?limit=20&cursor=...` | Owner-only summaries and nullable `next_cursor`; max limit 50 |
| `POST /v1/projects/{job_id}/claim` | Account claims a guest project, or legacy project with `{"job_token":"..."}` |

Project summaries contain `job_id`, `url`, `status`, `created_at`, `updated_at`,
and `part_count`. Pagination is in ascending job ID order, not date order.
Use the returned cursor unchanged. There is no project deletion endpoint yet.

All POST requests require `X-Requested-With: BharatSourcer` when auth is enabled.
If an Origin header is present it must be in `BS_CORS_ORIGINS`. All `/v1/`
requests still require the server-held integration key when configured.
Another owner's project returns 404. A leaked legacy job token cannot open an
account-owned or guest-owned project. With auth enabled, old unowned projects
must first be claimed using their original token. With auth disabled, existing
unowned job-token access continues; identity routes return 503 `AUTH_DISABLED`.

## Frontend proxy handoff — required before activation

The current `frontend/server.mjs` forwards only the earlier job-token headers.
The frontend teammate needs to:

- Forward `Authorization`, `Cookie`, `X-Requested-With` and `Origin`, alongside
  the existing request headers. Keep injecting `X-Integration-Key` server-side.
- Forward every `Set-Cookie` response header separately, plus `Cache-Control`
  and `Retry-After`. Do not combine cookies into one comma-separated header.
- Use `credentials: "include"` for browser requests. Never cache private API
  responses. Do not store Firebase tokens in project URLs or query strings.
- Stream with `fetch` so Authorization can be attached. Native EventSource
  cannot set a bearer header. Refresh expired credentials before reconnecting.
- If `BS_TRUSTED_PROXY_IP_HEADER=true`, overwrite `X-Client-IP` with the real
  client address obtained through a verified platform proxy chain. Never forward
  a caller-provided value. This setting requires integration-key authentication.
  Until configured, IP quotas use the socket peer and may group all proxy users.
- Add login/guest selection, saved-project list, explicit guest-project claim,
  and a usage-limit state that keeps existing projects readable.

## Default limits

| Limit | Account | Guest |
| --- | --- | --- |
| New projects per UTC day | 5 | 1 |
| Job POST attempts per UTC day, excluding pause | 40 | 5 |
| Job POST attempts per minute, excluding pause | 5 | 5 |
| Parts to source in a confirmation or refresh | configured global cap (default 10) | 3 |

The guest part limit applies to non-owned parts at confirmation and sourcing/
refresh batches. Extraction may show more draft parts; guests must reduce the
requested work before confirmation. This is not a video duration limit.

Additional defaults: 100 job POST attempts/IP/day, 1,000 across the service/day;
10 new guest sessions/IP/day and 1,000 across the service/day. Reusing a valid
guest cookie does not consume session quota. POST attempts consume quota before
body validation, including retries and idempotent repeats. Unauthorized ownership
attempts do not consume the project action quota. Reads, claims, logout and pause
are excluded. `429 USAGE_LIMIT` includes `Retry-After: 60`; a daily limit can remain
blocked until midnight UTC, so avoid automatic repeated retries.

Firestore transactions enforce counters across instances and fail closed on a
usage-store outage. Memory counters are for local development only and reset
on restart. These limits bound admitted requests, not exact monetary spend or
concurrent workers. Clearing cookies does not reset IP quotas, but distributed
attackers require additional edge protection. Firebase token signature, audience,
issuer and expiry are checked; revoked-token/disabled-user lookup is not implemented.

## Rollout checklist

1. Configure Firebase Authentication for `hackathon-510415`, enable Google sign-in,
   register the frontend web app and its authorized domain. Give the frontend
   teammate its public Firebase configuration; keep backend secrets private.
2. Store a randomly generated guest signing secret (at least 32 characters) in
   Secret Manager and bind it as `BS_GUEST_SESSION_SECRET` on the API service.
   Keep this stable across revisions; rotating it invalidates guest cookies.
3. Use `BS_STORAGE_BACKEND=firestore`. Enable a Firestore TTL policy on
   `expires_at` in collection group `backend_jobs_usage` (adjust if the jobs
   collection name changes). Expiry is for counter cleanup, not quota correctness.
4. Complete the proxy and UI changes above, allow the frontend Origin, and verify
   real-client IP handling before enabling the trusted proxy option.
5. Test two real accounts, guest creation/claim, expired tokens, reopening saved
   work, streams and quotas against Firestore in staging. The local suite's
   Firestore tests require `FIRESTORE_EMULATOR_HOST`; they are otherwise skipped.
6. Enable `BS_AUTH_ENABLED=true` on the API. Keep owned projects protected if a
   rollout is rolled back: disabling auth does not restore token access to them.

Backend tests cover isolation, claims, quota admission, cookie tampering and the
legacy path. Real Firebase sign-in and Firestore integration remain rollout checks.
