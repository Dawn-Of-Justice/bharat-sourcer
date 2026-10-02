"""Credentialed persistence smoke check. Creates and removes one synthetic demo job."""

import argparse

from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import ConfirmJob, CreateJob
from bharat_sourcer.storage import FirestoreJobStore

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--database", default="(default)")
args = parser.parse_args()
store = FirestoreJobStore(args.project, args.database)
service = JobService(store=store)
job, token = service.create(CreateJob(url="https://example.com/persistence-check"))
try:
    # Separate clients verify that no in-process dictionary is involved.
    resumed = JobService(store=FirestoreJobStore(args.project, args.database))
    resumed.extract(job.job_id)
    assert resumed.get(job.job_id, token).status == "awaiting_confirmation"
    resumed.confirm(job.job_id, token, ConfirmJob())
    resumed.finish(job.job_id)
    assert service.get(job.job_id, token).status == "done"
    print("Firestore create/read/confirm/report check passed. No Gemini calls were made.")
finally:
    store.collection.document(job.job_id).delete()
