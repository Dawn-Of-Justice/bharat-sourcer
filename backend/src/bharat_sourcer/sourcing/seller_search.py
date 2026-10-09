"""Search curated Indian sellers' own catalogues for candidate product URLs.

Adapters read public search endpoints that robots.txt allows (see `known_sellers.json`, which
records each review and date) and return candidate product URLs with optional title, price
and image *hints*. Hints only order candidates; they are never offers. Every candidate is
verified later on its product page or product JSON by the existing verifier.

Requests go through `Politeness` (pacing, caching, backoff, challenge detection) and
`SafeFetcher` (robots.txt, HTTPS, public-address pinning, size limits). Blocked sellers are
reported, never circumvented.
"""

import html
import json
import logging
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin, urlsplit

from bharat_sourcer.sourcing.fetch import FetchError, Page, SafeFetcher
from bharat_sourcer.sourcing.politeness import (
    BLOCKED,
    BlockedError,
    Politeness,
)
from bharat_sourcer.sourcing.routing import Rung, normalise
from bharat_sourcer.sourcing.sellers import host_of, listing_key
from bharat_sourcer.sourcing.textmatch import relevance

REGISTRY = json.loads((Path(__file__).parent / "known_sellers.json").read_text("utf-8"))["sellers"]
SEARCH_BYTES = 1_000_000
# Shopify handles may contain Unicode letters (e.g. "220µf-25v-..."); they are percent-encoded.
HANDLE = re.compile(r"^\w[\w%-]{0,250}$")
UNITS = {"ohm", "v", "uf", "nf", "pf", "mm", "w", "a", "ma", "k", "mah"}
TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
# Words that describe a listing rather than identify the part; ignored for overlap.
FILLER = {"pack", "of", "pcs", "piece", "pieces", "the", "and", "with", "for", "a", "set"}


@dataclass
class Candidate:
    url: str
    seller: str
    title: str | None = None
    # Search-result hints: never used as a verified price, stock or image.
    price_hint: str | None = None
    image_hint: str | None = None
    query: str = ""
    rank: int = 0
    score: float = 0.0
    source: str = "seller_search"


@dataclass
class SellerDiagnostic:
    seller: str
    status: str  # ok | no_results | blocked_by_bot_protection | robots_disallowed | error | timeout
    candidates: int = 0
    detail: str | None = None
    queries: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    queries: list[str]
    candidates: list[Candidate]
    diagnostics: list[SellerDiagnostic]
    known_blocked: list[str] = field(default_factory=list)

    def blocked(self) -> list[str]:
        runtime = [d.seller for d in self.diagnostics if d.status == BLOCKED]
        return list(dict.fromkeys(self.known_blocked + runtime))

    def message(self) -> str:
        """One sentence for no-offer diagnostics, e.g. 'robu.in blocked automated access; …'."""
        blocked = self.blocked()
        checked = [d for d in self.diagnostics if d.status in {"ok", "no_results"}]
        failed = [
            d for d in self.diagnostics if d.status in {"error", "timeout", "timeout_partial"}
        ]
        text = (
            f"Seller search checked {len(checked)} "
            f"{'other ' if blocked else ''}seller{'s' if len(checked) != 1 else ''} "
            f"and found {len(self.candidates)} candidate"
            f"{'s' if len(self.candidates) != 1 else ''}."
        )
        if blocked:
            text = f"{', '.join(blocked)} blocked automated access; " + text[0].lower() + text[1:]
        if failed:
            text += f" {len(failed)} seller search{'es' if len(failed) != 1 else ''} failed."
        return text


# --- text helpers --------------------------------------------------------------------------


def tokens(text: str) -> set[str]:
    words = TOKEN.findall(normalise(text))
    return {w.removesuffix("s") if len(w) > 3 and not w[0].isdigit() else w for w in words} - FILLER


# Descriptive words many store searches cannot match (they require every word).
DESCRIPTORS = {
    "clear",
    "water",
    "transparent",
    "diffused",
    "through",
    "hole",
    "tht",
    "round",
    "bright",
    "super",
    "standard",
    "radial",
    "axial",
    "lens",
}


def short_query(query: str) -> str:
    """The query without descriptive words, at most three words: a fallback search."""
    words = [w for w in normalise(query).split() if w not in DESCRIPTORS]
    return " ".join(words[:3])


def query_variants(names: list[str], limit: int = 3) -> list[str]:
    """Plain search strings: the normalised name, its bracketed alias, a short core form."""
    out = []
    for name in names:
        if not name or not name.strip():
            continue
        inner = re.findall(r"\(([^)]{2,40})\)", name)
        outer = re.sub(r"\([^)]*\)", " ", name)
        base = normalise(outer)
        out.append(normalise(name.replace("(", " ").replace(")", " ")))
        out.extend(normalise(part) for part in inner)
        words = base.split()
        if len(words) > 2:
            valued = [w for w in words[:-1] if any(c.isdigit() for c in w) or w in UNITS]
            out.append(" ".join([*valued, words[-1]]) if valued else " ".join(words[-2:]))
        out.append(base)
    return [q for q in dict.fromkeys(out) if q][:limit]


def overlap(query: str, title: str | None) -> float:
    wanted = tokens(query)
    if not wanted or not title:
        return 0.0
    return len(wanted & tokens(title)) / len(wanted)


def url_key(url: str) -> str:
    return listing_key(url)


def own_host(url: str, domain: str) -> bool:
    host, domain = host_of(url), host_of(domain)
    return urlsplit(url).scheme == "https" and (host == domain or host.endswith("." + domain))


def money_hint(raw: object, minor: int = 0) -> str | None:
    try:
        value = Decimal(str(raw)).scaleb(-minor)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    return f"{value.quantize(Decimal('0.01'))}"


# --- adapters ------------------------------------------------------------------------------

Fetch = Callable[[str], Page]


def json_body(page: Page):
    if page.status != 200 or "json" not in page.headers.get("content-type", ""):
        raise ValueError(f"HTTP {page.status}")
    return json.loads(page.body.decode("utf-8"))


def shopify_suggest(fetch: Fetch, seller: dict, query: str, limit: int) -> list[Candidate]:
    """Shopify predictive search: `/search/suggest.json` (public storefront endpoint)."""
    host = seller["host"]
    data = json_body(
        fetch(
            f"https://{host}/search/suggest.json?q={quote(query)}"
            f"&resources%5Btype%5D=product&resources%5Blimit%5D={min(limit, 10)}"
        )
    )
    if not isinstance(data, dict):
        raise ValueError("Invalid Shopify search response")
    products = data.get("resources", {}).get("results", {}).get("products")
    if not isinstance(products, list):
        raise ValueError("Invalid Shopify products response")
    found = []
    for product in products if isinstance(products, list) else []:
        handle = product.get("handle") if isinstance(product, dict) else None
        if not isinstance(handle, str) or not HANDLE.match(handle):
            continue
        image = product.get("image")
        found.append(
            Candidate(
                # Canonical product URL: tracking parameters (`_pos`, `_psq`) are dropped.
                url=f"https://{host}/products/{quote(handle, safe='%-_')}",
                seller=seller["domain"],
                title=str(product.get("title") or "")[:300] or None,
                price_hint=money_hint(product.get("price")),
                image_hint=image
                if isinstance(image, str) and image.startswith("https://")
                else None,
            )
        )
    return found[:limit]


def woo_store_api(fetch: Fetch, seller: dict, query: str, limit: int) -> list[Candidate]:
    """WooCommerce Store API product search (`/wp-json/wc/store/v1/products?search=`)."""
    host = seller["host"]
    data = json_body(
        fetch(
            f"https://{host}/wp-json/wc/store/v1/products?search={quote(query)}"
            f"&per_page={min(limit, 10)}"
        )
    )
    found = []
    if not isinstance(data, list):
        raise ValueError("Invalid WooCommerce search response")
    for product in data:
        if not isinstance(product, dict):
            continue
        link = product.get("permalink")
        if not isinstance(link, str) or not own_host(link, seller["domain"]):
            continue
        prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
        minor = prices.get("currency_minor_unit")
        hint = (
            money_hint(prices.get("price"), minor)
            if prices.get("currency_code") == "INR" and isinstance(minor, int) and 0 <= minor <= 4
            else None
        )
        images = product.get("images")
        image = images[0].get("src") if isinstance(images, list) and images else None
        found.append(
            Candidate(
                url=link,
                seller=seller["domain"],
                title=html.unescape(str(product.get("name") or ""))[:300] or None,
                price_hint=hint,
                image_hint=image
                if isinstance(image, str) and image.startswith("https://")
                else None,
            )
        )
    return found[:limit]


class ProductLinks(HTMLParser):
    """Collect anchors inside (or carrying) a configured product-link class."""

    def __init__(self, link_class: str):
        super().__init__(convert_charrefs=True)
        self.link_class = link_class
        self.stack: list[tuple[str, bool]] = []
        self.links: list[tuple[str, str]] = []
        self.current: list | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        marked = self.link_class in (values.get("class") or "").split()
        inside = marked or any(flag for _, flag in self.stack[-4:])
        if tag == "a" and inside and values.get("href"):
            self.current = [values["href"], values.get("title") or "", []]
        if tag not in {"img", "br", "meta", "link", "input", "source", "hr"}:
            self.stack.append((tag, marked))

    def handle_data(self, data):
        if self.current is not None:
            self.current[2].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            href, title, text = self.current
            self.links.append((href, " ".join("".join(text).split()) or title))
            self.current = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def html_links(page: Page, seller: dict, link_class: str, limit: int) -> list[Candidate]:
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        raise ValueError(f"HTTP {page.status}")
    parser = ProductLinks(link_class)
    parser.feed(page.body[:SEARCH_BYTES].decode("utf-8", errors="replace"))
    pattern = re.compile(seller["search"].get("href_pattern") or r".")
    found = []
    for href, title in parser.links:
        url = urljoin(page.url, href)
        if not own_host(url, seller["domain"]) or not pattern.search(url):
            continue
        found.append(Candidate(url=url, seller=seller["domain"], title=title[:300] or None))
    return found[:limit]


def bigcommerce_html(fetch: Fetch, seller: dict, query: str, limit: int) -> list[Candidate]:
    page = fetch(f"https://{seller['host']}/search.php?search_query={quote_plus(query)}")
    return html_links(page, seller, seller["search"].get("link_class", "card-title"), limit)


def magento_html(fetch: Fetch, seller: dict, query: str, limit: int) -> list[Candidate]:
    page = fetch(f"https://{seller['host']}/catalogsearch/result/?q={quote_plus(query)}")
    return html_links(page, seller, seller["search"].get("link_class", "product-item-link"), limit)


def html_template(fetch: Fetch, seller: dict, query: str, limit: int) -> list[Candidate]:
    """Generic HTML search page: `template` with `{query}` and a product-link class."""
    url = seller["search"]["template"].replace("{query}", quote_plus(query))
    return html_links(fetch(url), seller, seller["search"].get("link_class", "caption"), limit)


ADAPTERS = {
    "shopify_suggest": shopify_suggest,
    "woo_store_api": woo_store_api,
    "bigcommerce_html": bigcommerce_html,
    "magento_html": magento_html,
    "html_template": html_template,
}


def searchable(registry: list[dict]) -> list[dict]:
    sellers = []
    for entry in registry:
        search = entry.get("search")
        if not entry.get("enabled") or not isinstance(search, dict):
            continue
        if search.get("adapter") not in ADAPTERS:
            continue
        sellers.append({**entry, "host": search.get("host") or entry["domain"]})
    return sellers


# --- orchestration -------------------------------------------------------------------------


class SellerSearch:
    def __init__(
        self,
        politeness: Politeness | None = None,
        fetcher=None,
        registry: list[dict] | None = None,
        *,
        max_workers: int = 6,
        deadline_s: float = 20,
        queries_per_seller: int = 4,
    ):
        self.politeness = politeness or Politeness()
        self.fetcher = fetcher or SafeFetcher()
        self.registry = REGISTRY if registry is None else registry
        self.sellers = searchable(self.registry)
        self.max_workers = max(1, max_workers)
        self.deadline_s = deadline_s
        self.queries_per_seller = max(1, queries_per_seller)

    def _fetcher_for(self, seller: dict, query: str, pages: list[tuple[str, Page]]) -> Fetch:
        def fetch(url: str) -> Page:
            page = self.politeness.get(
                self.fetcher, url, kind="search", cacheable=False, max_bytes=SEARCH_BYTES
            )
            pages.append((url, page))
            return page

        return fetch

    def _search_one(self, seller: dict, queries: list[str], limit: int, progress=None):
        adapter = ADAPTERS[seller["search"]["adapter"]]
        collected, diagnostic, lock, stopped = progress or (
            [],
            SellerDiagnostic(seller["domain"], "no_results"),
            threading.Lock(),
            threading.Event(),
        )
        rungs = list(queries)
        if seller["search"]["adapter"] == "woo_store_api":
            rungs.sort(key=lambda q: getattr(q, "kind", "") != "model")
        part = getattr(rungs[0], "part_terms", str(rungs[0])) if rungs else ""
        seen = set()
        for rung in rungs[: self.queries_per_seller]:
            if stopped.is_set():
                break
            query = str(rung)
            with lock:
                diagnostic.queries.append(query)
            pages = []
            try:
                found = adapter(self._fetcher_for(seller, query, pages), seller, query, limit)
                for url, page in pages:
                    self.politeness.cache_response(
                        url,
                        page,
                        kind="search",
                        max_bytes=SEARCH_BYTES,
                        ttl_s=None if found else 600,
                    )
            except (BlockedError, FetchError) as exc:
                with lock:
                    diagnostic.status = (
                        BLOCKED
                        if isinstance(exc, BlockedError)
                        else ("robots_disallowed" if "robots" in str(exc).lower() else "error")
                    )
                    diagnostic.detail = str(exc)[:200]
                break
            except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
                with lock:
                    diagnostic.status = "error"
                    diagnostic.detail = str(exc)[:200]
                continue
            with lock:
                for candidate in found:
                    if url_key(candidate.url) in seen:
                        continue
                    seen.add(url_key(candidate.url))
                    candidate.query, candidate.rank = query, len(seen) - 1
                    candidate.score = relevance(part, candidate.title or "")
                    collected.append(candidate)
                diagnostic.candidates = len(collected)
            if (getattr(rung, "kind", "") == "model" or len(query.split()) >= 2) and any(
                c.score >= 0.8 for c in found
            ):
                break
        with lock:
            collected.sort(key=lambda c: (-c.score, c.rank))
            if collected and diagnostic.status not in {BLOCKED, "robots_disallowed"}:
                diagnostic.status = "ok"
        return collected, diagnostic

    def search(
        self, queries: list[str], limit_per_seller: int = 5, total_budget: int = 12
    ) -> SearchResult:
        queries = list(
            dict.fromkeys(q if isinstance(q, Rung) else q.strip() for q in queries if q.strip())
        )
        known_blocked = [
            e["domain"]
            for e in self.registry
            if e.get("access") == BLOCKED and not e.get("enabled")
        ]
        result = SearchResult([str(q) for q in queries[:4]], [], [], known_blocked)
        if not queries or not self.sellers:
            return result
        sellers = []
        for seller in self.sellers:
            reason = self.politeness.blocked_reason(seller["host"])
            if reason:
                result.diagnostics.append(
                    SellerDiagnostic(seller["domain"], BLOCKED, detail=reason)
                )
            else:
                sellers.append(seller)
        pool = ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(sellers))))
        progress = {
            seller["domain"]: (
                [],
                SellerDiagnostic(seller["domain"], "no_results"),
                threading.Lock(),
                threading.Event(),
            )
            for seller in sellers
        }
        try:
            futures = {
                pool.submit(
                    self._search_one, seller, queries, limit_per_seller, progress[seller["domain"]]
                ): seller
                for seller in sellers
            }
            done, _ = wait(futures, timeout=self.deadline_s)
            per_seller = []
            for future, seller in futures.items():
                collected, diagnostic, lock, stopped = progress[seller["domain"]]
                if future not in done:
                    stopped.set()
                    with lock:
                        found = sorted(collected, key=lambda c: (-c.score, c.rank))
                        diagnostic = SellerDiagnostic(
                            seller["domain"],
                            "timeout_partial" if found else "timeout",
                            len(found),
                            queries=list(diagnostic.queries),
                        )
                else:
                    try:
                        found, diagnostic = future.result()
                    except Exception:
                        logging.getLogger(__name__).warning("SELLER_SEARCH_FAILED", exc_info=True)
                        with lock:
                            found = list(collected)
                        diagnostic = SellerDiagnostic(seller["domain"], "error", len(found))
                result.diagnostics.append(diagnostic)
                per_seller.append(found)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        result.candidates = merge(per_seller, total_budget)
        logging.getLogger(__name__).info(
            "SELLER_SEARCH queries=%s candidates=%s statuses=%s",
            len(queries),
            len(result.candidates),
            {d.seller: d.status for d in result.diagnostics},
        )
        return result


def merge(per_seller: list[list[Candidate]], budget: int) -> list[Candidate]:
    """Round-robin across sellers (registry order) so one store cannot fill the budget."""
    merged, seen = [], set()
    depth = max((len(found) for found in per_seller), default=0)
    for level in range(depth):
        tier = [found[level] for found in per_seller if level < len(found)]
        for candidate in sorted(tier, key=lambda c: -round(c.score, 1)):
            key = url_key(candidate.url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
    return merged[: max(0, budget)]


def search_sellers(
    queries: list[str],
    limit_per_seller: int = 5,
    total_budget: int = 12,
    searcher: SellerSearch | None = None,
) -> SearchResult:
    return (searcher or SellerSearch()).search(queries, limit_per_seller, total_budget)


def from_settings(settings, cache=None) -> SellerSearch | None:
    """Build the shared searcher from `BS_SELLER_*` settings; None when disabled.

    `cache` is the optional shared cache (`sourcing.cache`); the in-memory cache always runs.
    """
    if not settings.seller_search_enabled:
        return None
    return SellerSearch(
        Politeness(
            search_ttl_s=settings.seller_search_cache_s,
            page_ttl_s=settings.seller_page_cache_s,
            blocked_cooldown_s=settings.seller_blocked_cooldown_s,
            cache=cache,
        )
    )
