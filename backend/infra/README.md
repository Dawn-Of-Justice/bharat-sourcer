# Firestore setup

Target project: `hackathon-510415`. Database: `(default)`, Standard edition, Native mode,
region `asia-south1` (Mumbai). Created and verified on 2 Oct 2026 with Google Cloud CLI 587.0.0.
The separate-client create/read/confirm/report smoke check passed at that time.
Local credentials and ignored environment files are machine-specific; configure them
on each development machine. The commands below document that setup.
Database location is a lasting infrastructure choice.

## 1. Create the database

Run in [Google Cloud Shell](https://console.cloud.google.com/cloudshell/editor?project=hackathon-510415)
or an authenticated Google Cloud CLI:

```sh
gcloud services enable firestore.googleapis.com --project=hackathon-510415
gcloud firestore databases create --project=hackathon-510415 --database='(default)' --location=asia-south1 --type=firestore-native
```

If a database already exists, inspect its location and type instead of recreating it:

```sh
gcloud firestore databases describe --project=hackathon-510415 --database='(default)'
```

Equivalent console flow: Firestore → Create database → Standard → Native mode →
`(default)` → Mumbai. Keep client access locked (production mode if prompted).
If Firebase rules are enabled, publish the contents of `firestore.rules` through the
Firestore Rules console before using this collection. Review existing rules first if
other applications share the database; an overlapping permissive rule can grant access.

## 2. Authenticate this developer machine

Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), then run locally:

```sh
gcloud auth application-default login
gcloud auth application-default set-quota-project hackathon-510415
```

The signed-in account needs Firestore data access (`roles/datastore.user` or equivalent)
and permission to use the quota project. Database creation requires separate admin rights.
Cloud Run should use an attached service account with Firestore data access.
Do not download service account keys into this repository. The Gemini key is separate.

## 3. Check and enable

From `backend/`:

```powershell
.venv/Scripts/python scripts/check_firestore.py --project hackathon-510415
```

The check writes one synthetic demo job, verifies it with a new client, then deletes
only that job. It makes no Gemini calls. After it passes, set in `backend/.env`:

```dotenv
BS_STORAGE_BACKEND=firestore
BS_GCP_PROJECT=hackathon-510415
BS_FIRESTORE_DATABASE=(default)
```

Restart the API. `/healthz` reports the configured backend; it is a liveness endpoint,
not a database connectivity test. Existing memory jobs are not migrated.

## Storage and recovery

`backend_jobs/{job_id}` is a private, versioned snapshot containing the job, token hash,
and extraction lease. Raw tokens never enter the database. Frontend requests continue
through the API; direct Firestore listeners are not enabled in this milestone.

Firestore transactions make edits, extraction claims, and report publication atomic.
Callbacks do not make external calls and may be retried by Firestore. A periodic sweep
resumes queued work and report creation after a process restart. Confirmation drafts
and completed/failed jobs remain untouched. Active extraction has a ten-minute lease;
once expired, recovery requeues it once per job. A later interruption marks it failed
with `EXTRACTION_INTERRUPTED`. Recovery can repeat billed extraction; late responses
cannot overwrite it. See [Cloud Run integration deployment](cloud-run.md).

The sweeper runs inside the API process, so Cloud Run needs CPU allocated outside requests.
This is not a durable task queue: recovery needs a running API instance, and graceful
shutdown can wait for an active recovery call. A queue/worker remains a later improvement.
Snapshots are capped at 800 KB and BOMs at 100 lines. Retention is described under
[Project retention](#project-retention). Keep development usage small. Shared project/database/collection settings
are required across workers; use separate collections for dev and production.

## Local emulator test

With the Google Cloud CLI and Java installed:

```sh
gcloud emulators firestore start --host-port=127.0.0.1:8085
```

In another PowerShell terminal, from `backend/`:

```powershell
$env:FIRESTORE_EMULATOR_HOST='127.0.0.1:8085'
.venv/Scripts/python -m pytest tests/test_firestore_integration.py
```

This integration test targets the emulator project `demo-bharat-sourcer` and removes its
own test document. Without the emulator variable, it is skipped. Emulator data is local
and is not evidence that cloud authentication or permissions work.

References: [database creation](https://cloud.google.com/firestore/docs/manage-databases),
[server authentication](https://firebase.google.com/docs/firestore/quickstart-server),
[emulator configuration](https://cloud.google.com/firestore/native/docs/emulator).

## Firestore TTL policies

Firestore deletes expired documents through TTL policies on the `expires_at` timestamp
field. Expired entries are also ignored on read, so the policies only reclaim storage.

| Collection group | Contents | Enabled |
| --- | --- | --- |
| `backend_integration_jobs_usage` | Quota and usage counters | Before 7 October 2026 |
| `backend_integration_jobs_cache` | Shared sourcing cache (`sourcing/cache.py`) | 7 October 2026 |
| `backend_integration_jobs_audio` | Explain-aloud audio cache (`gemini_extras.py`) | 7 October 2026 |

To add a policy for a new collection group:

```bash
gcloud firestore fields ttls update expires_at --collection-group=<group> \
  --enable-ttl --project hackathon-510415 --database="(default)"
```

## Project retention

v0.43.0 deletes projects after a period without an update, measured from `job.updated_at`:

- Guest-owned and unowned projects: 30 days (`BS_GUEST_RETENTION_DAYS`).
- Account-owned projects: 365 days (`BS_ACCOUNT_RETENTION_DAYS`).
- Claiming a guest project moves it to the account period.

Each save writes the deadline to the job document as the Timestamp field `expires_at`.
Expired jobs read as 404 straight away. Removal happens in two ways:

1. **TTL policy (not enabled yet).** Enable it once v0.43.0 is deployed:

   ```bash
   gcloud firestore fields ttls update expires_at \
     --collection-group=backend_integration_jobs \
     --enable-ttl --project hackathon-510415 --database="(default)"
   ```

   Check it with `gcloud firestore fields ttls list --project hackathon-510415`.
   - TTL deletes usually land within 24 hours of the deadline.
   - TTL only applies to documents that have a Timestamp `expires_at`. Documents written
     before v0.43.0 get one on their next save or from the sweep backfill.
2. **Sweep pass.** The Cloud Scheduler job that calls `/internal/sweep` (every five
   minutes, worker identity) also runs one bounded retention batch of `BS_RETENTION_BATCH`
   documents per phase (default 200):
   - Delete jobs whose stored `expires_at` has passed.
   - Advance a resumable scan, with its cursor in `backend_integration_jobs_meta/retention`,
     that deletes expired legacy jobs and backfills `expires_at`.

   One phase-1 query uses the automatic single-field index on `expires_at`. No composite
   index is needed.

Share links and derived data live on the job document. The shared `_cache`, `_audio` and
`_images` collections are content-keyed and carry no owner, so no per-project cleanup is
needed.

## Delete my data

`DELETE /v1/account` (see `docs/contracts/retention-and-deletion.md`) deletes an
identity's projects, settings and identity-keyed usage counters. For accounts it also
calls the Identity Toolkit admin API,
`POST https://identitytoolkit.googleapis.com/v1/projects/hackathon-510415/accounts:delete`,
with the runtime service account's ADC token.

That account (`bharat-sourcer-api@hackathon-510415.iam.gserviceaccount.com`) needs
`firebaseauth.users.delete`, for example through `roles/firebaseauth.admin`. If it lacks
the permission:
- The data is still deleted.
- The response reports `auth_user_deleted: false`.
- The log shows `AUTH_USER_DELETE_FAILED type=HTTPError`.

Check the grant before announcing the feature. This release does not change IAM.

## YouTube Data API key

The secret `bharat-sourcer-youtube` (already created in Secret Manager, with accessor granted
to `bharat-sourcer-api@hackathon-510415.iam.gserviceaccount.com`) must be mounted as
`BS_YOUTUBE_API_KEY` at deploy:

```bash
gcloud run services update bharat-sourcer-integration --region asia-south1 --update-secrets=BS_YOUTUBE_API_KEY=bharat-sourcer-youtube:latest
```

Without it the description intake is skipped and video extraction is unchanged. YouTube API
data on job snapshots (short description quotes, title, channel and links) is hidden from
responses 30 days after `video_meta.fetched_at`. The snapshot itself is not purged yet (see
`docs/contracts/multi-source-intake.md` §8).

## Demo and judging scaling (approved 7 October 2026)

- **Max instances:** `bharat-sourcer-integration` was raised from 1 to 3 on 7 October 2026
  (revision `bharat-sourcer-integration-00045-q4w`). Leases and Firestore transactions are
  multi-instance safe; daily quotas bound spend. The deploy workflow keeps scaling settings.
- **Min instances (15 October – 6 November 2026):** keep one warm instance of each service
  during recording and judging (about $0.65/day for both, about $15 in total):

  ```bash
  gcloud run services update bharat-sourcer-integration --region asia-south1 --min-instances=1
  gcloud run services update bharat-sourcer-web --region asia-south1 --min-instances=1
  ```

  **Revert on 7 November 2026** (otherwise about $20/month):

  ```bash
  gcloud run services update bharat-sourcer-integration --region asia-south1 --min-instances=0
  gcloud run services update bharat-sourcer-web --region asia-south1 --min-instances=0
  ```

## Compile runner (code-adapt tier 3)

Compile checks for code patches (`docs/contracts/code-adapt.md`) run in Cloud Run **jobs**,
one per core family, never in the API service. Provision or update everything with an owner
gcloud identity and Docker running, from `backend/`:

```bash
python scripts/setup_compile_runner.py            # all families
python scripts/setup_compile_runner.py --families avr --skip-build   # reuse pushed images
```

| Resource | Setting |
| --- | --- |
| VPC `bharat-sourcer-compile`, subnet `bharat-sourcer-compile-asia-south1` (`10.80.0.0/26`) | Private Google Access on; **no Cloud Router or NAT** (the script refuses if one exists) |
| Service account `bharat-sourcer-compile@` | No roles, no secrets |
| Artifact Registry `bharat-sourcer-compile` | Images `runner-<family>`; cleanup keeps the 2 newest per image |
| Jobs `bharat-sourcer-compile-{avr,esp32,esp8266,rp2040}` | 2 vCPU / 4 GiB, task timeout 600 s, no retries, Direct VPC egress `all-traffic`, env `BS_COMPILE_API_URL` |
| IAM | `bharat-sourcer-api@`: `run.jobsExecutorWithOverrides` on the jobs and `iam.serviceAccountUser` on the runner; `bharat-sourcer-deploy@`: `run.developer` on the jobs, `iam.serviceAccountUser` on the runner, `artifactregistry.writer` on the repository |
| API env | `BS_COMPILE_BACKEND=cloud_run_job`, `BS_COMPILE_SERVICE_ACCOUNT`, `BS_COMPILE_AUDIENCE` (kept by `deploy_integration.py` and the deploy workflow) |

**Isolation.** All job egress goes into the VPC. Without an external IP or NAT, the only
reachable destinations are Google endpoints through Private Google Access, which is how the
runner reaches this API's `run.app` URL. Cores and libraries are installed when the image
is built (`compile/pins.json`), so compiling needs no downloads. The runner checks every file
path, writes only source files (no `sketch.yaml` or build scripts), runs `arduino-cli
compile` (never `upload`) as a non-root user with a 300 s limit, and proves its identity to
the API with a metadata-server ID token; `/internal/compile/*` accepts only that account.
The API, not the runner, downloads the repository snapshot (`codeload.github.com`, 8 MB
cap) through the guarded fetcher.

**Updates.** Merges to `main` that change `backend/compile/` rebuild the four images and
update the jobs (`compile-images` in `.github/workflows/backend.yml`). Change versions only
in `compile/pins.json`.

**Cost.** Jobs bill only while running: one ESP32 compile (about 1–2 minutes at 2 vCPU /
4 GiB) is roughly $0.005 at Tier 1 prices and fits the monthly free tier at demo scale. The
images are 0.9 GB (AVR), 4.7 GB (ESP32), 1.0 GB (ESP8266) and 1.7 GB (RP2040) unpacked
(9 October 2026 build; ESP32 and RP2040 drop debuggers and other chips' toolchains, see
`prune` in `compile/pins.json`); compressed in Artifact Registry they stay well under
$1/month above the free 0.5 GB. The VPC and subnet have no charge without NAT. `BS_COMPILE_DAILY_LIMIT` (default
100) caps compile requests per day.

**Disable.** `gcloud run services update bharat-sourcer-integration --region asia-south1
--update-env-vars BS_COMPILE_BACKEND=none` (the route then answers 503). Jobs cost nothing
while idle.
