# Firestore setup

Target project: `hackathon-510415`. Database: `(default)`, Standard edition, Native mode,
region `asia-south1` (Mumbai). Created and verified on 2 Oct 2026. Google Cloud CLI 587.0.0
and local Application Default Credentials are configured on the current developer machine.
The separate-client create/read/confirm/report smoke check passed, and the local ignored
`backend/.env` selects Firestore. The commands below document setup for other machines.
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
Snapshots are capped at 800 KB and BOMs at 100 lines. There is no automated retention
policy yet. Keep development usage small. Shared project/database/collection settings
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
