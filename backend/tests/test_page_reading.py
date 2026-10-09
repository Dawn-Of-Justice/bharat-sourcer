"""Offline synthetic page shapes and historical 2026-10-08 extraction regressions."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import (
    clean_title,
    extract_product,
    meta_offer,
    parse_inr,
    reject_reason,
    stock_of,
    variant_url,
    verify_page,
)
from bharat_sourcer.sourcing.platforms import detect_platform, storefront_offer
from bharat_sourcer.sourcing.tax import detect_tax_included

URL = "https://seller.example/products/sg90"


def page(body, url=URL, headers=None):
    return Page(url, 200, headers or {"content-type": "text/html"}, body.encode())


def product(**fields):
    return {
        "@type": "Product",
        "name": "SG90 servo",
        "offers": {"price": "1,299.00", "priceCurrency": "inr", "availability": "schema:InStock"},
        **fields,
    }


def script(data):
    return '<script type="application/ld+json; charset=utf-8">' + json.dumps(data) + "</script>"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1299, "1299"),
        ("1,299.00", "1299"),
        ("\u20b91,299.00", "1299"),
        ("Rs. 1,299/-", "1299"),
        ("INR\u00a01,23,456.00", "123456"),
        ("12.0000", "12"),
        ("1.234,56", None),
        ("12-20", None),
        ("12.001", None),
        ("0", None),
        ("1,29", None),
        ("10000001", None),
        (True, None),
        ("NaN", None),
    ],
)
def test_inr_formats(raw, expected):
    assert parse_inr(raw, "INR") == (Decimal(expected) if expected else None)


def test_currency_must_be_declared_or_explicit():
    assert parse_inr("299") is None
    assert parse_inr("\u20b9299") == Decimal(299)
    assert parse_inr("\u20b9299", "USD") is None


@pytest.mark.parametrize("kind", ["Product", "IndividualProduct", "ProductModel"])
def test_main_entity_types_currency_and_dedup(kind):
    data = product(**{"@type": kind})
    body = script({"@type": "ItemPage", "mainEntity": data}) + script(data)
    assert verify_page(page(body)).price_inr == "1299.00"


def test_cdata_trailing_comma_control_char_repair():
    raw = json.dumps(product()).replace("SG90 servo", "SG90\nservo")
    raw = raw[:-1] + ",}"
    body = '<script type="application/ld+json">//<![CDATA[' + raw + "]]></script>"
    assert verify_page(page(body)).stock == "in_stock"


def test_product_group_variant_metadata():
    data = {
        "@type": "ProductGroup",
        "name": "SG90 servo",
        "priceCurrency": "INR",
        "hasVariant": [{"name": "SG90 blue", "sku": "BLUE", "url": URL, "offers": {"price": "99"}}],
    }
    extracted = extract_product(page(script(data)))
    assert extracted.options[0].sku == "BLUE"
    assert extracted.options[0].name == "SG90 blue"
    assert verify_page(page(script(data))).price_inr == "99.00"


def test_currency_price_spec_and_unresolved_aggregate_sibling():
    data = product(
        priceCurrency="INR",
        offers=[
            {"@type": "AggregateOffer", "lowPrice": 1, "highPrice": 2},
            {"@type": "Offer", "priceSpecification": {"price": "99"}},
        ],
    )
    assert verify_page(page(script(data))).price_inr == "99.00"
    data["offers"] = {
        "@type": "Offer",
        "priceSpecification": {"price": "99", "priceType": "https://schema.org/ListPrice"},
    }
    assert verify_page(page(script(data))) is None


@pytest.mark.parametrize(
    "stock,expected",
    [
        ("schema:InStock", "in_stock"),
        ("https://schema.org/OnlineOnly/", "in_stock"),
        ("LimitedAvailability", "in_stock"),
        ("BackOrder", "preorder"),
        ("PreSale", "preorder"),
        ("Discontinued", "out_of_stock"),
        ("SoldOut", "out_of_stock"),
        ("InStoreOnly", "unknown"),
    ],
)
def test_stock_vocabulary(stock, expected):
    assert stock_of(stock) == expected


@pytest.mark.parametrize(
    "offer_url",
    ["/products/sg90", "http://www.seller.example/products/sg90/", URL + "?utm_source=x"],
)
def test_offer_listing_identity(offer_url):
    data = product()
    data["offers"]["url"] = offer_url
    assert verify_page(page(script(data), URL + "?srsltid=tracking"))


def test_judge_variant_gate_keeps_unknown_title():
    data = product(name="Seller marketing title")
    data["offers"].update({"@type": "Offer", "url": URL + "?variant=12"})
    html = page(script(data), URL + "?utm_source=x")
    assert variant_url(html, None) == URL + "?variant=12"
    assert variant_url(html, "SG90 servo") is None


def test_related_products_never_read():
    assert verify_page(page(script({"@type": "ItemList", "itemListElement": [product()]}))) is None


@pytest.mark.parametrize(
    "heading", ["Product not found", "Page not found", "No longer available", "404"]
)
def test_soft_404(heading):
    html = page("<h1>" + heading + "</h1>" + script(product()))
    assert verify_page(html) is None
    assert reject_reason(html) == "soft_404"


def test_meta_requires_product_signal_and_reads_element_text():
    body = '<title>SG90 servo</title><span itemprop="price">\u20b9299.00</span>'
    assert meta_offer(page(body)).price_inr == "299.00"
    assert meta_offer(page(body, "https://seller.example/catalog")) is None
    assert meta_offer(page(body, "https://seller.example/category/servos")) is None


@pytest.mark.parametrize(
    "marker,platform",
    [
        ("Shopify.shop", "shopify"),
        ("shopify-section", "shopify"),
        ("woocommerce cdn.shopify.com", "woocommerce"),
        ("catalog/view/theme", "opencart"),
        ("cdn11.bigcommerce.com", "bigcommerce"),
        ("/modules/ps_", "prestashop"),
        ("static.wixstatic.com", "wix"),
        ("mydukaan", "dukaan"),
        ("instamojo", "instamojo"),
        ("cdn.shopify.com", "unknown"),
    ],
)
def test_platform_markers(marker, platform):
    assert detect_platform(page(marker)) == platform


@pytest.mark.parametrize(
    "phrase,value",
    [
        ("including 18% GST", True),
        ("excluding 18% GST", False),
        ("With GST", True),
        ("Without GST", False),
    ],
)
def test_tax_phrases_and_footer_scope(phrase, value):
    body = '<div class="price">Rs 299 ' + phrase + "</div><footer>Prices incl GST</footer>"
    assert detect_tax_included({}, body)[0] is value


def test_meta_ex_tax_price_does_not_inherit_visible_inclusive_tax():
    body = (
        '<title>SG90 servo</title><meta property="og:price:amount" content="254">'
        '<meta property="og:price:currency" content="INR">'
        '<div class="price">Rs 299 including 18% GST</div>'
    )
    assert meta_offer(page(body)).tax_included is None


def test_seller_suffix_cleanup_is_specific():
    assert clean_title("SG90 - Rytronics.in", "https://rytronics.in/product/sg90") == "SG90"
    assert clean_title("SG90 - Blue", URL) == "SG90 - Blue"


def test_shopify_fallback_with_unpriced_jsonld_and_tracking():
    html = page("Shopify.shop " + script(product(offers=[])), URL + "?utm_source=x")

    class Fetcher:
        def get(self, url, **kwargs):
            value = (
                {
                    "product": {
                        "handle": "sg90",
                        "title": "SG90 servo",
                        "variants": [{"id": 1, "price": "1,299.00", "price_currency": "INR"}],
                    }
                }
                if url.endswith(".json")
                else {"variants": [{"id": 1, "price": 129900, "available": True}]}
            )
            return page(json.dumps(value), url, {"content-type": "application/json"})

    assert storefront_offer(html, None, Fetcher()).price_inr == "1299.00"


def test_historical_quartz_comma_price_fixture():
    path = (
        Path(__file__).parent
        / "fixtures/seller_pages/historical_2026_10_08/quartz_comma_price_jsonld.html"
    )
    html = page(path.read_text(encoding="utf-8"), "https://quartzcomponents.com/products/synthetic")
    # The probe saved an excerpt ending mid-JSON; never fabricate its missing fields.
    assert extract_product(html) is None
    from bharat_sourcer.sourcing.listings import MetaPrices

    parser = MetaPrices()
    parser.feed(html.body.decode())
    assert parse_inr(parser.prices[0], parser.currencies[0]) == Decimal("2650.00")


def test_commented_cdata_wrapper():
    body = '<script type="application/ld+json"><!-- //<![CDATA['
    body += json.dumps(product()) + "//]]> --></script>"
    assert verify_page(page(body)).price_inr == "1299.00"


def test_product_group_single_variant_navigation():
    data = {
        "@type": "ProductGroup",
        "name": "SG90 servo",
        "hasVariant": [
            {
                "name": "SG90 blue",
                "url": URL + "?variant=7",
                "offers": {"price": 99, "priceCurrency": "INR"},
            }
        ],
    }
    assert variant_url(page(script(data)), None) == URL + "?variant=7"
