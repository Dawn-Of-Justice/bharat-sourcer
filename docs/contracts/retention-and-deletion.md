# Project retention and delete my data — v0.43.0

## Retention

Projects are deleted automatically after a period without an update, measured from
`Job.updated_at`:

| Owner | Kept for | Setting |
| --- | --- | --- |
| Account (`user:<uid>`) | 365 days | `BS_ACCOUNT_RETENTION_DAYS` |
| Guest session, or unowned token project | 30 days | `BS_GUEST_RETENTION_DAYS` |

- Claiming a guest project into an account (`POST /v1/projects/{job_id}/claim`) moves it
  to the account period straight away.
- `Job.updated_at` changes when the project's work or parts change (extraction,
  confirmation, sourcing, chat, edits). Opening a project to read it does not count as an
  update.
- An expired project is gone as far as the API is concerned, even before storage has
  physically removed it:
  - `GET /v1/jobs/{job_id}` and every other project route return `404 JOB_NOT_FOUND`.
  - Its share link returns `404 SHARE_NOT_FOUND`.
  - It is left out of `GET /v1/projects`.
- The share link and all derived project data (parts, offers, conversation, overview,
  build guide) are stored on the project document, so they are deleted with it.
- Shared caches (`_cache`, `_audio`, `_images`) are keyed by content, not by project or
  owner. They keep their own expiry: the sourcing cache by namespace, explain-aloud audio
  after 30 days.
- No response field exposes the deadline yet. Clients that want to warn users can compute
  it as `updated_at` plus the period for the session `kind`.

### How deletion happens

- Every save writes `expires_at` (a Firestore Timestamp) on the job document.
- A Firestore TTL policy on `expires_at` for the jobs collection group removes the document
  after the deadline, normally within 24 hours (see `backend/infra/README.md`).
- The scheduled `/internal/sweep` (worker identity only, every five minutes) also runs one
  bounded retention batch of up to `BS_RETENTION_BATCH` documents (default 200) per phase:
  1. Delete documents whose stored `expires_at` has passed. Each is re-checked against the
     current periods first.
  2. Continue a resumable scan by document id that deletes expired legacy documents and
     backfills `expires_at` on documents written before v0.43.0.

  The sweep response gains `retention: {scanned, deleted, backfilled, complete}`, or
  `{failed: true}`. A retention failure never fails the redispatch sweep.

## `DELETE /v1/account`

Deletes all data held for the current identity: a signed-in account (bearer token) or the
guest session (cookie). Requires auth to be enabled.

Request:

- Headers: `X-Requested-With: BharatSourcer` and the usual identity (bearer token or guest
  cookie).
- Body (JSON): `{"confirm": "DELETE"}`. This exact, case-sensitive value is required.

Response `200` (`AccountDeletion`), `Cache-Control: no-store`:

```json
{
  "kind": "account",
  "projects_deleted": 3,
  "share_links_revoked": 1,
  "settings_deleted": true,
  "auth_user_deleted": true
}
```

| Field | Meaning |
| --- | --- |
| `kind` | `"account"` or `"guest"` |
| `projects_deleted` | Projects owned by this identity that were removed, including any already past retention |
| `share_links_revoked` | How many of those projects had an active share link |
| `settings_deleted` | Saved account settings existed and were removed (always `false` for guests) |
| `auth_user_deleted` | Accounts only: `true` if the Firebase Auth user is deleted, or was already gone. `false` if that call failed; the data deletion still completed and the client may retry. `null` for guests |

What is removed:

- Every project whose owner is this identity, with its share link and derived data.
- Saved account settings (`GET /v1/account/settings` returns defaults again).
- Usage counters keyed by this identity: daily actions, daily projects, minute bursts and
  claim bursts.
- For a guest, the `__session` and legacy `bs_guest` cookies are cleared (`Max-Age=0`).
- For an account, the Firebase Auth user is deleted through the Identity Toolkit admin API
  (`accounts:delete`). Afterwards that bearer token no longer verifies, so the client
  should sign out of Firebase locally.

What is kept:

- Per-IP and global usage counters. They are needed for abuse limits and expire on their
  own after two days, so deleting and starting again does not reset per-network quotas.
- The per-identity limiter for this endpoint.
- Other users' projects, settings and share links. Projects this user copied from someone
  else's share link belong to this user and are deleted; the originals are not touched.

Errors (`ErrorResponse`):

| Status | Code | When |
| --- | --- | --- |
| 400 | `CONFIRMATION_REQUIRED` | Body missing, or `confirm` is not exactly `"DELETE"` |
| 401 | `IDENTITY_REQUIRED` | No valid bearer token or guest cookie. This includes a repeat call after the auth user was deleted, or after the guest cookie was cleared |
| 403 | `REQUEST_HEADER_REQUIRED` / `ORIGIN_REJECTED` | Missing app header or disallowed origin |
| 422 | `VALIDATION_ERROR` | Body is not a JSON object, has unknown fields, or `confirm` is longer than 20 characters |
| 429 | `USAGE_LIMIT` | More than 5 calls per identity per minute (`Retry-After` set) |
| 503 | `AUTH_DISABLED` / `IDENTITY_UNAVAILABLE` | Auth not enabled, or identity provider unreachable |

Idempotent: repeating the call with the same still-valid identity succeeds with zero
counts. If `auth_user_deleted` was `false`, repeating the call retries the auth deletion.
The call does not use the action budget.

Logs record counts and the error type only, never the uid, email or provider message.
