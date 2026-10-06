"""Seller catalogue search, politeness and staged sourcing; offline (recorded fixtures)."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem, SearchAttribution
from bharat_sourcer.sourcing import seller_search
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.politeness import (
    BLOCKED,
    BlockedError,
    PoliteFetcher,
    Politeness,
    challenge_reason,
)
from bharat_sourcer.sourcing.seller_search import (
    REGISTRY,
    Candidate,
    SearchResult,
    SellerDiagnostic,
    SellerSearch,
    merge,
    overlap,
    query_variants,
    searchable,
)
from bharat_sourcer.sourcing.service import DiscoveryError, JudgeVerdict, SourcingService

FIXTURES = Path(__file__).parent / "fixtures" / "seller_search"
JSON = {"content-type": "application/json; charset=utf-8"}
HTML = {"content-type": "text/html; charset=utf-8"}
# Synthetic Cloudflare interstitial (structure of a real challenge, no real page content).
CLOUDFLARE = (
    b"<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>"
    b"<script>window._cf_chl_opt={cType:'managed'};</script>"
    b'<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>'
    b"</body></html>"
)


def search_key(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    query = (params.get("q") or params.get("search") or [""])[0]
    return (parts.hostname or "").removeprefix("www."), query


def recorded() -> dict:
    pages = {}
    for path in FIXTURES.glob("*.json"):
        fixture = json.loads(path.read_text("utf-8"))
        assert fixture["_fixture"]["url"].startswith("https://")
        assert fixture["_fixture"]["fetched_on"]
        body = json.dumps(fixture["body"]).encode()
        url = fixture["_fixture"]["url"]
        pages[search_key(url)] = Page(url, 200, JSON, body)
    return pages


class FixtureFetcher:
    def __init__(self, overrides=None):
        self.pages = recorded()
        self.overrides = overrides or {}
        self.calls = []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.calls.append(url)
        host, query = search_key(url)
        if host in self.overrides:
            result = self.overrides[host]
            if isinstance(result, Exception):
                raise result
            return result
        return self.pages.get((host, query)) or Page(url, 200, JSON, b"[]")


def seller(domain):
    return next(s for s in searchable(REGISTRY) if s["domain"] == domain)


def fixture_fetch(url):
    return FixtureFetcher().get(url)


def quiet():
    return Politeness(min_interval_s=0, sleep=lambda s: None)


# --- registry ------------------------------------------------------------------------------


def test_registry_records_a_dated_robots_review_for_every_enabled_seller():
    for entry in REGISTRY:
        if entry.get("enabled"):
            assert entry["robots"]["search_allowed"] is True
            assert entry["robots"]["checked_on"] == "2026-10-07"
            assert entry["search"]["adapter"] in seller_search.ADAPTERS
        if entry.get("robots", {}).get("search_allowed") is False:
            assert not entry["enabled"]
    domains = {e["domain"] for e in searchable(REGISTRY)}
    assert {"robocraze.com", "quartzcomponents.com", "zbotic.in"} <= domains
    # Disallowed by robots.txt or blocked by bot protection: never searched.
    assert not domains & {"evelta.com", "probots.co.in", "electronicscomp.com", "robu.in"}


def test_seller_search_setting_defaults_on_and_can_be_disabled():
    assert seller_search.from_settings(Settings()) is not None
    assert seller_search.from_settings(Settings(seller_search_enabled=False)) is None


# --- adapters ------------------------------------------------------------------------------


def test_shopify_suggest_returns_canonical_product_urls_with_hints_only():
    found = seller_search.shopify_suggest(
        fixture_fetch, seller("robocraze.com"), "33k resistor", 10
    )
    assert found[0].title == "33k Ohm Resistor - (Pack of 10)"
    assert found[0].url.startswith("https://robocraze.com/products/")
    assert "?" not in found[0].url  # `_pos`/`_psq` tracking parameters dropped
    assert found[0].price_hint and found[0].seller == "robocraze.com"
    assert all(c.url.startswith("https://robocraze.com/products/") for c in found)


def test_woocommerce_store_api_parses_permalinks_minor_unit_hints_and_entities():
    found = seller_search.woo_store_api(fixture_fetch, seller("zbotic.in"), "ldr", 10)
    first = found[0]
    assert first.url == (
        "https://zbotic.in/product/lm393-photosensitive-light-dependent-control-sensor-ldr-module/"
    )
    assert first.price_hint == "22.77"
    sharvi = seller_search.woo_store_api(
        fixture_fetch, seller("sharvielectronics.com"), "5mm led", 10
    )
    assert any("–" in (c.title or "") for c in sharvi)  # &#8211; unescaped
    rytronics = seller_search.woo_store_api(fixture_fetch, seller("rytronics.in"), "ldr", 10)
    assert all(c.url.startswith("https://www.rytronics.in/product/") for c in rytronics)


def test_woocommerce_rejects_foreign_or_insecure_permalinks():
    body = json.dumps(
        [
            {"name": "LDR", "permalink": "https://evil.example/product/ldr/"},
            {"name": "LDR", "permalink": "http://zbotic.in/product/ldr/"},
            {"name": "LDR 5mm", "permalink": "https://zbotic.in/product/ldr-5mm/"},
        ]
    ).encode()
    found = seller_search.woo_store_api(
        lambda url: Page(url, 200, JSON, body), seller("zbotic.in"), "ldr", 10
    )
    assert [c.url for c in found] == ["https://zbotic.in/product/ldr-5mm/"]


# SYNTHETIC fixtures below: platform markup only, not real seller pages.
SYNTHETIC_BIGCOMMERCE = b"""<!-- SYNTHETIC (BigCommerce Cornerstone cards) -->
<html><body><ul class="productGrid">
<li><article class="card"><h4 class="card-title">
  <a href="https://evelta.com/33k-ohm-resistor-pack-of-10/">33K Ohm Resistor (Pack of 10)</a>
</h4></article></li>
<li><article class="card"><h4 class="card-title"><a href="/22uf-16v-capacitor/">22uF 16V</a></h4>
</article></li>
<li><a href="https://evelta.com/cart.php">Cart</a></li>
</ul></body></html>"""

SYNTHETIC_MAGENTO = b"""<!-- SYNTHETIC (Magento Luma product items) -->
<ol class="products"><li class="product-item"><strong class="product-item-name">
<a class="product-item-link" href="https://probots.co.in/ldr-5mm.html">LDR 5mm</a></strong></li>
<li><a href="https://probots.co.in/customer/account/">Account</a></li></ol>"""

SYNTHETIC_OPENCART = b"""<!-- SYNTHETIC (OpenCart default theme) -->
<div class="product-thumb"><div class="caption"><h4>
<a href="https://www.flyrobo.in/5mm-red-led">5mm Red LED</a></h4></div></div>
<div class="caption"><h4><a href="https://other.example/x">Elsewhere</a></h4></div>"""


def html_seller(domain, **search):
    entry = next(e for e in REGISTRY if e["domain"] == domain)
    host = (entry.get("search") or {}).get("host") or domain
    return {**entry, "host": host, "search": {**entry["search"], **search}}


def test_bigcommerce_magento_and_template_html_adapters_parse_product_links():
    page = lambda body: lambda url: Page(url, 200, HTML, body)  # noqa: E731
    big = seller_search.bigcommerce_html(
        page(SYNTHETIC_BIGCOMMERCE), html_seller("evelta.com"), "33k", 10
    )
    assert [c.url for c in big] == [
        "https://evelta.com/33k-ohm-resistor-pack-of-10/",
        "https://evelta.com/22uf-16v-capacitor/",
    ]
    assert big[0].title == "33K Ohm Resistor (Pack of 10)"
    magento = seller_search.magento_html(
        page(SYNTHETIC_MAGENTO), html_seller("probots.co.in"), "ldr", 10
    )
    assert [c.url for c in magento] == ["https://probots.co.in/ldr-5mm.html"]
    seen = []

    def fetch(url):
        seen.append(url)
        return Page(url, 200, HTML, SYNTHETIC_OPENCART)

    opencart = seller_search.html_template(fetch, html_seller("flyrobo.in"), "5mm led", 10)
    assert seen[0].endswith("search=5mm+led")
    assert [c.title for c in opencart] == ["5mm Red LED"]


def test_html_adapter_rejects_non_html_responses():
    with pytest.raises(ValueError):
        seller_search.magento_html(
            lambda url: Page(url, 404, HTML, b""), html_seller("probots.co.in"), "x", 5
        )


# --- queries, ranking, dedupe --------------------------------------------------------------


def test_query_variants_normalise_units_and_aliases():
    assert query_variants(["33kΩ resistor"]) == ["33k resistor"]
    assert query_variants(["22µF 16V electrolytic capacitor"]) == [
        "22uf 16v electrolytic capacitor",
        "22uf 16v capacitor",
    ]
    assert "ldr" in query_variants(["Light dependent resistor (LDR)"])
    assert query_variants(["10Ω resistor"]) == ["10 ohm resistor"]
    assert query_variants(["", "  "]) == []


def test_title_overlap_orders_but_never_drops_candidates():
    assert overlap("33k resistor", "33k Ohm Resistor - (Pack of 10)") == 1.0
    assert overlap("33k resistor", "330 Ohm Resistor") == 0.5
    robocraze = next(e for e in REGISTRY if e["domain"] == "robocraze.com")
    search = SellerSearch(quiet(), FixtureFetcher(), [robocraze])
    result = search.search(["22uf 16v capacitor"], limit_per_seller=10, total_budget=20)
    titles = [c.title for c in result.candidates]
    assert len(titles) == 10  # nothing rejected
    assert result.candidates[0].score >= result.candidates[-1].score


def test_merge_round_robins_sellers_and_dedupes_urls():
    a = [Candidate("https://a.in/p/1", "a.in", score=1), Candidate("https://a.in/p/2", "a.in")]
    b = [Candidate("https://www.a.in/p/1/", "b.in", score=1), Candidate("https://b.in/x", "b.in")]
    merged = merge([a, b], 10)
    assert [c.url for c in merged] == ["https://a.in/p/1", "https://a.in/p/2", "https://b.in/x"]
    assert len(merge([a, b], 2)) == 2


def test_search_runs_registry_sellers_and_reports_blocked_and_disallowed_hosts():
    fetcher = FixtureFetcher(
        {
            "thinkrobotics.com": Page("https://thinkrobotics.com/x", 403, HTML, CLOUDFLARE),
            "compoindia.com": FetchError("Robots policy prevents verification"),
        }
    )
    search = SellerSearch(quiet(), fetcher)
    result = search.search(query_variants(["33kΩ resistor"]), 5, 12)
    statuses = {d.seller: d.status for d in result.diagnostics}
    assert statuses["thinkrobotics.com"] == BLOCKED
    assert statuses["compoindia.com"] == "robots_disallowed"
    assert statuses["robocraze.com"] == statuses["quartzcomponents.com"] == "ok"
    assert len(result.candidates) <= 12
    assert {c.seller for c in result.candidates} >= {"robocraze.com", "quartzcomponents.com"}
    assert "robu.in" in result.blocked() and "thinkrobotics.com" in result.blocked()
    assert "blocked automated access" in result.message()
    # The blocked host is skipped (no request) on the next search during the cooldown.
    before = len(fetcher.calls)
    again = search.search(["ldr"], 5, 12)
    assert not any("thinkrobotics" in u for u in fetcher.calls[before:])
    assert {d.seller: d.status for d in again.diagnostics}["thinkrobotics.com"] == BLOCKED


def test_search_tries_a_second_query_only_when_the_first_finds_nothing():
    fetcher = FixtureFetcher()
    search = SellerSearch(quiet(), fetcher, [html_seller("zbotic.in")])
    result = search.search(["5mm led", "ldr"], 5, 12)
    assert [search_key(u)[1] for u in fetcher.calls] == ["5mm led", "ldr"]
    assert result.diagnostics[0].queries == ["5mm led", "ldr"]
    assert result.candidates and result.candidates[0].query == "ldr"


# --- politeness ----------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Scripted:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        page = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        return Page(url, page[0], page[1], page[2])


def polite(clock, **kw):
    return Politeness(clock=clock, sleep=clock.sleep, **kw)


def test_cache_serves_repeat_requests_until_ttl_expires():
    clock = Clock()
    politeness = polite(clock, search_ttl_s=60, page_ttl_s=10)
    fetcher = Scripted((200, JSON, b"[]"))
    politeness.get(fetcher, "https://a.in/s?q=1", kind="search")
    politeness.get(fetcher, "https://a.in/s?q=1", kind="search")
    assert fetcher.calls == 1
    clock.now += 61
    politeness.get(fetcher, "https://a.in/s?q=1", kind="search")
    assert fetcher.calls == 2
    # Product pages have their own, shorter lifetime; errors are never cached.
    pages = PoliteFetcher(Scripted((404, HTML, b""), (200, HTML, b"ok")), politeness)
    assert pages.get("https://a.in/p").status == 404
    assert pages.get("https://a.in/p").status == 200
    pages.get("https://a.in/p")
    assert pages.fetcher.calls == 2
    clock.now += 11
    pages.get("https://a.in/p")
    assert pages.fetcher.calls == 3


def test_backoff_honours_retry_after_and_gives_up_on_long_waits():
    clock = Clock()
    politeness = polite(clock, min_interval_s=0)
    fetcher = Scripted((429, {"retry-after": "3"}, b""), (200, JSON, b"[]"))
    assert politeness.get(fetcher, "https://a.in/x").status == 200
    assert clock.slept == [3.0]
    clock.slept.clear()
    fetcher = Scripted((503, {}, b""), (503, {}, b""), (200, JSON, b"[]"))
    assert politeness.get(fetcher, "https://b.in/x").status == 200
    assert clock.slept == [1.0, 2.0]
    clock.slept.clear()
    fetcher = Scripted((429, {"retry-after": "120"}, b""))
    assert politeness.get(fetcher, "https://c.in/x").status == 429
    assert fetcher.calls == 1 and clock.slept == []
    fetcher = Scripted((503, {}, b""))
    assert politeness.get(fetcher, "https://d.in/x").status == 503
    assert fetcher.calls == 3  # max_retries=2


def test_min_interval_spaces_requests_to_one_host():
    clock = Clock()
    politeness = polite(clock, min_interval_s=1.5)
    fetcher = Scripted((200, JSON, b"[]"))
    politeness.get(fetcher, "https://a.in/1")
    politeness.get(fetcher, "https://a.in/2")
    politeness.get(fetcher, "https://other.in/1")
    assert clock.slept == [1.5]


@pytest.mark.parametrize(
    "status, headers, body, expected",
    [
        (403, HTML, CLOUDFLARE, True),
        (200, {**HTML, "cf-mitigated": "challenge"}, b"<html></html>", True),
        (403, HTML, b'<div class="h-captcha" data-sitekey="x"></div>hcaptcha', True),
        (403, HTML, b"<h1>Access Denied</h1>errors.edgesuite.net Reference&#32;&#35;18", True),
        (403, HTML, b'<div id="px-captcha"></div>', True),
        (403, {**HTML, "x-datadome": "protected"}, b"blocked", True),
        (200, HTML, b'<form><div class="g-recaptcha"></div></form><h1>Contact us</h1>', False),
        (404, HTML, b"<title>Not found</title>", False),
        (200, JSON, b'{"products": []}', False),
    ],
)
def test_challenge_detection(status, headers, body, expected):
    assert (challenge_reason(Page("https://a.in/", status, headers, body)) is not None) == expected


def test_challenge_marks_host_blocked_for_a_cooldown_without_retrying():
    clock = Clock()
    politeness = polite(clock, blocked_cooldown_s=100)
    fetcher = Scripted((403, HTML, CLOUDFLARE), (200, JSON, b"[]"))
    with pytest.raises(BlockedError) as error:
        politeness.get(fetcher, "https://robu.in/")
    assert error.value.host == "robu.in"
    with pytest.raises(BlockedError):
        politeness.get(fetcher, "https://robu.in/other")
    assert fetcher.calls == 1
    assert politeness.blocked_hosts() == {"robu.in": "bot-protection challenge page"}
    clock.now += 101
    assert politeness.get(fetcher, "https://robu.in/other").status == 200


# --- staged sourcing -----------------------------------------------------------------------


def product_page(url, name, price="9.00", stock="InStock"):
    product = {
        "@type": "Product",
        "name": name,
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "INR",
            "availability": f"https://schema.org/{stock}",
        },
    }
    html = '<script type="application/ld+json">' + json.dumps(product) + "</script>"
    return Page(url, 200, HTML, html.encode())


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError("Page fetch failed")
        return self.pages[url]


class Discovery:
    def __init__(self, urls=(), fail=False):
        self.urls = list(urls)
        self.fail = fail
        self.calls = 0

    def discover(self, query):
        self.calls += 1
        if self.fail:
            raise DiscoveryError("failed")
        return SearchAttribution(source_urls=self.urls)


class FakeSearch(SellerSearch):
    def __init__(self, urls, blocked=()):
        super().__init__(quiet(), registry=[])
        self.urls = urls
        self.blocked_hosts = list(blocked)
        self.calls = []

    def search(self, queries, limit_per_seller=5, total_budget=12):
        self.calls.append(queries)
        candidates = [Candidate(u, urlsplit(u).hostname) for u in self.urls][:total_budget]
        diagnostics = [SellerDiagnostic("a.in", "ok", len(candidates))] + [
            SellerDiagnostic(h, BLOCKED) for h in self.blocked_hosts
        ]
        return SearchResult(queries, candidates, diagnostics)


LED = "5mm red LED"


def test_seller_offer_skips_paid_grounded_discovery():
    pages = Pages({"https://a.in/products/led": product_page("https://a.in/products/led", LED)})
    discovery = Discovery(["https://g.in/led"])
    search = FakeSearch(["https://a.in/products/led"])
    line = SourcingService(discovery, pages, seller_search=search).source(
        BomItem(line_id="L1", raw_name=LED)
    )
    assert line.sourcing_status == "offers_found"
    assert discovery.calls == 0
    assert line.stages == ["seller_search", "judge"]
    assert line.gemini_calls == 0
    assert line.attribution is None
    assert line.seller_search.candidate_urls == ["https://a.in/products/led"]
    assert search.calls == [["5mm red led", "5mm led"]]


def test_grounded_discovery_runs_when_seller_search_finds_no_acceptable_offer():
    url_g = "https://g.in/led"
    pages = Pages(
        {
            "https://a.in/p/oos": product_page("https://a.in/p/oos", LED, stock="OutOfStock"),
            url_g: product_page(url_g, LED),
        }
    )
    judged = []

    def judge(spec, offers):
        judged.append([str(o.url) for o in offers])
        return [JudgeVerdict("compatible") for _ in offers]

    discovery = Discovery([url_g, "https://a.in/p/oos"])
    line = SourcingService(
        discovery, pages, seller_search=FakeSearch(["https://a.in/p/oos"]), judge=judge
    ).source(BomItem(line_id="L1", raw_name=LED))
    assert discovery.calls == 1
    assert line.stages == ["seller_search", "judge", "grounded", "judge"]
    assert line.gemini_calls == 1
    # The second judge run sees only the new grounded offer; the old page is not refetched.
    assert judged == [["https://a.in/p/oos"], [url_g]]
    assert pages.calls.count("https://a.in/p/oos") == 1
    assert len(line.offers) == 2


def test_judge_rejection_triggers_grounded_and_failed_discovery_keeps_seller_offers():
    pages = Pages({"https://a.in/p/1": product_page("https://a.in/p/1", LED)})
    line = SourcingService(
        Discovery(fail=True),
        pages,
        seller_search=FakeSearch(["https://a.in/p/1"]),
        judge=lambda spec, offers: [JudgeVerdict("incompatible") for _ in offers],
    ).source(BomItem(line_id="L1", raw_name=LED))
    assert line.stages == ["seller_search", "judge", "grounded"]
    assert line.sourcing_status == "offers_found"


def test_no_offers_reports_blocked_sellers_in_the_diagnostic():
    line = SourcingService(
        Discovery([]), Pages({}), seller_search=FakeSearch(["https://a.in/p/x"], ["robu.in"])
    ).source(BomItem(line_id="L1", raw_name=LED))
    assert line.sourcing_status == "no_verified_offers"
    assert line.stages == ["seller_search", "grounded"]
    assert "robu.in blocked automated access" in line.sourcing_error.message
    assert line.seller_search.blocked_sellers == ["robu.in"]


def test_fetching_stops_after_three_in_stock_offers_from_two_sellers():
    urls = [f"https://{h}/p/{i}" for i, h in enumerate(["a.in", "a.in", "b.in", "b.in", "c.in"])]
    pages = Pages({u: product_page(u, LED) for u in urls})
    line = SourcingService(Discovery(), pages, seller_search=FakeSearch(urls)).source(
        BomItem(line_id="L1", raw_name=LED)
    )
    assert len(pages.calls) == 3 and len(line.offers) == 3


def test_challenge_on_a_product_page_is_reported_not_retried():
    class Challenged:
        calls = 0

        def get(self, url, **kwargs):
            Challenged.calls += 1
            return Page(url, 403, HTML, CLOUDFLARE)

    line = SourcingService(
        Discovery(["https://robu.in/product/x"]),
        Challenged(),
        seller_search=FakeSearch(["https://robu.in/product/y"]),
    ).source(BomItem(line_id="L1", raw_name=LED))
    assert Challenged.calls == 1  # second robu URL skipped during cooldown
    assert "robu.in" in line.seller_search.blocked_sellers


def test_identical_parts_in_a_job_are_sourced_once_and_owned_lines_skipped():
    pages = Pages({"https://a.in/p/1": product_page("https://a.in/p/1", LED)})
    search = FakeSearch(["https://a.in/p/1"])
    service = SourcingService(Discovery(), pages, seller_search=search)
    items = [
        BomItem(line_id="L1", raw_name=LED),
        BomItem(line_id="L2", raw_name="5mm  Red LED"),
        BomItem(line_id="L3", raw_name=LED, user_has_it=True),
    ]
    first = service.source_for_project(items[0], items)
    second = service.source_for_project(items[1], items)
    owned = service.source_for_project(items[2], items)
    assert len(search.calls) == 1 and len(pages.calls) == 1
    assert second.item.line_id == "L2" and second.offers[0].url == first.offers[0].url
    assert second.gemini_calls == 0
    assert owned.sourcing_status == "already_owned" and owned.stages == []
    # The same line again is a refresh: sourced fresh.
    service.source_for_project(items[0], items)
    assert len(search.calls) == 2


def test_without_seller_search_grounded_discovery_runs_first_as_before():
    url = "https://g.in/led"
    discovery = Discovery([url])
    line = SourcingService(discovery, Pages({url: product_page(url, LED)})).source(
        BomItem(line_id="L1", raw_name=LED)
    )
    assert discovery.calls == 1
    assert line.stages == ["grounded", "judge"] and line.gemini_calls == 1
    assert line.seller_search is None


def test_paid_budget_exhausted_skips_grounded_discovery(monkeypatch):
    from bharat_sourcer.sourcing import service

    monkeypatch.setattr(service, "paid_allowed", lambda: False)
    discovery = Discovery(["https://g.in/led"])
    line = SourcingService(discovery, Pages({}), seller_search=FakeSearch([])).source(
        BomItem(line_id="L1", raw_name=LED)
    )
    assert discovery.calls == 0 and line.gemini_calls == 0
    assert line.stages == ["seller_search"]
    assert service.BUDGET_MESSAGE in line.sourcing_error.message


class DictCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl_s):
        assert isinstance(value, dict) and ttl_s > 0
        self.values[key] = json.loads(json.dumps(value))


def test_shared_cache_is_used_across_politeness_instances():
    cache = DictCache()
    fetcher = FixtureFetcher()
    for _ in range(2):
        search = SellerSearch(
            Politeness(min_interval_s=0, cache=cache), fetcher, [html_seller("zbotic.in")]
        )
        result = search.search(["ldr"], 5, 5)
        assert result.candidates[0].url.startswith("https://zbotic.in/product/")
    assert len(fetcher.calls) == 1
    assert any(key.startswith("seller_search") for key in cache.values)


def test_rejected_seller_offers_do_not_stop_grounded_fetching():
    urls = [f"https://{h}/p/{i}" for i, h in enumerate(["a.in", "a.in", "b.in"])]
    grounded = "https://g.in/led"
    pages = Pages({u: product_page(u, LED) for u in [*urls, grounded]})

    def judge(spec, offers):
        return [JudgeVerdict("compatible" if "g.in" in str(o.url) else "wrong") for o in offers]

    line = SourcingService(
        Discovery([grounded]), pages, seller_search=FakeSearch(urls), judge=judge
    ).source(BomItem(line_id="L1", raw_name=LED))
    assert grounded in pages.calls and len(line.offers) == 4
