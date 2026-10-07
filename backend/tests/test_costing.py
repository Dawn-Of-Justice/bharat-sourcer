"""Costing estimates, GST detection, import baseline and cart plans (all offline).

Offers below are synthetic test data; seller hosts are used only to look up the dated
policy table. Fixture prices are historical parsing snapshots, never current prices.
"""

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer import plans
from bharat_sourcer.config import Settings
from bharat_sourcer.costing import Pick, cost_picks, load, parse_usd, policy_for, update_costs
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    Compatibility,
    CreateJob,
    PartResearch,
    Report,
    ReportLine,
    ResearchAssessment,
    ResearchCandidate,
    ResearchFact,
    VerifiedOffer,
    now,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import verify_page
from bharat_sourcer.sourcing.tax import detect_tax_included

FIXTURES = Path(__file__).parent / "fixtures" / "seller_pages"
HTML = {"content-type": "text/html; charset=utf-8"}
QUARTZ = "https://quartzcomponents.com/products/"
EVELTA = "https://evelta.com/"


def fixture_offer(name, query):
    body = (FIXTURES / name).read_bytes()
    url = body.decode("utf-8")[:400].split("Source: ")[1].split()[0]
    return verify_page(Page(url, 200, HTML, body), query)


# GST detection


def test_fixture_json_ld_tax_declarations():
    compo = fixture_offer("compoindia_ttp223.html", "TTP223 touch sensor")
    assert compo.tax_included is False
    assert "valueAddedTaxIncluded=false" in compo.tax_evidence
    rytronics = fixture_offer("rytronics_oled_096.html", "0.96 inch OLED display")
    assert rytronics.tax_included is True  # declared as the string "true"
    robocraze = fixture_offer("robocraze_resistor_10k.html", "10k resistor")
    assert robocraze.tax_included is None and robocraze.tax_evidence is None


def test_legal_mrp_line_is_not_a_selling_price_declaration():
    body = (FIXTURES / "electronicscomp_ttp223.html").read_text(encoding="utf-8")
    assert "Inclusive of all Taxes" in body
    assert detect_tax_included({}, body) == (None, None)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<span>Rs 15/-</span> <small>Incl. GST (No Hidden Charges)</small>", True),
        ("₹215 ₹329 (inc GST)", True),
        ("Price inclusive of all taxes", True),
        ("₹ 25.00 (Exclusive GST Tax 18%)", False),
        ("₹85 + GST", False),
        ("Prices excl. GST", False),
        ("Get a GST invoice for business purchases", None),
        ("Incl. GST on this item; accessories ₹10 + GST", None),
    ],
)
def test_page_text_phrases(text, expected):
    value, evidence = detect_tax_included({}, f"<div>{text}</div>")
    assert value is expected
    if expected is None and "Incl" in text:
        assert evidence.startswith("Conflicting")


def test_structured_and_text_conflict_is_unknown():
    offer = {"priceSpecification": {"0": {"valueAddedTaxIncluded": False}}}
    assert detect_tax_included(offer, "<p>incl. GST</p>")[0] is None
    assert detect_tax_included(offer, "<p>nothing</p>")[0] is False


# Seller policy table and per-seller estimates


def test_policy_table_entries_are_dated_and_sourced_or_unverified():
    data = load("seller_policies.json")
    assert "ESTIMATES only" in data["_label"]
    for host, entry in data["sellers"].items():
        for section in ("shipping", "gst"):
            policy = entry.get(section)
            if policy is None:
                continue
            assert policy["checked_on"], host
            assert policy["unverified"] or policy["source_url"], host
    rates = load("tax_rates.json")
    assert "not tax advice" in rates["_label"]
    assert rates["import"]["unverified"] and rates["courier"]["unverified"]
    assert policy_for("www.Evelta.com")["shipping"]["flat_fee_inr"] == "45.00"


def pick(line, seller, price, qty=1, tax=None):
    return Pick(line_id=line, seller=seller, unit_price=Decimal(price), qty=qty, tax_included=tax)


def test_threshold_flat_fee_and_gst_estimates():
    costing = cost_picks(
        [
            pick("L01", "quartzcomponents.com", "120.00", qty=2, tax=True),
            pick("L02", "evelta.com", "100.00"),
        ],
        [],
    )
    quartz, evelta = costing.sellers
    assert quartz.parts.amount_inr == "240.00" and quartz.parts.status == "known"
    assert quartz.gst.amount_inr == "0.00" and quartz.gst.status == "known"
    assert quartz.shipping.amount_inr == "50.00" and quartz.shipping.status == "estimated"
    assert quartz.free_shipping_gap_inr == "260.01"  # "More than ₹500"
    assert quartz.policy.source_url is not None
    # Evelta: ex-GST prices per its policy entry; ₹45 + 18% GST below ₹1000.
    assert evelta.gst.amount_inr == "18.00" and evelta.gst.status == "estimated"
    assert any("not tax advice" in a for a in evelta.gst.assumptions)
    assert evelta.shipping.amount_inr == "53.10"
    assert evelta.total.amount_inr == "171.10"
    assert costing.total.amount_inr == "461.10" and costing.total.status == "estimated"
    assert costing.complete and "not a final payable total" in costing.disclaimer


def test_free_shipping_above_threshold_and_inclusive_threshold():
    above = cost_picks([pick("L01", "quartzcomponents.com", "500.01", tax=True)], [])
    assert above.shipping.amount_inr == "0.00" and above.shipping.status == "estimated"
    equal = cost_picks([pick("L01", "quartzcomponents.com", "500.00", tax=True)], [])
    assert equal.shipping.amount_inr == "50.00"
    compo = cost_picks([pick("L01", "compoindia.com", "2000.00")], [])
    assert compo.shipping.amount_inr == "0.00"  # "on or above Rs.2000"
    assert compo.gst.amount_inr == "360.00"


@pytest.mark.parametrize(
    "seller,reason",
    [
        ("unknown-shop.example", "no shipping policy"),
        ("www.flyrobo.in", "unverified"),
        ("robocraze.com", "fee is not stated"),
    ],
)
def test_unknown_shipping_is_never_zero(seller, reason):
    costing = cost_picks([pick("L01", seller, "100.00", tax=True)], [])
    assert costing.shipping.status == "unknown" and costing.shipping.amount_inr is None
    assert costing.total.amount_inr is None and costing.total.partial_inr == "100.00"
    assert any(reason in a for a in costing.shipping.assumptions)


def test_unknown_gst_status_makes_total_unknown():
    costing = cost_picks([pick("L01", "quartzcomponents.com", "600.00")], ["L02"])
    assert costing.gst.status == "unknown" and costing.total.amount_inr is None
    assert costing.complete is False and costing.excluded_line_ids == ["L02"]


# Import baseline


def test_parse_usd_accepts_only_a_single_usd_amount():
    assert parse_usd("$4.95", None) == Decimal("4.95")
    assert parse_usd("4.95", "USD") == Decimal("4.95")
    assert parse_usd("USD 12", None) == Decimal("12")
    for value, unit in [
        ("₹400", None),
        ("4.95", "INR"),
        ("$4.95 per pack of 10", None),
        ("4", None),
    ]:
        assert parse_usd(value, unit) is None


def offer(url, price, tax=None, grade="A", stock="in_stock", age=0):
    return VerifiedOffer(
        url=url,
        seller=url.split("/")[2],
        title="Synthetic test part",
        price_inr=price,
        stock=stock,
        tax_included=tax,
        checked_at=now() - timedelta(hours=age),
        compatibility=Compatibility(status="compatible", grade=grade),
    )


def research_with_price(value, unit=None):
    return PartResearch(
        status="ready",
        summary="Synthetic research",
        candidates=[
            ResearchCandidate(
                url="https://distributor.example/part",
                title="Synthetic part",
                category="module",
                kind="seller",
                identity_quote="Synthetic part",
                match="exact",
                facts=[ResearchFact(name="unit price", value=value, unit=unit, quote=value)],
                assessment=ResearchAssessment(status="potential_match", explanation="test"),
            )
        ],
    )


def test_import_baseline_arithmetic_and_savings():
    report = Report(
        demo=False,
        summary="Synthetic",
        lines=[
            ReportLine(
                item=BomItem(line_id="L01", raw_name="Part", qty=2),
                sourcing_status="offers_found",
                offers=[offer(QUARTZ + "a", "600.00", tax=True)],
                selected_offer_url=QUARTZ + "a",
                price_inr="600.00",
                grade="A",
                research=research_with_price("$10.00"),
            )
        ],
    )
    update_costs(report)
    costing = report.costing
    baseline = costing.import_baseline
    # goods 20 USD × 95.99 = 1919.80; courier 30 × 95.99 = 2879.70; A = 4799.50
    # BCD 479.95 + SWS 47.995 + IGST 28% × 5327.445 = 1491.6846 → duty 2019.63
    assert baseline.goods_usd == "20.00" and baseline.goods_inr.amount_inr == "1919.80"
    assert baseline.courier_inr.amount_inr == "2879.70"
    assert baseline.duty_inr.amount_inr == "2019.63"
    assert baseline.landed_inr.amount_inr == "6819.13"
    assert baseline.complete and baseline.landed_inr.status == "estimated"
    assert any("unverified" in a for a in baseline.courier_inr.assumptions)
    assert "https://distributor.example/part" in baseline.sources
    assert costing.total.amount_inr == "1200.00"  # free shipping above ₹500
    assert costing.savings_vs_import.amount_inr == "5619.13"


def test_no_reference_means_no_baseline_and_partial_means_no_savings():
    lines = [
        ReportLine(
            item=BomItem(line_id=line_id, raw_name="Part"),
            sourcing_status="offers_found",
            research=research,
        )
        for line_id, research in [("L01", research_with_price("$3.00")), ("L02", None)]
    ]
    report = Report(demo=False, summary="Synthetic", lines=lines)
    update_costs(report)
    assert report.costing.import_baseline.complete is False
    assert report.costing.import_baseline.line_ids == ["L01"]
    assert report.costing.savings_vs_import is None
    lines[0].research = research_with_price("₹300")
    update_costs(report)
    assert report.costing.import_baseline is None


# API: costing on selection, import references and plans


def app_with_report(lines, demo=False):
    app = create_app(Settings(_env_file=None, demo_mode=True))
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://example.com"))

    def seed(record):
        record.job.demo = demo
        record.job.status = "done"
        record.job.report = Report(demo=demo, summary="Synthetic test report", lines=lines)

    service.store.mutate(job.job_id, seed)
    return TestClient(app), job.job_id, {"X-Job-Token": token}


def plan_lines():
    def line(line_id, offers):
        return ReportLine(
            item=BomItem(line_id=line_id, raw_name="Part " + line_id),
            sourcing_status="offers_found",
            offers=offers,
        )

    return [
        line("L01", [offer(QUARTZ + "l01", "260.00", tax=True), offer(EVELTA + "l01", "200.00")]),
        line("L02", [offer(QUARTZ + "l02", "260.00", tax=True), offer(EVELTA + "l02", "300.00")]),
        line(
            "L03",
            [
                offer(EVELTA + "l03", "900.00"),
                offer(QUARTZ + "l03-old", "1.00", tax=True, age=25),
                offer(QUARTZ + "l03-oos", "1.00", tax=True, stock="out_of_stock"),
                offer(QUARTZ + "l03-x", "1.00", tax=True, grade="X"),
            ],
        ),
        ReportLine(
            item=BomItem(line_id="L04", raw_name="Owned", user_has_it=True),
            sourcing_status="already_owned",
        ),
    ]


def test_selection_populates_costing_and_demo_never_does():
    client, job_id, headers = app_with_report(plan_lines())
    body = {"selections": [{"line_id": "L01", "offer_url": EVELTA + "l01"}]}
    report = client.post(f"/v1/jobs/{job_id}/selections", json=body, headers=headers).json()
    costing = report["report"]["costing"]
    assert report["report"]["total_inr"] is None  # still never a payable total
    assert costing["complete"] is False and costing["excluded_line_ids"] == ["L02", "L03"]
    assert costing["sellers"][0]["seller"] == "evelta.com"
    assert costing["total"]["amount_inr"] == "289.10"
    client, job_id, headers = app_with_report(plan_lines(), demo=True)
    assert client.get(f"/v1/jobs/{job_id}", headers=headers).json()["report"]["costing"] is None


def test_plans_cheapest_uses_thresholds_and_fewest_sellers():
    client, job_id, headers = app_with_report(plan_lines())
    path = f"/v1/jobs/{job_id}/plans"
    assert client.get(path).status_code == 404
    result = client.get(path, headers=headers).json()
    assert result["method"] == "exhaustive" and result["uncovered_line_ids"] == []
    cheapest, fewest, recommended = result["plans"]
    assert recommended["kind"] == "recommended" and result["seller_penalty_inr"] == "60.00"
    # Moving L01 to Evelta lifts it over ₹1000 (free shipping) although Quartz then pays ₹50.
    assert {p["line_id"]: p["seller"] for p in cheapest["picks"]} == {
        "L01": "evelta.com",
        "L02": "quartzcomponents.com",
        "L03": "evelta.com",
    }
    assert cheapest["costing"]["total"]["amount_inr"] == "1608.00"
    assert fewest["seller_count"] == 1 and fewest["costing"]["total"]["amount_inr"] == "1652.00"
    assert all("l03-" not in p["offer_url"] for p in cheapest["picks"] + fewest["picks"])
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert all(line["selected_offer_url"] is None for line in job["report"]["lines"])


def test_greedy_plans_match_on_small_case(monkeypatch):
    monkeypatch.setattr(plans, "MAX_COMBINATIONS", 1)
    client, job_id, headers = app_with_report(plan_lines())
    result = client.get(f"/v1/jobs/{job_id}/plans", headers=headers).json()
    assert result["method"] == "greedy"
    totals = [plan["costing"]["total"]["amount_inr"] for plan in result["plans"][:2]]
    assert totals == ["1608.00", "1652.00"]


def test_plans_report_uncovered_and_reject_demo():
    lines = plan_lines()
    lines[2].offers = lines[2].offers[1:]
    client, job_id, headers = app_with_report(lines)
    result = client.get(f"/v1/jobs/{job_id}/plans", headers=headers).json()
    assert result["uncovered_line_ids"] == ["L03"]
    assert result["plans"][0]["costing"]["complete"] is False
    client, job_id, headers = app_with_report(plan_lines(), demo=True)
    response = client.get(f"/v1/jobs/{job_id}/plans", headers=headers)
    assert response.status_code == 409


def test_import_references_set_clear_and_validate():
    client, job_id, headers = app_with_report(plan_lines())
    path = f"/v1/jobs/{job_id}/import-references"
    body = {"references": [{"line_id": "L01", "price_usd": "2.50"}]}
    assert client.post(path, json=body).status_code == 404
    report = client.post(path, json=body, headers=headers).json()["report"]
    assert report["lines"][0]["import_reference"]["source"] == "user"
    assert report["costing"]["import_baseline"]["line_ids"] == ["L01"]
    for bad in [
        {"line_id": "L04", "price_usd": "1.00"},
        {"line_id": "L99", "price_usd": "1.00"},
        {"line_id": "L01", "price_usd": "0.00"},
    ]:
        response = client.post(path, json={"references": [bad]}, headers=headers)
        assert response.json()["error"]["code"] == "INVALID_REFERENCE"
    cleared = client.post(path, json={"references": [{"line_id": "L01"}]}, headers=headers)
    assert cleared.json()["report"]["costing"]["import_baseline"] is None


def test_stored_reports_without_new_fields_still_load():
    stored = {"demo": False, "summary": "Old", "lines": [], "selected_parts_subtotal_inr": "0.00"}
    assert Report.model_validate(json.loads(json.dumps(stored))).costing is None
