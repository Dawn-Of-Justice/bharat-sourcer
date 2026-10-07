"""Deterministic offer recommendations and the seller-grouped order plan.

Every offer on a line gets a score from one table of weights (`WEIGHTS`), with a reason
per factor. The basket step then picks one acceptable offer per line, minimising the
estimated landed total (parts + GST + shipping, using the costing rules) plus a penalty
for each extra seller, so orders are consolidated unless splitting saves more than the
penalty. A recommendation becomes the line's selection only when the existing selection
rules allow it (in stock, checked within 24 hours, requirements met, grade A or B); a
user's own choice is never replaced. See docs/contracts/recommendations.md.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from itertools import product
from urllib.parse import urlsplit

from bharat_sourcer.costing import (
    ZERO,
    Pick,
    cost_picks,
    group,
    gst_charge,
    gst_percent,
    money,
    pack_size,
    packs_for,
    policy_ref,
    rupees,
    seller_charges,
    seller_key,
)
from bharat_sourcer.schemas import (
    LineRecommendation,
    OrderPlan,
    OrderPlanLine,
    OrderPlanSeller,
    Report,
    ReportLine,
    UnsourcedLine,
    VerifiedOffer,
    now,
)
from bharat_sourcer.sourcing.part_spec import is_assortment, seed_spec
from bharat_sourcer.sourcing.research import check_requirements

# One table for every scoring factor: (weight, value per state). The score is the weighted
# sum of values in [0, 1]; weights add up to 1. Missing information gets a neutral value
# that ranks below good evidence and above known problems.
WEIGHTS: dict[str, tuple[float, dict]] = {
    # Matching stream: VerifiedOffer.match.status (mismatch is excluded).
    "match": (0.30, {"exact": 1.0, "compatible": 0.8, "partial": 0.4, None: 0.55}),
    # Compatibility grade (X is excluded; None means unknown specs).
    "grade": (0.25, {"A": 1.0, "B": 0.85, "C": 0.45, "D": 0.3, None: 0.6}),
    # Seller-reported stock (out of stock is excluded while any other offer is not).
    "stock": (0.15, {"in_stock": 1.0, "unknown": 0.6, "preorder": 0.3, "out_of_stock": 0.05}),
    # SellerTrust.label; a price anomaly multiplies the value by PRICE_ANOMALY_FACTOR.
    "trust": (0.10, {"established": 1.0, "verified_basics": 0.75, "unverified": 0.4, None: 0.5}),
    # Cheapest cost to cover the needed quantity on this line ÷ this offer's cost.
    "price": (0.15, {}),
    # Age of checked_at.
    "freshness": (0.05, {"day": 1.0, "three_days": 0.6, "older": 0.3}),
}
PRICE_ANOMALY_FACTOR = 0.5
MATCH_SCORE_SPAN = 0.3  # a match score of 0 keeps 70% of the status value
MIN_ACCEPTABLE = 0.5  # below this an offer is never recommended
SCORE_BAND = 0.1  # basket candidates: within this much of the line's best score
SELLER_PENALTY_INR = Decimal("60")  # per extra seller: about one more shipping fee + hassle
# Ranking only (never shown as a cost): unknown shipping and unknown GST are not free.
ASSUMED_SHIPPING_INR = Decimal("60")
MAX_COMBINATIONS = 20_000
MAX_PASSES = 10
LABELS = {
    "A": "works as is",
    "B": "works with a small setting change",
    "C": "works with wiring or power changes",
    "D": "different part, similar result",
}


def attr(obj, name):
    """Read an attribute or mapping key; the matching stream's types may not exist yet."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


@dataclass(frozen=True)
class ScoreContext:
    qty: int
    cheapest_cost: Decimal | None
    any_available: bool
    at: datetime
    value_unknown: bool = False


def line_spec(line: ReportLine):
    """The buying spec that governs this line: the user's own edit, else the spec it was
    sourced with, else the item's AI spec, else the seed spec from the name."""
    item_spec = line.item.buyable_spec
    if item_spec is not None and item_spec.origin == "user":
        return item_spec
    spec = line.buyable_spec or item_spec
    if spec is None or spec.origin == "seed":
        # Seeds are deterministic: rebuild them, so lines sourced with an older seed (which
        # never set needs_value) follow the current rules too.
        return seed_spec(line.item)
    return spec


def value_unknown(line: ReportLine) -> bool:
    """The part's value (resistance, capacitance...) is not known: never guess it."""
    return bool(line_spec(line).needs_value)


def value_step(line: ReportLine) -> str:
    spec = line_spec(line)
    reason = f" ({spec.needs_value_reason})" if spec.needs_value_reason else ""
    return f"Choose the value for {line.item.raw_name}{reason}"


VALUE_BLOCK = (
    "Not selected automatically: the part's value is not known; choose the value first "
    "(a kit can cover it, a single-value listing would be a guess)."
)


@dataclass(frozen=True)
class OfferScore:
    offer: VerifiedOffer
    score: float
    reasons: tuple[str, ...]
    excluded: str | None
    packs: int
    pack_qty: int | None
    cost: Decimal


def requirement_status(line: ReportLine, offer: VerifiedOffer) -> str:
    """none, meets, does_not_meet or unknown, using the same evidence as /selections."""
    if not line.item.requirements:
        return "none"
    candidate = (
        next((c for c in line.research.candidates if c.url == offer.url), None)
        if line.research and line.research.status == "ready"
        else None
    )
    checks = check_requirements(line.item.requirements, candidate.facts if candidate else [])
    if any(check.status == "does_not_meet" for check in checks):
        return "does_not_meet"
    return "meets" if all(check.status == "meets" for check in checks) else "unknown"


def judge_confirmed(offer: VerifiedOffer) -> bool:
    """The spec judge found this listing an exact or compatible match, backed by quotes it
    verified in the listing (or by structured data stating every spec param)."""
    match = getattr(offer, "match", None)
    if match is None or match.status not in {"exact", "compatible"}:
        return False
    return match.method == "deterministic_shortcut" or bool(match.claims)


def eligible(line: ReportLine, offer: VerifiedOffer) -> bool:
    """Could this offer be chosen automatically (plans) without a research approval?"""
    return not value_unknown(line) and selection_block(line, offer) is None


def selection_block(line: ReportLine, offer: VerifiedOffer) -> str | None:
    """Why the selection rules forbid choosing this offer automatically, or None."""
    if offer.stock != "in_stock":
        return "Not selected automatically: the seller does not report it in stock."
    if offer.checked_at < now() - timedelta(hours=24):
        return "Not selected automatically: checked over 24 hours ago; refresh this part."
    confirmed = judge_confirmed(offer)
    status = requirement_status(line, offer)
    if status == "does_not_meet" or (status == "unknown" and not confirmed):
        return (
            "Not selected automatically: the declared requirements are not confirmed by "
            "evidence for this listing; review it and choose it yourself."
        )
    grade = offer.compatibility.grade if offer.compatibility else None
    if grade is None and confirmed:
        # The judge checked the listing against the buyable spec; rules had too little data.
        return None
    if grade is None:
        return (
            "Not selected automatically: compatibility is unknown until the missing specs "
            "are answered (unknown specs never get a positive grade)."
        )
    if grade not in {"A", "B"}:
        return f"Not selected automatically: grade {grade} ({LABELS.get(grade, grade)})."
    return None


def cover(line: ReportLine, offer: VerifiedOffer) -> tuple[int, Decimal]:
    packs = packs_for(line.item.qty or 1, offer)
    return packs, Decimal(offer.price_inr) * packs


def usable(offer: VerifiedOffer) -> bool:
    """Not excluded on stock, grade or match, so it can set the line's price reference."""
    return (
        offer.stock != "out_of_stock"
        and not (offer.compatibility and offer.compatibility.grade == "X")
        and attr(getattr(offer, "match", None), "status") != "mismatch"
    )


def context_for(line: ReportLine) -> ScoreContext:
    costs = [cover(line, offer)[1] for offer in line.offers if usable(offer)]
    available = any(offer.stock != "out_of_stock" for offer in line.offers)
    return ScoreContext(
        qty=line.item.qty or 1,
        cheapest_cost=min(costs, default=None),
        any_available=available,
        at=now(),
        value_unknown=value_unknown(line),
    )


def score_offer(line: ReportLine, offer: VerifiedOffer, context: ScoreContext) -> OfferScore:
    reasons, excluded, total = [], None, 0.0

    def add(factor: str, value: float, reason: str):
        nonlocal total
        total += WEIGHTS[factor][0] * value
        reasons.append(reason)

    match = getattr(offer, "match", None)
    status = attr(match, "status")
    if status == "mismatch":
        excluded = "the listing does not match the part"
        reasons.append("Match: mismatch with the part (excluded)")
    else:
        value = WEIGHTS["match"][1].get(status, WEIGHTS["match"][1][None])
        match_score = attr(match, "score")
        reason = f"Match: {status}" if status else "Match: no match details yet; neutral weight"
        if status is not None and isinstance(match_score, int | float):
            value *= 1 - MATCH_SCORE_SPAN + MATCH_SCORE_SPAN * max(0.0, min(1.0, match_score))
            reason += f" (score {match_score:.2f})"
        add("match", value, reason)

    if context.value_unknown and not is_assortment(offer.title):
        excluded = excluded or "the part's value is not known (a single-value listing guesses it)"
        reasons.append("Value: not known; a single-value listing would guess it (excluded)")
    elif context.value_unknown:
        reasons.append("Value: not known; this kit or assortment covers several values")

    grade = offer.compatibility.grade if offer.compatibility else None
    if grade == "X":
        excluded = excluded or "compatibility grade X (don't use)"
        reasons.append("Compatibility: grade X, don't use (excluded)")
    else:
        add(
            "grade",
            WEIGHTS["grade"][1][grade],
            f"Compatibility: grade {grade} ({LABELS[grade]})"
            if grade
            else "Compatibility: unknown until missing specs are answered; neutral weight",
        )

    requirements = requirement_status(line, offer)
    if requirements == "does_not_meet":
        excluded = excluded or "a declared requirement is not met"
        reasons.append("Requirements: evidence shows a declared requirement is not met (excluded)")
    elif requirements == "unknown":
        reasons.append("Requirements: not confirmed by evidence for this listing")
    elif requirements == "meets":
        reasons.append("Requirements: all declared requirements met by evidence")

    if offer.stock == "out_of_stock" and context.any_available:
        excluded = excluded or "out of stock while other listings are available"
        reasons.append("Stock: out of stock (excluded; other listings are available)")
    else:
        add(
            "stock",
            WEIGHTS["stock"][1][offer.stock],
            {
                "in_stock": "Stock: in stock",
                "unknown": "Stock: not reported",
                "preorder": "Stock: preorder (penalised)",
                "out_of_stock": "Stock: out of stock, but no listing is available",
            }[offer.stock],
        )

    trust = offer.trust
    label = trust.label if trust else None
    value = WEIGHTS["trust"][1][label]
    reason = f"Seller: {label.replace('_', ' ')}" if label else "Seller: trust not checked"
    if trust and trust.signals.price_anomaly:
        value *= PRICE_ANOMALY_FACTOR
        reason += "; price far from other listings (penalised)"
    add("trust", value, reason)

    packs, cost = cover(line, offer)
    size = pack_size(offer)
    if context.cheapest_cost and cost > 0:
        price_value = float(min(Decimal(1), context.cheapest_cost / cost))
    else:
        price_value = 1.0
    if size:
        units = packs * size
        pack_text = f"{packs} pack{'s' * (packs > 1)} of {size}"
        unit_text = f"{rupees(Decimal(offer.price_inr) / size)}/unit"
        extra = f", {units - context.qty} spare" if units > context.qty else ""
        pack_reason = f"{pack_text} cover the {context.qty} needed ({unit_text}{extra})"
    else:
        pack_reason = f"{packs} × {rupees(Decimal(offer.price_inr))}"
    if context.cheapest_cost is not None and cost <= context.cheapest_cost:
        price_reason = f"Price: {rupees(cost)} for {pack_reason}; cheapest on this line"
    elif context.cheapest_cost is not None:
        more = rupees(cost - context.cheapest_cost)
        price_reason = f"Price: {rupees(cost)} for {pack_reason}; {more} above the cheapest"
    else:
        price_reason = f"Price: {rupees(cost)} for {pack_reason}"
    add("price", price_value, price_reason)

    age = context.at - offer.checked_at
    bucket = (
        "day"
        if age <= timedelta(hours=24)
        else "three_days"
        if age <= timedelta(hours=72)
        else "older"
    )
    add(
        "freshness",
        WEIGHTS["freshness"][1][bucket],
        {
            "day": "Checked within 24 hours",
            "three_days": "Checked 1–3 days ago",
            "older": "Checked over 3 days ago",
        }[bucket],
    )
    score = 0.0 if excluded else round(total, 4)
    return OfferScore(offer, score, tuple(reasons), excluded, packs, size, cost)


def line_scores(line: ReportLine) -> list[OfferScore]:
    context = context_for(line)
    scores = [score_offer(line, offer, context) for offer in line.offers]
    return sorted(
        scores, key=lambda s: (s.excluded is not None, -s.score, s.cost, str(s.offer.url))
    )


def acceptable(scores: list[OfferScore]) -> list[OfferScore]:
    return [s for s in scores if s.excluded is None and s.score >= MIN_ACCEPTABLE]


def pick_for(line: ReportLine, offer: VerifiedOffer) -> Pick:
    return Pick(
        line_id=line.item.line_id,
        seller=offer.seller,
        unit_price=Decimal(offer.price_inr),
        qty=packs_for(line.item.qty or 1, offer),
        tax_included=offer.tax_included,
        family=line.item.specs.family,
        offer_url=str(offer.url),
    )


@lru_cache(maxsize=8192)
def ranking_cost(seller: str, picks: tuple[Pick, ...]) -> Decimal:
    """Parts + GST + shipping for ranking; unknown GST/shipping are assumed, never zero."""
    parts, _gst, shipping, _total, _gap = seller_charges(seller, picks)
    total = parts.partial
    for pick in picks:
        gst = gst_charge(pick)
        total += (
            gst.amount
            if gst.amount is not None
            else pick.unit_price * pick.qty * gst_percent(pick.family) / 100
        )
    return total + (shipping.amount if shipping.amount is not None else ASSUMED_SHIPPING_INR)


def basket_key(picks, penalty: Decimal, scores: dict):
    sellers = group(list(picks))
    total = sum((ranking_cost(seller, items) for seller, items in sellers.items()), ZERO)
    total += penalty * max(0, len(sellers) - 1)
    quality = sum(scores.get((p.line_id, p.offer_url), 0.0) for p in picks)
    return total, -quality, len(sellers)


def improve(start: list[Pick], choices: list[list[Pick]], key) -> list[Pick]:
    current, best = list(start), key(tuple(start))
    for _ in range(MAX_PASSES):
        changed = False
        for index, alternatives in enumerate(choices):
            for alternative in alternatives:
                trial = current.copy()
                trial[index] = alternative
                value = key(tuple(trial))
                if value < best:
                    current, best, changed = trial, value, True
        if not changed:
            break
    return current


def fewest_start(choices: list[list[Pick]], preferred: set[str] = frozenset()) -> list[Pick]:
    """Greedy set cover: the seller covering most remaining lines, then the cheapest."""
    remaining, chosen = set(range(len(choices))), set(preferred)
    for index in list(remaining):
        if any(seller_key(p.seller) in chosen for p in choices[index]):
            remaining.discard(index)
    while remaining:
        coverage: dict[str, list[int]] = {}
        for index in remaining:
            for pick in choices[index]:
                coverage.setdefault(seller_key(pick.seller), []).append(index)
        costs = {
            seller: sum(
                (
                    p.unit_price
                    for i in indexes
                    for p in choices[i]
                    if seller_key(p.seller) == seller
                ),
                ZERO,
            )
            for seller, indexes in coverage.items()
        }
        seller = min(coverage, key=lambda s: (-len(coverage[s]), costs[s], s))
        chosen.add(seller)
        remaining -= set(coverage[seller])

    def first(alternatives):
        return next((p for p in alternatives if seller_key(p.seller) in chosen), alternatives[0])

    return [first(alternatives) for alternatives in choices]


def optimise(choices: list[list[Pick]], fixed: list[Pick], penalty: Decimal, scores: dict):
    """Exhaustive for small baskets, else greedy set cover + single-swap improvement."""
    if not choices:
        return "none", []

    def key(picks):
        return basket_key(tuple(fixed) + tuple(picks), penalty, scores)

    combinations = 1
    for alternatives in choices:
        combinations *= len(alternatives)
    if combinations <= MAX_COMBINATIONS:
        return "exhaustive", list(min(product(*choices), key=key))
    starts = [
        [alternatives[0] for alternatives in choices],
        fewest_start(choices, {seller_key(p.seller) for p in fixed}),
    ]
    results = [improve(start, choices, key) for start in starts]
    return "greedy", min(results, key=lambda picks: key(tuple(picks)))


@dataclass
class Basket:
    method: str
    chosen: dict[str, OfferScore]
    fixed: list[Pick]
    unsourced: dict[str, LineRecommendation]
    scores: dict[str, list[OfferScore]]


def user_locked(line: ReportLine) -> bool:
    """A selection made through /selections (or saved before recommendations existed)."""
    return line.selection_source == "user" or (
        line.selection_source is None and line.selected_offer_url is not None
    )


def unsourced_recommendation(line: ReportLine, scores: list[OfferScore]) -> LineRecommendation:
    name = line.item.raw_name
    questions = [c.question for c in line.item.clarifications]
    missing = list(line.resolution.missing_specs) if line.resolution else []
    research = list(line.research.candidates) if line.research is not None else []
    research_steps = [f"Research candidate: {c.title} ({c.url})" for c in research[:3]]
    if line.item.qty is None:
        return LineRecommendation(
            status="unsourced",
            unsourced_reason="needs_quantity",
            reasons=["The quantity is unknown"],
            next_steps=[f"Set how many {name} you need"],
        )
    if not line.offers:
        if line.sourcing_status == "not_run" and line.sourcing_error is None:
            return LineRecommendation(
                status="unsourced",
                unsourced_reason="pending",
                reasons=["Sourcing has not checked this part yet"],
            )
        if value_unknown(line) and not (questions or missing):
            return LineRecommendation(
                status="unsourced",
                unsourced_reason="needs_value",
                reasons=[f"Needs a value: choose the value for {name}"],
                next_steps=[value_step(line)],
            )
        if questions or missing:
            fields = ", ".join(missing) or "the missing value"
            return LineRecommendation(
                status="unsourced",
                unsourced_reason="needs_value",
                reasons=[f"Needs a value: choose {fields} for {name}"],
                next_steps=questions or [f"Choose {fields} for {name}"],
            )
        return LineRecommendation(
            status="unsourced",
            unsourced_reason="no_offers",
            reasons=["No seller page with a verifiable price stocked it"],
            next_steps=research_steps
            or [f"Refresh this part, or search for {name} on a seller you trust"],
        )
    why = sorted({s.excluded for s in scores if s.excluded})
    if any(s.excluded is None for s in scores):
        why.append("the remaining listings scored below the acceptance threshold")
    steps = questions + research_steps
    unknown = value_unknown(line)
    if unknown:
        steps = [value_step(line), *steps]
    return LineRecommendation(
        status="unsourced",
        unsourced_reason="needs_value"
        if questions or missing or unknown
        else "no_acceptable_offer",
        reasons=[f"No acceptable listing: {'; '.join(why)}"],
        next_steps=steps or ["Refresh this part or review the listings and choose one yourself"],
    )


def build_basket(report: Report, penalty: Decimal = SELLER_PENALTY_INR) -> Basket:
    """Pure: the recommended offer per free line; user selections stay fixed."""
    fixed, choices, free, unsourced, all_scores, score_map = [], [], [], {}, {}, {}
    for line in report.lines:
        if line.item.user_has_it:
            continue
        line_id = line.item.line_id
        if user_locked(line) and line.selected_offer_url is not None:
            offer = next((o for o in line.offers if o.url == line.selected_offer_url), None)
            if offer is not None:
                fixed.append(pick_for(line, offer))
            continue
        if line.selection_source == "user" and line.user_offer_url is None:
            continue  # the user cleared this line; it is not ordered
        scores = line_scores(line)
        all_scores[line_id] = scores
        good = acceptable(scores)
        if not good or line.item.qty is None:
            unsourced[line_id] = unsourced_recommendation(line, scores)
            continue
        band = [s for s in good if s.score >= good[0].score - SCORE_BAND]
        per_seller: dict[str, OfferScore] = {}
        for entry in band:  # already best-first: keep each seller's best listing
            per_seller.setdefault(seller_key(entry.offer.seller), entry)
        options, by_url = [], {}
        for entry in per_seller.values():
            pick = pick_for(line, entry.offer)
            score_map[(pick.line_id, pick.offer_url)] = entry.score
            by_url[pick.offer_url] = entry
            options.append(pick)
        choices.append(options)
        free.append((line_id, by_url))
    method, picks = optimise(choices, fixed, penalty, score_map)
    chosen = {
        line_id: by_url[pick.offer_url] for (line_id, by_url), pick in zip(free, picks, strict=True)
    }
    return Basket(method, chosen, fixed, unsourced, all_scores)


def basket_reasons(line_id: str, entry: OfferScore, basket: Basket, penalty: Decimal):
    seller = seller_key(entry.offer.seller)
    others = sorted(
        {p.line_id for p in basket.fixed if seller_key(p.seller) == seller}
        | {
            key
            for key, other in basket.chosen.items()
            if key != line_id and seller_key(other.offer.seller) == seller
        }
    )
    reasons = []
    if others:
        reasons.append(f"Order: grouped with {', '.join(others)} from {seller}")
    cheaper = [
        s
        for s in acceptable(basket.scores.get(line_id, []))
        if s.cost < entry.cost and seller_key(s.offer.seller) != seller
    ]
    if cheaper:
        best = min(cheaper, key=lambda s: s.cost)
        reasons.append(
            f"Order: {rupees(entry.cost - best.cost)} more than {seller_key(best.offer.seller)}, "
            f"but avoids a separate order (penalty {rupees(penalty)} per extra seller plus "
            "its shipping)"
        )
    return reasons


def clear_selection(line: ReportLine) -> None:
    """Drop the current selection; a user's choice is remembered for later re-selection."""
    if user_locked(line):
        line.selection_source = "user"
        line.user_offer_url = line.user_offer_url or line.selected_offer_url
    elif line.selection_source == "recommended":
        line.selection_source = None
    line.selected_offer_url = None
    line.price_inr = line.grade = None
    line.changes_accepted = False
    line.research_accepted = False


def release_recommendations(report: Report | None) -> None:
    """Undo automatic selections (so offers can be re-graded); user choices stay."""
    for line in report.lines if report else []:
        if line.selection_source == "recommended":
            clear_selection(line)


def select(line: ReportLine, offer: VerifiedOffer, source: str) -> None:
    line.selected_offer_url = offer.url
    line.price_inr = offer.price_inr
    line.grade = offer.compatibility.grade
    # Grade B changes still need the user's acknowledgement (see recommendations.md).
    line.changes_accepted = False
    line.research_accepted = False
    line.selection_source = source


def reselect_user_choice(line: ReportLine) -> None:
    """After a refresh or spec update, restore the user's own offer if rules still allow it."""
    if line.selection_source != "user" or line.selected_offer_url is not None:
        return
    offer = next((o for o in line.offers if o.url == line.user_offer_url), None)
    if offer is not None and selection_block(line, offer) is None:
        select(line, offer, "user")


def apply_recommendations(report: Report | None, penalty: Decimal = SELLER_PENALTY_INR) -> str:
    """Recompute recommendations and apply them where allowed; never touches user choices."""
    if report is None:
        return "none"
    if report.demo:
        from bharat_sourcer.costing import update_costs

        update_costs(report)
        return "none"
    for line in report.lines:
        if line.item.user_has_it:
            line.recommendation = line.recommended_offer_url = None
            continue
        if user_locked(line):
            line.selection_source = "user"
            if line.selected_offer_url is not None:
                line.user_offer_url = line.user_offer_url or line.selected_offer_url
            reselect_user_choice(line)
        elif line.selection_source == "recommended":
            clear_selection(line)
    basket = build_basket(report, penalty)
    for line in report.lines:
        line_id = line.item.line_id
        if line_id in basket.unsourced:
            line.recommended_offer_url = None
            line.recommendation = basket.unsourced[line_id]
            continue
        entry = basket.chosen.get(line_id)
        if entry is None:
            continue  # owned, or a fixed user selection: its last recommendation stays
        offer = entry.offer
        unknown = value_unknown(line)
        # A kit on a line without a known value is recommended, never selected for the user.
        block = VALUE_BLOCK if unknown else selection_block(line, offer)
        reasons = list(entry.reasons) + basket_reasons(line_id, entry, basket, penalty)
        if block is None and offer.compatibility and offer.compatibility.grade == "B":
            reasons.append("Grade B: acknowledge the listed changes before ordering")
        line.recommended_offer_url = offer.url
        line.recommendation = LineRecommendation(
            status="recommended",
            offer_url=offer.url,
            seller=seller_key(offer.seller),
            score=entry.score,
            reasons=reasons,
            blocked_reason=block,
            qty=line.item.qty,
            pack_qty=entry.pack_qty,
            packs=entry.packs,
            next_steps=[value_step(line)] if unknown else [],
        )
        if block is None and line.selection_source != "user":
            select(line, offer, "recommended")
    from bharat_sourcer.costing import update_costs

    update_costs(report)
    return basket.method


def carry_selection(previous: ReportLine | None, line: ReportLine) -> None:
    """Keep a user's choice on a line whose offers are being replaced (refresh)."""
    if previous is None or line is previous or not user_locked(previous):
        return
    line.selection_source = "user"
    line.user_offer_url = previous.user_offer_url or previous.selected_offer_url


def plan_offer(line: ReportLine) -> tuple[VerifiedOffer | None, bool]:
    """The offer this line orders in the plan and whether it is the current selection."""
    if line.selected_offer_url is not None:
        offer = next((o for o in line.offers if o.url == line.selected_offer_url), None)
        return offer, True
    if line.selection_source == "user" and line.user_offer_url is None:
        return None, False  # the user cleared the line
    if line.recommended_offer_url is None:
        return None, False
    offer = next((o for o in line.offers if o.url == line.recommended_offer_url), None)
    return offer, False


def unsourced_entry(line: ReportLine) -> UnsourcedLine:
    name = line.item.raw_name
    if line.selection_source == "user" and line.user_offer_url is None:
        return UnsourcedLine(
            line_id=line.item.line_id,
            name=name,
            reason="cleared_by_user",
            message="You cleared this line's selection",
            next_steps=["Choose an offer, or mark the part as already owned"],
        )
    rec = line.recommendation
    if rec is None and line.offers and line.item.qty is not None:
        rec = LineRecommendation(
            status="unsourced",
            unsourced_reason="pending",
            reasons=["Recommendations are computed when sourcing completes"],
        )
    elif rec is None or rec.status != "unsourced":
        rec = unsourced_recommendation(line, line_scores(line))
    research = list(line.research.candidates[:3]) if line.research else []
    return UnsourcedLine(
        line_id=line.item.line_id,
        name=name,
        reason=rec.unsourced_reason or "no_acceptable_offer",
        message="; ".join(rec.reasons) or "No acceptable offer",
        next_steps=rec.next_steps,
        research_urls=[c.url for c in research],
    )


def build_order_plan(report: Report) -> OrderPlan:
    """Seller-grouped plan from selections, else recommendations; nothing is applied here."""
    entries, picks, unsourced = [], [], []
    for line in report.lines:
        if line.item.user_has_it:
            continue
        offer, selected = plan_offer(line)
        if line.item.qty is None or (offer is None and not selected):
            unsourced.append(unsourced_entry(line))
            continue
        if offer is None:  # a selection whose offer is no longer listed (older snapshots)
            if line.price_inr is None:
                unsourced.append(unsourced_entry(line))
                continue
            seller = urlsplit(str(line.selected_offer_url)).hostname or "unknown"
            price, url, title, size = line.price_inr, line.selected_offer_url, None, None
            grade = line.grade
        else:
            seller, price, url, title = offer.seller, offer.price_inr, offer.url, offer.title
            size = pack_size(offer)
            grade = offer.compatibility.grade if offer.compatibility else None
        packs = packs_for(line.item.qty, offer)
        pick = Pick(
            line_id=line.item.line_id,
            seller=seller,
            unit_price=Decimal(price),
            qty=packs,
            tax_included=offer.tax_included if offer else None,
            family=line.item.specs.family,
            offer_url=str(url),
        )
        picks.append(pick)
        rec = line.recommendation
        entries.append(
            (
                pick,
                OrderPlanLine(
                    line_id=line.item.line_id,
                    name=line.item.raw_name,
                    offer_url=url,
                    title=title,
                    qty=line.item.qty,
                    pack_qty=size,
                    packs=packs,
                    units=packs * size if size else packs,
                    unit_price_inr=price,
                    line_price_inr=money(Decimal(price) * packs),
                    selection_source=line.selection_source if selected else "recommended",
                    selected=selected,
                    grade=grade,
                    changes_required=grade == "B" and not line.changes_accepted,
                    blocked_reason=None
                    if selected
                    else rec.blocked_reason
                    if rec and rec.offer_url == url
                    else None,
                ),
            )
        )
    sellers = []
    for seller, items in group(picks).items():
        parts, gst, shipping, total, gap = seller_charges(seller, items)
        lines = [entry for pick, entry in entries if seller_key(pick.seller) == seller]
        sellers.append(
            OrderPlanSeller(
                seller=seller,
                lines=lines,
                subtotal_inr=money(parts.partial),
                gst=gst.model(),
                shipping=shipping.model(),
                total=total.model(),
                free_shipping_gap_inr=money(gap) if gap is not None else None,
                policy=policy_ref(seller),
                product_links=list(dict.fromkeys(entry.offer_url for entry in lines)),
            )
        )
    sellers.sort(key=lambda s: (-len(s.lines), -Decimal(s.subtotal_inr), s.seller))
    excluded = [entry.line_id for entry in unsourced]
    return OrderPlan(
        sellers=sellers,
        unsourced=unsourced,
        seller_count=len(sellers),
        costing=cost_picks(picks, excluded, basis="plan"),
        ready=bool(sellers) and not unsourced,
    )


def annotate(report: Report) -> None:
    """Called from costing.update_costs: line images always, the order plan for live data."""
    from bharat_sourcer.images import line_image

    for line in report.lines:
        line.line_image = line_image(line)
    report.order_plan = None if report.demo else build_order_plan(report)
