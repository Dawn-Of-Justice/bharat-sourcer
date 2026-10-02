"""Read explicit Product/Offer JSON-LD; never infer price or availability from prose."""

import json
import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import urlsplit

from bharat_sourcer.compat import parse_name
from bharat_sourcer.schemas import PartSpecs, SpecEvidence, VerifiedOffer
from bharat_sourcer.sourcing.fetch import Page


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
        return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if aliases.get(word, word)}

    expected, actual = tokens(query), tokens(title)
    return bool(expected) and expected.issubset(actual)


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
    values = parse_name(title).model_dump(exclude_none=True)
    evidence = {
        field: SpecEvidence(field=field, value=str(value), source="seller_title", locator=page.url)
        for field, value in values.items()
    }
    properties = product.get("additionalProperty", [])
    if isinstance(properties, dict):
        properties = [properties]
    if isinstance(properties, list):
        grouped = {}
        for prop in properties[:100]:
            if not isinstance(prop, dict) or not is_type(prop, "PropertyValue"):
                continue
            field = prop.get("name")
            if (
                isinstance(field, str)
                and field in PartSpecs.model_fields
                and prop.get("value") is not None
            ):
                grouped.setdefault(field, []).append(prop["value"])
        for field, entries in grouped.items():
            try:
                parsed = [getattr(PartSpecs(**{field: entry}), field) for entry in entries]
                if any(value != parsed[0] for value in parsed):
                    raise ValueError("Conflicting property values")
                if field in values and values[field] != parsed[0]:
                    raise ValueError("Title conflicts with property")
                values[field] = parsed[0]
                evidence[field] = SpecEvidence(
                    field=field, value=str(parsed[0]), source="seller_property", locator=page.url
                )
            except (ValueError, TypeError):
                values.pop(field, None)
                evidence.pop(field, None)
    try:
        specs = PartSpecs(**values)
    except ValueError:
        specs, evidence = PartSpecs(), {}
    return VerifiedOffer(
        url=page.url,
        seller=urlsplit(page.url).hostname,
        title=title,
        price_inr=f"{price:.2f}",
        stock=stock,
        specs=specs,
        spec_evidence=list(evidence.values()),
    )
