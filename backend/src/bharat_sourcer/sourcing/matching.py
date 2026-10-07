"""Candidate listings for the spec judge, and the few deterministic match guardrails.

Relevance is decided by the LLM judge (`judge.py`). This module only:

- builds the compact, bounded listing the judge sees (title, key spec rows, a short
  description, a <=800-char visible-text snippet, variant names and declared prices);
- takes a cost shortcut when structured data states every spec value exactly
  (`deterministic_shortcut`), so unambiguous cases need no model call;
- flags a title that states a different value than the spec (a server-side check on
  model verdicts; it can downgrade a verdict, never upgrade one).
"""

import html
import re
from dataclasses import dataclass, field

from bharat_sourcer.schemas import BuyableSpec, OfferMatch, VerifiedOffer
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import (
    ExtractedProduct,
    OfferOption,
    extract_product,
    page_products,
)
from bharat_sourcer.sourcing.part_spec import (
    find_measures,
    normalise_text,
    pack_quantity,
    param_matches,
)
from bharat_sourcer.sourcing.research import VisibleText, clean
from bharat_sourcer.sourcing.specs import SpecTables

SNIPPET_CHARS = 800
ROW_LIMIT = 12
CATEGORY_TERMS = {
    "resistor": ["resistor", "resistance"],
    "capacitor_electrolytic": ["electrolytic"],
    "capacitor_ceramic": ["ceramic capacitor", "mlcc", "ceramic"],
    "led": ["led"],
    "ldr": ["ldr", "photoresistor", "light dependent resistor", "photocell"],
    "wire": ["wire"],
    "diode": ["diode"],
    "transistor": ["transistor", "mosfet"],
    "switch": ["switch", "button"],
    "battery": ["battery", "cell"],
    "connector": ["connector", "header", "terminal"],
}
THT = re.compile(r"(?i)through[\s-]*hole|\btht\b|\baxial\b|\bradial\b|\bdip\b|\bpth\b")
SMD = re.compile(
    r"(?i)\bsmd\b|\bsmt\b|surface[\s-]*mount|\bchip resistor\b|\b(?:0402|0603|0805|1206)\b"
)


@dataclass
class Candidate:
    """One fetched product page offered to the judge for a BOM line."""

    url: str
    title: str
    offer: VerifiedOffer | None
    options: list[OfferOption] = field(default_factory=list)
    rows: list[str] = field(default_factory=list)
    description: str = ""
    snippet: str = ""
    # Set when the page declares several variants; the judge picks one.
    extracted: ExtractedProduct | None = field(default=None, repr=False)

    def variant_names(self) -> list[str]:
        return [o.name or o.sku or f"variant {i}" for i, o in enumerate(self.options)]

    def structured_text(self) -> str:
        return "\n".join([self.title, *self.rows, self.description])

    def listing(self, candidate_id: int) -> dict:
        """Exactly what the judge is shown; quotes are verified against this."""
        entry = {
            "candidate_id": candidate_id,
            "title": self.title,
            "spec_rows": self.rows,
            "description": self.description,
            "page_text": self.snippet,
        }
        if self.offer is not None:
            entry["price_inr"] = self.offer.price_inr
            entry["stock"] = self.offer.stock
        if len(self.options) > 1:
            entry["variants"] = [
                {"variant_id": i, "name": name, "price_inr": f"{o.price:.2f}", "stock": o.stock}
                for i, (name, o) in enumerate(zip(self.variant_names(), self.options, strict=True))
            ][:20]
        return entry

    def quote_text(self) -> str:
        return clean(
            " \n".join(
                [self.title, *self.rows, self.description, self.snippet, *self.variant_names()]
            )
        ).casefold()


def strip_tags(text: str) -> str:
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def spec_rows(page: Page, product: dict) -> list[str]:
    rows = []
    properties = product.get("additionalProperty", [])
    if isinstance(properties, dict):
        properties = [properties]
    for prop in properties[:30] if isinstance(properties, list) else []:
        if isinstance(prop, dict) and isinstance(prop.get("name"), str) and prop.get("value"):
            rows.append(f"{prop['name']}: {prop['value']}")
    tables = SpecTables(max_rows=40)
    tables.feed(page.body.decode("utf-8", errors="replace"))
    rows += [f"{label}: {value}" for label, value in tables.rows]
    kept, seen = [], set()
    for row in rows:
        row = clean(row)[:160]
        if row.casefold() not in seen:
            seen.add(row.casefold())
            kept.append(row)
    return kept[:ROW_LIMIT]


def snippet_of(page: Page, title: str, limit: int) -> str:
    visible = VisibleText()
    visible.feed(page.body.decode("utf-8", errors="replace"))
    text = clean(" ".join(visible.parts))
    # Start at the product title; navigation menus before it are noise.
    start = text.find(title[:40]) if title else -1
    return text[max(start, 0) : max(start, 0) + limit]


def build_candidate(
    page: Page,
    offer: VerifiedOffer | None,
    snippet_chars: int = SNIPPET_CHARS,
    extracted: ExtractedProduct | None = None,
) -> Candidate | None:
    """Candidate from a fetched page and the offer verified from it (if unambiguous).

    `extracted` overrides the page's own structured data (a Shopify variant group read from
    the store's product JSON).
    """
    extracted = extracted or extract_product(page)
    options = extracted.options if extracted else []
    if offer is None and len(options) < 2:
        return None
    products, _ = page_products(page)
    product = extracted.product if extracted else (products[0] if len(products) == 1 else {})
    title = offer.title if offer else extracted.title
    description = product.get("description") if isinstance(product, dict) else None
    return Candidate(
        url=str(offer.url) if offer else page.url,
        title=title,
        offer=offer,
        options=options if len(options) > 1 else [],
        rows=spec_rows(page, product if isinstance(product, dict) else {}),
        description=strip_tags(description)[:300] if isinstance(description, str) else "",
        snippet=snippet_of(page, title, snippet_chars),
        extracted=extracted if len(options) > 1 else None,
    )


def has_term(text: str, term: str) -> bool:
    pattern = r"(?<![\w])" + re.escape(term.casefold()) + r"(?:s|es)?(?![\w])"
    return re.search(pattern, text) is not None


def title_conflicts(spec: BuyableSpec, title: str) -> list[str]:
    """Required numeric params the title contradicts (states another value, never this one)."""
    measures = find_measures(title, spec.category in {"resistor", "ldr"})
    conflicts = []
    for param in spec.params:
        if not param.required or param.si_value is None:
            continue
        same = [m for m in measures if m.unit == param.unit]
        if same and not any(param_matches(param, m) for m in same):
            conflicts.append(param.name)
    return conflicts


def excluded_terms(spec: BuyableSpec, text: str) -> list[str]:
    folded = normalise_text(text).casefold()
    return [term for term in spec.exclude if has_term(folded, normalise_text(term))]


def shortcut_match(spec: BuyableSpec, candidate: Candidate) -> OfferMatch | None:
    """An exact verdict without a model call, only when nothing is uncertain."""
    if (
        spec.origin == "seed"
        or spec.category == "other"
        or spec.needs_value
        or not spec.params
        or candidate.offer is None
        or candidate.options
    ):
        return None
    structured = candidate.structured_text()
    folded = normalise_text(structured).casefold()
    terms = CATEGORY_TERMS.get(spec.category, []) + spec.synonyms
    if not any(has_term(folded, normalise_text(t)) for t in terms):
        return None
    if excluded_terms(spec, structured) or title_conflicts(spec, candidate.title):
        return None
    measures = find_measures(structured, spec.category in {"resistor", "ldr"})
    for param in spec.params:
        if param.si_value is None:
            if not has_term(folded, normalise_text(param.value)):
                return None
        elif not any(param_matches(param, m) for m in measures):
            return None
    mount_text = structured + "\n" + candidate.snippet
    if spec.mount == "tht" and (not THT.search(mount_text) or SMD.search(structured)):
        return None
    if spec.mount == "smd" and not SMD.search(mount_text):
        return None
    return OfferMatch(
        status="exact",
        score=1.0,
        matched=["category", *[p.name for p in spec.params]]
        + (["mount"] if spec.mount != "any" else []),
        reasons=["The listing's structured data states every spec value; judge not needed."],
        pack_qty=pack_quantity(candidate.title),
        method="deterministic_shortcut",
    )
