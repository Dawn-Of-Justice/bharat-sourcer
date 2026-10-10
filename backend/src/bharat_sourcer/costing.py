"""Auditable INR cost estimates using Decimal arithmetic.

Seller-published prices are `known`. GST added to ex-GST prices, shipping from the dated
seller policy table and the import comparison are `estimated` and list their assumptions.
Anything without a sourced rule is `unknown`, never zero. Nothing here is a payable total.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cache, lru_cache
from importlib import resources
from typing import cast
from urllib.parse import urlsplit

from bharat_sourcer.schemas import (
    CostAmount,
    CostBreakdown,
    ImportBaseline,
    ImportReference,
    Report,
    ReportLine,
    SavingsEstimate,
    SellerCost,
    ShippingPolicyRef,
)
from bharat_sourcer.sourcing.sellers import registrable_domain

CENT = Decimal("0.01")
RANK = {"known": 0, "estimated": 1, "unknown": 2}
ZERO = Decimal("0")


def money(value: Decimal) -> str:
    return f"{value.quantize(CENT, ROUND_HALF_UP):.2f}"


def rupees(value: Decimal) -> str:
    return "₹" + money(value)


@cache
def load(name: str) -> dict:
    return json.loads(resources.files("bharat_sourcer").joinpath("data", name).read_text("utf-8"))


def seller_key(host: str | None) -> str:
    return registrable_domain(host or "")


def policy_for(seller: str) -> dict | None:
    return load("seller_policies.json")["sellers"].get(seller_key(seller))


def gst_percent(family: str | None) -> Decimal:
    rates = load("tax_rates.json")["gst"]
    return Decimal(rates["by_family"].get(family or "", rates["default_percent"]))


def pack_size(offer) -> int | None:
    """Units per listing when the seller states a pack (`pack_qty`, read defensively)."""
    value = getattr(offer, "pack_qty", None) if offer is not None else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 1 else None


def packs_for(qty: int, offer) -> int:
    """Listings to buy for `qty` units: rounded up to whole packs when the pack is known."""
    size = pack_size(offer)
    return -(-qty // size) if size else qty


# A bulk pack a maker would not buy for one build: at least BULK_UNITS times the need,
# at least BULK_MIN_INR, and BULK_RATIO times a cheaper usable listing for the same line.
BULK_UNITS = 20
BULK_RATIO = 5
BULK_MIN_INR = Decimal(100)


def cover_cost(qty: int, offer) -> Decimal:
    return Decimal(offer.price_inr) * packs_for(qty, offer)


def cheapest_cover(qty: int, offers) -> Decimal | None:
    """The lowest cost to cover `qty` among listings not out of stock and not mismatched."""
    costs = [
        cover_cost(qty, offer)
        for offer in offers
        if offer.stock != "out_of_stock"
        and getattr(getattr(offer, "match", None), "status", None) != "mismatch"
    ]
    return min(costs, default=None)


def bulk_waste(qty: int, offer, cheapest: Decimal | None) -> bool:
    """A pack far beyond the need while a much cheaper listing covers it."""
    size = pack_size(offer)
    if not size or size < BULK_UNITS * qty or cheapest is None:
        return False
    cost = cover_cost(qty, offer)
    return cost >= BULK_MIN_INR and cost >= BULK_RATIO * cheapest


@dataclass(frozen=True)
class Pick:
    """One line bought from one seller at a seller-published listing price.

    `qty` counts listings: units for single items, whole packs when the pack size is known.
    """

    line_id: str
    seller: str
    unit_price: Decimal
    qty: int
    tax_included: bool | None = None
    family: str | None = None
    offer_url: str = ""


@dataclass
class Charge:
    amount: Decimal | None
    status: str
    assumptions: list[str] = field(default_factory=list)
    partial: Decimal = ZERO

    def model(self) -> CostAmount:
        return CostAmount(
            amount_inr=None if self.amount is None else money(self.amount),
            status=self.status,
            partial_inr=money(self.partial) if self.status == "unknown" else None,
            assumptions=self.assumptions,
        )


def charge(amount: Decimal | None, status: str, *assumptions: str) -> Charge:
    return Charge(amount, status, list(assumptions), amount if amount is not None else ZERO)


def combine(charges: list[Charge]) -> Charge:
    status = max((c.status for c in charges), key=RANK.__getitem__, default="known")
    partial = sum((c.partial for c in charges), ZERO)
    assumptions = list(dict.fromkeys(a for c in charges for a in c.assumptions))
    return Charge(None if status == "unknown" else partial, status, assumptions, partial)


def gst_charge(pick: Pick) -> Charge:
    included, level = pick.tax_included, "known"
    source = "the seller page declares"
    if included is None:
        policy = (policy_for(pick.seller) or {}).get("gst") or {}
        if not policy.get("unverified") and policy.get("prices_include_gst") is not None:
            included, level = policy["prices_include_gst"], "estimated"
            source = f"seller policy table (checked {policy.get('checked_on')}) says"
    if included is None:
        return charge(None, "unknown", f"{pick.line_id}: whether the price includes GST is unknown")
    if included:
        return charge(ZERO, level, f"{pick.line_id}: {source} the price includes GST")
    rate = gst_percent(pick.family)
    amount = pick.unit_price * pick.qty * rate / 100
    return charge(
        amount,
        "estimated",
        f"{pick.line_id}: {source} the price excludes GST; added {rate}% "
        "(assumed rate, not tax advice)",
    )


def shipping_charge(seller: str, subtotal: Decimal) -> tuple[Charge, Decimal | None]:
    """Shipping from the policy table; returns (charge, amount still needed for free)."""
    entry = policy_for(seller)
    ship = (entry or {}).get("shipping")
    if not ship:
        return charge(None, "unknown", f"{seller}: no shipping policy on file"), None
    checked = ship.get("checked_on")
    if ship.get("unverified"):
        hint = f" ({ship['note']})" if ship.get("note") else ""
        return charge(None, "unknown", f"{seller}: shipping policy unverified{hint}"), None
    gap = None
    threshold = Decimal(ship["free_above_inr"]) if ship.get("free_above_inr") else None
    if threshold is not None:
        above = ship.get("free_when", "above") == "above"
        if subtotal > threshold or (not above and subtotal == threshold):
            word = "above" if above else "at or above"
            return charge(
                ZERO,
                "estimated",
                f"{seller}: free shipping {word} {rupees(threshold)} per policy checked "
                f"{checked}; listed-price subtotal {rupees(subtotal)}",
            ), None
        gap = threshold - subtotal + (CENT if above else ZERO)
    if not ship.get("flat_fee_inr"):
        reason = (
            f"below the {rupees(threshold)} free-shipping threshold and the fee is not stated"
            if threshold is not None
            else "fee not stated"
        )
        return charge(None, "unknown", f"{seller}: {reason}"), gap
    fee = Decimal(ship["flat_fee_inr"])
    amount = fee * (1 + gst_percent(None) / 100) if ship.get("fee_plus_gst") else fee
    plus = f" + {gst_percent(None)}% GST" if ship.get("fee_plus_gst") else ""
    below = f" below {rupees(threshold)}" if threshold is not None else ""
    return charge(
        amount,
        "estimated",
        f"{seller}: flat shipping {rupees(fee)}{plus}{below} per policy checked {checked}",
    ), gap


@lru_cache(maxsize=4096)
def seller_charges(seller: str, picks: tuple[Pick, ...]):
    parts = combine(
        [charge(p.unit_price * p.qty, "known", "Listed seller prices at checked_at") for p in picks]
    )
    gst = combine([gst_charge(p) for p in picks])
    shipping, gap = shipping_charge(seller, parts.partial)
    return parts, gst, shipping, combine([parts, gst, shipping]), gap


def policy_ref(seller: str) -> ShippingPolicyRef | None:
    ship = (policy_for(seller) or {}).get("shipping")
    if not ship:
        return None
    return ShippingPolicyRef(
        seller=seller_key(seller),
        free_above_inr=ship.get("free_above_inr"),
        free_when=ship.get("free_when", "above"),
        flat_fee_inr=ship.get("flat_fee_inr"),
        fee_plus_gst=bool(ship.get("fee_plus_gst")),
        unverified=bool(ship.get("unverified")),
        source_url=ship.get("source_url"),
        checked_on=ship.get("checked_on"),
        note=ship.get("note"),
    )


def group(picks: list[Pick]) -> dict[str, tuple[Pick, ...]]:
    sellers: dict[str, list[Pick]] = {}
    for pick in picks:
        sellers.setdefault(seller_key(pick.seller), []).append(pick)
    return {seller: tuple(items) for seller, items in sellers.items()}


def cost_picks(
    picks: list[Pick], excluded: list[str], *, basis: str = "selected_offers"
) -> CostBreakdown:
    sellers, rows = [], []
    for seller, items in group(picks).items():
        parts, gst, shipping, total, gap = seller_charges(seller, items)
        rows.append((parts, gst, shipping))
        sellers.append(
            SellerCost(
                seller=seller,
                line_ids=[p.line_id for p in items],
                parts=parts.model(),
                gst=gst.model(),
                shipping=shipping.model(),
                total=total.model(),
                free_shipping_gap_inr=money(gap) if gap is not None else None,
                policy=policy_ref(seller),
            )
        )
    parts = combine([r[0] for r in rows])
    gst = combine([r[1] for r in rows])
    shipping = combine([r[2] for r in rows])
    return CostBreakdown(
        basis=basis,
        complete=not excluded,
        sellers=sellers,
        parts=parts.model(),
        gst=gst.model(),
        shipping=shipping.model(),
        total=combine([parts, gst, shipping]).model(),
        excluded_line_ids=excluded,
        rates_checked_on=date.fromisoformat(load("tax_rates.json")["gst"]["checked_on"]),
    )


USD_VALUE = re.compile(
    r"^\s*(?:US\$|USD|\$)\s*(\d{1,7}(?:\.\d{1,2})?)\s*$|^\s*(\d{1,7}(?:\.\d{1,2})?)\s*(?:USD|US\$)\s*$",
    re.IGNORECASE,
)
PLAIN_NUMBER = re.compile(r"^\s*(\d{1,7}(?:\.\d{1,2})?)\s*$")


def parse_usd(value: str, unit: str | None) -> Decimal | None:
    """A single USD amount only; pack sizes, ranges or other currencies are rejected."""
    if unit and unit.strip().upper() in {"USD", "US$", "$"}:
        match = PLAIN_NUMBER.match(value) or USD_VALUE.match(value)
    elif unit:
        return None
    else:
        match = USD_VALUE.match(value)
    if not match:
        return None
    amount = Decimal(next(g for g in match.groups() if g))
    return amount if amount > 0 else None


def import_reference(line: ReportLine) -> ImportReference | None:
    if line.import_reference is not None:
        return line.import_reference
    research = line.research
    if research is None or research.status != "ready":
        return None
    for candidate in research.candidates:
        if candidate.match != "exact":
            continue
        for fact in candidate.facts:
            if "price" in fact.name.casefold() and (usd := parse_usd(fact.value, fact.unit)):
                return ImportReference(
                    price_usd=money(usd),
                    source="research_fact",
                    source_url=candidate.url,
                    quote=fact.quote,
                )
    return None


def pct(value: str) -> Decimal:
    return Decimal(value) / 100


def import_baseline(lines: list[ReportLine]) -> ImportBaseline | None:
    """Landed cost if the same parts came from a US/global distributor (courier, 9804)."""
    needed = [line for line in lines if not line.item.user_has_it]
    refs = [
        (line, ref)
        for line in needed
        if line.item.qty is not None and (ref := import_reference(line)) is not None
    ]
    if not refs:
        return None
    rates = load("tax_rates.json")
    duty, fx, courier = rates["import"], rates["fx"], rates["courier"]
    rate = Decimal(fx["usd_inr"])
    # `refs` keeps only lines with a quantity; mypy cannot narrow through the tuple.
    goods_usd = sum((Decimal(ref.price_usd) * cast(int, line.item.qty) for line, ref in refs), ZERO)
    goods = (goods_usd * rate).quantize(CENT, ROUND_HALF_UP)
    freight = (Decimal(courier["usd_per_order"]) * rate).quantize(CENT, ROUND_HALF_UP)
    assessable = goods + freight
    bcd = assessable * pct(duty["bcd_percent"])
    sws = bcd * pct(duty["sws_percent_of_bcd"])
    igst = (assessable + bcd + sws) * pct(duty["igst_percent"])
    duties = (bcd + sws + igst).quantize(CENT, ROUND_HALF_UP)
    fx_note = f"USD→INR {fx['usd_inr']} ({fx['date']} RBI reference rate); {fx['note']}"
    duty_notes = [
        f"Heading {duty['heading']}: BCD {duty['bcd_percent']}% of assessable value, SWS "
        f"{duty['sws_percent_of_bcd']}% of BCD, IGST {duty['igst_percent']}% of value plus "
        "BCD and SWS; assessable value = goods + courier (CIF approximation, no insurance)",
        f"Duty rates checked {duty['checked_on']}, unverified: {duty['note']}",
        "Assumed rates, not tax advice",
    ]
    return ImportBaseline(
        line_ids=[line.item.line_id for line, _ in refs],
        complete=len(refs) == len(needed),
        goods_usd=money(goods_usd),
        fx_usd_inr=fx["usd_inr"],
        goods_inr=charge(
            goods,
            "estimated",
            "Reference unit prices × quantities: "
            + ", ".join(f"{ln.item.line_id} ${ref.price_usd} ({ref.source})" for ln, ref in refs),
            fx_note,
        ).model(),
        courier_inr=charge(
            freight,
            "estimated",
            f"Placeholder courier ${courier['usd_per_order']} per order, unverified: "
            + courier["note"],
        ).model(),
        duty_inr=charge(duties, "estimated", *duty_notes).model(),
        landed_inr=charge(
            goods + freight + duties, "estimated", "landed = goods + courier + duty"
        ).model(),
        formula=(
            "landed = goods + courier + duty; assessable = goods + courier; "
            "duty = BCD + SWS + IGST; BCD = bcd% × assessable; SWS = sws% × BCD; "
            "IGST = igst% × (assessable + BCD + SWS)"
        ),
        sources=list(
            dict.fromkeys(
                [str(ref.source_url) for _, ref in refs if ref.source_url]
                + [duty["source_url"], fx["source_url"]]
            )
        ),
    )


def selection_picks(report: Report) -> list[Pick]:
    picks = []
    for line in report.lines:
        if line.item.user_has_it or line.selected_offer_url is None or line.price_inr is None:
            continue
        if line.item.qty is None:
            continue
        offer = next((o for o in line.offers if o.url == line.selected_offer_url), None)
        picks.append(
            Pick(
                line_id=line.item.line_id,
                seller=offer.seller if offer else urlsplit(str(line.selected_offer_url)).hostname,
                unit_price=Decimal(line.price_inr),
                qty=packs_for(line.item.qty, offer),
                tax_included=offer.tax_included if offer else None,
                family=line.item.specs.family,
                offer_url=str(line.selected_offer_url),
            )
        )
    return picks


def selection_costing(report: Report) -> CostBreakdown:
    costing = cost_picks(selection_picks(report), list(report.unselected_line_ids))
    baseline = import_baseline(report.lines)
    costing.import_baseline = baseline
    if (
        baseline is not None
        and baseline.complete
        and costing.complete
        and costing.total.amount_inr is not None
    ):
        difference = Decimal(baseline.landed_inr.amount_inr) - Decimal(costing.total.amount_inr)
        costing.savings_vs_import = SavingsEstimate(
            amount_inr=money(difference),
            assumptions=[
                "Import landed estimate minus the India estimate for the same lines and "
                "quantities; positive means buying in India is estimated cheaper",
                "Both sides are estimates; delivery time is not compared",
            ],
        )
    return costing


def update_costs(report: Report) -> None:
    subtotal = Decimal("0.00")
    missing = []
    for line in report.lines:
        line.subtotal_inr = None
        if line.item.user_has_it:
            line.subtotal_inr = "0.00"
        elif line.selected_offer_url is not None and line.price_inr is not None:
            if line.item.qty is not None:
                offer = next((o for o in line.offers if o.url == line.selected_offer_url), None)
                amount = Decimal(line.price_inr) * packs_for(line.item.qty, offer)
                line.subtotal_inr = f"{amount:.2f}"
                subtotal += amount
            else:
                missing.append(line.item.line_id)
        else:
            missing.append(line.item.line_id)
    report.unselected_line_ids = missing
    report.selected_parts_subtotal_inr = f"{subtotal:.2f}"
    report.parts_subtotal_inr = f"{subtotal:.2f}" if not missing and not report.demo else None
    report.total_inr = None
    # Demo reports carry fixture data; no estimate is ever derived from it.
    report.costing = None if report.demo else selection_costing(report)
    # recommend.py builds on this module, so it is imported here rather than at the top.
    from bharat_sourcer.recommend import annotate

    annotate(report)
