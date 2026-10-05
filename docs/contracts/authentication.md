# Authentication and saved projects — v0.17

## Production activation — 5 October 2026

API v0.17.2 authentication is now enabled (`BS_AUTH_ENABLED=true`) on revision
`bharat-sourcer-integration-00026-fzl`, serving all traffic. The frontend production
domain is authorized in Firebase and allowed by backend CORS. Activation was
explicitly requested while the frontend deployment was still underway.

Direct backend checks passed: unauthenticated job rejection, production CORS,
secure guest cookie round trip, session, empty project list, usage counters,
invalid bearer rejection and logout. No jobs or model calls were started.
Run `backend/scripts/check_auth_live.py` from the backend directory to repeat.

Frontend proxy/browser integration and real Google login/revocation tests remain
pending. Trusted client-IP forwarding stays disabled until proxy handling is
verified; IP quotas currently use the socket peer and can group proxy users.
Account/guest quotas, project ownership and revoked-account checks are active.
The earlier handoff below describes the preparation stage; its disabled-auth
instructions are superseded by this activation record.

## Team handoff — 4 October 2026

Backend v0.17.2 is deployed and verified. Firebase project registration and the
`Bharat Sourcer Web` app now exist; Authentication is initialized. Google sign-in
is enabled and verified through the console and Firebase API. The approved public
name is `Bharat Sourcer`; the support email is configured in Firebase.
The SDK config is saved locally in ignored `backend/.data/firebase-web-config.json`;
obtain it from the project owner or Firebase project settings. Production-domain
authorization and an actual sign-in check remain pending. Backend auth stays off.

Frontend implementation belongs to the frontend teammate. No frontend files were
changed for this handoff. Backend infrastructure preparation uses
`backend/scripts/prepare_auth.py`; it preserves the auth flag and existing guest
secret, and requests TTL cleanup for the actual deployed usage collection
(`backend_integration_jobs_usage`). Source deployments preserve live auth settings
and existing secret bindings.

The live Firestore smoke check passed owner-only pagination and concurrent quota
admission across separate clients, using synthetic records that were removed.
Real Firebase login still needs production-domain authorization and the
frontend integration described below. Keep `BS_AUTH_ENABLED=false` until both are
verified together. The public frontend continues using the existing token flow.

### Frontend teammate acceptance checklist

- [x] Enable Firebase Google provider for project `hackathon-510415` (backend setup).
- [ ] Register
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
| `GET /v1/session/usage` | v0.17.1: personal daily actions, daily projects and minute actions, each with `limit`, `used`, `remaining`, `resets_at` (Unix seconds) |
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
are excluded. In v0.17.1, `429 USAGE_LIMIT` includes `Retry-After` seconds until the
latest reset of the exhausted limits: next minute for burst limits, midnight UTC
for daily limits. The header is exposed through CORS. Avoid retrying mutations
automatically because attempts themselves consume quota.

`GET /v1/session/usage` is deployed in v0.17.1. It reads only the
current identity's counters and does not consume action quota. It does not expose
other users, aggregate service usage or IP counters. Shared IP/global limits can
therefore reject an action even when personal `remaining` is positive. Values are
an advisory snapshot, not a reservation; another request can consume usage before
the next action. Fetch on opening the account panel or after an action/429, rather
than continuously polling. Reopening saved work remains available at zero quota.
The earlier v0.17.0 used a fixed 60-second retry hint.

Firestore transactions enforce counters across instances and fail closed on a
usage-store outage. Memory counters are for local development only and reset
on restart. These limits bound admitted requests, not exact monetary spend or
concurrent workers. Clearing cookies does not reset IP quotas, but distributed
attackers require additional edge protection. Firebase token signature, audience,
issuer and expiry are checked. v0.17.2 additionally checks Firebase account status
on every account-authenticated HTTP request, without caching successful lookups.
Disabled/deleted users and tokens whose `auth_time` precedes the account's
`validSince` are rejected with 401 `IDENTITY_REQUIRED`. Refreshing a token alone
does not fix revocation: prompt a new Google sign-in. Provider outages or missing
backend IAM return 503 `IDENTITY_UNAVAILABLE`; preserve the session and offer retry.
Neither response falls back to a guest session or admits paid work.

This v0.17.2 change is deployed with authentication still disabled. The backend
runtime service account has `roles/firebaseauth.viewer` on `hackathon-510415`,
which supplies `firebaseauth.users.get`; `prepare_auth.py` preserves this setup.
Live user revocation testing remains pending auth-enabled staging. The lookup uses Application
Default Credentials, never a downloaded service-account key. Requests to the
account-status endpoint have a 10-second timeout. Each new HTTP request checks
status once; an already-open SSE stream can continue until its bounded 60-second
end, and already-admitted queued work is not canceled by revocation.

References: [Firebase session revocation](https://firebase.google.com/docs/auth/admin/manage-sessions)
and [account lookup](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/lookup).

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
