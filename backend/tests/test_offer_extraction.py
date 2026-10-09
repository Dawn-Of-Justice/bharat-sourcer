"""Multi-offer, AggregateOffer and meta-tag price extraction on synthetic pages (not sellers)."""

import json

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import extract_product, meta_offer, verify_page

URL = "https://seller.example/product/ldr-5mm/"
HTML = {"content-type": "text/html; charset=utf-8"}


def page(body: str, url: str = URL) -> Page:
    return Page(url, 200, HTML, ("<!-- synthetic test page -->" + body).encode())


def jsonld(offers, name="LDR 5mm photoresistor") -> str:
    product = {"@type": "Product", "name": name, "offers": offers}
    return '<script type="application/ld+json">' + json.dumps(product) + "</script>"


def offer(price, url=None, name=None, currency="INR", stock="InStock"):
    entry = {
        "@type": "Offer",
        "price": price,
        "priceCurrency": currency,
        "availability": f"https://schema.org/{stock}",
    }
    if url:
        entry["url"] = url
    if name:
        entry["name"] = name
    return entry


def test_the_offer_for_the_page_url_is_chosen_among_variants():
    body = jsonld([offer("10.00", URL + "?v=1", "Pack of 10"), offer("40.00", URL, "Pack of 50")])
    result = verify_page(page(body))
    assert result.price_inr == "40.00" and str(result.url) == URL


def test_ambiguous_variants_are_kept_for_the_judge_not_priced():
    body = jsonld([offer("10.00", name="Pack of 10"), offer("40.00", name="Pack of 50")])
    assert verify_page(page(body)) is None
    extracted = extract_product(page(body))
    assert [o.name for o in extracted.options] == ["Pack of 10", "Pack of 50"]


@pytest.mark.parametrize(
    "aggregate, expected",
    [
        ({"lowPrice": "12.00", "highPrice": "12.00"}, "12.00"),
        ({"lowPrice": "12.00"}, "12.00"),
        ({"lowPrice": "12.00", "highPrice": "30.00"}, None),
        ({"lowPrice": "12.00", "priceCurrency": "USD"}, None),
        ({"offers": [offer("9.00", URL)]}, "9.00"),
    ],
)
def test_aggregate_offer(aggregate, expected):
    entry = {"@type": "AggregateOffer", "priceCurrency": "INR", **aggregate}
    result = verify_page(page(jsonld(entry)))
    assert (result.price_inr if result else None) == expected


def test_non_inr_variants_are_ignored():
    body = jsonld([offer("1.00", currency="USD"), offer("50.00", URL)])
    assert verify_page(page(body)).price_inr == "50.00"


META = (
    '<meta property="og:title" content="5mm White LED">'
    '<meta property="product:price:amount" content="{price}">'
    '<meta property="product:price:currency" content="{currency}">'
    '<meta property="product:availability" content="in stock">'
)


def test_meta_tag_price_fallback_requires_one_inr_price():
    result = meta_offer(page(META.format(price="7.00", currency="INR")))
    assert result.price_inr == "7.00" and result.stock == "in_stock"
    assert result.verification == "seller_meta_tags" and result.title == "5mm White LED"
    assert meta_offer(page(META.format(price="7.00", currency="USD"))) is None
    two = META.format(price="7.00", currency="INR") + '<span itemprop="price" content="9.00">'
    assert meta_offer(page(two)) is None
    assert meta_offer(page(META.format(price="7.005", currency="INR"))) is None
    # Legacy callers still pass a query: the title gate applies.
    assert meta_offer(page(META.format(price="7.00", currency="INR")), "LDR") is None


def test_microdata_price_fallback():
    body = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<h1 itemprop="name">LDR</h1><meta itemprop="name" content="GL5528 LDR 5mm">'
        '<meta itemprop="price" content="5.50"><meta itemprop="priceCurrency" content="INR">'
        '<link itemprop="availability" href="https://schema.org/OutOfStock"></div>'
    )
    result = meta_offer(page(body))
    assert result.price_inr == "5.50" and result.stock == "out_of_stock"


def test_meta_fallback_skips_shopify_and_pages_with_jsonld_offers():
    shopify = '<script>Shopify.shop = "example.myshopify.com";</script>'
    assert meta_offer(page(shopify + META.format(price="7.00", currency="INR"))) is None
    priced = jsonld(offer("7.00", URL)) + META.format(price="7.00", currency="INR")
    assert meta_offer(page(priced)) is None


def test_buyable_spec_is_editable_as_a_user_spec():
    with TestClient(create_app(Settings(_env_file=None, demo_mode=True))) as client:
        created = client.post(
            "/v1/jobs", json={"url": "https://example.com/build", "pin": "560001"}
        ).json()
        headers = {"X-Job-Token": created["job_token"]}
        path = created["watch"]
        spec = {
            "origin": "ai_inferred",
            "category": "resistor",
            "mount": "tht",
            "params": [{"name": "resistance", "value": "33k"}],
        }
        response = client.post(
            f"{path}/confirm",
            headers=headers,
            json={"edits": [{"op": "update", "line_id": "L01", "buyable_spec": spec}]},
        )
        assert response.status_code == 202
        job = client.get(path, headers=headers).json()
        saved = job["items"][0]["buyable_spec"]
        assert saved["origin"] == "user" and saved["mount"] == "tht"
        assert job["report"]["lines"][0]["item"]["buyable_spec"]["origin"] == "user"
