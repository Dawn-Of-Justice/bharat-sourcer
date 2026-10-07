"""Shopify and WooCommerce public product JSON as a structured verification source.

Fixtures in fixtures/storefront are trimmed real responses (source URL and fetch date in
each file). Their prices and stock are historical snapshots for parsing tests, never
current or verified seller facts. All tests are offline.
"""

import json
from pathlib import Path

import pytest

from bharat_sourcer.schemas import BomItem, SearchAttribution
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.platforms import detect_platform, storefront_offer
from bharat_sourcer.sourcing.service import SourcingService

FIXTURES = Path(__file__).parent / "fixtures"
HTML = {"content-type": "text/html; charset=utf-8"}
RC_URL = "https://robocraze.com/products/0-96in-oled-display-module-4pin"
QC_URL = "https://quartzcomponents.com/products/ttp223-based-capacitive-touch-sensor-module"
ZB_URL = "https://zbotic.in/product/drv8825-stepper-motor-driver-with-aluminum-heat-sink-2/"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / "storefront" / name).read_text("utf-8"))


def json_page(name: str, url: str | None = None, response=None) -> Page:
    data = recorded(name)
    body = json.dumps(data["response"] if response is None else response).encode()
    return Page(url or data["source_url"], 200, {"content-type": data["content_type"]}, body)


def shopify_html(url: str) -> Page:
    # A product page whose theme emits no Product JSON-LD; only the Shopify CDN marker.
    html = f'<link rel="preconnect" href="https://cdn.shopify.com"><h1>Product</h1><a href="{url}">'
    return Page(url, 200, HTML, html.encode())


class Fetcher:
    def __init__(self, pages: dict[str, Page | Exception]):
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.calls.append(url)
        result = self.pages.get(url)
        if isinstance(result, Exception):
            raise result
        if result is None:
            return Page(url, 404, {"content-type": "text/html"}, b"")
        return result


def shopify_fetcher(prefix: str, url: str, **overrides) -> Fetcher:
    pages = {
        url + ".json": json_page(prefix + ".json"),
        url + ".js": json_page(prefix + ".js.json"),
    }
    pages.update(overrides)
    return Fetcher(pages)


def test_shopify_json_verifies_price_and_js_adds_stock():
    fetcher = shopify_fetcher("shopify_robocraze_oled_096", RC_URL)
    offer = storefront_offer(shopify_html(RC_URL), "0.96 inch OLED display", fetcher)
    assert offer.verification == "shopify_storefront_json"
    assert offer.price_inr == "172.00"  # historical snapshot, parsing check only
    assert offer.stock == "out_of_stock"
    assert str(offer.url) == RC_URL
    assert offer.seller == "robocraze.com"
    assert str(offer.image_url).startswith("https://cdn.shopify.com/")
    assert offer.specs.family == "oled"
    assert fetcher.calls == [RC_URL + ".json", RC_URL + ".js"]


def test_shopify_quartz_in_stock():
    fetcher = shopify_fetcher("shopify_quartz_ttp223", QC_URL)
    offer = storefront_offer(shopify_html(QC_URL), "TTP223 touch sensor module", fetcher)
    assert (offer.price_inr, offer.stock) == ("18.00", "in_stock")


def test_shopify_stock_unknown_when_js_unavailable():
    fetcher = shopify_fetcher(
        "shopify_quartz_ttp223", QC_URL, **{QC_URL + ".js": FetchError("Robots")}
    )
    offer = storefront_offer(shopify_html(QC_URL), "TTP223 touch sensor module", fetcher)
    assert (offer.price_inr, offer.stock) == ("18.00", "unknown")


def test_shopify_sources_that_disagree_are_not_verified():
    data = recorded("shopify_quartz_ttp223.js.json")["response"]
    data["variants"][0]["price"] = 2000
    fetcher = shopify_fetcher(
        "shopify_quartz_ttp223",
        QC_URL,
        **{QC_URL + ".js": json_page("shopify_quartz_ttp223.js.json", response=data)},
    )
    assert storefront_offer(shopify_html(QC_URL), "TTP223 touch sensor module", fetcher) is None


@pytest.mark.parametrize("currency", [None, "USD"])
def test_shopify_currency_must_be_declared_inr(currency):
    data = recorded("shopify_quartz_ttp223.json")["response"]
    data["product"]["variants"][0]["price_currency"] = currency
    fetcher = shopify_fetcher(
        "shopify_quartz_ttp223",
        QC_URL,
        **{QC_URL + ".json": json_page("shopify_quartz_ttp223.json", response=data)},
    )
    assert storefront_offer(shopify_html(QC_URL), "TTP223 touch sensor module", fetcher) is None


def test_shopify_variant_group_needs_explicit_variant():
    data = recorded("shopify_quartz_ttp223.json")["response"]
    first = data["product"]["variants"][0]
    second = first | {"id": 42, "title": "Red", "price": "9.00"}
    data["product"]["variants"] = [first, second]
    page = json_page("shopify_quartz_ttp223.json", response=data)
    fetcher = shopify_fetcher("shopify_quartz_ttp223", QC_URL, **{QC_URL + ".json": page})
    assert storefront_offer(shopify_html(QC_URL), "TTP223 touch sensor module", fetcher) is None
    offer = storefront_offer(shopify_html(QC_URL + "?variant=42"), "TTP223 touch sensor", fetcher)
    assert offer.price_inr == "9.00"
    assert offer.title.endswith("- Red")
    assert str(offer.url) == QC_URL + "?variant=42"
    assert offer.stock == "unknown"  # the .js fixture has no variant 42


def test_shopify_title_gate_still_applies():
    fetcher = shopify_fetcher("shopify_quartz_ttp223", QC_URL)
    assert storefront_offer(shopify_html(QC_URL), "ESP32 development board", fetcher) is None


def test_pages_with_product_jsonld_never_use_the_fast_path():
    html = (FIXTURES / "seller_pages" / "robocraze_oled_096.html").read_bytes()
    fetcher = shopify_fetcher("shopify_robocraze_oled_096", RC_URL)
    assert storefront_offer(Page(RC_URL, 200, HTML, html), "0.96 inch OLED", fetcher) is None
    assert fetcher.calls == []


def test_robots_or_fetch_refusal_means_no_offer():
    fetcher = Fetcher({RC_URL + ".json": FetchError("Robots policy prevents verification")})
    assert storefront_offer(shopify_html(RC_URL), "0.96 inch OLED display", fetcher) is None


def woo_html(url=ZB_URL):
    html = '<body class="product-template-default woocommerce woocommerce-page"><h1>x</h1>'
    return Page(url, 200, HTML, html.encode())


WOO_API = (
    "https://zbotic.in/wp-json/wc/store/v1/products"
    "?slug=drv8825-stepper-motor-driver-with-aluminum-heat-sink-2"
)


def test_woocommerce_store_api_verifies_simple_product():
    fetcher = Fetcher({WOO_API: json_page("woocommerce_zbotic_drv8825.json", WOO_API)})
    offer = storefront_offer(woo_html(), "DRV8825 stepper motor driver", fetcher)
    assert offer.verification == "woocommerce_store_api"
    assert (offer.price_inr, offer.stock) == ("103.84", "out_of_stock")
    assert str(offer.url) == ZB_URL
    assert str(offer.image_url).startswith("https://cdn.zbotic.in/")


@pytest.mark.parametrize(
    "change",
    [
        {"type": "variable"},
        {"permalink": "https://zbotic.in/product/other/"},
        {"prices": {"price": "10384", "currency_code": "USD", "currency_minor_unit": 2}},
    ],
)
def test_woocommerce_rejects_unsupported_entries(change):
    data = recorded("woocommerce_zbotic_drv8825.json")["response"]
    data[0].update(change)
    fetcher = Fetcher({WOO_API: json_page("woocommerce_zbotic_drv8825.json", WOO_API, data)})
    assert storefront_offer(woo_html(), "DRV8825 stepper motor driver", fetcher) is None


@pytest.mark.parametrize(
    "headers, body, expected",
    [
        ({"x-shopid": "1"}, b"", "shopify"),
        (HTML, b'<img src="https://shop.example/cdn/shop/files/a.png">', "shopify"),
        (HTML, b'<div class="woocommerce">', "woocommerce"),
        (HTML, b'<div data-mage-init="{}">', "magento"),
        ({"x-magento-tags": "x"}, b"", "magento"),
        (
            HTML,
            b'<script type="application/ld+json">{"@type":"Product","name":"x"}</script>',
            "jsonld",
        ),
        (HTML, b"<p>plain page</p>", "unknown"),
    ],
)
def test_detect_platform(headers, body, expected):
    assert detect_platform(Page("https://shop.example/p", 200, headers, body)) == expected


def test_detect_platform_on_recorded_seller_pages():
    pages = FIXTURES / "seller_pages"
    for name, expected in [
        ("robocraze_oled_096.html", "shopify"),
        ("quartz_ttp223.html", "shopify"),
    ]:
        page = Page("https://seller.example/p", 200, HTML, (pages / name).read_bytes())
        assert detect_platform(page) == expected


class Discovery:
    def discover(self, query):
        return SearchAttribution(source_urls=[QC_URL])


def test_sourcing_uses_storefront_json_when_jsonld_is_missing():
    fetcher = shopify_fetcher("shopify_quartz_ttp223", QC_URL, **{QC_URL: shopify_html(QC_URL)})
    line = SourcingService(Discovery(), fetcher).source(
        BomItem(line_id="L01", raw_name="TTP223 touch sensor module")
    )
    assert line.sourcing_status == "offers_found"
    assert line.offers[0].verification == "shopify_storefront_json"
    assert line.offers[0].trust is None  # no trust checker configured


def test_shopify_variant_group_reaches_the_judge_with_per_variant_prices():
    """Synthetic Shopify product JSON (shape of a colour-variant LED pack)."""
    import json

    from bharat_sourcer.schemas import OfferMatch
    from bharat_sourcer.sourcing.fetch import Page
    from bharat_sourcer.sourcing.judge import judged_offer
    from bharat_sourcer.sourcing.matching import build_candidate
    from bharat_sourcer.sourcing.platforms import shopify_variants

    base = "https://shop.example.in/products/5mm-led-pack-of-10"
    product = {
        "handle": "5mm-led-pack-of-10",
        "title": "Transparent 5mm LED (Pack of 10)",
        "variants": [
            {"id": 1, "title": "Red", "price": "19.00", "price_currency": "INR"},
            {"id": 2, "title": "White", "price": "21.00", "price_currency": "INR"},
        ],
    }
    storefront = {"variants": [{"id": 1, "available": True}, {"id": 2, "available": True}]}

    class Fetcher:
        def get(self, url, max_bytes=None):
            body = {base + ".json": {"product": product}, base + ".js": storefront}[url]
            return Page(url, 200, {"content-type": "application/json"}, json.dumps(body).encode())

    page = Page(base, 200, {"content-type": "text/html"}, b"<html><title>LED</title></html>")
    group = shopify_variants(page, Fetcher())
    assert group is not None and [o.name for o in group.options] == ["Red", "White"]
    candidate = build_candidate(page, None, extracted=group)
    assert candidate.variant_names() == ["Red", "White"]
    offer = judged_offer(candidate, OfferMatch(status="exact", score=0.9, variant="White"))
    assert offer.price_inr == "21.00" and str(offer.url).endswith("?variant=2")
    assert offer.verification == "shopify_storefront_json"
