"""Atomic job snapshots. Transaction callbacks must not perform external I/O."""

from collections.abc import Callable
from datetime import datetime
from threading import RLock
from typing import Protocol

from pydantic import Field

from bharat_sourcer.schemas import Job, Model


class StoredJob(Model):
    job: Job
    token_hash: str
    run_id: str | None = None
    lease_until: datetime | None = None
    schema_version: int = Field(default=1, ge=1, le=1)


class StorageError(Exception):
    pass


def check_size(record: StoredJob) -> None:
    # Conservative budget below Firestore's 1 MiB document limit.
    if len(record.model_dump_json().encode()) > 800_000:
        raise StorageError("Job exceeds the supported storage size")


class JobStore(Protocol):
    def create(self, record: StoredJob) -> None: ...
    def get(self, job_id: str) -> StoredJob | None: ...
    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None: ...
    def pending(self) -> list[str]: ...


class MemoryJobStore:
    def __init__(self):
        self._records: dict[str, StoredJob] = {}
        self._lock = RLock()

    def create(self, record: StoredJob) -> None:
        with self._lock:
            check_size(record)
            if record.job.job_id in self._records:
                raise StorageError("Job already exists")
            self._records[record.job.job_id] = record.model_copy(deep=True)

    def get(self, job_id: str) -> StoredJob | None:
        with self._lock:
            record = self._records.get(job_id)
            return record.model_copy(deep=True) if record else None

    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None:
        with self._lock:
            record = self.get(job_id)
            if record is not None:
                change(record)
                check_size(record)
                self._records[job_id] = record.model_copy(deep=True)
            return record

    def pending(self) -> list[str]:
        with self._lock:
            return [
                key
                for key, record in self._records.items()
                if record.job.status in {"queued", "extracting", "resolving", "sourcing"}
            ]


class FirestoreJobStore:
    def __init__(self, project: str, database: str = "(default)", collection: str = "backend_jobs"):
        from google.cloud import firestore

        self.client = firestore.Client(project=project, database=database)
        self.collection = self.client.collection(collection)

    def create(self, record: StoredJob) -> None:
        check_size(record)
        self.collection.document(record.job.job_id).create(record.model_dump(mode="json"))

    def get(self, job_id: str) -> StoredJob | None:
        snapshot = self.collection.document(job_id).get()
        return StoredJob.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None:
        from google.cloud import firestore

        reference = self.collection.document(job_id)

        @firestore.transactional
        def apply(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return None
            record = StoredJob.model_validate(snapshot.to_dict())
            before = record.model_dump(mode="json")
            change(record)
            check_size(record)
            after = record.model_dump(mode="json")
            if before != after:
                transaction.set(reference, after)
            return record

        return apply(self.client.transaction())

    def pending(self) -> list[str]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        return [
            snapshot.id
            for snapshot in self.collection.where(
                filter=FieldFilter(
                    "job.status", "in", ["queued", "extracting", "resolving", "sourcing"]
                )
            ).stream()
        ]
