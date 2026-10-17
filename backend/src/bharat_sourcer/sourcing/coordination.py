"""Atomic host pacing and cooldowns, shared across Cloud Run instances in Firestore."""

import hashlib
import threading
import time
from datetime import UTC, datetime, timedelta


class FetchError(Exception):
    pass


class HostDeferred(FetchError):
    """No network request should run until the host's retry time."""

    def __init__(self, reason: str, retry_after: float):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


def reserve(state: dict, now: float, interval: float, max_wait: float) -> tuple[dict, float]:
    until = float(state.get("until", 0))
    if until > now:
        raise HostDeferred(str(state.get("reason", "cooldown")), until - now)
    start = max(now, float(state.get("next", 0)), float(state.get("last", 0)) + interval)
    if start - now > max_wait:
        raise HostDeferred("host_queue_full", start - now)
    return {**state, "last": start, "next": start + interval}, start - now


class MemoryCoordinator:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.hosts: dict[str, dict] = {}

    def acquire(self, host: str, interval: float, max_wait: float = 10) -> float:
        with self.lock:
            state, delay = reserve(self.hosts.get(host, {}), self.clock(), interval, max_wait)
            self.hosts[host] = state
            return delay

    def defer(self, host: str, seconds: float, reason: str) -> None:
        with self.lock:
            state = self.hosts.setdefault(host, {})
            until = self.clock() + seconds
            if until > state.get("until", 0):
                state.update(until=until, reason=reason)

    def reason(self, host: str) -> str | None:
        with self.lock:
            state = self.hosts.get(host, {})
            return state.get("reason") if state.get("until", 0) > self.clock() else None


class FirestoreCoordinator:
    def __init__(self, client, collection: str):
        self.client = client
        self.collection = client.collection(collection + "_seller_hosts")

    def _ref(self, host: str):
        return self.collection.document(hashlib.sha256(host.encode()).hexdigest())

    def _update(self, host, change):
        from google.cloud import firestore

        @firestore.transactional
        def apply(transaction):
            ref = self._ref(host)
            state = ref.get(transaction=transaction).to_dict() or {}
            updated, result = change(state, time.time())
            transaction.set(ref, updated | {"expires_at": datetime.now(UTC) + timedelta(days=7)})
            return result

        return apply(self.client.transaction())

    def acquire(self, host: str, interval: float, max_wait: float = 10) -> float:
        return self._update(host, lambda state, now: reserve(state, now, interval, max_wait))

    def defer(self, host: str, seconds: float, reason: str) -> None:
        def change(state, now):
            if now + seconds > state.get("until", 0):
                state.update(until=now + seconds, reason=reason)
            return state, None

        self._update(host, change)

    def reason(self, host: str) -> str | None:
        state = self._ref(host).get().to_dict() or {}
        return state.get("reason") if state.get("until", 0) > time.time() else None


def for_store(store):
    client = getattr(store, "client", None)
    return (
        FirestoreCoordinator(client, store.collection.id)
        if client is not None
        else MemoryCoordinator()
    )
