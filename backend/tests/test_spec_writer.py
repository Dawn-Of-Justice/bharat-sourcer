"""Engine fixes from the 2026-10-07 live check of "Freeform Light-Activated LED Circuit".

Batched spec writer, seed classification, never auto-selecting a guessed value, numeric
conflict checks and the research_skipped stage. Gemini is always mocked: every model reply
below is a hand-written fixture, not live output. Listings and prices are synthetic test
data, never verified seller quotes.
"""

import json

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractionResult
from bharat_sourcer.jobs import JobService
from bharat_sourcer.recommend import apply_recommendations
from bharat_sourcer.schemas import (
    BomItem,
    BuyableSpec,
    Compatibility,
    ConfirmJob,
    CreateJob,
    MatchClaim,
    OfferMatch,
    PartResearch,
    ProjectContext,
    RefreshOffers,
    Report,
    ReportLine,
    SearchAttribution,
    SpecParam,
    VerifiedOffer,
    now,
)
from bharat_sourcer.sourcing.cache import MemoryCache
from bharat_sourcer.sourcing.judge import VerdictDraft, checked_verdict
from bharat_sourcer.sourcing.matching import Candidate
from bharat_sourcer.sourcing.part_spec import (
    awg_m,
    buyable_spec,
    guard_spec,
    is_assortment,
    measure_conflicts,
    seed_spec,
)
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.sourcing.spec_writer import GeminiSpecWriter
from bharat_sourcer.usage import JobLedger, attribute

SETTINGS = Settings(_env_file=None, gemini_api_key="test")
PROJECT = ProjectContext(
    summary="A freeform, dead-bug soldered light-activated LED circuit on 3.6 V DC.",
    power="3.6 V DC",
    assumptions=[
        "The second through-hole resistor appears to be in the 1kΩ to 10kΩ range based on "
        "band colors, but exact nominal value is unknown."
    ],
)
WIRE, RESISTOR, LDR = "Bare copper wire", "Through-hole resistor", "LDR"


def items():
    return [
        BomItem(line_id="L01", raw_name=WIRE),
        BomItem(line_id="L02", raw_name=RESISTOR),
        BomItem(line_id="L03", raw_name=LDR),
        BomItem(line_id="L04", raw_name="Battery", user_has_it=True),
    ]


# Mocked model output for the three lines that need a spec (ids follow the request order).
SPEC_REPLY = {
    "items": [
        {
            "id": 0,
            "buyable": {
                "category": "wire",
                "mount": "tht",
                "mount_reason": "Hand-soldered freeform build.",
                "params": [
                    {
                        "name": "wire_gauge",
                        "value": "18 AWG",
                        "operator": "between",
                        "value_max": "24 AWG",
                        "origin": "inferred",
                        "reason": "A small freeform circuit needs thin bus wire.",
                    }
                ],
                "prefer": ["tinned"],
                "queries": ["tinned copper wire 22 AWG"],
            },
        },
        {
            "id": 1,
            "buyable": {
                "category": "resistor",
                "mount": "tht",
                "mount_reason": "Hand-soldered freeform build.",
                "params": [
                    {
                        "name": "resistance",
                        "value": "1kΩ",
                        "operator": "between",
                        "value_max": "10kΩ",
                        "origin": "inferred",
                        "reason": "Project assumptions give a 1k to 10k range.",
                    }
                ],
                "needs_value": True,
                "needs_value_reason": "The exact value is unknown.",
            },
        },
        {
            "id": 2,
            "buyable": {
                "category": "ldr",
                "mount": "tht",
                "mount_reason": "Leaded part soldered freeform.",
                "synonyms": ["photoresistor"],
            },
        },
    ]
}


def reply(body, finish="STOP"):
    text = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(
        200,
        json={
            "candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 3000, "candidatesTokenCount": 900},
        },
    )


class Model:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request):
        self.requests.append(request)
        return self.responses.pop(0)

    def writer(self, cache=None):
        return GeminiSpecWriter(SETTINGS, httpx.MockTransport(self), cache)

    def sent(self, index=-1):
        return json.loads(self.requests[index].content)


# Batched spec writer


def test_one_call_writes_specs_for_every_line_without_one():
    model = Model(reply(SPEC_REPLY))
    specs = model.writer().write(items(), PROJECT)
    assert len(model.requests) == 1
    assert set(specs) == {"L01", "L02", "L03"}  # the owned line is not sent
    payload = model.sent()
    assert "gemini-3.8-flash:generateContent" in str(model.requests[0].url)
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    sent = json.loads(payload["contents"][0]["parts"][0]["text"])
    assert [line["name"] for line in sent["lines"]] == [WIRE, RESISTOR, LDR]
    assert sent["project"]["power"] == "3.6 V DC" and sent["project"]["assumptions"]
    assert "freeform" in payload["systemInstruction"]["parts"][0]["text"]
    wire = specs["L01"]
    assert wire.origin == "ai_inferred" and wire.category == "wire" and wire.mount == "tht"
    gauge = wire.params[0]
    assert (gauge.si_value, gauge.si_value_max, gauge.unit) == (18, 24, "AWG")
    resistor = specs["L02"]
    # The range has a basis in the assumptions, but it is not a value: still needs_value.
    assert resistor.needs_value and resistor.params[0].si_value == 1000
    assert resistor.params[0].si_value_max == 10000


def test_guardrails_drop_an_inferred_value_without_a_project_basis():
    guessed = json.loads(json.dumps(SPEC_REPLY))
    guessed["items"][1]["buyable"]["params"] = [
        {"name": "resistance", "value": "220 ohm", "origin": "inferred", "reason": "Typical."}
    ]
    guessed["items"][1]["buyable"]["needs_value"] = False
    specs = Model(reply(guessed)).writer().write(items(), PROJECT)
    assert specs["L02"].params == [] and specs["L02"].needs_value
    assert any("no basis" in r for r in specs["L02"].reasons)


def test_specs_are_cached_per_item_and_project():
    cache = MemoryCache()
    first = Model(reply(SPEC_REPLY))
    first.writer(cache).write(items(), PROJECT)
    second = Model()  # no response queued: any call would fail the test
    specs = second.writer(cache).write(items(), PROJECT)
    assert second.requests == [] and set(specs) == {"L01", "L02", "L03"}
    other = ProjectContext(summary="A breadboard LED blinker on 5 V.")
    third = Model(reply(SPEC_REPLY))
    third.writer(cache).write(items(), other)
    assert len(third.requests) == 1  # another project is another key


@pytest.mark.parametrize(
    "response",
    [httpx.Response(400), reply("{not json"), reply(SPEC_REPLY, finish="MAX_TOKENS")],
)
def test_failure_falls_back_to_seed_specs_and_is_not_repeated(response):
    model = Model(response)
    writer = model.writer()
    assert writer.write(items(), PROJECT) == {}
    # A queued run for the next line does not pay for the same failing call again.
    assert writer.write(items(), PROJECT) == {} and len(model.requests) == 1


def test_budget_is_respected():
    model = Model(reply(SPEC_REPLY))
    with attribute(JobLedger("j1", budget_usd=0.0)):
        assert model.writer().write(items(), PROJECT) == {}
    assert model.requests == []


def test_lines_with_a_spec_make_no_call():
    model = Model()
    spec = BuyableSpec(origin="user", category="wire")
    done = [BomItem(line_id="L01", raw_name=WIRE, buyable_spec=spec)]
    assert model.writer().write(done, PROJECT) == {} and model.requests == []


class Extractor:
    def extract(self, url):
        return ExtractionResult(items=items(), project=PROJECT)


class NoDiscovery:
    def __init__(self):
        self.queries = []

    def discover(self, query):
        self.queries.append(query)
        return SearchAttribution(source_urls=[])


def sourced(model, sourcing_kwargs=None):
    sourcing = SourcingService(
        NoDiscovery(), spec_writer=model.writer(MemoryCache()), **(sourcing_kwargs or {})
    )
    service = JobService(Extractor(), sourcing=sourcing)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    return service, job.job_id, token


def test_sourcing_saves_ai_specs_on_items_once_per_job():
    model = Model(reply(SPEC_REPLY))
    service, job_id, token = sourced(model)
    job = service.get(job_id, token)
    assert len(model.requests) == 1
    saved = {item.line_id: item.buyable_spec for item in job.items}
    assert saved["L01"].origin == "ai_inferred" and saved["L04"] is None
    lines = {line.item.line_id: line for line in job.report.lines}
    assert lines["L01"].buyable_spec.params[0].name == "wire_gauge"
    assert lines["L02"].buyable_spec.needs_value
    assert job.cost_estimate.calls_by_site.get("spec") == 1
    # A refresh reuses the saved specs: no second spec call.
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
    service.finish(job_id)
    assert len(model.requests) == 1


def test_sourcing_continues_with_seed_specs_when_the_writer_fails():
    model = Model(httpx.Response(400))
    service, job_id, token = sourced(model)
    job = service.get(job_id, token)
    assert job.status == "done" and all(item.buyable_spec is None for item in job.items)
    lines = {line.item.line_id: line for line in job.report.lines}
    assert lines["L02"].buyable_spec.origin == "seed" and lines["L02"].buyable_spec.needs_value


# Seed specs


@pytest.mark.parametrize(
    "name,category",
    [
        ("Through-hole resistor", "resistor"),
        ("10k resistor", "resistor"),
        ("22uF capacitor", "capacitor_electrolytic"),
        ("100nF capacitor", "capacitor_ceramic"),
        ("Ceramic capacitor", "capacitor_ceramic"),
        ("5mm white LED", "led"),
        ("LDR", "ldr"),
        ("Light dependent resistor", "ldr"),
        ("Bare copper wire", "wire"),
        ("1N4148 diode", "diode"),
        ("BC547 transistor", "transistor"),
        ("NE555 timer IC", "ic"),
        ("HC-05 Bluetooth module", "module"),
        ("DHT11 sensor", "sensor"),
        ("Tactile push button", "switch"),
        ("CR2032 coin cell battery", "battery"),
        ("Arduino Nano", "board"),
        ("2-pin JST connector", "connector"),
        ("Small bracket", "other"),
    ],
)
def test_seed_spec_classifies_the_category_from_the_name(name, category):
    assert seed_spec(BomItem(line_id="L01", raw_name=name)).category == category


@pytest.mark.parametrize(
    "name,needs",
    [
        ("Through-hole resistor", True),
        ("Resistor", True),
        ("220 ohm resistor", False),
        ("4k7 resistor", False),
        ("Electrolytic capacitor", True),
        ("Capacitor", True),
        ("22uF 16V capacitor", False),
        ("Inductor", True),
        ("10uH inductor", False),
        ("5mm LED", False),
        ("LDR", False),
        ("Bare copper wire", False),
    ],
)
def test_seed_spec_needs_a_value_for_value_bearing_parts_without_one(name, needs):
    spec = seed_spec(BomItem(line_id="L01", raw_name=name))
    assert spec.needs_value is needs
    assert (spec.needs_value_reason is not None) is needs


def test_seed_spec_reads_the_mount_and_user_requirement_values():
    spec = seed_spec(BomItem(line_id="L01", raw_name="Through-hole resistor"))
    assert spec.mount == "tht" and spec.mount_origin == "stated" and "SMD" in spec.exclude
    from bharat_sourcer.schemas import PartRequirement

    item = BomItem(
        line_id="L01",
        raw_name="Through-hole resistor",
        requirements=[PartRequirement(name="resistance", value="4.7k", unit="ohm")],
    )
    spec = seed_spec(item)
    assert not spec.needs_value and spec.params[0].si_value == 4700
    assert spec.params[0].origin == "user"


# Never auto-select a guessed value


NEEDS_VALUE = buyable_spec(BomItem(line_id="L02", raw_name=RESISTOR))
SINGLE = "220 Ohm Resistor (Pack of 10)"
KIT = "600 Pcs 30 Values Resistor Kit 10 Ohm - 1M Ohm 1/4W"


def candidate(title, rows=()):
    offer = VerifiedOffer(
        url="https://seller.example/p/" + str(abs(hash(title))),
        seller="seller.example",
        title=title,
        price_inr="20.00",
        stock="in_stock",
    )
    return Candidate(url=str(offer.url), title=title, offer=offer, rows=list(rows))


def draft(status, quote, score=0.9):
    return VerdictDraft(
        candidate_id=0,
        status=status,
        score=score,
        claims=[{"claim": "value", "quote": quote}],
        reasons=["Looks right"],
    )


def test_assortments_are_told_apart_from_packs_of_one_value():
    assert is_assortment(KIT) and is_assortment("Resistor assortment box")
    assert not is_assortment(SINGLE) and not is_assortment("10K resistor 100 pcs")


def test_judge_caps_a_single_value_listing_at_partial_when_the_value_is_unknown():
    assert NEEDS_VALUE.needs_value
    match = checked_verdict(draft("compatible", "220 Ohm"), candidate(SINGLE), NEEDS_VALUE, "m")
    assert match.status == "partial" and match.score <= 0.6
    assert "not known" in match.reasons[0]


def test_judge_keeps_a_kit_compatible_but_never_exact():
    match = checked_verdict(draft("exact", "Resistor Kit"), candidate(KIT), NEEDS_VALUE, "m")
    assert match.status == "compatible" and "kit" in match.reasons[0]


def test_judge_never_upgrades():
    match = checked_verdict(draft("partial", "220 Ohm", 0.4), candidate(SINGLE), NEEDS_VALUE, "m")
    assert match.status == "partial" and match.score == 0.4


def offer_for(title, status):
    return VerifiedOffer(
        url="https://seller.example/p/" + ("kit" if "Kit" in title else "single"),
        seller="seller.example",
        title=title,
        price_inr="20.00" if "Kit" not in title else "120.00",
        stock="in_stock",
        checked_at=now(),
        compatibility=Compatibility(status="compatible", grade="A"),
        match=OfferMatch(
            status=status, score=0.9, claims=[MatchClaim(claim="value", quote=title[:20])]
        ),
    )


def needs_value_line(*offers):
    item = BomItem(line_id="L02", raw_name=RESISTOR, qty=1)
    return ReportLine(
        item=item,
        sourcing_status="offers_found",
        offers=list(offers),
        buyable_spec=NEEDS_VALUE,
    )


def test_a_guessed_value_is_never_selected_and_a_kit_is_only_recommended():
    # Even a (wrong) compatible verdict on the 220 Ω listing must not be applied.
    line = needs_value_line(offer_for(SINGLE, "compatible"), offer_for(KIT, "compatible"))
    report = Report(demo=False, summary="Synthetic test report", lines=[line])
    apply_recommendations(report)
    assert line.selected_offer_url is None and line.selection_source is None
    rec = line.recommendation
    assert rec.status == "recommended" and str(rec.offer_url).endswith("/kit")
    assert rec.blocked_reason and "value" in rec.blocked_reason
    assert rec.next_steps and rec.next_steps[0].startswith("Choose the value")


def test_only_single_value_listings_leave_the_line_needing_a_value():
    line = needs_value_line(offer_for(SINGLE, "compatible"))
    report = Report(demo=False, summary="Synthetic test report", lines=[line])
    apply_recommendations(report)
    assert line.selected_offer_url is None and line.recommended_offer_url is None
    assert line.recommendation.unsourced_reason == "needs_value"
    assert line.recommendation.next_steps[0].startswith("Choose the value")


def test_a_known_value_is_still_selected():
    spec = buyable_spec(BomItem(line_id="L02", raw_name="220 ohm resistor"))
    item = BomItem(line_id="L02", raw_name="220 ohm resistor", qty=1)
    line = ReportLine(
        item=item,
        sourcing_status="offers_found",
        offers=[offer_for(SINGLE, "exact")],
        buyable_spec=spec,
    )
    apply_recommendations(Report(demo=False, summary="Synthetic test report", lines=[line]))
    assert line.selection_source == "recommended"


# Physical suitability: numbers in the listing vs spec params


THIN_WIRE = guard_spec(
    BuyableSpec(
        origin="ai_inferred",
        category="wire",
        params=[
            SpecParam(
                name="diameter",
                value="0.5 mm",
                operator="between",
                value_max="1 mm",
                reason="Thin bus wire for a small freeform circuit.",
            )
        ],
    ),
    "",
    "",
)
GAUGE_WIRE = guard_spec(
    BuyableSpec(
        origin="ai_inferred",
        category="wire",
        params=[
            SpecParam(
                name="wire_gauge",
                value="18 AWG",
                operator="between",
                value_max="24 AWG",
                reason="Thin bus wire for a small freeform circuit.",
            )
        ],
    ),
    "",
    "",
)
ROD = "4mm Dia Pure Copper Wire Without Insulation -1 Meter"


def test_a_4mm_rod_is_downgraded_against_a_thin_wire_spec():
    assert THIN_WIRE.params[0].si_value == pytest.approx(0.0005)
    match = checked_verdict(draft("exact", "Pure Copper Wire"), candidate(ROD), THIN_WIRE, "m")
    assert match.status == "partial" and "diameter" in match.conflicts
    assert "different value" in match.reasons[0]


def test_a_4mm_rod_conflicts_with_an_awg_range_and_spec_rows_count():
    assert awg_m(24) == pytest.approx(0.000511, rel=0.01)
    assert measure_conflicts(GAUGE_WIRE, [ROD]) == ["wire_gauge"]
    assert measure_conflicts(GAUGE_WIRE, ["Tinned copper wire", "Diameter: 0.8 mm"]) == []
    assert measure_conflicts(GAUGE_WIRE, ["Copper wire", "Diameter: 4 mm"]) == ["wire_gauge"]
    match = checked_verdict(
        draft("compatible", "Copper Wire"),
        candidate("Pure Copper Wire", rows=["Diameter: 4 mm"]),
        GAUGE_WIRE,
        "m",
    )
    assert match.status == "partial"


def test_thin_wire_with_a_spool_length_is_not_a_conflict():
    assert measure_conflicts(THIN_WIRE, ["0.8mm Tinned Copper Wire 10m"]) == []
    assert measure_conflicts(GAUGE_WIRE, ["22 AWG Tinned Copper Bus Wire 10m"]) == []
    match = checked_verdict(
        draft("exact", "Tinned Copper Wire"),
        candidate("0.8mm Tinned Copper Wire 10m"),
        THIN_WIRE,
        "m",
    )
    assert match.status == "exact"


# Stage labels


class OneOffer:
    def discover(self, query):
        return SearchAttribution(source_urls=[])


class Research:
    def __init__(self, status):
        self.status, self.calls = status, 0

    def research(self, item, pages, sources, project):
        self.calls += 1
        return PartResearch(status=self.status, summary="Fixture")


@pytest.mark.parametrize(
    "status,stage,calls", [("skipped", "research_skipped", 1), ("no_evidence", "research", 2)]
)
def test_research_stage_is_labelled_by_whether_the_call_ran(status, stage, calls):
    line = SourcingService(OneOffer(), researcher=Research(status)).source(
        BomItem(line_id="L01", raw_name="TTP223")
    )
    assert line.stages == ["grounded", stage]
    assert line.gemini_calls == calls  # grounded discovery + research only when it ran


def test_a_line_sourced_with_an_older_seed_spec_follows_the_current_rule():
    line = needs_value_line(offer_for(SINGLE, "compatible"))
    line.buyable_spec = BuyableSpec(origin="seed", queries=[RESISTOR])  # v0.21 seed
    apply_recommendations(Report(demo=False, summary="Synthetic test report", lines=[line]))
    assert line.selected_offer_url is None
    assert line.recommendation.unsourced_reason == "needs_value"
