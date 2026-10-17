import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem, SearchAttribution
from bharat_sourcer.sourcing.coordination import HostDeferred, MemoryCoordinator
from bharat_sourcer.sourcing.fetch import Page, SafeFetcher
from bharat_sourcer.sourcing.politeness import BlockedError, Politeness
from bharat_sourcer.sourcing.providers import ProviderSearch, mouser_page
from bharat_sourcer.sourcing.service import SourcingService


class Fetch:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return Page(url, self.status, self.headers, b"ok")


def test_atomic_reservations_across_workers():
    coordinator = MemoryCoordinator(clock=lambda: 100)
    with ThreadPoolExecutor(max_workers=5) as pool:
        waits = list(pool.map(lambda _: coordinator.acquire("a.in", 1), range(5)))
    assert sorted(waits) == [0, 1, 2, 3, 4]
    assert coordinator.acquire("b.in", 1) == 0
    with pytest.raises(HostDeferred, match="host_queue_full"):
        coordinator.acquire("a.in", 1, max_wait=2)


def test_new_robots_interval_applies_to_first_product_request():
    coordinator = MemoryCoordinator(clock=lambda: 100)
    assert coordinator.acquire("a.in", 1) == 0  # robots request
    assert coordinator.acquire("a.in", 5) == 5  # newly read crawl-delay


def test_firestore_state_is_shared_between_coordinators(monkeypatch):
    from google.cloud import firestore

    from bharat_sourcer.sourcing.coordination import FirestoreCoordinator

    records = {}

    class Ref:
        def __init__(self, key):
            self.key = key

        def get(self, transaction=None):
            return self

        def to_dict(self):
            return records.get(self.key)

    class Client:
        def collection(self, name):
            assert name == "jobs_seller_hosts"
            return self

        def document(self, key):
            assert "a.in" not in key
            return Ref(key)

        def transaction(self):
            return self

        def set(self, ref, state):
            records[ref.key] = state

    monkeypatch.setattr(firestore, "transactional", lambda function: function)
    first, second = (FirestoreCoordinator(Client(), "jobs") for _ in range(2))
    assert first.acquire("a.in", 5) == 0
    assert second.acquire("a.in", 5) > 4
    first.defer("a.in", 120, "rate_limited")
    second.defer("a.in", 1, "shorter")
    assert second.reason("a.in") == "rate_limited"
    with pytest.raises(HostDeferred):
        second.acquire("a.in", 1)


def test_cooldowns_cross_instances_keep_unexpired_cache_and_do_not_extend_it():
    now = [100.0]
    coordinator = MemoryCoordinator(clock=lambda: now[0])
    first = Politeness(coordinator=coordinator, min_interval_s=0)
    second = Politeness(coordinator=coordinator, clock=lambda: now[0], page_ttl_s=10)
    fetch = Fetch()
    second.get(fetch, "https://a.in/p")
    first.mark_blocked("a.in", "Cloudflare challenge")
    assert second.get(fetch, "https://a.in/p").body == b"ok"
    with pytest.raises(BlockedError):
        second.get(fetch, "https://a.in/p", bypass_cache=True)
    now[0] += 11
    with pytest.raises(BlockedError):
        second.get(fetch, "https://a.in/p")
    assert fetch.calls == 1


def test_long_retry_after_stops_other_instances_without_network():
    coordinator = MemoryCoordinator()
    first = Politeness(coordinator=coordinator)
    second = Politeness(coordinator=coordinator)
    fetch = Fetch(429, {"retry-after": "120"})
    assert first.get(fetch, "https://a.in/p").status == 429
    with pytest.raises(HostDeferred, match="rate_limited"):
        second.get(fetch, "https://a.in/other")
    assert fetch.calls == 1


def test_robots_delay_is_scheduled_and_large_delay_is_distinguished():
    for seconds in (5, 60):
        fetcher = SafeFetcher()
        policy = f"User-agent: *\nCrawl-delay: {seconds}"
        with patch.object(
            fetcher,
            "_request",
            return_value=Page("https://a.in/robots.txt", 200, {}, policy.encode()),
        ):
            if seconds > 10:
                with pytest.raises(HostDeferred, match="crawl_delay_exceeds_worker_budget"):
                    fetcher._allowed("https://a.in/product")
            else:
                assert fetcher._allowed("https://a.in/product")
            assert fetcher._intervals["a.in"] == seconds


def test_robots_challenge_is_not_reported_as_disallow():
    fetcher = SafeFetcher(coordinator=MemoryCoordinator())
    with (
        patch.object(
            fetcher,
            "_request",
            return_value=Page("https://a.in/robots.txt", 403, {"cf-mitigated": "challenge"}, b""),
        ),
        pytest.raises(BlockedError),
    ):
        fetcher.get("https://a.in/product")
    assert fetcher.coordinator.reason("a.in") == "Cloudflare challenge"


def settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def part(**kwargs):
    return {
        "ProductDetailUrl": "https://www.mouser.in/ProductDetail/TI/NE555P",
        "ManufacturerPartNumber": "NE555P",
        "Description": "NE555P Timer DIP-8",
        "Min": "1",
        "Mult": "1",
        "AvailabilityInStock": "100",
        "PriceBreaks": [{"Quantity": 1, "Price": "25.00", "Currency": "INR"}],
        **kwargs,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"Min": "10"},
        {"Mult": "5"},
        {"RestrictionMessage": "not available"},
        {"PriceBreaks": [{"Quantity": 100, "Price": "2.00", "Currency": "INR"}]},
        {"PriceBreaks": [{"Quantity": 1, "Price": "2.00", "Currency": "USD"}]},
        {"ProductDetailUrl": "https://mouser.in.evil.example/p"},
    ],
)
def test_mouser_does_not_invent_single_unit_inr_offer(change):
    assert mouser_page(part(**change)) is None


def test_provider_errors_are_isolated_and_urls_are_filtered():
    calls = []

    def handle(request):
        calls.append(request)
        if "shopify" in request.url.host:
            return httpx.Response(503, headers={"retry-after": "120"})
        if "brave" in request.url.host:
            assert request.url.params["country"] == "IN"
            assert request.url.params["spellcheck"] == "false"
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"url": "https://localhost/p"},
                            {"url": "file:///secret"},
                            {"url": "https://a.in/product", "title": "NE555P"},
                        ]
                    }
                },
            )
        return httpx.Response(200, json={"SearchResults": {"Parts": [part()]}})

    search = ProviderSearch(
        settings(
            shopify_catalog_enabled=True,
            shopify_catalog_profile="https://example.com/profile.json",
            brave_search_api_key="brave-secret",
            mouser_search_api_key="mouser-secret",
        ),
        transport=httpx.MockTransport(handle),
        sleep=lambda _: None,
    )
    result = search.search("NE555P")
    assert len(result.candidates) == 2
    assert [d.status for d in result.diagnostics] == ["http_error", "ok", "ok"]
    assert len(result.pages) == 1
    search.search("NE555P")
    assert len([r for r in calls if "shopify" in r.url.host]) == 1


@pytest.mark.parametrize("sse", [False, True])
def test_shopify_protocol_and_no_response_cache(sse):
    calls = []

    def handle(request):
        payload = json.loads(request.content)
        args = payload["params"]["arguments"]
        assert args["catalog"]["filters"]["ships_to"] == {"country": "IN"}
        assert args["meta"]["ucp-agent"]["profile"] == "https://example.com/profile.json"
        calls.append(request)
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "structuredContent": {
                    "products": [
                        {"title": "ESP32", "variants": [{"url": "https://a.in/products/esp32"}]}
                    ]
                }
            },
        }
        if sse:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="event: message\ndata: " + json.dumps(data) + "\n\n",
            )
        return httpx.Response(200, json=data)

    search = ProviderSearch(
        settings(
            shopify_catalog_enabled=True, shopify_catalog_profile="https://example.com/profile.json"
        ),
        transport=httpx.MockTransport(handle),
        sleep=lambda _: None,
    )
    assert len(search.search("ESP32").candidates) == 1
    assert len(search.search("ESP32").candidates) == 1
    assert len(calls) == 2


def test_mouser_offer_survives_blocked_html_and_passes_existing_matcher():
    class NoHTML:
        def get(self, url, **kwargs):
            pytest.fail("Mouser's API evidence should not require its HTML page")

    class NoDiscovery:
        def discover(self, query):
            return SearchAttribution()

    providers = ProviderSearch(
        settings(mouser_search_api_key="test-secret"),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"SearchResults": {"Parts": [part()]}})
        ),
    )
    service = SourcingService(NoDiscovery(), fetcher=NoHTML(), providers=providers)
    result = service.source(BomItem(line_id="L1", raw_name="NE555P Timer DIP-8"))
    assert result.offers
    assert result.offers[0].price_inr == "25.00"
    assert result.offers[0].verification == "seller_product_api"
    assert result.offers[0].stock == "in_stock"


def test_unconfigured_providers_make_no_requests():
    def handle(request):
        pytest.fail("Providers must be opt-in")

    assert (
        not ProviderSearch(settings(), transport=httpx.MockTransport(handle))
        .search("ESP32")
        .candidates
    )
