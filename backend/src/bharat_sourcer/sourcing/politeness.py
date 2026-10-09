"""Polite fetching on top of `SafeFetcher`: per-host pacing, caching, backoff, challenge stops.

This layer never tries to get past bot protection. A challenge page (Cloudflare, captcha,
Akamai, PerimeterX, DataDome) marks the host blocked for a cooldown and the caller moves on;
there is no header, fingerprint, proxy or user-agent rotation and no captcha solving. The
user agent is the existing identifiable `USER_AGENT`; robots.txt is checked by `SafeFetcher`
with the strict parser before every request.
"""

import base64
import email.utils
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from bharat_sourcer.sourcing.fetch import FetchError, Page, SafeFetcher

try:  # Shared cache from the cost stream (merged on the integration branch).
    from bharat_sourcer.sourcing.cache import TTL, cache_key
except ImportError:  # pragma: no cover - local shim until the branches are merged
    TTL: dict[str, float] = {}

    def cache_key(*parts: str) -> str:
        return ":".join(parts)

    def normalise_part(text: str) -> str:
        return " ".join(text.lower().split())


BLOCKED = "blocked_by_bot_protection"

# Markers that identify an interstitial challenge rather than a seller page. Title and
# script markers are specific to challenge pages; captcha widgets alone are not (contact
# forms embed reCAPTCHA), so they count only on an error status.
CHALLENGE_ALWAYS = re.compile(
    rb"<title>\s*(?:just a moment|attention required|please wait)\b[^<]*</title>"
    rb"|_cf_chl_opt|cf-browser-verification|/cdn-cgi/challenge-platform/"
    rb"|sucuri_cloudproxy|Sucuri WebSite Firewall|_Incapsula_Resource|Incapsula incident"
    rb"|captcha-delivery\.com|px-captcha|_pxcaptcha|perimeterx",
    re.IGNORECASE,
)
CHALLENGE_ON_ERROR = re.compile(
    rb"hcaptcha|g-recaptcha|recaptcha/api\.js|cf-turnstile|challenges\.cloudflare\.com"
    rb"|errors\.edgesuite\.net|reference&#32;&#35;|datadome|are you a robot"
    rb"|verify you are (?:a )?human",
    re.IGNORECASE,
)
ERROR_STATUSES = {401, 403, 405, 429, 503}


def challenge_reason(page: Page) -> str | None:
    """Return a short provider label when the response is a bot-protection challenge."""
    headers = page.headers
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "Cloudflare challenge"
    if "x-datadome" in headers and page.status in ERROR_STATUSES:
        return "DataDome challenge"
    head = page.body[:200_000]
    if CHALLENGE_ALWAYS.search(head):
        return "bot-protection challenge page"
    if page.status in ERROR_STATUSES and CHALLENGE_ON_ERROR.search(head):
        return "bot-protection challenge page"
    return None


class BlockedError(FetchError):
    """The host served a challenge or is cooling down after one; never retried."""

    def __init__(self, host: str, reason: str):
        super().__init__(f"{host} blocked automated access ({reason})")
        self.host = host
        self.reason = reason


@dataclass
class CachedPage:
    page: Page
    expires: float


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    return max(0.0, parsed.timestamp() - time.time())


class Politeness:
    """Shared, thread-safe politeness state for one `SourcingService` instance."""

    def __init__(
        self,
        *,
        per_host: int = 2,
        min_interval_s: float = 1.0,
        search_ttl_s: float = 6 * 3600,
        page_ttl_s: float = 900,
        blocked_cooldown_s: float = 1800,
        max_retries: int = 2,
        max_retry_wait_s: float = 10,
        cache_entries: int = 2000,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        cache=None,
    ):
        # Optional shared cache (`get(key)` / `set(key, dict, ttl_s)`); in-memory always.
        self.cache = cache
        self.per_host = max(1, min(per_host, 2))
        self.min_interval_s = min_interval_s
        self.search_ttl_s = search_ttl_s
        self.page_ttl_s = page_ttl_s
        self.blocked_cooldown_s = blocked_cooldown_s
        self.max_retries = max_retries
        self.max_retry_wait_s = max_retry_wait_s
        self.cache_entries = cache_entries
        self.clock = clock
        self.sleep = sleep
        self._lock = threading.Lock()
        self._slots: dict[str, threading.BoundedSemaphore] = {}
        self._next_request: dict[str, float] = {}
        self._blocked: dict[str, tuple[float, str]] = {}
        self._cache: OrderedDict[str, CachedPage] = OrderedDict()

    # --- blocked hosts -------------------------------------------------------------
    def blocked_reason(self, host: str) -> str | None:
        with self._lock:
            entry = self._blocked.get(host)
            if entry and entry[0] > self.clock():
                return entry[1]
            self._blocked.pop(host, None)
            return None

    def mark_blocked(self, host: str, reason: str) -> None:
        with self._lock:
            self._blocked[host] = (self.clock() + self.blocked_cooldown_s, reason)

    def blocked_hosts(self) -> dict[str, str]:
        now = self.clock()
        with self._lock:
            return {h: r for h, (until, r) in self._blocked.items() if until > now}

    # --- cache ---------------------------------------------------------------------
    def _shared_key(self, kind: str, url: str, shared_key: str | None) -> str | None:
        if self.cache is None:
            return None
        if shared_key and kind != "search":
            return shared_key
        if kind == "search":
            return cache_key("seller_search", urlsplit(url).hostname or "", url)
        return cache_key("page", url)

    def _shared_get(self, key: str | None) -> Page | None:
        if key is None:
            return None
        try:
            value = self.cache.get(key)
            if not isinstance(value, dict):
                return None
            return Page(
                value["url"],
                int(value["status"]),
                dict(value["headers"]),
                base64.b64decode(value["body"]),
            )
        except Exception:
            # The shared cache is an optimisation; any failure falls back to fetching.
            logging.getLogger(__name__).warning("POLITE_CACHE_READ_FAILED", exc_info=True)
            return None

    def _shared_set(
        self, key: str | None, page: Page, kind: str, ttl_s: float | None = None
    ) -> None:
        if key is None:
            return
        name = "seller_search" if kind == "search" else "page"
        configured = self.search_ttl_s if kind == "search" else self.page_ttl_s
        ttl = min(TTL.get(name, configured), configured, ttl_s if ttl_s is not None else configured)
        if ttl <= 0:
            return
        value = {
            "url": page.url,
            "status": page.status,
            "headers": page.headers,
            "body": base64.b64encode(page.body).decode("ascii"),
        }
        try:
            self.cache.set(key, value, ttl)
        except Exception:
            logging.getLogger(__name__).warning("POLITE_CACHE_WRITE_FAILED", exc_info=True)

    def _cached(self, key: str) -> Page | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires <= self.clock():
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return entry.page

    def _store(self, key: str, page: Page, ttl: float) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._cache[key] = CachedPage(page, self.clock() + ttl)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_entries:
                self._cache.popitem(last=False)

    # --- pacing --------------------------------------------------------------------
    def _slot(self, host: str) -> threading.BoundedSemaphore:
        with self._lock:
            if host not in self._slots:
                self._slots[host] = threading.BoundedSemaphore(self.per_host)
            return self._slots[host]

    def _wait_turn(self, host: str) -> None:
        with self._lock:
            now = self.clock()
            start = max(now, self._next_request.get(host, 0.0))
            self._next_request[host] = start + self.min_interval_s
        if start > now:
            self.sleep(start - now)

    # --- fetching ------------------------------------------------------------------
    def get(
        self,
        fetcher,
        url: str,
        *,
        kind: str = "page",
        shared_key: str | None = None,
        cacheable: bool | Callable[[Page], bool] | None = None,
        cache_ttl_s: float | None = None,
        bypass_cache: bool = False,
        **kwargs,
    ) -> Page:
        """Fetch `url` politely; `kind` is "search" or "page" (cache lifetime)."""
        host = (urlsplit(url).hostname or "").lower()
        reason = self.blocked_reason(host)
        if reason:
            raise BlockedError(host, reason)
        key = f"{kind}:{url}:{kwargs.get('max_bytes', '')}"
        cached = None if bypass_cache else self._cached(key)
        if cached is not None:
            return cached
        shared = self._shared_key(kind, url, shared_key)
        cached = None if bypass_cache else self._shared_get(shared)
        if cached is not None:
            # Do not extend an existing shared entry beyond its original expiry.
            return cached
        attempt = 0
        with self._slot(host):
            while True:
                self._wait_turn(host)
                page = fetcher.get(url, **kwargs)
                final_host = (urlsplit(page.url).hostname or host).lower()
                reason = challenge_reason(page)
                if reason:
                    self.mark_blocked(final_host, reason)
                    if final_host != host:
                        self.mark_blocked(host, reason)
                    raise BlockedError(final_host, reason)
                if page.status in {429, 503} and attempt < self.max_retries:
                    wait = retry_after_seconds(page.headers.get("retry-after"))
                    if wait is None:
                        wait = 2.0**attempt
                    if wait > self.max_retry_wait_s:
                        # Asked to stay away longer than a request can wait: give up now.
                        return page
                    attempt += 1
                    self.sleep(wait)
                    continue
                break
        allowed = cacheable(page) if callable(cacheable) else cacheable
        if page.status == 200 and (allowed is True or (allowed is None and kind != "search")):
            self.cache_response(url, page, kind=kind, ttl_s=cache_ttl_s, **kwargs)
        return page

    def cache_response(
        self, url: str, page: Page, *, kind: str = "search", ttl_s: float | None = None, **kwargs
    ) -> None:
        """Store only responses whose caller successfully parsed the adapter payload."""
        if page.status != 200 or challenge_reason(page):
            return
        configured = self.search_ttl_s if kind == "search" else self.page_ttl_s
        ttl = min(configured, ttl_s if ttl_s is not None else configured)
        key = f"{kind}:{url}:{kwargs.get('max_bytes', '')}"
        if kind == "search" and (
            self._cached(key) is not None
            or self._shared_get(self._shared_key(kind, url, None)) is not None
        ):
            # Adapters validate cache hits too. Validation must not renew the original
            # expiry on every read, especially for short-lived empty search results.
            return
        self._store(key, page, ttl)
        self._shared_set(self._shared_key(kind, url, None), page, kind, ttl)

    def wrap(self, fetcher) -> "PoliteFetcher":
        return fetcher if isinstance(fetcher, PoliteFetcher) else PoliteFetcher(fetcher, self)


class PoliteFetcher:
    """Drop-in fetcher (`get(url, ...)`) that routes product-page reads through `Politeness`."""

    def __init__(self, fetcher=None, politeness: Politeness | None = None):
        self.fetcher = fetcher or SafeFetcher()
        self.politeness = politeness or Politeness()

    def get(self, url: str, **kwargs) -> Page:
        return self.politeness.get(self.fetcher, url, kind="page", **kwargs)
