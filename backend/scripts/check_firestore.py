"""Credentialed persistence smoke check. Creates and removes one synthetic demo job."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from bharat_sourcer.identity import Principal
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

# Isolated synthetic collection: validate the production query and shared quota transaction.
collection = "auth_smoke_" + uuid4().hex
first = FirestoreJobStore(args.project, args.database, collection)
second = FirestoreJobStore(args.project, args.database, collection)
owner = Principal("user:smoke-fixture")
created = []
try:
    for _ in range(3):
        created.append(
            JobService(store=first).create(CreateJob(url="https://example.com"), owner)[0]
        )
    page = second.owned(owner.owner, "", 2)
    tail = second.owned(owner.owner, page[-1].job.job_id, 2)
    assert len(page) == 2 and len(tail) == 1
    assert second.owned("user:other-fixture", "", 2) == []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: [first, second][i % 2].consume({"fixture": 2}), range(4)))
    assert sum(results) == 2
    print("Firestore owner pagination and atomic quota check passed. Synthetic records removed.")
finally:
    for saved in created:
        first.collection.document(saved.job_id).delete()
    first.usage.document("fixture").delete()
