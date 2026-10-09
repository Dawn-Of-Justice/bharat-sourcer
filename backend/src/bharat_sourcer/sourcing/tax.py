"""Read whether a seller's price includes GST from explicit declarations only.

Signals come from Offer/priceSpecification `valueAddedTaxIncluded` in JSON-LD and from
fixed page phrases such as "incl. GST" or "(Exclusive GST Tax 18%)". Disagreeing signals
leave the status unknown. The legal MRP line ("MRP ... inclusive of all taxes") describes
the maximum retail price, not the selling price, so it is ignored.
"""

import html
import re

INCLUDED = re.compile(
    r"\b(?:incl(?:\.|usive|uding|udes)?|inc\.?)\s*(?:of\s+)?(?:all\s+)?(?:\d+(?:\.\d+)?%\s*)?(?:gst|taxes|tax)\b"
    r"|\bwith\s+gst\b|\b(?:gst|taxes|tax)\s+(?:incl(?:\.|uded|usive)?|inclusive)\b",
    re.IGNORECASE,
)
EXCLUDED = re.compile(
    r"\b(?:excl(?:\.|usive|uding|udes)?|ex)[\s.-]*(?:of\s+)?(?:all\s+)?(?:\d+(?:\.\d+)?%\s*)?(?:gst|taxes|tax)\b"
    r"|\bwithout\s+gst\b|\+\s*gst\b|\bplus\s+gst\b|\b(?:gst|taxes)\s+(?:extra|excluded|additional)\b",
    re.IGNORECASE,
)
MRP = re.compile(r"\bm\.?r\.?p\b", re.IGNORECASE)
TEXT_LIMIT = 300_000


def boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return None


def specifications(offer: dict) -> list[dict]:
    """priceSpecification may be a dict, a list, or (WooCommerce) a dict keyed "0", "1"."""
    spec = offer.get("priceSpecification")
    if isinstance(spec, list):
        return [s for s in spec[:10] if isinstance(s, dict)]
    if not isinstance(spec, dict):
        return []
    found = [spec] if "valueAddedTaxIncluded" in spec else []
    found.extend(v for k, v in list(spec.items())[:10] if k.isdigit() and isinstance(v, dict))
    return found


def page_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", body[:TEXT_LIMIT])
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


def text_signals(text: str) -> list[tuple[bool, str]]:
    signals = []
    for value, pattern in ((True, INCLUDED), (False, EXCLUDED)):
        for match in pattern.finditer(text):
            if MRP.search(text[max(0, match.start() - 60) : match.start()]):
                continue
            signals.append((value, match.group(0)))
            break
    return signals


def detect_tax_included(offer: dict, body: str) -> tuple[bool | None, str | None]:
    """Return (tax_included, evidence); None when nothing is declared or signals conflict."""
    signals = []
    for source in [offer, *specifications(offer)]:
        if (value := boolean(source.get("valueAddedTaxIncluded"))) is not None:
            signals.append((value, f"JSON-LD valueAddedTaxIncluded={str(value).lower()}"))
    for value, quote in text_signals(price_text(body)):
        signals.append((value, f'page text "{quote}"'))
    if not signals:
        return None, None
    evidence = "; ".join(dict.fromkeys(e for _, e in signals))[:300]
    if len({value for value, _ in signals}) > 1:
        return None, f"Conflicting tax declarations: {evidence}"[:300]
    return signals[0][0], evidence


def price_text(body: str) -> str:
    """Limit tax declarations to price blocks, excluding navigation and recommendations."""
    body = re.sub(r"(?is)<(footer|aside|nav|script|style)\b[^>]*>.*?</\1>", " ", body[:TEXT_LIMIT])
    body = re.sub(
        r'(?is)<(?:div|section)\b[^>]*(?:class|id)=["\'][^"\']*(?:related|recommend)[^"\']*["\'][^>]*>.*',
        " ",
        body,
    )
    blocks = re.findall(
        r'(?is)<(?:div|p|span)\b[^>]*(?:class|id)=["\'][^"\']*(?:price|offer)[^"\']*["\'][^>]*>(.*?)</(?:div|p|span)>',
        body,
    )
    if blocks:
        return " ".join(page_text(block) for block in blocks)
    text = page_text(body)
    # Small standalone declarations remain useful, e.g. a price block passed by a caller.
    if len(text) <= 250:
        return text
    return " ".join(
        text[max(0, m.start() - 50) : m.end() + 100]
        for m in re.finditer(r"(?:\u20b9|Rs\.?|INR)\s*[0-9][0-9,.]*", text)
    )
