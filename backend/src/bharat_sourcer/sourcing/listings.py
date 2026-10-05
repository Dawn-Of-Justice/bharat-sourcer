"""Read explicit Product/Offer JSON-LD; never infer price or availability from prose."""

import json
import re
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
from bharat_sourcer.sourcing.specs import label_field, parse_value, table_specs


class ProductScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.buffer = []

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


def title_matches(query: str, title: str) -> bool:
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


def product_image_url(product: dict, page_url: str) -> str | None:
    """Return the first safe HTTPS image explicitly attached to this Product entity."""
    images = product.get("image")
    if isinstance(images, (str, dict)):
        images = [images]
    if not isinstance(images, list):
        return None
    for image in images[:20]:
        if isinstance(image, dict):
            image = image.get("url") or image.get("contentUrl")
        if not isinstance(image, str) or not image.strip() or len(image) > 2048:
            continue
        try:
            url = urljoin(page_url, image.strip())
            parsed = urlsplit(url)
            if (
                len(url) <= 2048
                and parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and parsed.port in (None, 443)
                and not any(c in url for c in "\r\n\t")
            ):
                return url
        except (ValueError, UnicodeError):
            continue
    return None


def page_images(page: Page, query: str) -> list[PartImage]:
    """Matching product photos can exist even when price/stock cannot be verified."""
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return []
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    images = []
    for script in parser.scripts[:30]:
        try:
            for product in nodes(json.loads(script)):
                if not is_type(product, "Product") or not title_matches(
                    query, str(product.get("name", ""))
                ):
                    continue
                url = product_image_url(product, page.url)
                if url and url not in {image.url for image in images}:
                    images.append(
                        PartImage(
                            url=url,
                            kind="source",
                            label="Product reference · visual only",
                            source_url=page.url,
                        )
                    )
        except (ValueError, RecursionError):
            continue
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
        or dest.path.rstrip("/") != source.path.rstrip("/")
        or source.query
        or dest.fragment
    ):
        return None
    params = parse_qs(dest.query)
    if set(params) != {"variant"} or len(params["variant"]) != 1:
        return None
    return target


def verify_page(page: Page, query: str) -> VerifiedOffer | None:
    if page.status != 200 or "text/html" not in page.headers.get("content-type", ""):
        return None
    parser = ProductScripts()
    parser.feed(page.body.decode("utf-8", errors="replace"))
    products = []
    for script in parser.scripts[:30]:
        try:
            products.extend(node for node in nodes(json.loads(script)) if is_type(node, "Product"))
        except (ValueError, RecursionError):
            continue
    # Category pages and unresolved variant groups are not single-product offers.
    if len(products) != 1:
        return None
    product = products[0]
    title = product.get("name")
    if not isinstance(title, str) or len(title) > 500 or not title_matches(query, title):
        return None
    offers = product.get("offers", [])
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list) or len(offers) != 1 or not isinstance(offers[0], dict):
        return None
    offer = offers[0]
    if not is_type(offer, "Offer") or offer.get("priceCurrency") != "INR":
        return None
    if offer.get("url"):
        # A different variant URL requires its own page verification.
        if str(offer["url"]).split("#")[0].rstrip("/") != page.url.split("#")[0].rstrip("/"):
            return None
    try:
        price = Decimal(str(offer["price"]))
        if not price.is_finite() or price <= 0 or price > 10_000_000:
            return None
        if price != price.quantize(Decimal("0.01")):
            return None
    except (KeyError, InvalidOperation, ValueError):
        return None
    stock = {"InStock": "in_stock", "OutOfStock": "out_of_stock", "PreOrder": "preorder"}.get(
        str(offer.get("availability", "")).rsplit("/", 1)[-1], "unknown"
    )
    specs, evidence, conflicts = seller_specs(product, page, title)
    return VerifiedOffer(
        url=page.url,
        seller=urlsplit(page.url).hostname,
        title=title,
        image_url=product_image_url(product, page.url),
        price_inr=f"{price:.2f}",
        stock=stock,
        specs=specs,
        spec_evidence=evidence,
        spec_conflicts=conflicts,
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
            for key, value in parse_value(field, raw).items():
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
