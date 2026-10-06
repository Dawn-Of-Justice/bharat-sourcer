"""Recommendations, the seller-grouped order plan and line images (all offline).

Offers are synthetic test data, not seller quotes. Seller hosts are used only to look up the
dated policy table. `match` and `pack_qty` come from parallel work streams, so they are
attached as plain attributes here to exercise the defensive reads.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from bharat_sourcer.jobs import JobService
from bharat_sourcer.recommend import (
    MIN_ACCEPTABLE,
    WEIGHTS,
    apply_recommendations,
    context_for,
    line_scores,
    score_offer,
)
from bharat_sourcer.schemas import (
    BomItem,
    Clarification,
    Compatibility,
    ConfirmJob,
    CreateJob,
    PartImage,
    PartResearch,
    RefreshOffers,
    Report,
    ReportLine,
    ResearchAssessment,
    ResearchCandidate,
    SelectOffers,
    SellerTrust,
    TrustSignals,
    UpdateJobSpecs,
    VerifiedOffer,
    now,
)
from bharat_sourcer.storage import MemoryJobStore

ROBO = "https://robocraze.com/products/"
COMPO = "https://compoindia.com/product/"


def offer(
    url,
    price="100.00",
    grade="A",
    stock="in_stock",
    age=0,
    tax=None,
    trust=None,
    anomaly=False,
    image=None,
    match=None,
    pack_qty=None,
):
    made = VerifiedOffer(
        url=url,
        seller=url.split("/")[2],
        title="Synthetic test part",
        image_url=image,
        price_inr=price,
        stock=stock,
        tax_included=tax,
        checked_at=now() - timedelta(hours=age),
        compatibility=Compatibility(
            status="unknown" if grade is None else "compatible", grade=grade
        ),
        trust=SellerTrust(label=trust, signals=TrustSignals(price_anomaly=anomaly))
        if trust
        else None,
    )
    # Fields from the matching stream (not in this branch's schema yet).
    if match is not None:
        object.__setattr__(made, "match", match)
    if pack_qty is not None:
        object.__setattr__(made, "pack_qty", pack_qty)
    return made


def line(line_id, offers, qty=1, name=None, **extra):
    return ReportLine(
        item=BomItem(line_id=line_id, raw_name=name or f"Part {line_id}", qty=qty),
        sourcing_status="offers_found" if offers else "no_verified_offers",
        offers=offers,
        **extra,
    )


def report(*lines):
    return Report(demo=False, summary="Synthetic test report", lines=list(lines))


def scored(target):
    return {str(s.offer.url): s for s in line_scores(target)}


# Scoring


def test_weights_table_sums_to_one():
    assert sum(weight for weight, _ in WEIGHTS.values()) == pytest.approx(1.0)


def test_match_quality_orders_offers_and_mismatch_is_excluded():
    target = line(
        "L01",
        [
            offer("https://a.example/exact", match={"status": "exact", "score": 1.0}),
            offer("https://a.example/compatible", match={"status": "compatible", "score": 0.9}),
            offer("https://a.example/partial", match={"status": "partial", "score": 0.5}),
            offer("https://a.example/none"),
            offer("https://a.example/mismatch", match={"status": "mismatch", "score": 0.1}),
        ],
    )
    scores = line_scores(target)
    assert [str(s.offer.url).rsplit("/", 1)[1] for s in scores] == [
        "exact",
        "compatible",
        "none",
        "partial",
        "mismatch",
    ]
    assert scores[-1].excluded and scores[-1].score == 0
    assert any("Match: exact" in r for r in scores[0].reasons)
    assert any("neutral weight" in r for r in scores[2].reasons)


def test_grade_stock_trust_and_freshness_factors():
    target = line(
        "L01",
        [
            offer("https://a.example/a", grade="A", trust="established"),
            offer("https://a.example/b", grade="B", trust="established"),
            offer("https://a.example/unknown", grade=None, trust="established"),
            offer("https://a.example/c", grade="C", trust="established"),
            offer("https://a.example/x", grade="X", trust="established"),
            offer("https://a.example/preorder", stock="preorder", trust="established"),
            offer("https://a.example/oos", stock="out_of_stock", trust="established"),
            offer("https://a.example/unverified", trust="unverified"),
            offer("https://a.example/anomaly", trust="established", anomaly=True),
            offer("https://a.example/old", trust="established", age=80),
        ],
    )
    s = {url.rsplit("/", 1)[1]: entry for url, entry in scored(target).items()}
    assert s["a"].score > s["b"].score > s["unknown"].score > s["c"].score
    assert s["x"].excluded and s["oos"].excluded
    assert s["a"].score > s["preorder"].score and s["a"].score > s["unverified"].score
    assert s["a"].score > s["anomaly"].score and s["a"].score > s["old"].score
    assert any("price far from other listings" in r for r in s["anomaly"].reasons)
    # One reason per factor: match, grade, stock, seller, price, freshness.
    assert len(s["a"].reasons) == 6


def test_out_of_stock_is_kept_when_nothing_else_is_available():
    target = line("L01", [offer("https://a.example/oos", stock="out_of_stock")])
    entry = line_scores(target)[0]
    assert entry.excluded is None
    assert any("no listing is available" in r for r in entry.reasons)


def test_effective_unit_cost_uses_pack_size():
    single = offer("https://a.example/single", price="10.00")
    pack = offer("https://a.example/pack", price="50.00", pack_qty=10)
    target = line("L01", [single, pack], qty=12)
    context = context_for(target)
    pack_score = score_offer(target, pack, context)
    single_score = score_offer(target, single, context)
    assert (pack_score.packs, pack_score.cost) == (2, Decimal("100.00"))
    assert (single_score.packs, single_score.cost) == (12, Decimal("120.00"))
    assert pack_score.score > single_score.score
    assert any("2 packs of 10 cover the 12 needed" in r for r in pack_score.reasons)
    assert any("8 spare" in r for r in pack_score.reasons)


# Basket


def consolidation_report():
    # robocraze.com: prices include GST, free shipping above ₹999 (policy table).
    # compoindia.com: prices exclude GST (18% added), free shipping above ₹2000.
    return report(
        line("L01", [offer(ROBO + "l01", "1500.00"), offer(COMPO + "l01", "1100.00")]),
        line("L02", [offer(ROBO + "l02", "1500.00"), offer(COMPO + "l02", "1100.00")]),
        line("L03", [offer(ROBO + "l03", "1000.00")]),
    )


def sellers(result):
    return {ln.item.line_id: str(ln.selected_offer_url).split("/")[2] for ln in result.lines}


def test_basket_consolidates_when_savings_are_below_the_penalty():
    # Splitting L01/L02 to Compoindia saves 2 × (1500 − 1298) = ₹404 landed.
    result = consolidation_report()
    assert apply_recommendations(result, Decimal("500")) == "exhaustive"
    assert set(sellers(result).values()) == {"robocraze.com"}
    plan = result.order_plan
    assert plan.seller_count == 1 and plan.ready
    assert [ln.line_id for ln in plan.sellers[0].lines] == ["L01", "L02", "L03"]
    assert plan.sellers[0].shipping.amount_inr == "0.00"
    reasons = result.lines[0].recommendation.reasons
    assert any("grouped with L02, L03 from robocraze.com" in r for r in reasons)
    assert any("avoids a separate order" in r for r in reasons)


def test_basket_splits_when_savings_exceed_the_penalty():
    result = consolidation_report()
    apply_recommendations(result, Decimal("300"))
    assert sellers(result) == {
        "L01": "compoindia.com",
        "L02": "compoindia.com",
        "L03": "robocraze.com",
    }
    plan = result.order_plan
    assert plan.seller_count == 2
    compo = next(s for s in plan.sellers if s.seller == "compoindia.com")
    assert compo.subtotal_inr == "2200.00" and compo.gst.amount_inr == "396.00"
    assert [str(u) for u in compo.product_links] == [COMPO + "l01", COMPO + "l02"]
    assert plan.costing.total.amount_inr == "3596.00"


def test_greedy_basket_matches_exhaustive(monkeypatch):
    from bharat_sourcer import recommend

    monkeypatch.setattr(recommend, "MAX_COMBINATIONS", 1)
    result = consolidation_report()
    assert apply_recommendations(result, Decimal("500")) == "greedy"
    assert set(sellers(result).values()) == {"robocraze.com"}


def test_pack_rounding_in_order_plan():
    result = report(line("L01", [offer(ROBO + "led", "50.00", pack_qty=10)], qty=12))
    apply_recommendations(result)
    entry = result.order_plan.sellers[0].lines[0]
    assert (entry.qty, entry.pack_qty, entry.packs, entry.units) == (12, 10, 2, 20)
    assert entry.unit_price_inr == "50.00" and entry.line_price_inr == "100.00"
    assert result.lines[0].subtotal_inr == "100.00"
    assert result.costing.parts.amount_inr == "100.00"


def test_unknown_grade_is_recommended_but_not_selected():
    result = report(line("L01", [offer(ROBO + "a", grade=None)]))
    apply_recommendations(result)
    target = result.lines[0]
    assert str(target.recommended_offer_url) == ROBO + "a"
    assert target.selected_offer_url is None and target.selection_source is None
    assert "compatibility is unknown" in target.recommendation.blocked_reason
    entry = result.order_plan.sellers[0].lines[0]
    assert entry.selected is False and entry.blocked_reason
    assert result.costing.excluded_line_ids == ["L01"]  # selection costing is unchanged


def test_grade_b_is_applied_without_acknowledging_changes():
    result = report(line("L01", [offer(ROBO + "b", grade="B")]))
    apply_recommendations(result)
    target = result.lines[0]
    assert target.selection_source == "recommended" and target.grade == "B"
    assert target.changes_accepted is False
    assert result.order_plan.sellers[0].lines[0].changes_required is True


def test_unsourced_group_reasons_and_next_steps():
    research = PartResearch(
        status="ready",
        summary="Synthetic research",
        candidates=[
            ResearchCandidate(
                url="https://maker.example/part",
                title="Synthetic module",
                category="module",
                kind="manufacturer",
                identity_quote="Synthetic module",
                match="exact",
                assessment=ResearchAssessment(status="potential_match", explanation="test"),
            )
        ],
    )
    needs_value = line("L01", [], name="Resistor")
    needs_value.item.clarifications = [
        Clarification(field="resistance", question="Which resistor value do you need?")
    ]
    no_offers = line("L02", [], research=research)
    mismatch = line(
        "L03", [offer(ROBO + "x", match={"status": "mismatch", "score": 0.0}, grade="X")]
    )
    result = report(needs_value, no_offers, mismatch, line("L04", [offer(ROBO + "ok")]))
    apply_recommendations(result)
    unsourced = {u.line_id: u for u in result.order_plan.unsourced}
    assert unsourced["L01"].reason == "needs_value"
    assert unsourced["L01"].next_steps == ["Which resistor value do you need?"]
    assert unsourced["L02"].reason == "no_offers"
    assert "research candidate" in unsourced["L02"].next_steps[0].lower()
    assert [str(u) for u in unsourced["L02"].research_urls] == ["https://maker.example/part"]
    assert unsourced["L03"].reason == "no_acceptable_offer"
    assert "does not match" in unsourced["L03"].message
    assert result.order_plan.ready is False and result.order_plan.seller_count == 1


def test_low_scores_are_not_recommended():
    bad = offer(
        ROBO + "bad",
        grade="D",
        stock="preorder",
        trust="unverified",
        anomaly=True,
        age=100,
        match={"status": "partial", "score": 0.0},
    )
    target = line("L01", [bad])
    assert line_scores(target)[0].score < MIN_ACCEPTABLE
    result = report(target)
    apply_recommendations(result)
    assert result.lines[0].recommended_offer_url is None
    assert result.order_plan.unsourced[0].reason == "no_acceptable_offer"


# Line images


def test_line_image_fallback_order():
    photo = "https://cdn.example/{}.jpg"
    reference = PartImage(
        url="https://page.example/photo.jpg",
        kind="source",
        label="Project page photo",
        source_url="https://page.example/",
    )
    chosen = offer(ROBO + "chosen", image=photo.format("chosen"))
    other = offer(ROBO + "other", price="200.00", image=photo.format("other"))
    plain = offer(ROBO + "plain", price="90.00")
    result = report(
        line("L01", [other, chosen], image_candidates=[reference]),
        line("L02", [plain, other.model_copy()], image_candidates=[reference]),
        line("L03", [plain.model_copy()], image_candidates=[reference]),
        line("L04", [plain.model_copy()], name="10k resistor"),
        line("L05", [], name="Mystery gizmo"),
    )
    result.lines[0].offers[1] = chosen
    apply_recommendations(result)
    # L01: the recommendation (cheapest) has a photo, and it becomes the selection.
    images = [ln.line_image for ln in result.lines]
    assert images[0].kind == "selected_offer" and images[0].url == photo.format("chosen")
    assert images[1].kind == "offer" and images[1].url == photo.format("other")
    assert images[2].kind == "reference" and images[2].url == reference.url
    assert images[3].kind == "category" and images[3].url.startswith("data:image/svg+xml")
    assert images[4].kind == "placeholder"
    result.lines[0].selected_offer_url = None
    result.lines[0].selection_source = None
    apply_recommendations(result)
    assert result.lines[0].line_image.kind == "selected_offer"
    # A recommended offer that is not selectable still provides the image.
    result.lines[0].offers = [offer(ROBO + "unknown", grade=None, image=photo.format("rec"))]
    apply_recommendations(result)
    assert result.lines[0].line_image.kind == "recommended_offer"


def test_demo_reports_get_images_but_no_plan():
    result = Report(demo=True, summary="Demo", lines=[line("L01", [offer(ROBO + "a")])])
    apply_recommendations(result)
    assert result.order_plan is None and result.lines[0].selected_offer_url is None
    assert result.lines[0].line_image is not None


# Completion hook and selection_source (mocked sourcing, no Gemini)


class Extractor:
    def extract(self, url):
        return [
            BomItem(line_id="L01", raw_name="Synthetic board"),
            BomItem(line_id="L02", raw_name="Synthetic sensor", qty=2),
        ]


class Source:
    def __init__(self):
        self.offers = {
            "L01": [offer(ROBO + "l01", "300.00"), offer(ROBO + "l01-alt", "320.00")],
            "L02": [offer(ROBO + "l02", "200.00", image="https://cdn.example/l02.jpg")],
        }

    def source(self, item):
        return ReportLine(
            item=item,
            sourcing_status="offers_found",
            offers=[o.model_copy(deep=True) for o in self.offers[item.line_id]],
        )


def completed_job():
    source = Source()
    service = JobService(Extractor(), store=MemoryJobStore(), sourcing=source)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    return service, source, job.job_id, token


def test_completion_applies_recommendations_and_order_plan():
    service, _, job_id, token = completed_job()
    job = service.get(job_id, token)
    assert job.status == "done"
    first, second = job.report.lines
    assert first.selection_source == second.selection_source == "recommended"
    assert str(first.selected_offer_url) == ROBO + "l01"
    assert first.recommendation.status == "recommended" and first.recommendation.reasons
    assert second.line_image.kind == "selected_offer"
    plan = job.report.order_plan
    assert plan.ready and plan.seller_count == 1
    assert plan.sellers[0].subtotal_inr == "700.00"
    assert job.report.costing.complete


def test_manual_selection_survives_refresh_and_spec_updates():
    service, source, job_id, token = completed_job()
    choose = SelectOffers.model_validate(
        {"selections": [{"line_id": "L01", "offer_url": ROBO + "l01-alt"}]}
    )
    job = service.select_offers(job_id, token, choose)
    assert job.report.lines[0].selection_source == "user"
    service.update_specs(
        job_id,
        token,
        UpdateJobSpecs.model_validate(
            {"updates": [{"line_id": "L02", "specs": {"family": "sensor"}}]}
        ),
    )
    job = service.get(job_id, token)
    assert str(job.report.lines[0].selected_offer_url) == ROBO + "l01-alt"
    # The edited line was re-graded and re-recommended; the user's line was not touched.
    assert str(job.report.lines[1].recommended_offer_url) == ROBO + "l02"
    # Refresh the user's line: the same offer comes back and is restored.
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
    pending = service.get(job_id, token)
    assert pending.report.lines[0].selection_source == "user"
    assert pending.report.order_plan.unsourced[0].reason == "pending"
    service.finish(job_id)
    job = service.get(job_id, token)
    target = job.report.lines[0]
    assert target.selection_source == "user"
    assert str(target.selected_offer_url) == ROBO + "l01-alt"
    # If the user's offer disappears, nothing else is selected for them.
    source.offers["L01"] = [offer(ROBO + "l01", "300.00")]
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
    service.finish(job_id)
    target = service.get(job_id, token).report.lines[0]
    assert target.selected_offer_url is None and target.selection_source == "user"
    assert str(target.user_offer_url) == ROBO + "l01-alt"
    assert str(target.recommended_offer_url) == ROBO + "l01"


def test_user_cleared_line_stays_cleared():
    service, _, job_id, token = completed_job()
    clear = SelectOffers.model_validate({"selections": [{"line_id": "L01", "offer_url": None}]})
    service.select_offers(job_id, token, clear)
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
    service.finish(job_id)
    job = service.get(job_id, token)
    assert job.report.lines[0].selected_offer_url is None
    assert job.report.order_plan.unsourced[0].reason == "cleared_by_user"


def test_plans_endpoint_includes_recommended_alternative():
    from bharat_sourcer.plans import plans_for

    service, _, job_id, token = completed_job()
    result = plans_for(service.get(job_id, token))
    kinds = [plan.kind for plan in result.plans]
    assert kinds == ["cheapest", "fewest_sellers", "recommended"]
    assert result.plans[-1].matches_selection
