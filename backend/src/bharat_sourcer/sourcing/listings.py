"""Read explicit Product/Offer JSON-LD; never infer price or availability from prose."""

import json
import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from bharat_sourcer.compat import parse_name
from bharat_sourcer.schemas import (
    PartImage,
    PartSpecs,
    SpecConflict,
    SpecEvidence,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.specs import label_field, label_unit, parse_value, table_specs
from bharat_sourcer.sourcing.tax import detect_tax_included


class ProductScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.meta_images: list[str] = []
        self.buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and (values.get("type") or "").lower() == "application/ld+json":
            self.buffer = []
        elif tag == "meta" and len(self.meta_images) < 5:
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image:secure_url", "og:image", "twitter:image"} and values.get(
                "content"
            ):
                self.meta_images.append(values["content"])

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.buffer is not None:
            self.scripts.append("".join(self.buffer))
            self.buffer = None


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        # Only inspect top-level product entities, never related/recommended products.
        yield from nodes(value.get("@graph", []))


def is_type(value: dict, expected: str) -> bool:
    types = value.get("@type", [])
    if isinstance(types, str):
        types = [types]
    return isinstance(types, list) and any(
        isinstance(kind, str) and kind.rsplit("/", 1)[-1] == expected for kind in types
    )


def title_matches(query: str | None, title: str) -> bool:
    """Legacy relevance gate, used only when no spec judge is configured or it failed.

    ``query=None`` means relevance is decided later by the spec judge (`judge.py`), so
    extraction functions shared with that path accept every title.
    """
    if query is None:
        return True
    aliases = {
        "microcontroller": "",
        "development": "",
        "board": "",
        "module": "",
        "compatible": "",
        "sensor": "",
        "display": "",
        "capacitive": "",
    }

    def tokens(text):
        # Sellers write sizes as 0.96", 0.96″ or "0.91 in."; all mean the same inch token.
        text = re.sub(r"(\d)\s*(?:″|”|\"|inch(?:es)?\b|in\.)", r"\1 inch ", text.lower())
        # One spelling for units, so "22µF" and "22uF" are the same token.
        text = text.replace("µ", "u").replace("μ", "u").replace("ω", "ohm")
        plurals = {
            "resistors": "resistor",
            "leds": "led",
            "wires": "wire",
            "buttons": "button",
            "switches": "switch",
        }
        return {
            plurals.get(word, word)
            for word in re.findall(r"[a-z0-9]+", text.lower())
            if aliases.get(word, word)
        }

    expected, actual = tokens(query), tokens(title)
    return bool(expected) and expected.issubset(actual)


# Storefront "no image" assets are not product photos (e.g. Shopify's no-image-2048.gif).
PLACEHOLDER_IMAGE = re.compile(
    r"no[-_]?image|noimage|placeholder|default[-_]?(?:product|image)"
    r"|image[-_]?not[-_]?available|coming[-_]?soon",
    re.IGNORECASE,
)


def same_url(left: str, right: str) -> bool:
    """Equal after dropping fragment/trailing slash; percent-escape hex case is insignificant."""

    def norm(url):
        url = url.split("#")[0].rstrip("/")
        return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), url)

    return norm(left) == norm(right)


def safe_image_url(raw: object, page_url: str, *, upgrade: bool = False) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("url") or raw.get("contentUrl")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 2048:
        return None
    try:
        url = urljoin(page_url, raw.strip())
        parsed = urlsplit(url)
        page_host = urlsplit(page_url).hostname
        # Page metadata often says http:// for the seller's own HTTPS CDN path.
        if upgrade and parsed.scheme == "http" and parsed.hostname == page_host:
            url = "https" + url[4:]
            parsed = urlsplit(url)
        if (
            len(url) <= 2048
            and parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not any(c in url for c in "\r\n\t")
            and not PLACEHOLDER_IMAGE.search(parsed.path)
        ):
            return url
    except (ValueError, UnicodeError):
        return None
    return None


def product_image_url(product: dict, page_url: str, meta_images=()) -> str | None:
    """First real HTTPS image of this Product; page og:image only for single-product pages."""
    images = product.get("image")
    if isinstance(images, (str, dict)):
        images = [images]
    for image in images[:20] if isinstance(images, list) else []:
        if url := safe_image_url(image, page_url):
            return url
    for image in meta_images:
        if url := safe_image_url(image, page_url, upgrade=True):
            return url
    return None


def page_images(page: Page, query: str) -> list[PartImage]:
    """Matching product photos can exist even when price/stock cannot be verified."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return []
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(n for n in nodes(json.loads(script)) if is_type(n, "Product"))
        except (ValueError, RecursionError):
            continue
    meta = parser.meta_images if len(products) == 1 else ()
    images = []
    for product in products:
        if title_matches(query, str(product.get("name", ""))):
            url = product_image_url(product, page.url, meta)
            if url and url not in {image.url for image in images}:
                images.append(
                    PartImage(
                        url=url,
                        kind="source",
                        label="Product reference · visual only",
                        source_url=page.url,
                    )
                )
    return images[:5]


def variant_url(page: Page, query: str) -> str | None:
    """Follow one explicitly declared variant on the same product path, then reverify."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(n for n in nodes(json.loads(script)) if is_type(n, "Product"))
        except (ValueError, RecursionError):
            continue
    if len(products) != 1:
        return None
    product = products[0]
    if not isinstance(product.get("name"), str) or not title_matches(query, product["name"]):
        return None
    offers = product.get("offers", [])
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list) or len(offers) != 1 or not isinstance(offers[0], dict):
        return None
    target = offers[0].get("url")
    if not isinstance(target, str) or not is_type(offers[0], "Offer"):
        return None
    source, dest = urlsplit(page.url), urlsplit(target)
    if (
        dest.scheme != "https"
        or dest.netloc != source.netloc
        or not same_url(dest.path, source.path)
        or source.query
        or dest.fragment
    ):
        return None
    params = parse_qs(dest.query)
    if set(params) != {"variant"} or len(params["variant"]) != 1:
        return None
    return target


def sane_price(raw: object) -> Decimal | None:
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price <= 0 or price > 10_000_000:
        return None
    if price != price.quantize(Decimal("0.01")):
        return None
    return price


STOCK = {
    "instock": "in_stock",
    "in stock": "in_stock",
    "outofstock": "out_of_stock",
    "out of stock": "out_of_stock",
    "oos": "out_of_stock",
    "soldout": "out_of_stock",
    "preorder": "preorder",
}


def stock_of(raw: object) -> str:
    key = str(raw or "").rsplit("/", 1)[-1].strip().lower().replace("_", "")
    return STOCK.get(key, STOCK.get(key.replace(" ", ""), "unknown"))


@dataclass
class OfferOption:
    """One INR price the page's structured data declares (a variant or the only offer)."""

    price: Decimal
    stock: str
    name: str | None = None
    sku: str | None = None
    url: str | None = None
    source: dict = dataclass_field(default_factory=dict, repr=False)


@dataclass
class ExtractedProduct:
    """A single Product with its declared INR offers; relevance is not judged here."""

    page: Page
    product: dict
    title: str
    options: list[OfferOption]
    meta_images: list[str]

    def resolved(self) -> OfferOption | None:
        """The one offer this page unambiguously sells, or None for a variant group."""
        if len(self.options) == 1:
            option = self.options[0]
            # A different variant URL requires its own page verification.
            if option.url and not same_url(option.url, self.page.url):
                return None
            return option
        # The page's own URL names the variant it sells; anything else is for the judge,
        # which picks a variant (or confirms that every variant matches the spec).
        own = [o for o in self.options if o.url and same_url(o.url, self.page.url)]
        return own[0] if len(own) == 1 else None

    def offer(self, option: OfferOption) -> VerifiedOffer:
        url = self.page.url
        if option.url and not same_url(option.url, self.page.url):
            target, page = urlsplit(urljoin(self.page.url, option.url)), urlsplit(self.page.url)
            if target.scheme == "https" and target.hostname == page.hostname:
                url = target.geturl()
        specs, evidence, conflicts = seller_specs(self.product, self.page, self.title)
        tax_included, tax_evidence = detect_tax_included(
            option.source, self.page.body.decode("utf-8", errors="replace")
        )
        return VerifiedOffer(
            url=url,
            seller=urlsplit(self.page.url).hostname,
            title=self.title,
            image_url=product_image_url(self.product, self.page.url, self.meta_images),
            price_inr=f"{option.price:.2f}",
            stock=option.stock,
            specs=specs,
            spec_evidence=evidence,
            spec_conflicts=conflicts,
            tax_included=tax_included,
            tax_evidence=tax_evidence,
        )


def offer_options(offers: object, currency: str | None = None) -> list[OfferOption] | None:
    """Flatten Offer / Offer list / AggregateOffer; None when a price range is unresolvable."""
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list):
        return []
    options: list[OfferOption] = []
    for entry in offers[:50]:
        if not isinstance(entry, dict):
            continue
        entry_currency = entry.get("priceCurrency") or currency
        if is_type(entry, "AggregateOffer"):
            nested = entry.get("offers")
            if nested:
                inner = offer_options(nested, entry_currency)
                if inner is None:
                    return None
                options.extend(inner)
                continue
            low, high = sane_price(entry.get("lowPrice")), sane_price(entry.get("highPrice"))
            if low is None or (high is not None and high != low):
                # A price range without its offers cannot be attributed to a variant.
                return None
            raw_price = low
        elif is_type(entry, "Offer"):
            raw_price = entry.get("price")
        else:
            continue
        price = sane_price(raw_price)
        if price is None or entry_currency != "INR":
            continue
        item = entry.get("itemOffered") if isinstance(entry.get("itemOffered"), dict) else {}
        name = entry.get("name") or item.get("name")
        sku = entry.get("sku") or item.get("sku")
        url = entry.get("url")
        options.append(
            OfferOption(
                price=price,
                stock=stock_of(entry.get("availability")),
                name=name[:300] if isinstance(name, str) else None,
                sku=str(sku)[:100] if isinstance(sku, (str, int)) else None,
                url=url if isinstance(url, str) and len(url) <= 2048 else None,
                source=entry,
            )
        )
    return options


def page_products(page: Page) -> tuple[list[dict], ProductScripts]:
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(node for node in nodes(json.loads(script)) if is_type(node, "Product"))
        except (ValueError, RecursionError):
            continue
    return products, parser


def extract_product(page: Page) -> ExtractedProduct | None:
    """The page's single JSON-LD Product with its INR offers (several variants allowed)."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    products, parser = page_products(page)
    # Category pages list several products; they are not product pages.
    if len(products) != 1:
        return None
    product = products[0]
    title = product.get("name")
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        return None
    options = offer_options(product.get("offers", []))
    if not options:
        return None
    return ExtractedProduct(page, product, title, options, parser.meta_images)


def verify_page(page: Page, query: str | None = None) -> VerifiedOffer | None:
    """Verified price/stock for an unambiguous product page.

    With a query string this keeps the legacy title gate (used when no spec judge runs).
    With ``query=None`` relevance is not judged here; the spec judge decides it.
    """
    extracted = extract_product(page)
    if extracted is None or not title_matches(query, extracted.title):
        return None
    option = extracted.resolved()
    return extracted.offer(option) if option else None


class MetaPrices(HTMLParser):
    """OpenGraph product meta tags and schema.org microdata price properties."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.prices: list[str] = []
        self.currencies: list[str] = []
        self.stock: list[str] = []
        self.titles: list[str] = []
        self.images: list[str] = []
        self.in_title = False
        self.doc_title: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        key = (values.get("property") or values.get("name") or "").lower()
        prop = (values.get("itemprop") or "").lower()
        content = values.get("content")
        if tag == "title":
            self.in_title = True
        if content is None and prop in {"price", "pricecurrency", "availability"}:
            content = values.get("href") if prop == "availability" else None
        if not isinstance(content, str) or len(self.prices) > 20:
            return
        if key in {"product:price:amount", "og:price:amount"} or prop == "price":
            self.prices.append(content.strip())
        elif key in {"product:price:currency", "og:price:currency"} or prop == "pricecurrency":
            self.currencies.append(content.strip().upper())
        elif key in {"product:availability", "og:availability"} or prop == "availability":
            self.stock.append(content)
        elif key == "og:title" or (prop == "name" and tag == "meta"):
            self.titles.append(content.strip())
        elif key in {"og:image:secure_url", "og:image"}:
            self.images.append(content)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.doc_title.append(data)


def meta_offer(page: Page, query: str | None = None) -> VerifiedOffer | None:
    """Fallback for pages whose Product JSON-LD has no offers (or no JSON-LD at all).

    Uses only seller-declared `product:price:*` / `og:price:*` meta tags or microdata
    `itemprop=price`: one distinct price, declared INR. Shopify pages are skipped because
    their meta price belongs to whichever variant is selected (the storefront JSON path
    handles them).
    """
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    products, _ = page_products(page)
    if len(products) > 1 or any(offer_options(p.get("offers", [])) for p in products):
        return None
    from bharat_sourcer.sourcing.platforms import detect_platform

    if detect_platform(page) == "shopify":
        return None
    parser = MetaPrices()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    prices = {sane_price(raw) for raw in parser.prices}
    if len(prices) != 1 or None in prices or set(parser.currencies) != {"INR"}:
        return None
    price = prices.pop()
    product = products[0] if products else {}
    title = product.get("name") if isinstance(product.get("name"), str) else None
    title = title or next(iter(parser.titles), None) or " ".join("".join(parser.doc_title).split())
    if not title or len(title) > 500 or not title_matches(query, title):
        return None
    stocks = {stock_of(raw) for raw in parser.stock} - {"unknown"}
    specs, evidence, conflicts = seller_specs(product, page, title)
    tax_included, tax_evidence = detect_tax_included({}, page.body.decode("utf-8", "replace"))
    return VerifiedOffer(
        url=page.url,
        seller=urlsplit(page.url).hostname,
        title=title,
        image_url=product_image_url(product, page.url, parser.images[:5]),
        price_inr=f"{price:.2f}",
        stock=stocks.pop() if len(stocks) == 1 else "unknown",
        verification="seller_meta_tags",
        specs=specs,
        spec_evidence=evidence,
        spec_conflicts=conflicts,
        tax_included=tax_included,
        tax_evidence=tax_evidence,
    )


INVALID = object()


def seller_specs(product: dict, page: Page, title: str):
    """Combine title, JSON-LD property and spec-table values; disagreement means unknown."""
    candidates: dict[str, list[tuple[object, SpecEvidence]]] = {}

    def add(field, value, source, shown=None):
        shown = shown or str(value)
        evidence = SpecEvidence(field=field, value=shown, source=source, locator=page.url)
        candidates.setdefault(field, []).append((value, evidence))

    for field, value in parse_name(title).model_dump(exclude_none=True).items():
        add(field, value, "seller_title")
    properties = product.get("additionalProperty", [])
    if isinstance(properties, dict):
        properties = [properties]
    for prop in properties[:100] if isinstance(properties, list) else []:
        if not isinstance(prop, dict) or not is_type(prop, "PropertyValue"):
            continue
        name, raw = prop.get("name"), prop.get("value")
        if not isinstance(name, str) or raw is None:
            continue
        if name in PartSpecs.model_fields:
            try:
                add(name, getattr(PartSpecs(**{name: raw}), name), "seller_property")
            except (ValueError, TypeError):
                # An invalid explicit value is a contradiction, not an absence.
                add(name, INVALID, "seller_property", shown=f"invalid: {str(raw)[:50]}")
        elif field := label_field(name):
            for key, value in parse_value(field, raw, label_unit(name)).items():
                add(key, value, "seller_property")
    for field, value, _label in table_specs(page.body.decode("utf-8", errors="replace")):
        add(field, value, "seller_table")
    values, evidence, conflicts = {}, [], []
    priority = {"seller_property": 0, "seller_table": 1, "seller_title": 2}
    for field, entries in candidates.items():
        if len({str(value) for value, _ in entries}) > 1 or INVALID in [v for v, _ in entries]:
            unique = list({(e.value, e.source): e for _, e in entries}.values())
            conflicts.append(SpecConflict(field=field, candidates=unique[:20]))
            continue
        value, best = min(entries, key=lambda entry: priority[entry[1].source])
        values[field] = value
        evidence.append(best)
    try:
        return PartSpecs(**values), evidence, conflicts
    except ValueError:
        return PartSpecs(), [], conflicts
