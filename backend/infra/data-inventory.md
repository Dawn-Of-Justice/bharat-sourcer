# Data inventory

Every place Bharat Sourcer stores data, derived from `src/bharat_sourcer/storage.py`,
`access.py`, `config.py`, `identity.py`, `images.py`, `gemini_extras.py` and
`sourcing/cache.py`, and checked against the live project on 17 October 2026 (read-only
`gcloud`). **Unknown** means not verifiable from code or a read-only check.

Production collection prefix: `BS_FIRESTORE_COLLECTION=backend_integration_jobs` (set by
`scripts/deploy_integration.py`); database `(default)`, `asia-south1`. Every Firestore
collection is closed to web clients by [firestore.rules](firestore.rules) (`allow read,
write: if false`); only IAM principals reach it.

## Firestore access (applies to every collection below)

| Principal | Role | Effect |
| --- | --- | --- |
| `bharat-sourcer-api@hackathon-510415.iam.gserviceaccount.com` (API runtime) | `roles/datastore.user` (project-wide) | Read/write all collections |
| `689415686498-compute@developer.gserviceaccount.com` (default compute) | `roles/editor` | Read/write all collections (Google default; not used by the services) |
| `claude-readonly@hackathon-510415.iam.gserviceaccount.com` | `roles/datastore.viewer`, `roles/logging.viewer` | Read all collections and logs |
| Human project Owner / Editor accounts | `roles/owner`, `roles/editor` | Full access |
| `firestore-backup@...` (planned, `backups.md` on `ops/firestore-backups`) | `roles/datastore.importExportAdmin` | Export all collections; not created yet |

Check: `gcloud projects get-iam-policy hackathon-510415 --format=json`.

## Inventory

| Store | Contents | Personal data | Retention | Deletion path | Access |
| --- | --- | --- | --- | --- | --- |
| Firestore `backend_integration_jobs` | One `StoredJob` per project: source URL, extracted project text, parts, offers, chat messages (free text written by the user), events, actions, overview, build guide, YouTube metadata (`video_meta`), `copied_from`; `token_hash`, `share_token_hash` (SHA-256, never raw tokens); `owner_id` (`user:<firebase uid>` or `guest:<id>`) | **Yes**: owner uid, free-text chat may contain anything | On `main`: none automated (kept until deleted). v0.43.0 (`feat/retention-and-deletion`, unmerged): 30 days after last update for guest/unowned, 365 days for accounts, via `expires_at`; the TTL policy on this group is **not enabled** (live check). YouTube fields hidden from responses after 30 days but stay stored | `DELETE /v1/projects/{job_id}` (owner); `DELETE /v1/account` (v0.43.0); retention sweep + TTL (v0.43.0); operator delete in console | API runtime, see table above |
| Firestore `backend_integration_jobs_usage` | Quota counters: `count`, `expires_at`. Keys contain SHA-256 of the owner id or HMAC-SHA256 of the client IP (keyed by the guest-session secret), plus day or minute | **Pseudonymous**: hashed owner and IP | 2 days (`expires_at`); TTL **enabled** | TTL; owner-keyed counters removed by `DELETE /v1/account` (v0.43.0); per-IP and global counters kept until TTL | API runtime |
| Firestore `backend_integration_jobs_accounts` | One doc per account, id `user:<uid>`: `country`, `updated_at` | **Yes**: uid, country preference | Until deleted (no TTL) | `DELETE /v1/account` (v0.43.0); otherwise operator only | API runtime |
| Firestore `backend_integration_jobs_cache` | Shared sourcing cache by namespace (`discovery`, `judge`, `page`, `seller_search`, `research`, `markets`, `spec`, `spec_fill`, `reconcile`, `cart_recipe`, `fabrication`, overview, ...); content-keyed, no owner | **No** direct identifiers. `spec`, `spec_fill`, `reconcile` values derive from one project's text; `markets` keys hash a rounded location | Per namespace, 6 h to 30 days (`TTL` in `sourcing/cache.py`); TTL **enabled** | TTL; manual delete is safe (cache) | API runtime |
| Firestore `backend_integration_jobs_audio` | Explain-aloud TTS audio chunks, content-keyed | **No** | 30 days; TTL **enabled** | TTL | API runtime |
| Firestore `backend_integration_jobs_images` | Generated part-image assets and leases (`images.py`), content-keyed | **No** | **No `expires_at`, no TTL: kept indefinitely.** Image generation is off in production (`BS_IMAGE_GENERATION_ENABLED=false`), so expected empty or small (unknown) | Manual only | API runtime |
| Firestore `backend_integration_jobs_meta` | Housekeeping: retention scan cursor (`meta/retention`). v0.43.0 only | **No** | Overwritten each sweep | Manual | API runtime |
| GCS `gs://hackathon-510415-firestore-backups` | Weekly full Firestore exports (all collections above) | **Yes** (copies of all of the above) | 30 days (lifecycle). **Not created yet** (live check: 404; `backups.md` says not applied) | Ages out; user deletion does **not** remove data from existing exports | Planned: `firestore-backup@` (objectAdmin), project Owners/Editors |
| Firestore PITR | Point-in-time versions of every document | **Yes** | 7 days once enabled; currently 1 hour (PITR off, per `backups.md`) | Ages out | Firestore readers above |
| Cloud Logging `_Default` bucket | App logs (redacted: tokens, keys, emails, URL queries removed by `observability.py`); `job_id`, `line_id`, hosts; Cloud Run request logs with **full request URLs** (can include share tokens in the path), client IP, user agent, latency | **Yes**: IPs and user agents in request logs; job ids | 30 days (live check) | Ages out; no per-user deletion | `roles/logging.viewer` and above: `claude-readonly@`, project Owners/Editors |
| Cloud Logging `_Required` bucket | Admin Activity and system audit logs (who changed IAM, services, secrets) | **Yes**: principal emails of admins | 400 days (fixed by Google) | Cannot be deleted | Project Owners/Editors, `roles/logging.viewer` |
| Firebase Authentication (project `hackathon-510415`) | Accounts signed in with Google: uid, email, display name, photo URL, provider, created / last sign-in times | **Yes** | Until the account is deleted | `DELETE /v1/account` (v0.43.0) calls Identity Toolkit `accounts:delete`, but the runtime account has only `roles/firebaseauth.viewer` (live check), so it returns `auth_user_deleted: false` until granted delete; otherwise Firebase console | `bharat-sourcer-api@` (viewer), `firebase-adminsdk-fbsvc@` (Firebase admin SDK agent), project Owners/Editors |
| Guest session cookie (browser) | Signed `__session` cookie (legacy `bs_guest`): guest id and expiry | Pseudonymous | 14 days (`BS_GUEST_SESSION_DAYS`) | Logout or `DELETE /v1/account` clears it; rotating `bharat-sourcer-guest-session` invalidates all | The user's browser |
| Cloud Tasks queue `bharat-sourcer` | Task payloads: job id and work kind only (no tokens, no keys) | **No** | Until delivered, at most 1 day (`--max-retry-duration=86400s`) | `gcloud tasks queues purge bharat-sourcer --location=asia-south1` | API runtime (`roles/cloudtasks.enqueuer`), project Owners/Editors |
| Secret Manager | `bharat-sourcer-gemini`, `bharat-sourcer-integration-key`, `bharat-sourcer-guest-session`, `bharat-sourcer-youtube` | **No** (credentials) | All versions kept until destroyed | `gcloud secrets versions destroy` | Accessor granted to `bharat-sourcer-api@`; `bharat-sourcer-web@` reads the integration key; per-secret policy otherwise **unknown** |
| Gemini API / Vertex AI (processor, not a store we control) | Prompts contain fetched page text, parts, chat text and, for the parts-bin scan, the user's photo (not persisted by the app; sent to Gemini only) | **Yes** (as sent) | Per Google's terms for the API key tier and Vertex AI; **unknown** for this account's configuration | n/a | Google |

## Gaps to close

- Enable the TTL policy on `backend_integration_jobs` once v0.43.0 is deployed
  (`README.md`, Project retention section on the retention branch).
- Grant `firebaseauth.users.delete` to the runtime account before announcing account
  deletion.
- `_images` has no expiry; decide on a TTL if image generation is turned on.
- Request logs keep share tokens in URLs for 30 days; consider a log exclusion or a
  shorter bucket retention.
- Secret-level IAM and Gemini data-use terms for this project are unverified.
