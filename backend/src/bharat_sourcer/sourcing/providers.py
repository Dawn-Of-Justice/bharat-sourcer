"""Optional official discovery APIs. Responses are never put in the shared page cache.

Search snippets are only URL hints. Mouser can additionally supply a conservative,
single-unit INR offer from its own API; all matching still uses the existing verifier.
"""

import html
import json
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from bharat_sourcer.observability import elapsed_ms, log_event
from bharat_sourcer.sourcing.coordination import HostDeferred, MemoryCoordinator
from bharat_sourcer.sourcing.fetch import FetchError, Page, validate_url
from bharat_sourcer.sourcing.politeness import retry_after_seconds
from bharat_sourcer.sourcing.seller_search import Candidate, SellerDiagnostic, merge
from bharat_sourcer.sourcing.textmatch import relevance


@dataclass
class ApiPage(Page):
    verification: str = "seller_product_api"


@dataclass
class ProviderResult:
    candidates: list[Candidate] = field(default_factory=list)
    pages: dict[str, Page] = field(default_factory=dict)
    diagnostics: list[SellerDiagnostic] = field(default_factory=list)


class ProviderFetcher:
    """Request-scoped API evidence, with ordinary safe fetching for all other URLs."""

    def __init__(self, pages: dict[str, Page], fallback):
        self.pages = pages
        self.fallback = fallback

    def get(self, url: str, **kwargs):
        if url in self.pages:
            return self.pages[url]
        return self.fallback.get(url, **kwargs)


def mouser_page(part: dict) -> ApiPage | None:
    """Avoid treating bulk-tier prices, USD or uncertain stock as a one-piece INR offer."""
    from bharat_sourcer.sourcing.listings import parse_inr

    url = part.get("ProductDetailUrl", "")
    host = urlsplit(url).hostname or ""
    if not any(host == d or host.endswith("." + d) for d in ("mouser.in", "mouser.com")):
        return None
    if part.get("RestrictionMessage") or part.get("Min") not in ("1", 1):
        return None
    if part.get("Mult") not in ("1", 1):
        return None
    prices = {
        parse_inr(p.get("Price"), "INR")
        for p in part.get("PriceBreaks", [])
        if isinstance(p, dict) and p.get("Currency") == "INR" and p.get("Quantity") == 1
    } - {None}
    if len(prices) != 1:
        return None
    price = prices.pop()
    title = " ".join(
        str(part.get(k) or "") for k in ("ManufacturerPartNumber", "Description")
    ).strip()
    if not title:
        return None
    count = str(part.get("AvailabilityInStock", ""))
    stock = ("InStock" if int(count) > 0 else "OutOfStock") if count.isdigit() else None
    offer = {"@type": "Offer", "url": url, "price": str(price), "priceCurrency": "INR"}
    if stock:
        offer["availability"] = "https://schema.org/" + stock
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "url": url,
        "mpn": part.get("ManufacturerPartNumber"),
        "offers": offer,
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": a.get("AttributeName"),
                "value": a.get("AttributeValue"),
            }
            for a in part.get("ProductAttributes", [])
            if isinstance(a, dict)
        ],
    }
    body = (
        "<h1>"
        + html.escape(title)
        + '</h1><script type="application/ld+json">'
        + json.dumps(product).replace("<", "\\u003c")
        + "</script>"
    )
    return ApiPage(url, 200, {"content-type": "text/html"}, body.encode())


class ProviderSearch:
    def __init__(self, settings, coordinator=None, transport=None, sleep=time.sleep):
        self.settings = settings
        self.coordinator = coordinator or MemoryCoordinator()
        self.transport = transport
        self.sleep = sleep

    def _request(self, method: str, url: str, **kwargs) -> dict:
        host = urlsplit(url).hostname or ""
        delay = self.coordinator.acquire(host, self.settings.seller_provider_interval_s, 2)
        self.sleep(delay)
        # Fixed vendor endpoints; redirects disabled so credentials cannot cross hosts.
        with (
            httpx.Client(
                timeout=self.settings.seller_provider_timeout_s,
                transport=self.transport,
                follow_redirects=False,
            ) as client,
            client.stream(method, url, **kwargs) as response,
        ):
            if response.status_code in {429, 503}:
                seconds = retry_after_seconds(response.headers.get("retry-after")) or 60
                self.coordinator.defer(host, seconds, "rate_limited")
            if response.status_code in {401, 403}:
                self.coordinator.defer(host, 300, "credentials_or_access")
            response.raise_for_status()
            data = bytearray()
            started = time.monotonic()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if (
                    len(data) > 2_000_000
                    or time.monotonic() - started > self.settings.seller_provider_timeout_s
                ):
                    raise ValueError("provider_response_limit")
        if "text/event-stream" in response.headers.get("content-type", ""):
            events = [
                json.loads(line[5:].strip())
                for line in data.decode().splitlines()
                if line.startswith("data:") and line[5:].strip()
            ]
            decoded = next(
                (event for event in events if isinstance(event, dict) and event.get("id") == 1), {}
            )
        else:
            decoded = json.loads(data)
        if not isinstance(decoded, dict):
            raise ValueError("provider_schema")
        return decoded

    def _shopify(self, query, limit):
        data = self._request(
            "POST",
            "https://catalog.shopify.com/api/ucp/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_catalog",
                    "arguments": {
                        "meta": {"ucp-agent": {"profile": self.settings.shopify_catalog_profile}},
                        "catalog": {
                            "query": query,
                            "filters": {"ships_to": {"country": "IN"}, "available": True},
                            "context": {"address_country": "IN", "currency": "INR"},
                            "pagination": {"limit": limit},
                        },
                    },
                },
            },
        )
        if data.get("error") or data.get("result", {}).get("isError"):
            raise ValueError("shopify_protocol_error")
        products = data["result"]["structuredContent"]["products"]
        rows = []
        for product in products:
            if not isinstance(product, dict):
                continue
            if product.get("url"):
                rows.append((product["url"], product.get("title"), None))
            for variant in product.get("variants", []):
                if isinstance(variant, dict) and variant.get("url"):
                    rows.append((variant["url"], product.get("title"), None))
        return rows

    def _brave(self, query, limit):
        data = self._request(
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.settings.brave_search_api_key.get_secret_value()},
            params={
                "q": query + " buy India",
                "country": "IN",
                "count": limit,
                "spellcheck": "false",
                "result_filter": "web",
            },
        )
        return [
            (p.get("url"), p.get("title"), None)
            for p in data.get("web", {}).get("results", [])
            if isinstance(p, dict)
        ]

    def _mouser(self, query, limit):
        data = self._request(
            "POST",
            "https://api.mouser.com/api/v1/search/keyword",
            params={"apiKey": self.settings.mouser_search_api_key.get_secret_value()},
            json={
                "SearchByKeywordRequest": {
                    "keyword": query,
                    "records": limit,
                    "startingRecord": 0,
                    "searchOptions": "4",
                }
            },
        )
        if data.get("Errors"):
            raise ValueError("mouser_api_error")
        return [
            (p.get("ProductDetailUrl"), p.get("Description"), mouser_page(p))
            for p in data["SearchResults"]["Parts"]
            if isinstance(p, dict)
        ]

    def search(self, query: str, budget: int = 8) -> ProviderResult:
        result = ProviderResult()
        if budget <= 0:
            return result
        query = " ".join(query.split()[:60])[:450]
        if not query:
            return result
        providers = []
        if self.settings.shopify_catalog_enabled and self.settings.shopify_catalog_profile:
            providers.append(("shopify_catalog", self._shopify))
        if self.settings.brave_search_api_key:
            providers.append(("brave", self._brave))
        if self.settings.mouser_search_api_key:
            providers.append(("mouser", self._mouser))
        groups = []
        for name, search in providers:
            started = time.perf_counter()
            found = []
            outcome = "no_results"
            try:
                rows = search(query, min(budget, 10))
                for url, title, page in rows:
                    try:
                        if not isinstance(url, str):
                            continue
                        validate_url(url)
                    except FetchError:
                        continue
                    candidate = Candidate(
                        url,
                        urlsplit(url).hostname or "",
                        title=str(title or "")[:300],
                        source=name,
                        score=relevance(query, str(title or "")),
                    )
                    found.append(candidate)
                    if page is not None:
                        result.pages[url] = page
                outcome = "ok" if found else "no_results"
            except HostDeferred:
                outcome = "deferred"
            except httpx.HTTPStatusError as exc:
                outcome = {429: "rate_limited", 401: "credentials", 403: "access_denied"}.get(
                    exc.response.status_code, "http_error"
                )
            except httpx.TimeoutException:
                outcome = "timeout"
            except (ValueError, KeyError, TypeError, AttributeError):
                outcome = "parse_error"
            except Exception:
                # Never log exception text: Mouser authenticates in its query string.
                outcome = "error"
            groups.append(found)
            result.diagnostics.append(SellerDiagnostic(name, outcome, len(found)))
            log_event(
                "SELLER_PROVIDER",
                provider=name,
                outcome=outcome,
                candidates=len(found),
                duration_ms=elapsed_ms(started),
            )
        result.candidates = merge(groups, budget)
        return result
