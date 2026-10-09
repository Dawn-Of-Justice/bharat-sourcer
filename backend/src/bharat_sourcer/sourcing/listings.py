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
from bharat_sourcer.sourcing.sellers import canonical_url, host_of, identify, same_listing
from bharat_sourcer.sourcing.specs import label_field, label_unit, parse_value, table_specs
from bharat_sourcer.sourcing.tax import detect_tax_included, price_text
from bharat_sourcer.sourcing.textmatch import title_gate


class ProductScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.meta_images: list[str] = []
        self.buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and (values.get("type") or "").lower().startswith("application/ld+json"):
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
        yield from nodes(value.get("mainEntity", []))


def is_type(value: dict, expected: str) -> bool:
    types = value.get("@type", [])
    if isinstance(types, str):
        types = [types]
    return isinstance(types, list) and any(
        isinstance(kind, str) and re.split(r"[/:]", kind)[-1] == expected for kind in types
    )


def title_matches(query: str | None, title: str) -> bool:
    """Legacy relevance gate, used only when no spec judge is configured or it failed.

    ``query=None`` means relevance is decided later by the spec judge (`judge.py`), so
    extraction functions shared with that path accept every title.
    """
    if query is None:
        return True
    return title_gate(query, title)


# Storefront "no image" assets are not product photos (e.g. Shopify's no-image-2048.gif).
PLACEHOLDER_IMAGE = re.compile(
    r"no[-_]?image|noimage|placeholder|default[-_]?(?:product|image)"
    r"|image[-_]?not[-_]?available|coming[-_]?soon",
    re.IGNORECASE,
)


def same_url(left: str, right: str) -> bool:
    """Compare listing identity while preserving functional variant parameters."""
    return same_listing(left, right, base=right)


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
    if page_rejection(page):
        return []
    products, parser = page_products(page)
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


def variant_url(page: Page, query: str | None) -> str | None:
    """Follow one explicitly declared variant on the same product path, then reverify."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    if page_rejection(page):
        return None
    extracted = extract_product(page)
    if extracted is None or not title_matches(query, extracted.title):
        return None
    if len(extracted.options) != 1:
        return None
    target = extracted.options[0].url
    if not isinstance(target, str):
        return None
    target = canonical_url(urljoin(page.url, target))
    source, dest = urlsplit(canonical_url(page.url)), urlsplit(target)
    if (
        dest.scheme != "https"
        or host_of(dest.netloc) != host_of(source.netloc)
        or not same_url(dest.path, source.path)
        or source.query
        or dest.fragment
    ):
        return None
    params = parse_qs(dest.query)
    if set(params) != {"variant"} or len(params["variant"]) != 1:
        return None
    return target


def parse_inr(raw: object, declared_currency: str | None = None) -> Decimal | None:
    """Strict seller-declared rupee amount, including Western and lakh grouping."""
    if isinstance(raw, bool) or raw is None:
        return None
    text = str(raw).strip().replace("\xa0", " ")
    explicit = bool(re.search(r"\u20b9|\b(?:INR|Rs\.?)", text, re.I))
    if declared_currency and str(declared_currency).strip().upper() != "INR":
        return None
    if not declared_currency and not explicit:
        return None
    text = re.sub(r"^(?:\u20b9|INR\b|Rs\.?)\s*", "", text, flags=re.I)
    text = re.sub(r"\s*/-$", "", text).strip()
    if not re.fullmatch(
        r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]+)?", text
    ):
        return None
    try:
        price = Decimal(text.replace(",", ""))
        if not price.is_finite() or not 0 < price <= 10_000_000:
            return None
        return price if price == price.quantize(Decimal("0.01")) else None
    except (InvalidOperation, ValueError):
        return None


def sane_price(raw: object) -> Decimal | None:
    """Compatibility helper for callers with an already declared INR currency."""
    return parse_inr(raw, "INR")


STOCK = {
    "instock": "in_stock",
    "in stock": "in_stock",
    "outofstock": "out_of_stock",
    "out of stock": "out_of_stock",
    "oos": "out_of_stock",
    "soldout": "out_of_stock",
    "preorder": "preorder",
    "presale": "preorder",
    "backorder": "preorder",
    "limitedavailability": "in_stock",
    "onlineonly": "in_stock",
    "discontinued": "out_of_stock",
}


def stock_of(raw: object) -> str:
    key = re.split(r"[/:]", str(raw or "").rstrip("/"))[-1].strip().lower().replace("_", "")
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
    # How the prices were read; Shopify variant groups come from the public product JSON.
    verification: str = "seller_structured_data"

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
            verification=self.verification,
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
        specs = entry.get("priceSpecification", [])
        specs = [specs] if isinstance(specs, dict) else specs
        specs = (
            [
                v
                for v in specs
                if isinstance(v, dict)
                and str(v.get("priceType", "")).rsplit("/", 1)[-1].lower()
                not in {"listprice", "strikethroughprice", "msrp"}
            ]
            if isinstance(specs, list)
            else []
        )
        spec = specs[0] if len(specs) == 1 else {}
        entry_currency = entry.get("priceCurrency") or spec.get("priceCurrency") or currency
        if is_type(entry, "AggregateOffer"):
            nested = entry.get("offers")
            if nested:
                inner = offer_options(nested, entry_currency)
                options.extend(inner or [])
                continue
            low, high = sane_price(entry.get("lowPrice")), sane_price(entry.get("highPrice"))
            if low is None or (high is not None and high != low):
                # A price range without its offers cannot be attributed to a variant.
                continue
            raw_price = low
        elif is_type(entry, "Offer") or (not entry.get("@type") and ("price" in entry or specs)):
            raw_price = entry.get("price", spec.get("price"))
        else:
            continue
        price = parse_inr(raw_price, entry_currency)
        if price is None:
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


def load_script(script: str):
    script = re.sub(r"^\s*<!--|-->\s*$", "", script).strip()
    script = re.sub(r"^\s*(?://\s*)?<!\[CDATA\[", "", script)
    script = re.sub(r"(?://\s*)?\]\]>\s*$", "", script).strip()
    try:
        return json.loads(script)
    except json.JSONDecodeError:
        # Repair only punctuation outside strings; do not alter text or numbers.
        repaired, quoted, escaped = [], False, False
        for i, char in enumerate(script):
            if quoted:
                repaired.append(json.dumps(char)[1:-1] if ord(char) < 32 else char)
                if char == '"' and not escaped:
                    quoted = False
                escaped = char == "\\" and not escaped
            else:
                if char == '"':
                    quoted = True
                if char == "," and script[i + 1 :].lstrip().startswith(("}", "]")):
                    continue
                repaired.append(char)
        return json.loads("".join(repaired))


def is_product(node):
    return any(
        is_type(node, kind)
        for kind in ("Product", "ProductGroup", "IndividualProduct", "ProductModel")
    )


def clean_title(title: str, url: str) -> str:
    seller = identify(url)
    parts = re.split(r"\s+(?:\||-|\u2013)\s+", title)
    if len(parts) > 1:
        tail = re.sub(r"[^a-z0-9]", "", parts[-1].lower())
        aliases = (seller.name, seller.domain, seller.domain.split(".")[0])
        if any(
            tail.startswith(re.sub(r"[^a-z0-9]", "", alias.lower())) for alias in aliases if alias
        ):
            return title[: len(title) - len(parts[-1])].rstrip(" |-\u2013")
    return title


def page_rejection(page: Page) -> str | None:
    body = page.body.decode("utf-8", "replace")
    headings = re.findall(r"<(?:title|h1)\b[^>]*>(.*?)</(?:title|h1)>", body, re.I | re.S)
    if any(
        re.search(
            r"\b(?:page not found|product not found|no longer available|404)\b",
            re.sub(r"<[^>]+>", " ", heading),
            re.I,
        )
        for heading in headings
    ):
        return "soft_404"
    path = urlsplit(page.url).path.lower()
    if path in {"", "/"} or (
        re.match(r"^/(?:collections|category|product-category|search)(?:/|$)", path)
        and "/products/" not in path
    ):
        return "category_page"
    return None


def reject_reason(page: Page) -> str:
    if reason := page_rejection(page):
        return reason
    products, _ = page_products(page)
    if len(products) > 1:
        return "category_page"
    for product in products:
        for node in [product, *nodes(product.get("offers", []))]:
            currency = node.get("priceCurrency")
            if currency and str(currency).upper() != "INR":
                return "not_inr"
    return "no_structured_price"


def page_products(page: Page) -> tuple[list[dict], ProductScripts]:
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(node for node in nodes(load_script(script)) if is_product(node))
        except (ValueError, RecursionError):
            continue
    unique = {}
    for product in products:
        identity = product.get("@id") or product.get("url")
        key = (
            str(identity)
            if identity
            else json.dumps(
                {k: product.get(k) for k in ("name", "sku", "offers", "hasVariant")}, sort_keys=True
            )
        )
        unique.setdefault(key, product)
    return list(unique.values()), parser


def extract_product(page: Page) -> ExtractedProduct | None:
    """The page's single JSON-LD Product with its INR offers (several variants allowed)."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    if page_rejection(page):
        return None
    products, parser = page_products(page)
    # Category pages list several products; they are not product pages.
    if len(products) != 1:
        return None
    product = products[0]
    title = product.get("name")
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        return None
    title = clean_title(title, page.url)
    options = offer_options(product.get("offers", []), product.get("priceCurrency")) or []
    variants = product.get("hasVariant", [])
    variants = [variants] if isinstance(variants, dict) else variants
    for variant in variants[:50] if isinstance(variants, list) else []:
        if not isinstance(variant, dict):
            continue
        for option in (
            offer_options(
                variant.get("offers", []),
                variant.get("priceCurrency") or product.get("priceCurrency"),
            )
            or []
        ):
            option.name = option.name or variant.get("name")
            option.sku = option.sku or variant.get("sku")
            option.url = option.url or variant.get("url")
            options.append(option)
    if not options:
        return None
    return ExtractedProduct(page, product, title, options, parser.meta_images)


def verify_page(page: Page, query: str | None = None, *, seller=None) -> VerifiedOffer | None:
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
        self.product_signal = False
        self.product_count = 0
        self.text_prop = None
        self.text_buffer = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        key = (values.get("property") or values.get("name") or "").lower()
        prop = (values.get("itemprop") or "").lower()
        content = values.get("content")
        if str(values.get("itemtype", "")).rstrip("/").rsplit("/", 1)[-1] == "Product":
            self.product_count += 1
        if key == "og:type" and content in {"product", "product.item"}:
            self.product_signal = True
        if prop in {"price", "pricecurrency"} and content is None:
            self.text_prop = (tag, prop)
            self.text_buffer = []
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
        if self.text_prop and tag == self.text_prop[0]:
            target = self.prices if self.text_prop[1] == "price" else self.currencies
            target.append("".join(self.text_buffer).strip())
            self.text_prop = None
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.doc_title.append(data)
        if self.text_prop:
            self.text_buffer.append(data)


def meta_offer(page: Page, query: str | None = None) -> VerifiedOffer | None:
    """Fallback for pages whose Product JSON-LD has no offers (or no JSON-LD at all).

    Uses only seller-declared `product:price:*` / `og:price:*` meta tags or microdata
    `itemprop=price`: one distinct price, declared INR. Shopify pages are skipped because
    their meta price belongs to whichever variant is selected (the storefront JSON path
    handles them).
    """
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    if page_rejection(page):
        return None
    products, _ = page_products(page)
    if len(products) > 1 or any(offer_options(p.get("offers", [])) for p in products):
        return None
    from bharat_sourcer.sourcing.platforms import detect_platform

    if detect_platform(page) == "shopify":
        return None
    parser = MetaPrices()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    path_signal = bool(re.search(r"/(?:products?|dp|p)/", urlsplit(page.url).path))
    if not (parser.product_signal or parser.product_count == 1 or path_signal):
        return None
    currencies = {v.upper() for v in parser.currencies}
    if currencies - {"INR"}:
        return None
    prices = {parse_inr(raw, "INR" if currencies else None) for raw in parser.prices}
    if len(prices) != 1 or None in prices:
        return None
    price = prices.pop()
    product = products[0] if products else {}
    title = product.get("name") if isinstance(product.get("name"), str) else None
    title = title or next(iter(parser.titles), None) or " ".join("".join(parser.doc_title).split())
    title = clean_title(title, page.url) if title else title
    if not title or len(title) > 500 or not title_matches(query, title):
        return None
    stocks = {stock_of(raw) for raw in parser.stock} - {"unknown"}
    specs, evidence, conflicts = seller_specs(product, page, title)
    tax_included, tax_evidence = detect_tax_included(
        {"price": str(price)}, page.body.decode("utf-8", "replace")
    )
    visible = price_text(page.body.decode("utf-8", "replace"))
    if tax_included is True:
        visible_prices = {
            parse_inr(m.group(), "INR")
            for m in re.finditer(r"(?:\u20b9|Rs\.?|INR)\s*[0-9][0-9,.]*", visible, re.I)
        } - {None}
        if visible_prices and price not in visible_prices:
            tax_included, tax_evidence = (
                None,
                "Tax-inclusive visible price differs from structured price",
            )
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
