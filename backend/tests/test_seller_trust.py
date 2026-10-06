"""Seller trust labels: offline checks with fake fetchers and recorded RDAP fixtures.

RDAP fixtures in fixtures/storefront are trimmed real responses (source URL and date in
each file). Synthetic shops below use reserved example domains; their GSTIN is the public
GSTN format example, not a real seller's registration.
"""

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from bharat_sourcer.schemas import BomItem, SearchAttribution, TrustSignals, VerifiedOffer
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.sourcing.trust import (
    TrustChecker,
    decide,
    find_gstin,
    gstin_valid,
    mark_price_anomalies,
    policy_links,
    rdap_url,
    registrable_domain,
    registration_date,
)

FIXTURES = Path(__file__).parent / "fixtures" / "storefront"
HTML = {"content-type": "text/html; charset=utf-8"}
RDAP = {"content-type": "application/rdap+json"}
NOW = datetime(2026, 10, 6, tzinfo=UTC)
EXAMPLE_GSTIN = "27AAPFU0939F1ZV"
SHOP = "https://newshop.example.in"


class Fetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls: list[tuple[str, bool]] = []
        self.lock = threading.Lock()

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        with self.lock:
            self.calls.append((url, robots))
        result = self.pages.get(url)
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        return result or Page(url, 404, HTML, b"")


def rdap_page(url, registered: datetime) -> Page:
    data = {
        "ldhName": "x",
        "events": [{"eventAction": "registration", "eventDate": str(registered)}],
    }
    return Page(url, 200, RDAP, json.dumps(data).encode())


def html(url, body: str) -> Page:
    return Page(url, 200, HTML, body.encode())


def offer(url, price="100.00") -> VerifiedOffer:
    return VerifiedOffer(url=url, seller=urlsplit(url).hostname, title="x", price_inr=price)


def checker(fetcher, **kwargs) -> TrustChecker:
    return TrustChecker(fetcher, clock=lambda: NOW, **kwargs)


@pytest.mark.parametrize(
    "value, valid",
    [
        (EXAMPLE_GSTIN, True),
        ("27AAPFU0939F1ZW", False),  # wrong check character
        ("27aapfu0939f1zv", False),
        ("40AAPFU0939F1ZV", False),  # no such state code
        ("27AAPFU0939F1Z", False),
    ],
)
def test_gstin_checksum(value, valid):
    assert gstin_valid(value) is valid


def test_find_gstin_skips_invalid_candidates():
    text = "GSTIN: 27AAPFU0939F1ZW <footer>GST No. 27AAPFU0939F1ZV</footer>"
    assert find_gstin(text) == EXAMPLE_GSTIN
    assert find_gstin("X27AAPFU0939F1ZV") is None


@pytest.mark.parametrize(
    "host, domain, rdap",
    [
        ("www.robocraze.com", "robocraze.com", "https://rdap.org/domain/robocraze.com"),
        ("robu.in", "robu.in", "https://rdap.nixiregistry.in/rdap/domain/robu.in"),
        (
            "shop.example.co.in",
            "example.co.in",
            "https://rdap.nixiregistry.in/rdap/domain/example.co.in",
        ),
        ("in.element14.com", "element14.com", "https://rdap.org/domain/element14.com"),
    ],
)
def test_registrable_domain_and_rdap_endpoint(host, domain, rdap):
    assert registrable_domain(host) == domain
    assert rdap_url(domain) == rdap


@pytest.mark.parametrize(
    "name, expected",
    [
        ("rdap_com_robocraze.json", datetime(2014, 6, 30, 9, 53, 53, tzinfo=UTC)),
        ("rdap_in_robu.json", datetime(2012, 5, 11, 1, 2, 58, 93000, tzinfo=UTC)),
    ],
)
def test_registration_date_from_recorded_rdap(name, expected):
    data = json.loads((FIXTURES / name).read_text("utf-8"))["response"]
    assert registration_date(data) == expected


def test_policy_links_same_host_only():
    page = html(
        SHOP + "/products/a",
        '<a href="/pages/refund-policy">Refunds</a><a href="/shipping">Shipping info</a>'
        '<a href="https://other.example/contact">Contact</a>'
        '<a href="/pages/reach-us">Contact us</a>',
    )
    assert policy_links(page) == {
        "returns": SHOP + "/pages/refund-policy",
        "shipping": SHOP + "/shipping",
        "contact": SHOP + "/pages/reach-us",
    }


def signals(**values) -> TrustSignals:
    return TrustSignals(**({"domain": "newshop.example.in", "https": True} | values))


ALL = ["returns", "shipping", "contact"]


@pytest.mark.parametrize(
    "values, label, new",
    [
        ({"domain": "robocraze.com", "known_seller": True}, "established", False),
        ({"domain_age_days": 800, "gstin": EXAMPLE_GSTIN, "policies": ALL}, "established", False),
        ({"domain_age_days": 800, "gstin": EXAMPLE_GSTIN}, "verified_basics", False),
        ({"domain_age_days": 10, "gstin": EXAMPLE_GSTIN}, "verified_basics", True),
        ({"domain_age_days": 200, "policies": ALL}, "verified_basics", True),
        ({"domain_age_days": 10, "policies": ALL}, "unverified", True),
        ({"domain_age_days": 2000}, "unverified", False),
        ({"https": False, "gstin": EXAMPLE_GSTIN, "policies": ALL}, "unverified", False),
        ({"unavailable": ["all"]}, "unverified", False),
    ],
)
def test_labels(values, label, new):
    trust = decide(signals(**values))
    assert (trust.label, trust.new_seller) == (label, new)
    assert trust.reasons


def test_unavailable_checks_are_reasons_not_failures():
    trust = decide(signals(unavailable=["all"]))
    assert "Trust checks unavailable (timed out or failed)" in trust.reasons
    assert not any("No GSTIN" in reason for reason in trust.reasons)


def test_price_anomaly_flags_without_hiding():
    offers = [
        offer(f"{SHOP}/p/{i}", price) for i, price in enumerate(["100.00", "110.00", "30.00"])
    ]
    assert mark_price_anomalies(offers) == {f"{SHOP}/p/2"}
    assert mark_price_anomalies(offers[1:]) == set()  # needs two other offers
    trust = decide(signals(domain_age_days=900, price_anomaly=True))
    assert any(reason.startswith("Unusually cheap") for reason in trust.reasons)


def new_shop_pages(registered=NOW - timedelta(days=20)):
    product = html(
        SHOP + "/products/oled",
        '<footer><a href="/pages/returns">Returns</a><a href="/pages/shipping">Shipping</a>'
        '<a href="/pages/contact">Contact</a></footer>',
    )
    filler = "<p>" + "Policy text. " * 30 + "</p>"
    fetcher = Fetcher(
        {
            "https://rdap.nixiregistry.in/rdap/domain/example.in": rdap_page("r", registered),
            SHOP + "/pages/returns": html(SHOP + "/pages/returns", filler),
            SHOP + "/pages/shipping": html(SHOP + "/pages/shipping", filler),
            SHOP + "/pages/contact": html(
                SHOP + "/pages/contact", filler + f"<p>GSTIN: {EXAMPLE_GSTIN}</p>"
            ),
        }
    )
    return fetcher, product


def test_new_seller_with_gstin_and_policies_is_verified_basics():
    fetcher, product = new_shop_pages()
    offers = [offer(SHOP + "/products/oled")]
    checker(fetcher).label_offers(offers, [product])
    trust = offers[0].trust
    assert trust.label == "verified_basics"
    assert trust.new_seller is True
    assert trust.signals.domain_age_days == 20
    assert trust.signals.gstin == EXAMPLE_GSTIN
    assert trust.signals.policies == ALL
    assert trust.signals.web_risk == "not_checked"
    assert trust.checked_at == NOW
    # RDAP is a machine API (no robots.txt); seller pages keep the robots check.
    assert fetcher.calls[0] == ("https://rdap.nixiregistry.in/rdap/domain/example.in", False)
    assert all(robots for _, robots in fetcher.calls[1:])
    assert len(fetcher.calls) == 4


def test_results_are_cached_per_host():
    fetcher, product = new_shop_pages()
    trust = checker(fetcher)
    trust.label_offers([offer(SHOP + "/products/oled")], [product])
    calls = len(fetcher.calls)
    second = [offer(SHOP + "/products/other")]
    trust.label_offers(second, [])
    assert len(fetcher.calls) == calls
    assert second[0].trust.label == "verified_basics"


def test_seed_sellers_need_no_network():
    fetcher = Fetcher({})
    offers = [offer("https://robocraze.com/products/a")]
    checker(fetcher).label_offers(offers, [])
    assert offers[0].trust.label == "established"
    assert offers[0].trust.signals.known_seller is True
    assert fetcher.calls == []


def test_failed_lookups_fail_open():
    fetcher = Fetcher({"https://rdap.nixiregistry.in/rdap/domain/example.in": FetchError("x")})
    offers = [offer(SHOP + "/products/oled")]
    checker(fetcher).label_offers(offers, [html(SHOP + "/products/oled", "<p>x</p>")])
    trust = offers[0].trust
    assert trust.label == "unverified"
    assert "domain_age" in trust.signals.unavailable
    assert "Domain age check unavailable" in trust.reasons


def test_slow_checks_time_out_to_unverified():
    release = threading.Event()

    def slow():
        release.wait(5)
        raise FetchError("late")

    fetcher = Fetcher({"https://rdap.nixiregistry.in/rdap/domain/example.in": slow})
    offers = [offer(SHOP + "/products/oled")]
    try:
        checker(fetcher, deadline_s=0.05).label_offers(offers, [])
    finally:
        release.set()
    assert offers[0].trust.label == "unverified"
    assert offers[0].trust.signals.unavailable == ["all"]
    assert "Trust checks unavailable (timed out or failed)" in offers[0].trust.reasons


class Discovery:
    def discover(self, query):
        return SearchAttribution(source_urls=[SHOP + "/products/ttp223"])


PRODUCT = {
    "@type": "Product",
    "name": "TTP223 Capacitive Touch Sensor Module",
    "offers": {"@type": "Offer", "price": "25.50", "priceCurrency": "INR"},
}


def test_sourcing_attaches_trust_after_verification():
    fetcher, _ = new_shop_pages()
    url = SHOP + "/products/ttp223"
    fetcher.pages[url] = html(
        url, '<script type="application/ld+json">' + json.dumps(PRODUCT) + "</script>"
    )
    service = SourcingService(Discovery(), fetcher, trust=checker(fetcher))
    line = service.source(BomItem(line_id="L01", raw_name="TTP223 touch sensor module"))
    # 20-day-old domain, no GSTIN on the product page and no policy links found.
    assert line.offers[0].trust.label == "unverified"
    assert line.offers[0].trust.new_seller is True
    assert line.offers[0].seller_trust == "unverified"  # legacy field is unchanged


def test_trust_errors_never_drop_offers():
    class Broken:
        def label_offers(self, offers, pages):
            raise RuntimeError("boom")

    url = SHOP + "/products/ttp223"
    fetcher = Fetcher(
        {url: html(url, '<script type="application/ld+json">' + json.dumps(PRODUCT) + "</script>")}
    )
    line = SourcingService(Discovery(), fetcher, trust=Broken()).source(
        BomItem(line_id="L01", raw_name="TTP223 touch sensor module")
    )
    assert line.sourcing_status == "offers_found"
    assert line.offers[0].trust is None
