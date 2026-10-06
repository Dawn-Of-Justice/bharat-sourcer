"""Cart plan alternatives over verified offers, and user import reference prices.

`GET /plans` computes alternatives on request and never applies them: cheapest and fewest
sellers (A/B offers that could be selected now) plus the recommended basket, the same
computation that `recommend.apply_recommendations` applies when sourcing completes and
exposes as `report.order_plan`. Search is exhaustive for small BOMs and a bounded
greedy/local search otherwise (shared with recommend.py).
"""

from decimal import Decimal
from itertools import product

from bharat_sourcer.costing import (
    Pick,
    cost_picks,
    group,
    money,
    packs_for,
    seller_charges,
    update_costs,
)
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.recommend import (
    SELLER_PENALTY_INR,
    build_basket,
    eligible,
    fewest_start,
    improve,
)
from bharat_sourcer.schemas import (
    CartPlan,
    CartPlans,
    ImportReference,
    Job,
    PlanPick,
    Report,
    SetImportReferences,
    now,
)
from bharat_sourcer.storage import StoredJob

MAX_COMBINATIONS = 20_000
RULES = [
    "Cheapest and fewest sellers: only offers that could be selected now: in stock, checked "
    "within 24 hours, grade A or B and meeting any declared requirements. Research-only "
    "matches need explicit approval and are left out.",
    "One offer per seller per line: the cheapest listed price.",
    "Quantities are rounded up to whole packs when the listing states a pack size.",
    "Cheapest: fewest unknown cost components first, then the lowest estimated total.",
    "Fewest sellers: fewest distinct sellers first, then as Cheapest.",
    "Recommended: the automatic basket (recommendations.md): user selections stay fixed; "
    "other lines use acceptable offers by score, minimising the estimated landed total plus "
    "a per-extra-seller penalty. It can include offers whose compatibility is still unknown.",
    "Totals use the same GST and shipping estimates as the report costing; plans are "
    "suggestions and do not change selections. Grade B picks need accept_changes.",
]


def options(report: Report):
    choices, offers, uncovered = [], {}, []
    for line in report.lines:
        if line.item.user_has_it:
            continue
        best: dict[str, Pick] = {}
        for offer in line.offers:
            if line.item.qty is None or not eligible(line, offer):
                continue
            pick = Pick(
                line_id=line.item.line_id,
                seller=offer.seller,
                unit_price=Decimal(offer.price_inr),
                qty=packs_for(line.item.qty, offer),
                tax_included=offer.tax_included,
                family=line.item.specs.family,
                offer_url=str(offer.url),
            )
            key = pick.seller.lower()
            cost = pick.unit_price * pick.qty
            if key not in best or cost < best[key].unit_price * best[key].qty:
                best[key] = pick
                offers[(pick.line_id, pick.offer_url)] = offer
        if best:
            choices.append(sorted(best.values(), key=lambda p: (p.unit_price * p.qty, p.seller)))
        else:
            uncovered.append(line.item.line_id)
    return choices, offers, uncovered


def score(picks: tuple[Pick, ...]):
    unknown, total = 0, Decimal("0")
    sellers = group(list(picks))
    for seller, items in sellers.items():
        cost = seller_charges(seller, items)[3]
        unknown += cost.status == "unknown"
        total += cost.partial
    return len(sellers), unknown, total


def cheapest_key(picks):
    count, unknown, total = score(picks)
    return unknown, total, count


def fewest_key(picks):
    return score(picks)


def search(choices: list[list[Pick]]):
    combinations = 1
    for alternatives in choices:
        combinations *= len(alternatives)
    if combinations <= MAX_COMBINATIONS:
        every = list(product(*choices))
        return "exhaustive", list(min(every, key=cheapest_key)), list(min(every, key=fewest_key))
    cheapest = improve([alternatives[0] for alternatives in choices], choices, cheapest_key)
    fewest = improve(fewest_start(choices), choices, fewest_key)
    return "greedy", cheapest, fewest


def plan_pick(pick: Pick, offer, qty: int | None) -> PlanPick:
    grade = offer.compatibility.grade if offer is not None and offer.compatibility else None
    return PlanPick(
        line_id=pick.line_id,
        offer_url=pick.offer_url,
        seller=pick.seller,
        price_inr=money(pick.unit_price),
        grade=None if grade == "X" else grade,
        changes_required=grade == "B",
        qty=qty,
        packs=pick.qty,
    )


def recommended_plan(report: Report, penalty: Decimal, selected: set) -> CartPlan | None:
    """The automatic basket as an alternative; user selections are part of it, fixed."""
    basket = build_basket(report, penalty)
    lines = {line.item.line_id: line for line in report.lines}
    picks: list[Pick] = list(basket.fixed)
    offers = {
        pick.line_id: next(
            (o for o in lines[pick.line_id].offers if str(o.url) == pick.offer_url), None
        )
        for pick in basket.fixed
    }
    for line_id, entry in basket.chosen.items():
        offers[line_id] = entry.offer
        picks.append(
            Pick(
                line_id=line_id,
                seller=entry.offer.seller,
                unit_price=Decimal(entry.offer.price_inr),
                qty=entry.packs,
                tax_included=entry.offer.tax_included,
                family=lines[line_id].item.specs.family,
                offer_url=str(entry.offer.url),
            )
        )
    if not picks:
        return None
    order = {line.item.line_id: index for index, line in enumerate(report.lines)}
    picks.sort(key=lambda p: order[p.line_id])
    covered = {p.line_id for p in picks}
    uncovered = [
        line.item.line_id
        for line in report.lines
        if not line.item.user_has_it and line.item.line_id not in covered
    ]
    return CartPlan(
        kind="recommended",
        picks=[plan_pick(p, offers[p.line_id], lines[p.line_id].item.qty) for p in picks],
        seller_count=len(group(picks)),
        costing=cost_picks(picks, uncovered, basis="plan"),
        matches_selection={(p.line_id, p.offer_url) for p in picks} == selected,
    )


def plans_for(job: Job, penalty: Decimal = SELLER_PENALTY_INR) -> CartPlans:
    report = job.report
    if job.status != "done" or report is None or job.demo:
        raise JobError(409, "INVALID_STATE", "Plans need a completed live report")
    choices, offers, uncovered = options(report)
    selected = {
        (line.item.line_id, str(line.selected_offer_url))
        for line in report.lines
        if line.selected_offer_url is not None
    }
    plans, method = [], "none"
    if choices:
        method, cheapest, fewest = search(choices)
        qty = {line.item.line_id: line.item.qty for line in report.lines}
        for kind, picks in (("cheapest", cheapest), ("fewest_sellers", fewest)):
            plans.append(
                CartPlan(
                    kind=kind,
                    picks=[
                        plan_pick(p, offers[(p.line_id, p.offer_url)], qty[p.line_id])
                        for p in picks
                    ],
                    seller_count=len(group(picks)),
                    costing=cost_picks(picks, uncovered, basis="plan"),
                    matches_selection={(p.line_id, p.offer_url) for p in picks} == selected,
                )
            )
    recommended = recommended_plan(report, penalty, selected)
    if recommended is not None:
        plans.append(recommended)
    return CartPlans(
        plans=plans,
        method=method,
        uncovered_line_ids=uncovered,
        rules=RULES,
        seller_penalty_inr=money(penalty),
    )


def cart_plans(service: JobService, job_id: str, token) -> CartPlans:
    return plans_for(service.get(job_id, token), service.seller_penalty_inr)


def set_import_references(
    service: JobService, job_id: str, token, request: SetImportReferences
) -> Job:
    """Store user-supplied US/global unit prices; only the import comparison uses them."""
    service._validate_id(job_id)

    def change(record: StoredJob):
        job = service._authorized(record, token)
        if job.status != "done" or job.report is None or job.demo:
            raise JobError(409, "INVALID_STATE", "Set import prices in a completed live report")
        lines = {line.item.line_id: line for line in job.report.lines}
        seen = set()
        for reference in request.references:
            line = lines.get(reference.line_id)
            if line is None or reference.line_id in seen or line.item.user_has_it:
                raise JobError(422, "INVALID_REFERENCE", "Unknown, repeated or owned line")
            seen.add(reference.line_id)
            if reference.price_usd is not None and Decimal(reference.price_usd) <= 0:
                raise JobError(422, "INVALID_REFERENCE", "Reference price must be positive")
        for reference in request.references:
            lines[reference.line_id].import_reference = (
                None
                if reference.price_usd is None
                else ImportReference(
                    price_usd=reference.price_usd, source="user", source_url=reference.source_url
                )
            )
        update_costs(job.report)
        job.updated_at = now()

    record = service.store.mutate(job_id, change)
    if record is None:
        raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
    return record.job.model_copy(deep=True)
