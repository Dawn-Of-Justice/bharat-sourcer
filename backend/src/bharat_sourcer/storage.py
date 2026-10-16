"""Atomic job snapshots. Transaction callbacks must not perform external I/O."""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from pydantic import Field

from bharat_sourcer.schemas import AccountSettings, Job, Model


class StoredJob(Model):
    job: Job
    token_hash: str
    owner_id: str | None = None
    part_limit: int | None = None
    run_id: str | None = None
    lease_until: datetime | None = None
    sourcing_scope: list[str] | None = None
    chat_run_id: str | None = None
    chat_lease_until: datetime | None = None
    # SHA-256 of the read-only share token; None when no share link is active.
    share_token_hash: str | None = None
    shared_at: datetime | None = None
    # Offer URLs of lines queued for refresh: re-fetched before any paid rediscovery.
    refresh_urls: dict[str, list[str]] | None = None
    # Project overview drawing (overview.py): the running attempt and when a pending
    # drawing counts as interrupted (it can then be restarted).
    overview_run_id: str | None = None
    overview_lease_until: datetime | None = None
    # Build guide generation (build_guide.py): the running attempt and its lease.
    build_guide_run_id: str | None = None
    build_guide_lease_until: datetime | None = None
    # Retention deadline (Retention.of), recomputed on every save. Firestore stores it as
    # a Timestamp so a TTL policy on `expires_at` deletes the document once it passes.
    expires_at: datetime | None = None
    schema_version: int = Field(default=1, ge=1, le=1)


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class Retention:
    """How long a project survives without an update, by owner kind, from job.updated_at.

    Account projects ("user:<uid>") keep the account period. Guest projects ("guest:...")
    and unowned token projects keep the guest period. Claiming a guest project changes its
    owner, so the claim's save moves it to the account period.
    """

    guest_days: int = 30
    account_days: int = 365

    def days(self, owner_id: str | None) -> int:
        return self.account_days if (owner_id or "").startswith("user:") else self.guest_days

    def expiry(self, owner_id: str | None, updated_at: datetime) -> datetime:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return updated_at + timedelta(days=self.days(owner_id))

    def of(self, record: "StoredJob") -> datetime:
        return self.expiry(record.owner_id, record.job.updated_at)

    def expired(self, record: "StoredJob", at: datetime | None = None) -> bool:
        return self.of(record) <= (at or datetime.now(UTC))


class OwnerDeletion(Model):
    projects: int = 0
    share_links: int = 0


def check_size(record: StoredJob) -> None:
    # Conservative budget below Firestore's 1 MiB document limit.
    if len(record.model_dump_json().encode()) > 800_000:
        raise StorageError("Job exceeds the supported storage size")


class JobStore(Protocol):
    retention: Retention

    def create(self, record: StoredJob) -> None: ...
    # Returns a private copy the caller may change; it never aliases stored state.
    # Expired jobs read as missing (None) until retention deletes them.
    def get(self, job_id: str) -> StoredJob | None: ...
    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None: ...
    def delete(self, job_id: str) -> bool: ...
    def pending(self, limit: int | None = None) -> list[str]: ...
    def owned(self, owner: str, after: str, limit: int) -> list[StoredJob]: ...
    def consume(self, limits: dict[str, int]) -> bool: ...
    def usage_counts(self, keys: list[str]) -> dict[str, int]: ...
    def get_account(self, owner: str) -> AccountSettings | None: ...
    def put_account(self, owner: str, settings: AccountSettings) -> None: ...
    def delete_account(self, owner: str) -> bool: ...
    # Every project of `owner`, expired or not, with its share link; counts what went.
    def delete_owned(self, owner: str) -> OwnerDeletion: ...
    def delete_usage(self, keys: list[str]) -> None: ...
    # One bounded retention batch: deletes expired jobs and backfills `expires_at`.
    def retention_pass(self, limit: int) -> dict[str, Any]: ...


def parse_account(data: dict | None) -> AccountSettings | None:
    # A saved country that is no longer supported reads as "no saved settings".
    try:
        return AccountSettings.model_validate(data) if data else None
    except ValueError:
        return None


class MemoryJobStore:
    def __init__(self, retention: Retention | None = None):
        self.retention = retention or Retention()
        self._records: dict[str, StoredJob] = {}
        self._lock = RLock()
        self._usage: dict[str, int] = {}
        self._accounts: dict[str, dict] = {}
        self._retention_cursor = ""

    def get_account(self, owner: str) -> AccountSettings | None:
        with self._lock:
            return parse_account(self._accounts.get(owner))

    def put_account(self, owner: str, settings: AccountSettings) -> None:
        with self._lock:
            self._accounts[owner] = settings.model_dump(mode="json")

    def delete_account(self, owner: str) -> bool:
        with self._lock:
            return self._accounts.pop(owner, None) is not None

    def usage_counts(self, keys: list[str]) -> dict[str, int]:
        with self._lock:
            return {key: self._usage.get(key, 0) for key in keys}

    def delete_usage(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self._usage.pop(key, None)

    def consume(self, limits: dict[str, int]) -> bool:
        with self._lock:
            if any(self._usage.get(key, 0) >= cap for key, cap in limits.items()):
                return False
            for key in limits:
                self._usage[key] = self._usage.get(key, 0) + 1
            return True

    def owned(self, owner: str, after: str, limit: int) -> list[StoredJob]:
        with self._lock:
            keys = sorted(
                k
                for k, v in self._records.items()
                if v.owner_id == owner and k > after and not self.retention.expired(v)
            )
            return [self._records[k].model_copy(deep=True) for k in keys[:limit]]

    def delete_owned(self, owner: str) -> OwnerDeletion:
        with self._lock:
            keys = [k for k, v in self._records.items() if v.owner_id == owner]
            result = OwnerDeletion(
                projects=len(keys),
                share_links=sum(1 for k in keys if self._records[k].share_token_hash),
            )
            for key in keys:
                del self._records[key]
            return result

    def retention_pass(self, limit: int) -> dict[str, Any]:
        at = datetime.now(UTC)
        stats: dict[str, Any] = {"scanned": 0, "deleted": 0, "backfilled": 0}
        with self._lock:
            keys = sorted(k for k in self._records if k > self._retention_cursor)
            for key in keys[:limit]:
                record = self._records[key]
                stats["scanned"] += 1
                expiry = self.retention.of(record)
                if expiry <= at:
                    del self._records[key]
                    stats["deleted"] += 1
                elif record.expires_at != expiry:
                    record.expires_at = expiry
                    stats["backfilled"] += 1
            stats["complete"] = len(keys) <= limit
            self._retention_cursor = "" if stats["complete"] else keys[limit - 1]
        return stats

    def create(self, record: StoredJob) -> None:
        with self._lock:
            check_size(record)
            if record.job.job_id in self._records:
                raise StorageError("Job already exists")
            stored = record.model_copy(deep=True)
            stored.expires_at = self.retention.of(stored)
            self._records[record.job.job_id] = stored

    def get(self, job_id: str) -> StoredJob | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or self.retention.expired(record):
                return None
            return record.model_copy(deep=True)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._records.pop(job_id, None) is not None

    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None:
        with self._lock:
            record = self.get(job_id)
            if record is not None:
                change(record)
                record.expires_at = self.retention.of(record)
                check_size(record)
                self._records[job_id] = record.model_copy(deep=True)
            return record

    def pending(self, limit: int | None = None) -> list[str]:
        with self._lock:
            return [
                key
                for key, record in self._records.items()
                if (
                    record.job.status in {"queued", "extracting", "resolving", "sourcing"}
                    or record.job.chat_state in {"queued", "thinking"}
                )
                and not self.retention.expired(record)
            ][:limit]


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


class FirestoreJobStore:
    # Firestore batches hold at most 500 writes.
    batch_size = 400

    def __init__(
        self,
        project: str,
        database: str = "(default)",
        collection: str = "backend_jobs",
        retention: Retention | None = None,
    ):
        from google.cloud import firestore

        self.retention = retention or Retention()
        self.client = firestore.Client(project=project, database=database)
        self.collection = self.client.collection(collection)
        self.usage = self.client.collection(collection + "_usage")
        # One document per owner ("user:<uid>"); preferences only, no project data.
        self.accounts = self.client.collection(collection + "_accounts")
        # Housekeeping state (the retention scan cursor); no user data.
        self.meta = self.client.collection(collection + "_meta")

    def _document(self, record: StoredJob) -> dict:
        data = record.model_dump(mode="json")
        # A native Timestamp, not an ISO string: TTL policies ignore non-timestamp values.
        data["expires_at"] = record.expires_at
        return data

    def _delete_refs(self, refs: list) -> None:
        for start in range(0, len(refs), self.batch_size):
            batch = self.client.batch()
            for ref in refs[start : start + self.batch_size]:
                batch.delete(ref)
            batch.commit()

    def get_account(self, owner: str) -> AccountSettings | None:
        snapshot = self.accounts.document(owner).get()
        return parse_account(snapshot.to_dict()) if snapshot.exists else None

    def put_account(self, owner: str, settings: AccountSettings) -> None:
        self.accounts.document(owner).set(settings.model_dump(mode="json"))

    def delete_account(self, owner: str) -> bool:
        ref = self.accounts.document(owner)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def usage_counts(self, keys: list[str]) -> dict[str, int]:
        snapshots = self.client.get_all([self.usage.document(key) for key in keys])
        counts = {snapshot.id: (snapshot.to_dict() or {}).get("count", 0) for snapshot in snapshots}
        return {key: counts.get(key, 0) for key in keys}

    def delete_usage(self, keys: list[str]) -> None:
        # Deleting a missing document is a no-op, so no reads are needed.
        self._delete_refs([self.usage.document(key) for key in keys])

    def consume(self, limits: dict[str, int]) -> bool:
        from google.cloud import firestore

        @firestore.transactional
        def apply(transaction):
            refs = {key: self.usage.document(key) for key in limits}
            # One batched read for every window, not a round trip per counter.
            stored = {
                snapshot.id: (snapshot.to_dict() or {}).get("count", 0)
                for snapshot in transaction.get_all(list(refs.values()))
            }
            counts = {key: stored.get(key, 0) for key in limits}
            if any(counts[key] >= cap for key, cap in limits.items()):
                return False
            for key, ref in refs.items():
                transaction.set(
                    ref,
                    {
                        "count": counts[key] + 1,
                        "expires_at": datetime.now(UTC) + timedelta(days=2),
                    },
                )
            return True

        return apply(self.client.transaction())

    def owned(self, owner: str, after: str, limit: int) -> list[StoredJob]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        results: list[StoredJob] = []
        # Expired documents (awaiting TTL) are skipped; read on so a page stays full.
        for _ in range(10):
            query = self.collection.where(filter=FieldFilter("owner_id", "==", owner))
            query = query.order_by("__name__")
            if after:
                query = query.start_after({"__name__": self.collection.document(after)})
            page = [StoredJob.model_validate(s.to_dict()) for s in query.limit(limit).stream()]
            results.extend(r for r in page if not self.retention.expired(r))
            if len(page) < limit or len(results) >= limit:
                break
            after = page[-1].job.job_id
        return results[:limit]

    def delete_owned(self, owner: str) -> OwnerDeletion:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.collection.where(filter=FieldFilter("owner_id", "==", owner))
        snapshots = list(query.select(["share_token_hash"]).stream())
        self._delete_refs([snapshot.reference for snapshot in snapshots])
        return OwnerDeletion(
            projects=len(snapshots),
            share_links=sum(
                1 for snapshot in snapshots if (snapshot.to_dict() or {}).get("share_token_hash")
            ),
        )

    def _expiry_of(self, data: dict) -> datetime | None:
        updated_at = _parse_time((data.get("job") or {}).get("updated_at"))
        return self.retention.expiry(data.get("owner_id"), updated_at) if updated_at else None

    def retention_pass(self, limit: int) -> dict[str, Any]:
        """Bounded: at most `limit` documents past their stored `expires_at`, then `limit`
        documents of a resumable name-ordered scan that backfills the field."""
        from google.api_core.exceptions import NotFound
        from google.cloud.firestore_v1.base_query import FieldFilter

        at = datetime.now(UTC)
        stats: dict[str, Any] = {"scanned": 0, "deleted": 0, "backfilled": 0}
        fields = ["owner_id", "job.updated_at", "expires_at"]
        doomed = []

        def visit(snapshot) -> None:
            data = snapshot.to_dict() or {}
            stats["scanned"] += 1
            expiry = self._expiry_of(data)
            if expiry is None:
                return
            if expiry <= at:
                doomed.append(snapshot.reference)
            elif _parse_time(data.get("expires_at")) != expiry:
                # A document deleted meanwhile has nothing left to backfill.
                with suppress(NotFound):
                    snapshot.reference.update({"expires_at": expiry})
                    stats["backfilled"] += 1

        expired = self.collection.where(filter=FieldFilter("expires_at", "<=", at))
        for snapshot in expired.select(fields).limit(limit).stream():
            # Re-checked against the current periods, so a longer setting is respected.
            visit(snapshot)
        cursor_ref = self.meta.document("retention")
        cursor = (cursor_ref.get().to_dict() or {}).get("cursor", "")
        scan = self.collection.order_by("__name__")
        if cursor:
            scan = scan.start_after({"__name__": self.collection.document(cursor)})
        # One extra document tells whether the scan has reached the end.
        page = list(scan.select(fields).limit(limit + 1).stream())
        for snapshot in page[:limit]:
            visit(snapshot)
        stats["complete"] = len(page) <= limit
        cursor_ref.set({"cursor": "" if stats["complete"] else page[limit - 1].id})
        unique = list({ref.id: ref for ref in doomed}.values())
        self._delete_refs(unique)
        stats["deleted"] = len(unique)
        return stats

    def create(self, record: StoredJob) -> None:
        check_size(record)
        record = record.model_copy()
        record.expires_at = self.retention.of(record)
        self.collection.document(record.job.job_id).create(self._document(record))

    def get(self, job_id: str) -> StoredJob | None:
        snapshot = self.collection.document(job_id).get()
        if not snapshot.exists:
            return None
        record = StoredJob.model_validate(snapshot.to_dict())
        return None if self.retention.expired(record) else record

    def delete(self, job_id: str) -> bool:
        ref = self.collection.document(job_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None:
        from google.cloud import firestore

        reference = self.collection.document(job_id)

        @firestore.transactional
        def apply(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return None
            record = StoredJob.model_validate(snapshot.to_dict())
            if self.retention.expired(record):
                return None
            before = record.model_dump(mode="json")
            change(record)
            # Also backfills documents written before `expires_at` existed.
            record.expires_at = self.retention.of(record)
            check_size(record)
            if before != record.model_dump(mode="json"):
                transaction.set(reference, self._document(record))
            return record

        return apply(self.client.transaction())

    def pending(self, limit: int | None = None) -> list[str]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        def ids(field, values):
            query = self.collection.where(filter=FieldFilter(field, "in", values))
            return [snapshot.id for snapshot in (query.limit(limit) if limit else query).stream()]

        workflow_ids = ids("job.status", ["queued", "extracting", "resolving", "sourcing"])
        chat_ids = ids("job.chat_state", ["queued", "thinking"])
        return list(dict.fromkeys(workflow_ids + chat_ids))[:limit]
