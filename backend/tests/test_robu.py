"""robu.in through its GraphQL proxy; offline (synthetic API responses, no real catalogue data)."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from bharat_sourcer.sourcing.fetch import ApiRoute, FetchError, Page, SafeFetcher
from bharat_sourcer.sourcing.listings import reject_reason, verify_page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.seller_search import REGISTRY, SellerSearch, searchable

JSON = {"content-type": "application/json"}
HTML = {"content-type": "text/html; charset=utf-8"}
URL = "https://robu.in/product/synthetic-touch-module/"


def details(**overrides):
    product = {
        "sku": "900001",
        "type": "simple",
        "name": "Synthetic Touch Module",
        "url_key": "synthetic-touch-module",
        "short_description": "<ul><li>Input Voltage : 2 V – 5.5 V</li></ul>",
        "description": "<p>Synthetic.</p><script>alert(1)</script>",
        "in_stock": True,
        "is_backorder": False,
        "price": {"final": 19},
        "images": [{"url": "https://media.example.in/synthetic.jpg"}],
        **overrides,
    }
    return {"data": {"productdetails": {"status": True, "code": 200, "data": product}}}


class Api:
    """Answers GraphQL GETs by operation; records each request's decoded query."""

    def __init__(self, details=None, search=None):
        self.details, self.search, self.queries = details, search, []

    def get(self, url, **kwargs):
        parts = urlsplit(url)
        assert parts.path == "/api/proxy/graphql/", url
        query = parse_qs(parts.query)["query"][0]
        self.queries.append(query)
        body = self.details if "productdetails" in query else self.search
        return Page(url, 200, JSON, json.dumps(body).encode())


def polite():
    return Politeness(min_interval_s=0, sleep=lambda s: None)


def test_product_page_is_read_through_productdetails_and_verified():
    api = Api(details())
    page = polite().wrap(api).get(URL + "?utm_source=x")
    assert 'productdetails(slug: "synthetic-touch-module")' in api.queries[0]
    offer = verify_page(page, None)
    assert offer.url.unicode_string() == URL and offer.price_inr == "19.00"
    assert offer.stock == "in_stock" and offer.verification == "seller_product_api"
    assert str(offer.image_url) == "https://media.example.in/synthetic.jpg"
    assert b"<script>alert" not in page.body  # seller markup kept, active content dropped


def test_missing_product_is_a_soft_404_and_variant_groups_have_no_single_offer():
    gone = {"data": {"productdetails": {"status": False, "code": 400, "data": None}}}
    page = polite().wrap(Api(gone)).get(URL)
    assert page.status == 404 and reject_reason(page) == "soft_404"
    configurable = polite().wrap(Api(details(type="configurable"))).get(URL)
    assert verify_page(configurable, None) is None


@pytest.mark.parametrize(
    "overrides, stock",
    [
        ({"in_stock": False}, "out_of_stock"),
        ({"in_stock": False, "is_backorder": True}, "preorder"),
    ],
)
def test_stock_comes_from_the_api_flags(overrides, stock):
    page = polite().wrap(Api(details(**overrides))).get(URL)
    assert verify_page(page, None).stock == stock


def test_a_different_product_or_a_non_product_page_is_never_accepted():
    with pytest.raises(ValueError):
        polite().wrap(Api(details(url_key="other-module"))).get(URL)
    api = Api(details())
    for url in ["https://robu.in/", "https://robu.in/product-category/sensors/"]:
        with pytest.raises(FetchError):
            polite().wrap(api).get(url)
    assert api.queries == []


def test_safe_fetcher_never_requests_robu_pages():
    fetcher = SafeFetcher()
    with pytest.raises(ApiRoute) as route:
        fetcher.get(URL)
    assert route.value.url == URL
    with pytest.raises(ApiRoute):
        fetcher.get("https://www.robu.in/")


def test_a_search_redirect_that_lands_on_robu_is_read_through_the_api():
    api = Api(details())

    class Redirected:
        def get(self, url, **kwargs):
            if "vertexaisearch" in url:
                raise ApiRoute(URL)
            return api.get(url, **kwargs)

    page = (
        polite()
        .wrap(Redirected())
        .get("https://vertexaisearch.cloud.google.com/grounding-api-redirect/synthetic")
    )
    assert page.url == URL and verify_page(page, None).price_inr == "19.00"


def test_search_adapter_reads_product_search_hints():
    hits = {
        "data": {
            "productSearch": {
                "status": True,
                "data": {
                    "products": [
                        {
                            "name": "Synthetic Touch Module",
                            "slug": "synthetic-touch-module",
                            "price": 19,
                            "in_stock": True,
                        },
                        {"name": "Bad slug touch", "slug": "../admin", "price": 1},
                        {"name": "Unrelated PCIe Adapter", "slug": "pcie-adapter", "price": 9},
                    ]
                },
            }
        }
    }
    api = Api(search=hits)
    seller = next(s for s in searchable(REGISTRY) if s["domain"] == "robu.in")
    result = SellerSearch(polite(), api, [seller]).search(["touch module"], 5, 12)
    assert 'productSearch(search: "touch module")' in api.queries[0]
    assert [(c.url, c.price_hint) for c in result.candidates] == [(URL, "19.00")]
