"""Set up Firestore backups: 7-day PITR plus a weekly export kept 30 days. Idempotent.

Without --apply the script only reads the current state and prints the plan. With --apply
(owner gcloud identity) it creates, or brings up to date:

1. point-in-time recovery (7 days, about 1-minute granularity) on the (default) database;
2. bucket gs://hackathon-510415-firestore-backups in asia-south1: Standard class, uniform
   bucket-level access, public access prevention enforced, soft delete off, and a
   lifecycle rule that deletes objects older than 30 days;
3. service account firestore-backup@ with only roles/datastore.importExportAdmin on the
   project and roles/storage.objectAdmin on that bucket;
4. Cloud Scheduler job firestore-weekly-export (Sundays 03:00 Asia/Kolkata) that POSTs
   databases/(default):exportDocuments with an OAuth token for that account.

It ends with a summary of PITR, the bucket lifecycle and the scheduler job.
See infra/backups.md for restore commands and the restore drill.

Run from backend/: python scripts/setup_backups.py [--apply]
"""

import argparse
import json
from pathlib import Path

from deploy_integration import PROJECT, REGION, command

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "(default)"
BUCKET = f"gs://{PROJECT}-firestore-backups"
BACKUP_SA = f"firestore-backup@{PROJECT}.iam.gserviceaccount.com"
JOB = "firestore-weekly-export"
SCHEDULE = "0 3 * * 0"  # Sundays 03:00
TIME_ZONE = "Asia/Kolkata"
RETENTION_DAYS = 30
EXPORT_URI = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/{DATABASE}:exportDocuments"
)
# A bucket-only prefix makes Firestore create a new start-time folder per export
# (e.g. 2026-10-18T21:30:00_12345/). A fixed path such as /exports would make every weekly
# export write into the same folder, so only one export would ever be kept.
EXPORT_BODY = {"outputUriPrefix": BUCKET}
LIFECYCLE = {"rule": [{"action": {"type": "Delete"}, "condition": {"age": RETENTION_DAYS}}]}
SERVICES = ("firestore.googleapis.com", "storage.googleapis.com", "cloudscheduler.googleapis.com")


class Runner:
    """Runs changing gcloud commands with --apply; otherwise prints them as the plan."""

    def __init__(self, apply: bool) -> None:
        self.apply = apply

    def __call__(self, *args: str) -> None:
        if self.apply:
            command(*args)
        else:
            print("    would run: gcloud " + " ".join(args), flush=True)


def describe(*args: str) -> dict | None:
    """Read-only describe; None when the resource does not exist."""
    result = command(*args, "--format=json", optional=True)
    if result.returncode:
        return None
    return json.loads(result.stdout or "{}")


def data_file(name: str, payload: dict) -> Path:
    path = ROOT / ".data" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def database() -> dict:
    found = describe("firestore", "databases", "describe", f"--database={DATABASE}")
    if found is None:
        raise RuntimeError(f"Firestore database {DATABASE} not found in {PROJECT}")
    return found


def pitr(run: Runner) -> None:
    state = database().get("pointInTimeRecoveryEnablement", "unknown")
    print(f"[1] PITR on {DATABASE}: {state}", flush=True)
    if state == "POINT_IN_TIME_RECOVERY_ENABLED":
        print("    already enabled", flush=True)
        return
    run("firestore", "databases", "update", f"--database={DATABASE}", "--enable-pitr")


def bucket(run: Runner) -> None:
    found = describe("storage", "buckets", "describe", BUCKET)
    print(f"[2] Bucket {BUCKET}: {'exists' if found else 'missing'}", flush=True)
    if found is None:
        run(
            "storage",
            "buckets",
            "create",
            BUCKET,
            f"--location={REGION}",
            "--default-storage-class=STANDARD",
            "--uniform-bucket-level-access",
            "--public-access-prevention",
        )
    # Always (re)apply the settings so drift is corrected.
    lifecycle = data_file("firestore-backup-lifecycle.json", LIFECYCLE) if run.apply else None
    run(
        "storage",
        "buckets",
        "update",
        BUCKET,
        "--default-storage-class=STANDARD",
        "--uniform-bucket-level-access",
        "--public-access-prevention",
        "--clear-soft-delete",
        f"--lifecycle-file={lifecycle or '.data/firestore-backup-lifecycle.json'}",
    )


def identity(run: Runner) -> None:
    found = describe("iam", "service-accounts", "describe", BACKUP_SA)
    print(f"[3] Service account {BACKUP_SA}: {'exists' if found else 'missing'}", flush=True)
    if found is None:
        run(
            "iam",
            "service-accounts",
            "create",
            BACKUP_SA.split("@", maxsplit=1)[0],
            "--display-name=Firestore weekly export (backups only)",
        )
    run(
        "projects",
        "add-iam-policy-binding",
        PROJECT,
        f"--member=serviceAccount:{BACKUP_SA}",
        "--role=roles/datastore.importExportAdmin",
        "--condition=None",
    )
    run(
        "storage",
        "buckets",
        "add-iam-policy-binding",
        BUCKET,
        f"--member=serviceAccount:{BACKUP_SA}",
        "--role=roles/storage.objectAdmin",
    )


def scheduler(run: Runner) -> None:
    jobs = command(
        "scheduler", "jobs", "list", f"--location={REGION}", "--format=value(name)", optional=True
    )
    existing = [line.rsplit("/", 1)[-1] for line in jobs.stdout.split()]
    print(f"[4] Scheduler jobs in {REGION}: {', '.join(existing) or 'none'}", flush=True)
    # Same API-enable pattern as enable_queued_dispatch.py (enabling is a no-op when on).
    run("services", "enable", *SERVICES)
    found = JOB in existing
    print(f"    {JOB}: {'exists, will update' if found else 'missing, will create'}", flush=True)
    body = data_file("firestore-export-body.json", EXPORT_BODY) if run.apply else None
    run(
        "scheduler",
        "jobs",
        "update" if found else "create",
        "http",
        JOB,
        f"--location={REGION}",
        f"--schedule={SCHEDULE}",
        f"--time-zone={TIME_ZONE}",
        "--http-method=POST",
        f"--uri={EXPORT_URI}",
        # A body file avoids gcloud.cmd quoting problems with JSON on Windows.
        f"--message-body-from-file={body or '.data/firestore-export-body.json'}",
        "--update-headers=Content-Type=application/json"
        if found
        else "--headers=Content-Type=application/json",
        f"--oauth-service-account-email={BACKUP_SA}",
        "--oauth-token-scope=https://www.googleapis.com/auth/datastore",
        "--attempt-deadline=180s",
    )
    if not run.apply:
        print(f"    export body: {json.dumps(EXPORT_BODY)}", flush=True)


def summary() -> None:
    print("\nVerification summary (current state):", flush=True)
    db = database()
    print(
        f"  PITR: {db.get('pointInTimeRecoveryEnablement')}, "
        f"version retention {db.get('versionRetentionPeriod')}, "
        f"earliest version {db.get('earliestVersionTime')}",
        flush=True,
    )
    found = describe("storage", "buckets", "describe", BUCKET)
    if found is None:
        print("  Bucket: missing", flush=True)
    else:
        print(
            f"  Bucket: {found.get('location')}, class {found.get('default_storage_class')}, "
            f"public access prevention {found.get('public_access_prevention')}, "
            f"uniform access {found.get('uniform_bucket_level_access')}",
            flush=True,
        )
        print(f"  Lifecycle: {json.dumps(found.get('lifecycle_config'))}", flush=True)
        print(f"  Soft delete: {json.dumps(found.get('soft_delete_policy'))}", flush=True)
    job = describe("scheduler", "jobs", "describe", JOB, f"--location={REGION}")
    if job is None:
        print(f"  Scheduler {JOB}: missing", flush=True)
    else:
        target = job.get("httpTarget", {})
        print(
            f"  Scheduler {JOB}: {job.get('state')}, '{job.get('schedule')}' "
            f"{job.get('timeZone')}, {target.get('httpMethod')} {target.get('uri')}, "
            f"OAuth as {target.get('oauthToken', {}).get('serviceAccountEmail')}, "
            f"last attempt {job.get('lastAttemptTime', 'never')} "
            f"status {json.dumps(job.get('status', {}))}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the changes (default: plan)")
    args = parser.parse_args()
    run = Runner(args.apply)
    print(
        f"{'Applying' if args.apply else 'Plan only (pass --apply to change anything)'}: "
        f"Firestore backups for {PROJECT}/{DATABASE}\n",
        flush=True,
    )
    pitr(run)
    bucket(run)
    identity(run)
    scheduler(run)
    summary()


if __name__ == "__main__":
    main()
