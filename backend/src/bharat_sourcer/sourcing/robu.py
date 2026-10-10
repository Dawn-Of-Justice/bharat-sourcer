"""Robu.in through its public GraphQL proxy.

robu.in answers every HTML page with a Cloudflare challenge, but its robots.txt (checked
2026-10-10) allows `/api/proxy/graphql` for all agents: the storefront renders its own product
and category pages from it. Only that path is read, never the challenged pages:

- search: `productSearch(search:)`, the storefront's catalogue search;
- product pages: `productdetails(slug:)`, rendered into a minimal page with one Product
  JSON-LD block so the normal verifier and judge read it like any seller page.

robu.in's own `/api/search/` is disallowed by robots.txt and is not used. Requests go through
the same fetcher (robots.txt, HTTPS, public-address pinning, size limits) and `Politeness`.
"""

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.sellers import host_of

HOST = "robu.in"
GRAPHQL = f"https://{HOST}/api/proxy/graphql/"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,250}$")
PRODUCT_PATH = re.compile(r"^/product/([^/?#]+)/?$")
SEARCH = "{ productSearch(search: %s) { status data { products { name slug price in_stock } } } }"
DETAILS = (
    "{ productdetails(slug: %s) { status code message data { sku type name url_key "
    "short_description description in_stock is_backorder price { final } images { url } } } }"
)
# Seller description markup is kept for spec tables; active content is dropped.
ACTIVE = re.compile(r"<(script|style|iframe|object|embed)\b.*?</\1\s*>", re.I | re.S)


@dataclass
class ApiPage(Page):
    """A product page rendered from the seller's own product API."""

    verification: str = "seller_product_api"


def handles(url: str) -> bool:
    return host_of(url) == HOST


def literal(text: str) -> str:
    # A JSON string is a valid GraphQL string literal; GET requests carry no variables.
    return json.dumps(" ".join(text.split())[:200])


def api_url(query: str) -> str:
    return f"{GRAPHQL}?{urlencode({'query': query})}"


def search_url(query: str) -> str:
    return api_url(SEARCH % literal(query))


def product_url(slug: str) -> str:
    return f"https://{HOST}/product/{slug}/"


def product_slug(url: str) -> str | None:
    parts = urlsplit(url)
    match = PRODUCT_PATH.match(parts.path)
    if parts.scheme != "https" or not handles(url) or not match:
        return None
    slug = match.group(1).lower()
    return slug if SLUG.match(slug) else None


def payload(page: Page, field: str):
    """The `data.<field>` envelope of a GraphQL response, checked."""
    if page.status != 200 or "json" not in page.headers.get("content-type", ""):
        raise ValueError(f"HTTP {page.status}")
    data = json.loads(page.body.decode("utf-8"))
    envelope = (data.get("data") or {}).get(field) if isinstance(data, dict) else None
    if not isinstance(envelope, dict):
        raise ValueError("Invalid robu.in API response")
    return envelope


def search_results(page: Page) -> list[dict]:
    """Search hits as {url, title, price}; hints only, every hit is verified on its own."""
    data = payload(page, "productSearch").get("data") or {}
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise ValueError("Invalid robu.in search response")
    found = []
    for product in products:
        slug = product.get("slug") if isinstance(product, dict) else None
        if not isinstance(slug, str) or not SLUG.match(slug):
            continue
        found.append(
            {
                "url": product_url(slug),
                "title": html.unescape(str(product.get("name") or ""))[:300] or None,
                "price": product.get("price"),
            }
        )
    return found


def price(raw: object) -> str | None:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return f"{value:.2f}" if value.is_finite() and value > 0 else None


def availability(product: dict) -> str:
    if product.get("in_stock") is True:
        return "https://schema.org/InStock"
    if product.get("is_backorder") is True:
        return "https://schema.org/BackOrder"
    return "https://schema.org/OutOfStock" if product.get("in_stock") is False else ""


def render(url: str, product: dict) -> bytes:
    """One Product JSON-LD block plus the seller's description, for the usual readers."""
    name = str(product.get("name") or "")[:500]
    node: dict = {"@context": "https://schema.org", "@type": "Product", "name": name, "url": url}
    if product.get("sku"):
        node["sku"] = str(product["sku"])[:80]
    images = [
        i["url"]
        for i in product.get("images") or []
        if isinstance(i, dict) and isinstance(i.get("url"), str) and i["url"].startswith("https://")
    ]
    if images:
        node["image"] = images[:5]
    amount = price((product.get("price") or {}).get("final"))
    # Configurable products list a price per variant; their headline price is not an offer.
    if product.get("type") == "simple" and amount:
        node["offers"] = {
            "@type": "Offer",
            "price": amount,
            "priceCurrency": "INR",
            "url": url,
            **({"availability": a} if (a := availability(product)) else {}),
        }
    script = json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
    description = "\n".join(
        ACTIVE.sub("", str(product.get(k) or ""))[:100_000]
        for k in ("short_description", "description")
    )
    title = html.escape(name)
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
        f'<script type="application/ld+json">{script}</script></head>'
        f"<body><h1>{title}</h1><main>{description}</main></body></html>"
    ).encode()


def product_page(get: Callable[[str], Page], url: str) -> Page:
    """Read a robu.in product URL through `productdetails`; other robu.in pages are not read."""
    slug = product_slug(url)
    if slug is None:
        raise FetchError("robu.in is read only through its product API")
    envelope = payload(get(api_url(DETAILS % literal(slug))), "productdetails")
    product = envelope.get("data")
    canonical = product_url(slug)
    headers = {"content-type": "text/html; charset=utf-8"}
    if envelope.get("status") is not True or not isinstance(product, dict):
        # The API's "Product not found." becomes the soft 404 the verifier already rejects.
        return ApiPage(canonical, 404, headers, b"<title>Product not found</title>")
    if product.get("url_key") != slug or not isinstance(product.get("name"), str):
        raise ValueError("robu.in API returned a different product")
    return ApiPage(canonical, 200, headers, render(canonical, product))
