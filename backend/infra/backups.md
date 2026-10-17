# Firestore backups

Project `hackathon-510415`, database `(default)` (Native mode, `asia-south1`).
Set up by [`scripts/setup_backups.py`](../scripts/setup_backups.py). The script prints its
plan by default and only changes anything with `--apply`:

```powershell
# from backend/
.venv/Scripts/python scripts/setup_backups.py           # plan + current state
.venv/Scripts/python scripts/setup_backups.py --apply   # owner gcloud identity
```

**Status (17 October 2026): not yet applied.** When the script was written, PITR was
disabled (1-hour version retention), the bucket and service account did not exist, and the
only Cloud Scheduler job was `bharat-sourcer-reconcile` (`/internal/sweep`, every 5 min).
Update this line after the first `--apply`.

## What is backed up

| Layer | What | Retention | RPO | RTO (estimate) |
| --- | --- | --- | --- | --- |
| Point-in-time recovery (PITR) | Every document in `(default)`, all collections | 7 days | About 1 minute (versions are kept at 1-minute granularity; whole-minute timestamps only) | Minutes for a targeted read; roughly 10–60 min to clone the database, depending on size |
| Weekly export | Full export of all collections to `gs://hackathon-510415-firestore-backups/<start-time>/` | 30 days (bucket lifecycle), so about 4 exports | Up to 7 days | Roughly 10–60 min to import into a new database, depending on size |

Not covered: Firestore security rules (in git as `firestore.rules`), TTL and index
definitions (recreate from this folder's docs), Secret Manager, Cloud Run configuration and
anything outside Firestore. TTL policies keep deleting expired documents, so expired cache
and usage entries are not in later exports.

Resources the script manages:

- PITR on `(default)` (`gcloud firestore databases update --enable-pitr`); version
  retention becomes 7 days.
- Bucket `gs://hackathon-510415-firestore-backups`, `asia-south1`, Standard class, uniform
  bucket-level access, public access prevention enforced, soft delete **off** (so deleted
  exports are not billed for another 7+ days), lifecycle: delete objects older than 30 days.
- Service account `firestore-backup@hackathon-510415.iam.gserviceaccount.com` with only
  `roles/datastore.importExportAdmin` on the project and `roles/storage.objectAdmin` on
  the bucket. No keys.
- Cloud Scheduler job `firestore-weekly-export` (`asia-south1`), `0 3 * * 0` in
  `Asia/Kolkata` (Sundays 03:00 IST). It POSTs
  `https://firestore.googleapis.com/v1/projects/hackathon-510415/databases/(default):exportDocuments`
  with body `{"outputUriPrefix": "gs://hackathon-510415-firestore-backups"}` and an OAuth
  token for the service account. The prefix is the bucket alone on purpose: Firestore then
  writes each export into its own start-time folder. A fixed path (for example `/exports`)
  would make each weekly export write into the same folder and keep only one copy.

## Restore

**Always restore into a new database first**, check it, and only then move data back or
repoint the API. Never import or clone over `(default)` directly. Run in Cloud Shell or an
owner gcloud; on Windows quote `--database='(default)'` and avoid commas in arguments.

### From PITR (last 7 days)

Find the window you can use:

```sh
gcloud firestore databases describe --database='(default)' --project=hackathon-510415 \
  --format='value(pointInTimeRecoveryEnablement,earliestVersionTime)'
```

**Targeted read** (one document or a few, no new database): any Firestore client can read at
a whole-minute `read_time` within the last 7 days. Python example:

```python
from datetime import datetime, timezone
from google.cloud import firestore

db = firestore.Client(project="hackathon-510415", database="(default)")
when = datetime(2026, 10, 17, 9, 30, tzinfo=timezone.utc)  # whole minute, inside the window
snapshot = db.collection("backend_integration_jobs").document("JOB_ID").get(read_time=when)
print(snapshot.to_dict())
```

Write recovered documents back through a one-off script after review.

**Whole database clone** to a new database:

```sh
gcloud firestore databases clone \
  --source-database='projects/hackathon-510415/databases/(default)' \
  --snapshot-time='2026-10-17T09:30:00Z' \
  --destination-database='restore-20261017' \
  --project=hackathon-510415
```

`--snapshot-time` must be a whole minute inside the PITR window. The command returns a
long-running operation (`gcloud firestore operations list --database=restore-20261017`).

**PITR export** (copy a past minute into the bucket, for example to keep it longer):

```sh
gcloud firestore export gs://hackathon-510415-firestore-backups/pitr-20261017-0930 \
  --database='(default)' --snapshot-time='2026-10-17T09:30:00Z' --project=hackathon-510415
```

(This folder is also deleted by the 30-day lifecycle rule.)

### From a weekly export (up to 30 days)

```sh
# 1. Pick an export folder
gcloud storage ls gs://hackathon-510415-firestore-backups/

# 2. Create an empty database in the same region
gcloud firestore databases create --database='restore-20261017' \
  --location=asia-south1 --type=firestore-native --project=hackathon-510415

# 3. Import the export into it (all collections, or add --collection-ids=...)
gcloud firestore import gs://hackathon-510415-firestore-backups/2026-10-12T21:30:00_12345/ \
  --database='restore-20261017' --project=hackathon-510415
```

Import overwrites documents with the same ID and leaves others alone, so a new, empty
database gives a clean copy. The account running the import needs
`roles/datastore.importExportAdmin` and read access to the bucket.

### After a restore check

- Compare document counts or a sample of job IDs against what you expected.
- To switch the API to the restored database, set `BS_FIRESTORE_DATABASE` on
  `bharat-sourcer-integration` and redeploy; the restored database also needs the TTL
  policies from [Firestore setup](README.md#firestore-ttl-policies) and the security rules.
- Delete restore databases you no longer need (`gcloud firestore databases delete
  --database=restore-...`); each one is billed for storage while it exists.

## Quarterly restore drill

Run in the first week of January, April, July and October. Record the date, operator and
timings in the PR or ops log.

- [ ] `python scripts/setup_backups.py` (plan mode) shows PITR enabled, 7-day retention,
      the lifecycle rule, soft delete off and the scheduler job `ENABLED`.
- [ ] The scheduler job's last attempt is a recent Sunday with status OK
      (`gcloud scheduler jobs describe firestore-weekly-export --location=asia-south1`), and
      the bucket has roughly 4 export folders, none older than 30 days.
- [ ] Clone `(default)` from PITR at a minute from the past hour into `drill-pitr-YYYYMMDD`;
      note how long it took.
- [ ] Import the newest weekly export into a new database `drill-export-YYYYMMDD`; note
      how long it took.
- [ ] In both, read 3 known job documents and compare them with production.
- [ ] Do a targeted PITR read of one document at a past minute.
- [ ] Delete both drill databases.
- [ ] Update the RTO estimates above if the timings changed.

## Cost

The data size is not known yet (check it in the console: Firestore → Usage, or Cloud
Monitoring metric `firestore.googleapis.com/storage/data_and_index_storage_bytes`).
Let `S` be the stored size in GiB (data plus indexes), `C` the size of 7 days of changes
in GiB, and `N` the number of documents.

| Item | Formula (per month) | Notes |
| --- | --- | --- |
| PITR storage | `(S + C) × Firestore storage rate` | Rate is roughly $0.11–0.18 per GiB-month depending on region; check the `asia-south1` price. PITR is billed as extra storage, not per read. |
| Export reads | `N × 4.3 exports × read rate` | One document read per exported document; about $0.03–0.06 per 100,000 reads. May partly fall inside the daily free read quota. |
| Export storage | `4.3 × export size × $0.02–0.023 per GB-month` | Standard class in `asia-south1`; export size is usually below `S`. Soft delete is off, so nothing is billed after the 30-day delete. |
| Cloud Scheduler | `$0.10 per job beyond 3 free per billing account` | The project has 2 jobs with this one, so likely $0. |
| Operations, egress | ~$0 | Same-region writes; a handful of class A operations per export. |

Plausible range (estimates, not measured):

| Stored size `S` | Documents `N` | Approximate monthly cost |
| --- | --- | --- |
| 50 MB | 20,000 | under $0.10 |
| 500 MB | 200,000 | about $0.20–0.70 |
| 5 GB | 2,000,000 | about $2–7 (mostly export reads) |

Restore drills add the storage of the temporary databases for the hours they exist plus
one read per imported document, which is cents at these sizes.
