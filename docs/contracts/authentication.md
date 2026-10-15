# Authentication and saved projects — v0.17

## Production activation — 5 October 2026

API v0.17.2 authentication is now enabled (`BS_AUTH_ENABLED=true`) on revision
`bharat-sourcer-integration-00026-fzl`, serving all traffic. The frontend production
domain is authorized in Firebase and allowed by backend CORS.

Direct backend checks passed: unauthenticated job rejection, production CORS,
secure guest cookie round trip, session, empty project list, usage counters,
invalid bearer rejection and logout. No jobs or model calls were started.
Run `backend/scripts/check_auth_live.py` from the backend directory to repeat.

The frontend proxy later passed guest session, project list, usage and logout checks.
Real Google login, guest-to-account claim, two-account isolation and revocation tests
remain pending. Trusted client-IP forwarding stays disabled until proxy handling is
verified; IP quotas currently use the socket peer and can group proxy users.
Account/guest quotas, project ownership and revoked-account checks are active.


## User flow

1. Offer Google sign-in through Firebase Authentication, or Continue as guest.
2. For sign-in, obtain a Firebase **ID token** and send `Authorization: Bearer <token>`.
   The backend accepts verified Google-provider accounts for `BS_GCP_PROJECT`.
   Refresh the token with the Firebase SDK when it expires; never send a Google
   OAuth access token in its place.
3. For guests, call `POST /v1/session/guest`. This sets `__session`, a signed,
   Secure, HttpOnly, SameSite=Lax cookie lasting 14 days by default. JavaScript
   does not read this cookie. Use HTTPS and a same-origin proxy. The name is the only
   cookie Firebase Hosting forwards to Cloud Run (v0.31.1); cookies issued earlier as
   `bs_guest` are still accepted until they expire.
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
| `DELETE /v1/projects/{job_id}` | v0.24: permanently deletes an owned project (account or guest owner) with its parts list, offers, conversation and share link; 204. Needs `X-Requested-With: BharatSourcer`. Other owners and unknown ids get 404 `JOB_NOT_FOUND`. Does not use the action budget. Work still running for the project stops changing it; nothing is recreated. |
| `GET` / `POST /v1/account/settings` | v0.23: saved account preferences (`country`); see [countries.md](countries.md) |
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

## Frontend proxy

The frontend forwards Authorization, Cookie, Origin and X-Requested-With, preserves
separate Set-Cookie headers, Cache-Control and Retry-After, and injects the integration
key server-side. Browser requests include credentials, and fetch-based streaming
refreshes credentials on reconnect. Private API responses are not cached.

Trusted client-IP forwarding remains disabled until the platform proxy chain is
verified. The proxy does not forward caller-supplied client-IP headers.

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

At the 4 October v0.17.2 deployment, authentication was still disabled. The backend
runtime service account has `roles/firebaseauth.viewer` on `hackathon-510415`,
which supplies `firebaseauth.users.get`; `prepare_auth.py` preserves this setup.
Live user revocation testing remains pending auth-enabled staging. The lookup uses Application
Default Credentials, never a downloaded service-account key. Requests to the
account-status endpoint have a 10-second timeout. Each instance reuses one authorised
session (credentials, access token and connection) for these lookups; the lookup itself
still runs on every request. Firebase's public signing certificates are kept for their
`Cache-Control` max-age (at most six hours; downloads time out after 10 seconds) instead
of being downloaded per request. A token the cached certificates reject is checked once more
against a fresh download, at most once every five minutes. Each new HTTP request checks
status once; an already-open SSE stream can continue until its bounded 60-second
end, and already-admitted queued work is not canceled by revocation.

References: [Firebase session revocation](https://firebase.google.com/docs/auth/admin/manage-sessions)
and [account lookup](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/lookup).

## Outstanding verification

Real Google sign-in, guest-to-account claim, two-account isolation, expiry, revocation,
and returning-account access still need live browser checks. Verify the platform proxy
chain before enabling trusted client-IP forwarding. Keep existing owned projects
protected during any deployment rollback.

Backend tests cover isolation, claims, quota admission, cookie tampering and the
legacy path. Real Firebase sign-in and Firestore integration remain rollout checks.
