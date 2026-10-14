"""Cross-job shared cache for paid sourcing results (docs/contracts/cost-controls.md).

API: `cache.get(key) -> dict | None` and `cache.set(key, value, ttl_s)`, with keys from
`cache_key(namespace, *parts)`. Values must be JSON-serialisable dicts built only from
public evidence (seller pages, grounded URLs, judge verdicts): never store a user's
project text, tokens or identity, because entries are shared across every job and owner.

The cache is advisory: read and write failures are logged and behave as a miss, and an
expired entry is ignored on read. Stale data is harmless because offers are always
re-verified from fetched seller pages before they are shown.
"""

import hashlib
import json
import logging
import re
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol

from bharat_sourcer.usage import record_cache_hit

log = logging.getLogger(__name__)

HOUR = 3600
DAY = 24 * HOUR
# Suggested TTLs per namespace. Price and stock change quickly, so page results are short.
TTL = {
    "discovery": 7 * DAY,  # normalised part query -> grounded candidate URLs
    "judge": 7 * DAY,  # spec hash + URL + content hash -> verdict
    "page": 8 * HOUR,  # URL -> extracted offer (price/stock)
    "seller_search": 6 * HOUR,  # seller + query -> candidate URLs
    "research": 7 * DAY,  # normalised spec + documents -> quote-checked research evidence
    "markets": 7 * DAY,  # rounded lat/lng + part categories -> Maps-grounded shop list
    # item text + project hash -> guarded buyable spec. Derived from that project's text, so
    # only a job with the same item and the same project context can read it.
    "spec": 7 * DAY,
    # line name + family + missing fields + known values + code quotes + project hash ->
    # AI-filled required spec values (spec_fill.py); project-derived like "spec".
    "spec_fill": 7 * DAY,
    # Merges and removals for one parts list and project (reconcile.py).
    "reconcile": 7 * DAY,
    # store host + add-to-cart form shape -> link recipe (sourcing/cart_engine.py). Store
    # behaviour changes rarely; a stale recipe only yields a link that may not work.
    "cart_recipe": 30 * DAY,
    # items hash + code hash -> judged project overview (overview.py). Keyed by the parts
    # list itself, so only a job with the same lines and the same code can read it.
    "overview": 7 * DAY,
    # items hash + compact build input -> AI build steps (build_guide.py). Keyed by the
    # parts list and project context, so only a job with the same input can read it.
    "build_guide": 7 * DAY,
}
NAMESPACES = frozenset(TTL)


class SharedCache(Protocol):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict, ttl_s: int) -> None: ...


# Before case folding, so 1 MΩ (mega) and 1 mΩ (milli) never share an entry.
_MEGA = re.compile(r"(\d)\s*M(?=\s*(?:Ω|ohms?\b|\b))")
_OHM = re.compile(r"(\d(?:\.\d+)?)\s*(k|meg|r)?\s*ohms?\b")
_PREFIXED = re.compile(r"(\d(?:\.\d+)?)\s+(k|meg|m|u|n|p)?(v|a|w|f|h|hz|mm|cm|m|g|kg|mah)\b")
_UNIT_WORDS = {
    "volts": "v",
    "volt": "v",
    "amps": "a",
    "amp": "a",
    "amperes": "a",
    "ampere": "a",
    "watts": "w",
    "watt": "w",
    "farads": "f",
    "farad": "f",
}


def normalise_part(text: str) -> str:
    """Lowercase, unit-normalised, whitespace-collapsed part text for cache keys.

    "33kΩ resistor", "33K resistor" and "33 k ohm  Resistor" all become "33k resistor".
    """
    value = str(text).replace("Ω", " ohm").replace("µ", "u").replace("μ", "u")
    value = _MEGA.sub(r"\1meg", value)
    value = " ".join(value.casefold().split())
    value = " ".join(_UNIT_WORDS.get(word, word) for word in value.split())
    value = _OHM.sub(lambda m: m.group(1) + (m.group(2) or ""), value)
    value = _PREFIXED.sub(lambda m: m.group(1) + (m.group(2) or "") + m.group(3), value)
    # "33 k resistor" -> "33k resistor"; a bare r suffix (e.g. 330r) is kept.
    value = re.sub(r"(\d)\s+(k|meg)\b", r"\1\2", value)
    return " ".join(value.split())


def stable_hash(value: object) -> str:
    """SHA-256 of canonical JSON (sorted keys); use for specs, payloads and content."""
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def cache_key(namespace: str, *parts: object) -> str:
    """`<namespace>-<hash>`; normalise free-text part names with `normalise_part` first."""
    if namespace not in NAMESPACES:
        raise ValueError(f"Unknown cache namespace: {namespace}")
    return f"{namespace}-{stable_hash(list(parts))[:40]}"


def part_key(namespace: str, name: str, *extra: object) -> str:
    """Key for a part-name lookup, e.g. `part_key("discovery", query)`."""
    return cache_key(namespace, normalise_part(name), *extra)


def _namespace(key: str) -> str:
    return key.split("-", 1)[0]


class MemoryCache:
    """Process-local LRU cache for local runs and tests."""

    def __init__(self, max_entries: int = 2048):
        self.max_entries = max_entries
        self.records: OrderedDict[str, tuple[datetime, str]] = OrderedDict()
        self.lock = RLock()

    def get(self, key: str) -> dict | None:
        with self.lock:
            record = self.records.get(key)
            if record is None:
                return None
            if record[0] <= datetime.now(UTC):
                self.records.pop(key, None)
                return None
            self.records.move_to_end(key)
            value = json.loads(record[1])
        record_cache_hit(_namespace(key))
        return value

    def set(self, key: str, value: dict, ttl_s: int) -> None:
        if ttl_s <= 0:
            return
        encoded = json.dumps(value, default=str)
        with self.lock:
            self.records[key] = (datetime.now(UTC) + timedelta(seconds=ttl_s), encoded)
            self.records.move_to_end(key)
            while len(self.records) > self.max_entries:
                self.records.popitem(last=False)


class FirestoreCache:
    """`<collection>_cache`: one document per key, chunked below the 1 MiB document limit.

    Small values are stored inline in the key document. Larger values are written as chunk
    documents (`<key>-<n>`) first, then the key document with `chunks`, so a reader never
    sees metadata without its data. Lookups are by document id only: no indexes. An
    `expires_at` field on every document allows a Firestore TTL policy (owner decision).
    """

    CHUNK = 900_000

    def __init__(self, client, collection: str):
        self.client = client
        self.collection = client.collection(collection + "_cache")

    @classmethod
    def for_store(cls, store) -> "FirestoreCache | None":
        """Cache beside a `FirestoreJobStore`, or None for stores without a client."""
        client = getattr(store, "client", None)
        return cls(client, store.collection.id) if client is not None else None

    def get(self, key: str) -> dict | None:
        try:
            meta = self.collection.document(key).get().to_dict()
            if not meta or _expired(meta.get("expires_at")):
                return None
            if "value" in meta:
                encoded = meta["value"]
            else:
                chunks = [
                    self.collection.document(f"{key}-{index}").get().to_dict() or {}
                    for index in range(int(meta.get("chunks", 0)))
                ]
                if not chunks or any("data" not in chunk for chunk in chunks):
                    return None
                encoded = "".join(chunk["data"] for chunk in chunks)
            value = json.loads(encoded)
        except Exception:  # The cache is advisory
            log.warning("CACHE_READ_FAILED namespace=%s", _namespace(key), exc_info=True)
            return None
        if not isinstance(value, dict):
            return None
        record_cache_hit(_namespace(key))
        return value

    def set(self, key: str, value: dict, ttl_s: int) -> None:
        if ttl_s <= 0:
            return
        try:
            encoded = json.dumps(value, default=str)
            expires = datetime.now(UTC) + timedelta(seconds=ttl_s)
            base = {"namespace": _namespace(key), "expires_at": expires}
            if len(encoded.encode()) <= self.CHUNK:
                self.collection.document(key).set(base | {"value": encoded})
                return
            # Chunk by characters with a byte-safe width: 4 bytes per character at most.
            width = self.CHUNK // 4
            parts = [encoded[i : i + width] for i in range(0, len(encoded), width)]
            for index, part in enumerate(parts):
                self.collection.document(f"{key}-{index}").set(
                    {"data": part, "expires_at": expires}
                )
            self.collection.document(key).set(base | {"chunks": len(parts)})
        except Exception:  # The cache is advisory
            log.warning("CACHE_WRITE_FAILED namespace=%s", _namespace(key), exc_info=True)


def _expired(value) -> bool:
    if not isinstance(value, datetime):
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def build_cache(settings, store=None) -> SharedCache | None:
    """The app's shared cache: Firestore beside the job store, else in memory."""
    if not settings.cache_enabled:
        return None
    if settings.storage_backend == "firestore" and store is not None:
        cache = FirestoreCache.for_store(store)
        if cache is not None:
            return cache
    return MemoryCache()
