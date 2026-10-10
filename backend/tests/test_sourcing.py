import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import BomItem, ConfirmJob, CreateJob, PartSpecs, SearchAttribution, now
from bharat_sourcer.sourcing.fetch import (
    FetchError,
    Page,
    SafeFetcher,
    public_addresses,
    validate_url,
)
from bharat_sourcer.sourcing.listings import verify_page
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService, resolve_part
from bharat_sourcer.storage import MemoryJobStore

URL = "https://seller.example/products/ttp223"
PRODUCT = {
    "@type": "Product",
    "name": "TTP223 Capacitive Touch Sensor Module",
    "offers": {
        "@type": "Offer",
        "price": "25.50",
        "priceCurrency": "INR",
        "availability": "https://schema.org/InStock",
    },
}


def page(product=PRODUCT, url=URL):
    html = '<script type="application/ld+json">' + json.dumps(product) + "</script>"
    return Page(url, 200, {"content-type": "text/html; charset=utf-8"}, html.encode())


def test_verified_offer_has_no_invented_safety_or_cost_claims():
    offer = verify_page(page(), "TTP223 touch sensor module")
    assert offer.price_inr == "25.50"
    assert offer.stock == "in_stock"
    assert offer.seller_trust == "unverified"
    assert offer.tax_included is None
    assert offer.compatibility_status == "not_checked"


@pytest.mark.parametrize(
    "image, expected",
    [
        ("https://cdn.seller.example/ttp223.webp", "https://cdn.seller.example/ttp223.webp"),
        (
            [{"@type": "ImageObject", "url": "/images/ttp223.png"}],
            "https://seller.example/images/ttp223.png",
        ),
        ("http://seller.example/logo.png", None),
        ("//seller.example/logo.png", "https://seller.example/logo.png"),
        ("javascript:alert(1)", None),
        ({"url": "https://user:pass@seller.example/p.png"}, None),
        (None, None),
    ],
)
def test_product_image_is_optional_and_limited_to_safe_https_urls(image, expected):
    product = {**PRODUCT, "image": image}
    offer = verify_page(page(product), "TTP223")
    assert (str(offer.image_url) if offer.image_url else None) == expected
    # Image metadata must never change whether the seller offer itself verifies.
    assert offer.price_inr == "25.50"


@pytest.mark.parametrize(
    "change",
    [
        {"priceCurrency": "USD"},
        {"price": "nan"},
        {"price": "-10"},
        {"price": "25.555"},
        {"@type": "AggregateOffer"},
        {"url": URL + "?variant=other"},
    ],
)
def test_reject_ambiguous_or_invalid_offer(change):
    product = {**PRODUCT, "offers": {**PRODUCT["offers"], **change}}
    assert verify_page(page(product), "TTP223") is None


def test_reject_category_page_and_wrong_part():
    # Duplicate theme/SEO declarations describe one product; distinct products are a list.
    assert verify_page(page([PRODUCT, PRODUCT]), "TTP223") is not None
    other = {**PRODUCT, "name": "A different product"}
    assert verify_page(page([PRODUCT, other]), "TTP223") is None
    assert verify_page(page(), "TTP224") is None
    assert verify_page(page({**PRODUCT, "offers": [PRODUCT["offers"]] * 2}), "TTP223") is None


def test_unknown_stock_stays_unknown():
    product = {**PRODUCT, "offers": {**PRODUCT["offers"], "availability": "not specified"}}
    assert verify_page(page(product), "TTP223").stock == "unknown"


@pytest.mark.parametrize(
    "url",
    [
        "http://seller.example/x",
        "file:///etc/passwd",
        "https://user:pass@seller.example/x",
        "https://seller.example:8080/x",
    ],
)
def test_unsafe_url_rejected(url):
    with pytest.raises(FetchError):
        validate_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
def test_private_dns_rejected(address):
    with (
        patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", (address, 443))]),
        pytest.raises(FetchError),
    ):
        public_addresses("seller.example")


def test_redirect_rechecks_robots_before_fetching_destination():
    fetcher = SafeFetcher()
    with (
        patch.object(fetcher, "_allowed", side_effect=[True, False]),
        patch.object(
            fetcher,
            "_request",
            return_value=Page(URL, 302, {"location": "https://other.example/x"}, b""),
        ) as request,
    ):
        with pytest.raises(FetchError, match="Robots"):
            fetcher.get(URL)
        assert request.call_count == 1


def test_robot_disallow_and_long_delay_are_respected():
    for policy in [b"User-agent: *\nDisallow: /", b"User-agent: *\nCrawl-delay: 10"]:
        fetcher = SafeFetcher()
        with patch.object(
            fetcher,
            "_request",
            return_value=Page("https://seller.example/robots.txt", 200, {}, policy),
        ) as request:
            with pytest.raises(FetchError):
                fetcher.get(URL)
            assert request.call_count == 1


@pytest.mark.parametrize("finish_reason", ["STOP", "MAX_TOKENS"])
def test_discovery_uses_grounding_metadata_not_generated_urls(finish_reason):
    def handle(request):
        payload = json.loads(request.content)
        assert payload["tools"] == [{"google_search": {}}]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": finish_reason,
                        "content": {"parts": [{"text": "https://invented.example"}]},
                        "groundingMetadata": {
                            "groundingChunks": [{"web": {"uri": URL}}],
                            "webSearchQueries": ["TTP223 buy India"],
                            "searchEntryPoint": {
                                "renderedContent": "<div>Search suggestions</div>"
                            },
                        },
                    }
                ]
            },
        )

    discovery = GeminiDiscovery(
        Settings(_env_file=None, gemini_api_key="test"), httpx.MockTransport(handle)
    )
    result = discovery.discover("TTP223")
    assert result.source_urls == [URL]
    assert result.search_suggestions_html is not None


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", "RECITATION"])
def test_truncated_without_grounding_or_blocked_discovery_is_rejected(finish_reason):
    from bharat_sourcer.sourcing.service import DiscoveryError

    candidate = {
        "finishReason": finish_reason,
        "content": {"parts": [{"text": "https://invented.example"}]},
    }
    if finish_reason != "MAX_TOKENS":
        candidate["groundingMetadata"] = {"groundingChunks": [{"web": {"uri": URL}}]}
    discovery = GeminiDiscovery(
        Settings(_env_file=None, gemini_api_key="test"),
        httpx.MockTransport(lambda request: httpx.Response(200, json={"candidates": [candidate]})),
    )
    with pytest.raises(DiscoveryError):
        discovery.discover("33k resistor")


def test_resolution_flags_unknown_variants():
    assert (
        "logic_v" in resolve_part(BomItem(line_id="L01", raw_name="Pro Micro board")).missing_specs
    )
    assert (
        "controller"
        in resolve_part(BomItem(line_id="L02", raw_name="I2C OLED display")).missing_specs
    )


class Discovery:
    calls = 0

    def discover(self, query):
        self.calls += 1
        return SearchAttribution(source_urls=[URL])


class Fetcher:
    def get(self, url):
        return page()


def test_owned_parts_skip_network_and_verified_results_survive():
    discovery = Discovery()
    service = SourcingService(discovery, Fetcher())
    assert (
        service.source(BomItem(line_id="L01", raw_name="TTP223", user_has_it=True)).sourcing_status
        == "already_owned"
    )
    assert discovery.calls == 0
    result = service.source(BomItem(line_id="L01", raw_name="TTP223"))
    assert result.sourcing_status == "offers_found"
    assert len(result.offers) == 1
    assert result.offers[0].compatibility_status == "unknown"
    assert result.offers[0].compatibility.grade is None


@pytest.mark.parametrize("mode, grade", [("momentary", "A"), ("toggle", "X")])
def test_sourcing_assesses_seller_properties_and_preserves_evidence(mode, grade):
    # Synthetic seller data exercises the pipeline; these are not verified module specs.
    specs = PartSpecs(
        family="ttp223",
        controller="ttp223",
        interface="digital",
        logic_v=3.3,
        supply_min_v=2.0,
        supply_max_v=5.5,
        pinout="GND,IO,VCC",
        output_mode="momentary",
        active_level="high",
    )
    seller_values = specs.model_dump(exclude_none=True) | {"output_mode": mode}
    product = PRODUCT | {
        "additionalProperty": [
            {"@type": "PropertyValue", "name": field, "value": value}
            for field, value in seller_values.items()
        ]
    }
    with patch.object(Fetcher, "get", return_value=page(product)):
        result = SourcingService(Discovery(), Fetcher()).source(
            BomItem(line_id="L01", raw_name="TTP223", specs=specs)
        )
    offer = result.offers[0]
    assert offer.compatibility.grade == grade
    assert offer.compatibility_status == ("compatible" if grade == "A" else "incompatible")
    assert URL in offer.compatibility.references
    assert any(
        evidence.field == "output_mode"
        and evidence.source == "seller_property"
        and evidence.locator == URL
        for evidence in offer.spec_evidence
    )
    assert result.grade is None


def test_job_sourcing_limit_checkpoints_and_recovery():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id=f"L{i:02d}", raw_name="TTP223") for i in range(1, 3)]

    discovery = Discovery()
    store = MemoryJobStore()
    service = JobService(
        Extractor(),
        store=store,
        sourcing=SourcingService(discovery, Fetcher()),
        sourcing_max_parts=1,
    )
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    result = service.get(job.job_id, token)
    assert result.status == "done"
    assert result.report.lines[0].sourcing_status == "offers_found"
    assert result.report.lines[1].sourcing_error.code == "SOURCING_LIMIT"
    assert result.report.total_inr is None
    assert discovery.calls == 1
    service.finish(job.job_id)
    assert discovery.calls == 1

    def interrupted(record):
        record.job.recovery_attempts = 1
        record.job.status = "sourcing"
        record.run_id = "old"
        record.lease_until = now() - timedelta(seconds=1)

    store.mutate(job.job_id, interrupted)
    service.recover()
    assert service.get(job.job_id, token).error.code == "SOURCING_INTERRUPTED"
    assert len(service.get(job.job_id, token).report.lines) == 2
    assert discovery.calls == 1


def test_sourcing_claim_and_expiry_reject_late_result():
    started, release = Event(), Event()

    class SlowDiscovery(Discovery):
        def discover(self, query):
            self.calls += 1
            started.set()
            assert release.wait(5)
            return SearchAttribution(source_urls=[URL])

    class Extractor:
        def extract(self, url):
            return [BomItem(line_id="L01", raw_name="TTP223")]

    discovery = SlowDiscovery()
    store = MemoryJobStore()
    first = JobService(Extractor(), store=store, sourcing=SourcingService(discovery, Fetcher()))
    second = JobService(Extractor(), store=store, sourcing=SourcingService(discovery, Fetcher()))
    job, token = first.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    first.extract(job.job_id)
    first.confirm(job.job_id, token, ConfirmJob())
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(first.finish, job.job_id)
        try:
            assert started.wait(5)
            second.finish(job.job_id)
            assert second.get(job.job_id, token).status == "sourcing"

            def expire(record):
                record.job.recovery_attempts = 1
                record.lease_until = now() - timedelta(seconds=1)

            store.mutate(job.job_id, expire)
            second.recover()
        finally:
            release.set()
        running.result(timeout=5)
    result = second.get(job.job_id, token)
    assert discovery.calls == 1
    assert result.status == "failed"
    assert result.error.code == "SOURCING_INTERRUPTED"
    assert result.report.lines == []


def test_failed_and_empty_discovery_are_distinct():
    discovery = GeminiDiscovery(
        Settings(_env_file=None, gemini_api_key="test"),
        httpx.MockTransport(lambda request: httpx.Response(429)),
    )
    item = BomItem(line_id="L01", raw_name="TTP223")
    assert SourcingService(discovery, Fetcher()).source(item).sourcing_status == "failed"

    class EmptyDiscovery:
        def discover(self, query):
            return SearchAttribution()

    assert (
        SourcingService(EmptyDiscovery(), Fetcher()).source(item).sourcing_status
        == "no_verified_offers"
    )


def test_discovery_gives_indian_retail_pages_the_limited_fetch_slots():
    titles = ["tti.com", "mouser.com", "example.org", "robocraze.com", "www.flyrobo.in"]
    chunks = [{"web": {"uri": f"https://{t}/p{i}", "title": t}} for i, t in enumerate(titles)]
    chunks.append({"web": {"uri": "https://untitled.example/x"}})
    candidate = {"finishReason": "STOP", "groundingMetadata": {"groundingChunks": chunks}}
    discovery = GeminiDiscovery(
        Settings(_env_file=None, gemini_api_key="test", sourcing_candidates_per_part=4),
        httpx.MockTransport(lambda request: httpx.Response(200, json={"candidates": [candidate]})),
    )
    assert discovery.discover("LED").source_urls == [
        "https://robocraze.com/p3",
        "https://www.flyrobo.in/p4",
        "https://example.org/p2",
        "https://untitled.example/x",
    ]
