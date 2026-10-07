"""Detect storefront platforms and read their public product JSON as a verified source.

Used only when a fetched product page has no Product JSON-LD. Requests go through the
same fetcher (robots.txt, HTTPS, public-address pinning, size limits). Robocraze and
Quartz robots.txt (checked 2026-10-06) allow `/products/<handle>.json` and `.js`; Zbotic
allows `/wp-json/wc/store/`. A store that disallows these paths is skipped by the fetcher.
"""

import html
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, quote, urlsplit

from bharat_sourcer.schemas import StorePlatform, VerifiedOffer
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.listings import (
    ExtractedProduct,
    OfferOption,
    ProductScripts,
    is_type,
    nodes,
    safe_image_url,
    same_url,
    seller_specs,
    title_matches,
)

JSON_LIMIT = 1_000_000
# Theme-independent markers that each platform's storefront emits.
SHOPIFY_MARKERS = ("cdn.shopify.com", "/cdn/shop/", "shopify.shop", "shopify-digital-wallet")
WOO_MARKERS = ("woocommerce", "/wp-json/wc/")
MAGENTO_MARKERS = ("data-mage-init", "mage/cookies", "magento_")
SHOPIFY_PATH = re.compile(
    r"^(?:/[a-z]{2}(?:-[a-z]{2})?)?(?:/collections/[^/]+)?/products/([^/?#.]+)/?$", re.I
)
WOO_PATH = re.compile(r"^/product/([^/?#]+)/?$")


def html_page(page: Page) -> bool:
    return page.status == 200 and "text/html" in page.headers.get("content-type", "")


def product_jsonld(page: Page) -> list[dict]:
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(n for n in nodes(json.loads(script)) if is_type(n, "Product"))
        except (ValueError, RecursionError):
            continue
    return products


def detect_platform(page: Page) -> StorePlatform:
    """Deterministic platform guess from response headers and page markup."""
    headers = page.headers
    if "x-shopid" in headers or headers.get("powered-by", "").lower() == "shopify":
        return "shopify"
    if any(name.startswith("x-magento") for name in headers):
        return "magento"
    if not html_page(page):
        return "unknown"
    text = page.body[:2_000_000].decode("utf-8", errors="replace").lower()
    if any(marker in text for marker in SHOPIFY_MARKERS):
        return "shopify"
    if any(marker in text for marker in WOO_MARKERS):
        return "woocommerce"
    if any(marker in text for marker in MAGENTO_MARKERS):
        return "magento"
    return "jsonld" if product_jsonld(page) else "unknown"


def checked_price(raw: object) -> Decimal | None:
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price <= 0 or price > 10_000_000:
        return None
    if price != price.quantize(Decimal("0.01")):
        return None
    return price


def load_json(fetcher, url: str):
    response = fetcher.get(url, max_bytes=JSON_LIMIT)
    content_type = response.headers.get("content-type", "")
    # Shopify serves `.js` as text/javascript; the body is still JSON.
    if response.status != 200 or not ("json" in content_type or "javascript" in content_type):
        return None
    return json.loads(response.body.decode("utf-8"))


def shopify_offer(page: Page, query: str, fetcher) -> VerifiedOffer | None:
    """Read `/products/<handle>.json` (price, currency) and `.js` (availability)."""
    parsed = urlsplit(page.url)
    match = SHOPIFY_PATH.match(parsed.path)
    if not match:
        return None
    params = parse_qs(parsed.query)
    if set(params) - {"variant"} or len(params.get("variant", [""])) != 1:
        return None
    wanted = params.get("variant", [None])[0]
    if wanted is not None and not wanted.isdigit():
        return None
    handle = match.group(1)
    base = f"https://{parsed.hostname}/products/{quote(handle, safe='%-_')}"
    data = load_json(fetcher, base + ".json")
    product = data.get("product") if isinstance(data, dict) else None
    if not isinstance(product, dict) or product.get("handle") != handle:
        return None
    variants = [v for v in product.get("variants", []) if isinstance(v, dict)]
    if wanted is not None:
        variants = [v for v in variants if str(v.get("id")) == wanted]
    # Several variants without a chosen one is a variant group, not a single offer.
    if len(variants) != 1:
        return None
    variant = variants[0]
    title = product.get("title")
    if not isinstance(title, str) or len(title) > 500:
        return None
    variant_title = variant.get("title")
    if isinstance(variant_title, str) and variant_title not in {"", "Default Title"}:
        title = f"{title} - {variant_title}"
    if not title_matches(query, title):
        return None
    # Currency must be declared; it is never assumed from the store's country.
    if variant.get("price_currency") != "INR":
        return None
    price = checked_price(variant.get("price"))
    if price is None:
        return None
    stock = "unknown"
    try:
        storefront = load_json(fetcher, base + ".js")
    except (FetchError, ValueError):
        storefront = None
    if isinstance(storefront, dict):
        matching = [
            v
            for v in storefront.get("variants", [])
            if isinstance(v, dict) and str(v.get("id")) == str(variant.get("id"))
        ]
        if len(matching) == 1:
            # `.js` prices are minor units; a disagreement means neither is verified.
            if matching[0].get("price") != int(price * 100):
                return None
            available = matching[0].get("available")
            if isinstance(available, bool):
                stock = "in_stock" if available else "out_of_stock"
    image = product.get("image")
    images = product.get("images")
    if not image and isinstance(images, list) and images:
        image = images[0]
    image_url = safe_image_url(image.get("src") if isinstance(image, dict) else None, page.url)
    url = base + (f"?variant={variant['id']}" if wanted is not None else "")
    specs, evidence, conflicts = seller_specs({}, page, title)
    return VerifiedOffer(
        url=url,
        seller=parsed.hostname,
        title=title,
        image_url=image_url,
        price_inr=f"{price:.2f}",
        stock=stock,
        verification="shopify_storefront_json",
        specs=specs,
        spec_evidence=evidence,
        spec_conflicts=conflicts,
    )


def shopify_variants(page: Page, fetcher) -> ExtractedProduct | None:
    """A Shopify variant group (colours, sizes) from the public product JSON, for the judge.

    Each variant keeps its own INR price and availability; the judge picks the variant that
    matches the spec, and the price always comes from that variant. Single-variant products
    are left to `shopify_offer`.
    """
    parsed = urlsplit(page.url)
    match = SHOPIFY_PATH.match(parsed.path)
    if not match or parsed.query:
        return None
    handle = match.group(1)
    base = f"https://{parsed.hostname}/products/{quote(handle, safe='%-_')}"
    data = load_json(fetcher, base + ".json")
    product = data.get("product") if isinstance(data, dict) else None
    if not isinstance(product, dict) or product.get("handle") != handle:
        return None
    title = product.get("title")
    variants = [v for v in product.get("variants", []) if isinstance(v, dict)][:50]
    if not isinstance(title, str) or len(title) > 500 or len(variants) < 2:
        return None
    try:
        storefront = load_json(fetcher, base + ".js")
    except (FetchError, ValueError):
        storefront = None
    available = {
        str(v.get("id")): v.get("available")
        for v in (storefront or {}).get("variants", [])
        if isinstance(v, dict)
    }
    options = []
    for variant in variants:
        price = checked_price(variant.get("price"))
        name = variant.get("title")
        if variant.get("price_currency") != "INR" or price is None or not isinstance(name, str):
            continue
        flag = available.get(str(variant.get("id")))
        stock = "unknown" if not isinstance(flag, bool) else "in_stock" if flag else "out_of_stock"
        options.append(
            OfferOption(
                price=price,
                stock=stock,
                name=name[:200],
                sku=str(variant.get("sku") or "")[:80] or None,
                url=f"{base}?variant={variant.get('id')}",
            )
        )
    if len(options) < 2:
        return None
    image = product.get("image") or (product.get("images") or [None])[0]
    src = image.get("src") if isinstance(image, dict) else None
    return ExtractedProduct(
        page=page,
        product={"name": title, **({"image": src} if src else {})},
        title=title,
        options=options,
        meta_images=[],
        verification="shopify_storefront_json",
    )


def woocommerce_offer(page: Page, query: str, fetcher) -> VerifiedOffer | None:
    """Read the public WooCommerce Store API entry for this simple product."""
    parsed = urlsplit(page.url)
    match = WOO_PATH.match(parsed.path)
    if not match or parsed.query:
        return None
    slug = match.group(1)
    data = load_json(
        fetcher,
        f"https://{parsed.hostname}/wp-json/wc/store/v1/products?slug={quote(slug, safe='%-_')}",
    )
    if not isinstance(data, list):
        return None
    matches = [
        p
        for p in data[:20]
        if isinstance(p, dict)
        and isinstance(p.get("permalink"), str)
        and same_url(p["permalink"], page.url)
    ]
    if len(matches) != 1 or matches[0].get("type") != "simple":
        return None
    product = matches[0]
    title = product.get("name")
    if not isinstance(title, str) or len(title) > 500:
        return None
    title = html.unescape(title)
    if not title_matches(query, title):
        return None
    prices = product.get("prices")
    if not isinstance(prices, dict) or prices.get("currency_code") != "INR":
        return None
    minor = prices.get("currency_minor_unit")
    raw = prices.get("price")
    if not isinstance(minor, int) or not 0 <= minor <= 4 or not isinstance(raw, str):
        return None
    if not raw.isdigit():
        return None
    price = checked_price(Decimal(raw).scaleb(-minor))
    if price is None:
        return None
    in_stock = product.get("is_in_stock")
    stock = {True: "in_stock", False: "out_of_stock"}.get(in_stock, "unknown")
    images = product.get("images")
    image = images[0] if isinstance(images, list) and images else None
    image_url = safe_image_url(image.get("src") if isinstance(image, dict) else None, page.url)
    specs, evidence, conflicts = seller_specs({}, page, title)
    return VerifiedOffer(
        url=page.url,
        seller=parsed.hostname,
        title=title,
        image_url=image_url,
        price_inr=f"{price:.2f}",
        stock=stock,
        verification="woocommerce_store_api",
        specs=specs,
        spec_evidence=evidence,
        spec_conflicts=conflicts,
    )


def storefront_offer(page: Page, query: str, fetcher) -> VerifiedOffer | None:
    """Structured fallback for product pages without Product JSON-LD; never raises."""
    if not html_page(page) or product_jsonld(page):
        return None
    try:
        platform = detect_platform(page)
        if platform == "shopify":
            return shopify_offer(page, query, fetcher)
        if platform == "woocommerce":
            return woocommerce_offer(page, query, fetcher)
    except (FetchError, ValueError, TypeError, KeyError, RecursionError, InvalidOperation):
        return None
    return None
