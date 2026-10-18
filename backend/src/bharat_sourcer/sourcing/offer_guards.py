"""Seller-stated listing facts that must survive every model and fallback path."""

import re

from bharat_sourcer.schemas import BuyableSpec, OfferMatch, VerifiedOffer
from bharat_sourcer.sourcing.part_spec import pack_quantity


def fill_pack_quantity(offer: VerifiedOffer) -> None:
    """Recover an explicit title pack count without overwriting variant-specific data."""
    if offer.pack_qty is None:
        offer.pack_qty = pack_quantity(offer.title)
    if isinstance(offer.match, OfferMatch) and offer.match.pack_qty is None:
        offer.match.pack_qty = offer.pack_qty


def pitch_conflict(spec: BuyableSpec | None, offer: VerifiedOffer) -> bool:
    if spec is None:
        return False
    required = [
        p
        for p in spec.params
        if p.required and "pitch" in p.name.lower() and p.operator == "equals"
    ]
    if not required:
        return False
    title = offer.title.lower()
    # Prefer an explicitly labelled pitch. A single mm value in a header/connector
    # title is also usable, but multiple unlabelled dimensions are ambiguous.
    values = re.findall(r"(\d+(?:\.\d+)?)\s*mm\s*(?:pin\s*)?pitch", title)
    values += re.findall(r"pitch\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mm", title)
    if not values and re.search(r"\b(?:headers?|connectors?)\b", title):
        values = re.findall(r"(\d+(?:\.\d+)?)\s*mm\b", title)
    offered = {float(v) for v in values}
    if len(offered) != 1:
        return False
    # Explicitly reviewed wiring/adapter changes can accommodate a different pitch.
    compatibility = offer.compatibility
    if compatibility and compatibility.grade == "B" and compatibility.changes:
        changes = " ".join(compatibility.changes).lower()
        if "pitch" in changes and re.search(r"adapter|wir(?:e|ing)|breakout", changes):
            return False
    for param in required:
        if param.unit == "m" and param.si_value is not None:
            expected = param.si_value * 1000
        else:
            parsed = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*mm\s*", param.value)
            if not parsed:
                continue
            expected = float(parsed.group(1))
        if abs(next(iter(offered)) - expected) > 0.02:
            return True
    return False


def guard_offer(spec: BuyableSpec | None, offer: VerifiedOffer) -> None:
    fill_pack_quantity(offer)
    if pitch_conflict(spec, offer):
        previous = offer.match
        offer.match = OfferMatch(
            status="mismatch",
            score=0.0,
            conflicts=["pitch"],
            reasons=["Seller-stated connector pitch conflicts with the required PCB pitch."],
            method="deterministic_shortcut",
            pack_qty=offer.pack_qty,
            claims=previous.claims if isinstance(previous, OfferMatch) else [],
        )
