"""Offline regression checks; all seller pages and prices are synthetic."""

from types import SimpleNamespace

from test_sourcing import PRODUCT, URL, page

from bharat_sourcer.schemas import BomItem, PartResearch, SearchAttribution
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import Politeness, challenge_reason
from bharat_sourcer.sourcing.service import DiscoveryError, SourcingService
from bharat_sourcer.sourcing.trust import TrustChecker


class Discovery:
    def discover(self, query):
        raise DiscoveryError("offline failure")


class Catalogue:
    def __init__(self):
        self.politeness = Politeness(min_interval_s=0)

    def search(self, queries, *args):
        return SimpleNamespace(
            candidates=[SimpleNamespace(url=URL)],
            queries=list(queries),
            diagnostics=[],
            blocked=lambda: [],
            message=lambda: "Synthetic catalogue",
        )


def test_discovery_failure_preserves_free_pages_and_research():
    observed = []

    class Fetch:
        def get(self, url, **kwargs):
            return Page(url, 200, {"content-type": "text/html"}, b"<h1>TTP223</h1>")

    class Research:
        def research(self, item, pages, sources, *args):
            observed.extend(pages)
            return PartResearch(status="no_evidence", summary="Synthetic page", sources=sources)

    result = SourcingService(Discovery(), Fetch(), Research(), seller_search=Catalogue()).source(
        BomItem(line_id="L1", raw_name="TTP223")
    )
    assert observed and result.research.sources
    assert result.sourcing_status == "no_verified_offers"
    assert result.sourcing_error.code == "DISCOVERY_FAILED"
    assert "catalogue results were kept" in result.sourcing_error.message


def test_url_exception_isolated_and_identity_added(monkeypatch):
    class Discover:
        def discover(self, query):
            return SearchAttribution(source_urls=["https://broken.example/p/x", URL])

    class Fetch:
        def get(self, url, **kwargs):
            if "broken" in url:
                raise RuntimeError("parser bug")
            return page()

    monkeypatch.setattr("bharat_sourcer.sourcing.service.assess_offer", lambda *a: 1 / 0)
    monkeypatch.setattr("bharat_sourcer.sourcing.service.page_images", lambda *a: 1 / 0)
    result = SourcingService(Discover(), Fetch()).source(BomItem(line_id="L1", raw_name="TTP223"))
    assert len(result.offers) == 1
    assert result.offers[0].seller_kind == "direct"
    assert result.offers[0].seller_domain == "seller.example"


def test_challenge_detection_without_catalogue_search():
    for marker in (b"sucuri_cloudproxy", b"_Incapsula_Resource"):
        assert challenge_reason(Page(URL, 200, {}, marker))


def test_platform_store_does_not_inherit_domain_age():
    class Fetch:
        def get(self, url, **kwargs):
            raise AssertionError("No RDAP request for a hosted store")

    signals = TrustChecker(Fetch())._check("smallshop.myshopify.com", []).signals
    assert signals.domain == "smallshop.myshopify.com"
    assert signals.domain_age_days is None
    assert "domain_age" in signals.unavailable


def test_marketplace_trust_does_not_verify_merchant():
    class Fetch:
        def get(self, url, **kwargs):
            return Page(url, 404, {}, b"")

    from bharat_sourcer.sourcing.listings import verify_page

    offer = verify_page(page(PRODUCT, "https://amazon.in/dp/synthetic"))
    TrustChecker(Fetch()).label_offers([offer], [])
    assert offer.trust.label == "unverified"
    assert "third-party merchant" in offer.trust.reasons[0]


def test_policy_redirect_home_is_not_evidence():
    class Fetch:
        def get(self, url, **kwargs):
            return Page(
                "https://store.example/",
                200,
                {"content-type": "text/html"},
                b"return shipping contact " * 30,
            )

    product = Page(
        "https://store.example/p/x",
        200,
        {"content-type": "text/html"},
        b'<a href="/returns">Returns</a>',
    )
    signals = TrustChecker(Fetch())._check("store.example", [product]).signals
    assert signals.policies == []


def test_shared_page_ttl_respects_configuration_and_unparsed_search_not_cached():
    writes = []

    class Cache:
        def get(self, key):
            return None

        def set(self, key, value, ttl):
            writes.append(ttl)

    class Fetch:
        def get(self, url, **kwargs):
            return page()

    polite = Politeness(min_interval_s=0, page_ttl_s=15, cache=Cache())
    polite.get(Fetch(), URL)
    assert writes == [15]
    polite.get(Fetch(), URL + "?q=one", kind="search")
    assert writes == [15]


def test_exhausted_budget_keeps_free_catalogue_search(monkeypatch):
    monkeypatch.setattr("bharat_sourcer.sourcing.service.paid_allowed", lambda: False)

    class Fetch:
        def get(self, url, **kwargs):
            return page()

    result = SourcingService(Discovery(), Fetch(), seller_search=Catalogue()).source(
        BomItem(line_id="L1", raw_name="TTP223")
    )
    assert result.offers and result.gemini_calls == 0
    assert "seller_search" in result.stages and "grounded" not in result.stages


def test_failed_judge_keeps_deterministic_shortcut():
    from test_judge import LDR, PROJECT, Model, candidate

    from bharat_sourcer.sourcing.judge import review_candidates

    model = Model()
    offers = review_candidates(
        LDR,
        PROJECT,
        [candidate("zbotic_ldr_5mm_pack10.html"), candidate("sharvi_cap_22uf_16v.html")],
        model.judge(),
    )
    assert offers[0].match.method == "deterministic_shortcut"


def test_canonical_tracking_urls_are_fetched_once():
    calls = []

    class Discover:
        def discover(self, query):
            return SearchAttribution(source_urls=[URL + "?utm_source=a", URL + "?utm_source=b"])

    class Fetch:
        def get(self, url, **kwargs):
            calls.append(url)
            return page()

    result = SourcingService(Discover(), Fetch()).source(BomItem(line_id="L1", raw_name="TTP223"))
    assert calls == [URL]
    assert len(result.offers) == 1


def test_single_variant_candidate_survives_for_judge():
    from bharat_sourcer.sourcing.matching import build_candidate

    product = {
        **PRODUCT,
        "offers": {
            **PRODUCT["offers"],
            "url": URL + "?variant=12",
            "name": "Blue variant",
        },
    }
    candidate = build_candidate(page(product), None)
    assert candidate is not None
    assert candidate.listing(0)["variants"][0]["name"] == "Blue variant"
    assert candidate.extracted is not None
