"""Cart plan suggestions over verified offers, and user import reference prices.

Plans are computed on request and never stored or applied: the user's selection stays as
it is. Search is exhaustive for small BOMs and a bounded greedy/local search otherwise.
"""

from datetime import timedelta
from decimal import Decimal
from itertools import product

from bharat_sourcer.costing import Pick, cost_picks, group, seller_charges, update_costs
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import (
    CartPlan,
    CartPlans,
    ImportReference,
    Job,
    PlanPick,
    Report,
    ReportLine,
    SetImportReferences,
    VerifiedOffer,
    now,
)
from bharat_sourcer.sourcing.research import check_requirements
from bharat_sourcer.storage import StoredJob

MAX_COMBINATIONS = 20_000
MAX_PASSES = 10
RULES = [
    "Only offers that could be selected now: in stock, checked within 24 hours, grade A or B "
    "and meeting any declared requirements. Research-only matches need explicit approval and "
    "are left out.",
    "One offer per seller per line: the cheapest listed price.",
    "Cheapest: fewest unknown cost components first, then the lowest estimated total.",
    "Fewest sellers: fewest distinct sellers first, then as Cheapest.",
    "Totals use the same GST and shipping estimates as the report costing; plans are "
    "suggestions and do not change selections. Grade B picks need accept_changes.",
]


def eligible(line: ReportLine, offer: VerifiedOffer) -> bool:
    if offer.stock != "in_stock" or offer.checked_at < now() - timedelta(hours=24):
        return False
    if offer.compatibility is None or offer.compatibility.grade not in {"A", "B"}:
        return False
    if line.item.requirements:
        candidate = (
            next((c for c in line.research.candidates if c.url == offer.url), None)
            if line.research and line.research.status == "ready"
            else None
        )
        checks = check_requirements(line.item.requirements, candidate.facts if candidate else [])
        if any(check.status != "meets" for check in checks):
            return False
    return True


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
                qty=line.item.qty,
                tax_included=offer.tax_included,
                family=line.item.specs.family,
                offer_url=str(offer.url),
            )
            key = pick.seller.lower()
            if key not in best or pick.unit_price < best[key].unit_price:
                best[key] = pick
                offers[(pick.line_id, pick.offer_url)] = offer
        if best:
            choices.append(sorted(best.values(), key=lambda p: (p.unit_price, p.seller)))
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


def fewest_start(choices: list[list[Pick]]) -> list[Pick]:
    """Greedy set cover: the seller covering most remaining lines, then the cheapest."""
    remaining, chosen = set(range(len(choices))), set()
    while remaining:
        coverage: dict[str, list[int]] = {}
        for index in remaining:
            for pick in choices[index]:
                coverage.setdefault(pick.seller.lower(), []).append(index)
        seller = min(
            coverage,
            key=lambda s: (
                -len(coverage[s]),
                sum(p.unit_price for i in coverage[s] for p in choices[i] if p.seller.lower() == s),
                s,
            ),
        )
        chosen.add(seller)
        remaining -= set(coverage[seller])
    return [next(p for p in alts if p.seller.lower() in chosen) for alts in choices]


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


def plans_for(job: Job) -> CartPlans:
    report = job.report
    if job.status != "done" or report is None or job.demo:
        raise JobError(409, "INVALID_STATE", "Plans need a completed live report")
    choices, offers, uncovered = options(report)
    if not choices:
        return CartPlans(uncovered_line_ids=uncovered, rules=RULES)
    method, cheapest, fewest = search(choices)
    selected = {
        (line.item.line_id, str(line.selected_offer_url))
        for line in report.lines
        if line.selected_offer_url is not None
    }
    plans = []
    for kind, picks in (("cheapest", cheapest), ("fewest_sellers", fewest)):
        grades = {p.line_id: offers[(p.line_id, p.offer_url)].compatibility.grade for p in picks}
        plans.append(
            CartPlan(
                kind=kind,
                picks=[
                    PlanPick(
                        line_id=p.line_id,
                        offer_url=p.offer_url,
                        seller=p.seller,
                        price_inr=f"{p.unit_price:.2f}",
                        grade=grades[p.line_id],
                        changes_required=grades[p.line_id] == "B",
                    )
                    for p in picks
                ],
                seller_count=len(group(picks)),
                costing=cost_picks(picks, uncovered, basis="plan"),
                matches_selection={(p.line_id, p.offer_url) for p in picks} == selected,
            )
        )
    return CartPlans(plans=plans, method=method, uncovered_line_ids=uncovered, rules=RULES)


def cart_plans(service: JobService, job_id: str, token) -> CartPlans:
    return plans_for(service.get(job_id, token))


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
