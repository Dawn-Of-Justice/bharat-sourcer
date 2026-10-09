"""Seller trust labels from free, deterministic checks. Labels inform; offers are never hidden.

Per seller host: HTTPS, domain registration date via public RDAP, a checksum-valid GSTIN on
fetched pages, and return/shipping/contact pages. Per offer: price far below the other
verified offers for the same line. Checks run after verification with a deadline, so a slow
lookup fails open to `unverified` ("check unavailable") without delaying offers further.
"""

import json
import logging
import re
import statistics
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bharat_sourcer.schemas import SellerTrust, TrustSignals, VerifiedOffer, now
from bharat_sourcer.sourcing.fetch import Page, SafeFetcher
from bharat_sourcer.sourcing.platforms import detect_platform, html_page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.sellers import identify, registrable_domain

# Curated seed list; see the file's note. It is project knowledge, not seller evidence.
KNOWN_SELLERS = {
    seller["domain"]: seller
    for seller in json.loads((Path(__file__).parent / "known_sellers.json").read_text("utf-8"))[
        "sellers"
    ]
}

GSTIN = re.compile(r"(?<![A-Z0-9])(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])(?![A-Z0-9])")
GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# 01-38 are states and union territories; 97 other territory; 99 centre jurisdiction.
GSTIN_STATES = {f"{code:02d}" for code in range(1, 39)} | {"97", "99"}
# Second-level registrations under .in (https://www.registry.in/policies).
POLICY_KINDS = {
    "returns": re.compile(r"return|refund|cancell?ation"),
    "shipping": re.compile(r"shipping|delivery"),
    "contact": re.compile(r"contact"),
}
SHOPIFY_POLICY_PATHS = {
    "returns": "/policies/refund-policy",
    "shipping": "/policies/shipping-policy",
    "contact": "/pages/contact",
}
ANOMALY_RATIO = Decimal("0.4")
UNAVAILABLE = {
    "domain_age": "Domain age check unavailable",
    "policies": "Policy page check unavailable",
    "all": "Trust checks unavailable (timed out or failed)",
}


def gstin_valid(value: str) -> bool:
    """Format, state code and the GSTN mod-36 check character; no online lookup."""
    if not GSTIN.fullmatch(value) or value[:2] not in GSTIN_STATES:
        return False
    total = 0
    for index, char in enumerate(value[:14]):
        product = GSTIN_CHARS.index(char) * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return value[14] == GSTIN_CHARS[(36 - total % 36) % 36]


def find_gstin(text: str) -> str | None:
    for candidate in GSTIN.findall(text[:2_000_000]):
        if gstin_valid(candidate):
            return candidate
    return None


def rdap_url(domain: str) -> str:
    # NIXI runs the .in RDAP service; rdap.org redirects to the registry for other TLDs.
    if domain.endswith(".in"):
        return f"https://rdap.nixiregistry.in/rdap/domain/{domain}"
    return f"https://rdap.org/domain/{domain}"


def registration_date(data: object) -> datetime | None:
    events = data.get("events") if isinstance(data, dict) else None
    for event in events if isinstance(events, list) else []:
        if isinstance(event, dict) and event.get("eventAction") == "registration":
            try:
                value = datetime.fromisoformat(str(event.get("eventDate")))
            except ValueError:
                return None
            return value if value.tzinfo else value.replace(tzinfo=UTC)
    return None


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and len(self.links) < 1000:
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join("".join(self.text).split())[:80]))
            self.href = None


def policy_links(page: Page) -> dict[str, str]:
    """First same-host HTTPS link per policy kind, matched on its path or short link text."""
    if not html_page(page):
        return {}
    parser = Links()
    parser.feed(page.body[:2_000_000].decode("utf-8", errors="replace"))
    host = urlsplit(page.url).hostname
    found: dict[str, str] = {}
    for href, text in parser.links:
        try:
            url = urljoin(page.url, href.strip())
            parsed = urlsplit(url)
        except (ValueError, AttributeError):
            continue
        if parsed.scheme != "https" or parsed.hostname != host or len(url) > 2048:
            continue
        label = (parsed.path + " " + text).lower()
        for kind, pattern in POLICY_KINDS.items():
            if kind not in found and pattern.search(label):
                found[kind] = url.split("#")[0]
    return found


def web_risk_check(domain: str) -> None:
    """HOOK (not implemented): Google Web Risk `uris.search` would plug in here.

    Web Risk is a keyed, metered Google Cloud API, so it needs owner approval before use.
    Until then every signal reports `web_risk: not_checked` and no seller is blocked on it.
    """
    return None


def decide(signals: TrustSignals) -> SellerTrust:
    reasons: list[str] = []
    age = signals.domain_age_days
    basics = {"returns", "shipping", "contact"}.issubset(signals.policies)
    seeded = bool(KNOWN_SELLERS.get(signals.domain or "", {}).get("established"))
    checked = "all" not in signals.unavailable and not seeded
    if not signals.https:
        label = "unverified"
        reasons.append("Not served over HTTPS")
    elif seeded:
        label = "established"
        reasons.append("On Bharat Sourcer's curated seed-seller list (not seller-verified)")
    elif signals.gstin and age is not None and age >= 365 and basics:
        label = "established"
    elif age is not None and age < 30 and not signals.gstin:
        label = "unverified"
        reasons.append("Domain registered less than 30 days ago and no GSTIN found")
    elif signals.gstin or basics:
        label = "verified_basics"
    else:
        label = "unverified"
    if age is not None:
        years = age // 365
        reasons.append(
            f"Domain registered about {years} year{'s' if years != 1 else ''} ago"
            if years
            else f"Domain registered {age} days ago"
        )
    if signals.gstin:
        reasons.append(
            "GSTIN shown on the site (format and checksum valid; not checked with the GST portal)"
        )
    elif checked:
        reasons.append("No GSTIN found on the pages checked")
    if signals.policies:
        reasons.append("Found pages: " + ", ".join(signals.policies))
    missing = [k for k in ("returns", "shipping", "contact") if k not in signals.policies]
    if missing and checked and "policies" not in signals.unavailable:
        reasons.append("Not found: " + ", ".join(missing))
    for check in signals.unavailable:
        reasons.append(UNAVAILABLE[check])
    if signals.price_anomaly:
        reasons.append(
            "Unusually cheap: under 40% of the median of other verified offers; check the seller"
        )
    if label == "unverified":
        reasons.append("Check the seller before paying; prefer cash on delivery")
    return SellerTrust(
        label=label,
        new_seller=not seeded and age is not None and age < 365,
        reasons=reasons,
        signals=signals,
    )


def mark_price_anomalies(offers: list[VerifiedOffer]) -> set[str]:
    """Offer URLs priced under 40% of the median of at least two other offers on the line."""
    flagged = set()
    for offer in offers:
        others = [Decimal(o.price_inr) for o in offers if o is not offer]
        if len(others) >= 2 and Decimal(offer.price_inr) < ANOMALY_RATIO * statistics.median(
            others
        ):
            flagged.add(str(offer.url))
    return flagged


class TrustChecker:
    """Domain checks are cached in memory per host and shared across parallel lines."""

    def __init__(
        self,
        fetcher: SafeFetcher | None = None,
        *,
        deadline_s: float = 12,
        ttl_s: float = 24 * 3600,
        failure_ttl_s: float = 15 * 60,
        max_policy_fetches: int = 3,
        clock: Callable[[], datetime] = now,
        max_workers: int = 4,
    ):
        self.fetcher = Politeness().wrap(fetcher or SafeFetcher())
        self.deadline_s = deadline_s
        self.ttl_s = ttl_s
        self.failure_ttl_s = failure_ttl_s
        self.max_policy_fetches = max_policy_fetches
        self.clock = clock
        self._cache: dict[str, tuple[float, SellerTrust]] = {}
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="trust")

    def label_offers(self, offers: list[VerifiedOffer], pages: list[Page]) -> None:
        """Set `offer.trust` on every offer; checks that miss the deadline fail open."""
        if not offers:
            return
        hosts = list(dict.fromkeys(registrable_domain(offer.seller) for offer in offers))
        futures = {host: self._submit(host, pages) for host in hosts}
        wait(futures.values(), timeout=self.deadline_s)
        anomalies = mark_price_anomalies(offers)
        for offer in offers:
            future = futures[registrable_domain(offer.seller)]
            base = None
            if future.done() and not future.cancelled() and future.exception() is None:
                base = future.result()
            if base is None:
                base = SellerTrust(
                    label="unverified",
                    signals=TrustSignals(
                        domain=registrable_domain(offer.seller),
                        unavailable=["all"],
                    ),
                    checked_at=self.clock(),
                )
            signals = base.signals.model_copy(
                update={
                    "https": str(offer.url).startswith("https://"),
                    "price_anomaly": str(offer.url) in anomalies,
                },
                deep=True,
            )
            trust = decide(signals)
            if identify(str(offer.url)).kind == "marketplace":
                trust.label = "unverified"
                trust.reasons = [
                    "Marketplace listing: the third-party merchant is unverified; "
                    "marketplace trust does not verify the merchant."
                ]
                trust.signals = TrustSignals(
                    domain=registrable_domain(offer.seller),
                    https=signals.https,
                    unavailable=["domain_age"],
                )
            trust.checked_at = base.checked_at
            offer.trust = trust

    def _submit(self, host: str, pages: list[Page]) -> Future:
        host = registrable_domain(host)
        with self._lock:
            cached = self._cache.get(host)
            if cached and cached[0] > time.monotonic():
                future: Future = Future()
                future.set_result(cached[1])
                return future
            if host in self._inflight:
                return self._inflight[host]
            own = [p for p in pages if registrable_domain(urlsplit(p.url).hostname or "") == host]
            future = self._executor.submit(self._check, host, own)
            self._inflight[host] = future
        future.add_done_callback(lambda done: self._store(host, done))
        return future

    def _store(self, host: str, future: Future) -> None:
        with self._lock:
            self._inflight.pop(host, None)
            if future.cancelled() or future.exception() is not None:
                return
            trust = future.result()
            ttl = self.failure_ttl_s if trust.signals.unavailable else self.ttl_s
            self._cache[host] = (time.monotonic() + ttl, trust)
            if len(self._cache) > 1000:
                self._cache.pop(next(iter(self._cache)))

    def _check(self, host: str, pages: list[Page]) -> SellerTrust:
        domain = registrable_domain(host)
        signals = TrustSignals(domain=domain)
        platforms = [detect_platform(page) for page in pages if html_page(page)]
        signals.platform = next((p for p in platforms if p != "unknown"), None) or (
            platforms[0] if platforms else None
        )
        web_risk_check(domain)
        if KNOWN_SELLERS.get(domain, {}).get("established"):
            signals.known_seller = True
            # Seed sellers were reviewed by the team; skip network checks to save budget.
            return SellerTrust(label="established", signals=signals, checked_at=self.clock())
        signals.known_seller = domain in KNOWN_SELLERS
        try:
            registered = (
                None
                if identify(domain).kind in {"platform_hosted", "marketplace"}
                else self._registered(domain)
            )
        except Exception:
            registered = None
        if registered:
            signals.domain_registered = registered
            signals.domain_age_days = max(0, (self.clock() - registered).days)
        else:
            signals.unavailable.append("domain_age")
        texts = [page.body.decode("utf-8", errors="replace") for page in pages if html_page(page)]
        links: dict[str, str] = {}
        for page in pages:
            for kind, url in policy_links(page).items():
                links.setdefault(kind, url)
        if signals.platform == "shopify":
            for kind, path in SHOPIFY_POLICY_PATHS.items():
                links.setdefault(kind, urljoin(pages[0].url if pages else f"https://{host}", path))
        fetched, failed = 0, 0
        for kind in ("returns", "shipping", "contact"):
            if kind not in links or fetched >= self.max_policy_fetches:
                continue
            fetched += 1
            try:
                page = self.fetcher.get(links[kind])
            except Exception:
                failed += 1
                continue
            if (
                html_page(page)
                and len(page.body) > 200
                and urlsplit(page.url).path.strip("/")
                and registrable_domain(urlsplit(page.url).hostname or "") == domain
                and POLICY_KINDS[kind].search(page.body.decode("utf-8", errors="replace").lower())
            ):
                signals.policies.append(kind)
                texts.append(page.body.decode("utf-8", errors="replace"))
        if fetched and failed == fetched:
            signals.unavailable.append("policies")
        signals.gstin = next((g for g in map(find_gstin, texts) if g), None)
        logging.getLogger(__name__).info(
            "SELLER_TRUST host=%s age_days=%s gstin=%s policies=%s unavailable=%s",
            host,
            signals.domain_age_days,
            bool(signals.gstin),
            ",".join(signals.policies),
            ",".join(signals.unavailable),
        )
        return SellerTrust(label="unverified", signals=signals, checked_at=self.clock())

    def _registered(self, domain: str) -> datetime | None:
        # RDAP (RFC 9083) is a machine API without robots.txt; other fetch guards apply.
        response = self.fetcher.get(rdap_url(domain), robots=False, max_bytes=200_000)
        if response.status != 200:
            return None
        return registration_date(json.loads(response.body.decode("utf-8")))
