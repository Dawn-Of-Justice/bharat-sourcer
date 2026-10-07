"""Spec judge with mocked Gemini replies over real trimmed seller pages (fetched 2026-10-07).

Verdict JSON below is a mocked model response, not live model output. Fixture prices are
historical snapshots used to exercise parsing; they are never current or verified prices.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import (
    BomItem,
    BuyableSpec,
    ProjectContext,
    SearchAttribution,
    SpecParam,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.judge import GeminiJudge, MemoryCache, review_candidates
from bharat_sourcer.sourcing.listings import meta_offer, verify_page
from bharat_sourcer.sourcing.matching import build_candidate, shortcut_match
from bharat_sourcer.sourcing.part_spec import guard_spec
from bharat_sourcer.sourcing.service import SourcingService

FIXTURES = Path(__file__).parent / "fixtures" / "seller_pages"
HTML = {"content-type": "text/html; charset=utf-8"}
SETTINGS = Settings(_env_file=None, gemini_api_key="test")
PROJECT = ProjectContext(
    summary="A freeform, dead-bug soldered light-activated LED circuit on 3.6 V DC.",
    power="3.6 V DC",
    assumptions=["Colour bands on the unmarked resistor suggest 1k–10k."],
)


def fixture_page(name: str) -> Page:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    url = re.search(r"Source: (\S+)", text[:400]).group(1)
    return Page(url, 200, HTML, text.encode())


def candidate(name: str):
    page = fixture_page(name)
    return build_candidate(page, verify_page(page) or meta_offer(page))


def spec(**values) -> BuyableSpec:
    base = BuyableSpec(origin="ai_inferred", **values)
    return guard_spec(base, " ".join(p.value for p in base.params), "")


RESISTOR_33K = spec(
    category="resistor",
    mount="tht",
    mount_origin="inferred",
    mount_reason="Freeform dead-bug soldering needs through-hole parts.",
    params=[
        SpecParam(name="resistance", value="33kΩ", origin="stated"),
        SpecParam(
            name="power_rating",
            value="1/4W",
            operator="at_least",
            required=False,
            reason="Hobby size",
        ),
    ],
    exclude=["SMD", "0603", "chip resistor"],
)
CAP_22UF = spec(
    category="capacitor_electrolytic",
    mount="tht",
    mount_origin="inferred",
    mount_reason="Radial part for a hand-soldered build.",
    params=[
        SpecParam(name="capacitance", value="22µF", origin="stated"),
        SpecParam(name="voltage_rating", value="16V", operator="at_least", origin="stated"),
    ],
)
LDR = spec(
    category="ldr",
    mount="tht",
    mount_origin="inferred",
    mount_reason="Leaded LDR soldered freeform.",
    params=[SpecParam(name="size", value="5mm", origin="stated")],
    synonyms=["photoresistor", "light dependent resistor", "GL5528"],
)


def reply(verdicts, finish="STOP", text=None):
    body = text if text is not None else json.dumps({"verdicts": verdicts})
    return httpx.Response(
        200,
        json={
            "candidates": [{"finishReason": finish, "content": {"parts": [{"text": body}]}}],
            "usageMetadata": {"promptTokenCount": 1800, "candidatesTokenCount": 300},
        },
    )


class Model:
    """MockTransport for the judge; records each request payload."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.responses.pop(0)

    def judge(self, **settings):
        values = {"_env_file": None, "gemini_api_key": "test", **settings}
        return GeminiJudge(Settings(**values), httpx.MockTransport(self), MemoryCache())

    def payload(self, index=-1):
        return json.loads(self.requests[index].content)

    def listings(self, index=-1):
        return json.loads(self.payload(index)["contents"][0]["parts"][0]["text"])["candidates"]


def verdict(candidate_id, status, claims=(), score=0.9, **extra):
    return {
        "candidate_id": candidate_id,
        "status": status,
        "score": score,
        "reasons": [f"{status} for this build"],
        "claims": [{"claim": c, "quote": q} for c, q in claims],
        **extra,
    }


def test_sharvi_22uf_page_verifies_with_its_structured_price():
    model = Model(
        reply(
            [
                verdict(
                    0,
                    "exact",
                    [
                        ("value and rating", "22uF 16V Electrolytic Capacitor"),
                        ("rating", "Voltage Rating: 16V"),
                    ],
                )
            ]
        )
    )
    offers = review_candidates(
        CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], model.judge()
    )
    assert len(offers) == 1
    offer = offers[0]
    assert offer.price_inr == "7.65" and offer.stock == "in_stock"
    assert offer.match.status == "exact" and offer.match.dropped_claims == 0
    assert offer.match.method == "llm_judge" and offer.match.model == "gemini-3.1-flash-lite"
    # The model never sees a request to produce prices, and returns none.
    assert "price" not in json.dumps(model.payload()["generationConfig"]["responseJsonSchema"])


def test_smd_chip_resistor_is_a_mismatch_for_the_tht_33k_spec():
    model = Model(
        reply(
            [
                verdict(
                    0,
                    "exact",
                    [("33k, 1/4 W", "1/4 W 33kohm resistor")],
                    reasons=["Leaded 1/4 W resistors are through-hole"],
                ),
                verdict(1, "mismatch", [("SMD package", "SMD Chip Resistor, 33 kOhm")], 0.1),
                verdict(2, "mismatch", [("wrong value", "10K OHM SMD Resistor")], 0.0),
            ]
        )
    )
    names = [
        "probots_resistor_33k_quarter_w.html",
        "lioncircuits_smd_0603_33k.html",
        "probots_smd_0603_10k.html",
    ]
    offers = review_candidates(RESISTOR_33K, PROJECT, [candidate(n) for n in names], model.judge())
    assert [o.seller for o in offers] == ["probots.co.in"]
    assert offers[0].title.startswith("33kohm") and offers[0].match.status == "exact"
    request = model.payload()
    assert "gemini-3.1-flash-lite:generateContent" in str(model.requests[0].url)
    assert request["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert all(len(c["page_text"]) <= 800 for c in model.listings())


def test_server_downgrades_a_wrong_exact_verdict_on_an_smd_listing():
    model = Model(reply([verdict(0, "exact", [("value", "33 kOhm")])]))
    offers = review_candidates(
        RESISTOR_33K, PROJECT, [candidate("lioncircuits_smd_0603_33k.html")], model.judge()
    )
    # The model is wrong; the excluded terms in the title stop it being shown as exact.
    assert offers[0].match.status == "partial" and offers[0].match.score <= 0.6
    assert "excluded terms" in offers[0].match.reasons[0]


def test_unverified_quotes_are_dropped_and_the_verdict_downgraded():
    model = Model(
        reply([verdict(0, "exact", [("through hole", "Mounting: Axial through-hole, 33K")])])
    )
    offers = review_candidates(
        RESISTOR_33K,
        PROJECT,
        [candidate("probots_resistor_33k_quarter_w.html")],
        model.judge(),
    )
    match = offers[0].match
    assert match.claims == [] and match.dropped_claims == 1
    assert match.status == "partial"
    assert match.reasons[0] == "No supporting quote was found in the listing."


@pytest.mark.parametrize(
    "response",
    [
        reply([], text="{not json"),
        reply([], text=json.dumps({"verdicts": [{"candidate_id": 0, "status": "great"}]})),
        reply([verdict(0, "exact")], finish="MAX_TOKENS"),
        httpx.Response(400),
    ],
)
def test_malformed_or_incomplete_judge_output_means_no_verdict(response):
    model = Model(response)
    result = review_candidates(
        CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], model.judge()
    )
    assert result is None


def test_out_of_range_and_duplicate_verdicts_are_ignored():
    model = Model(reply([verdict(5, "exact"), verdict(0, "mismatch"), verdict(0, "exact")]))
    offers = review_candidates(
        CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], model.judge()
    )
    assert offers == []


def variant_page(variants, page_url="https://seller.example/products/ldr-5mm"):
    product = {
        "@type": "Product",
        "name": "LDR Photoresistor 5mm GL5528",
        "offers": [
            {
                "@type": "Offer",
                "name": name,
                "price": price,
                "priceCurrency": "INR",
                "availability": f"https://schema.org/{stock}",
                "url": f"{page_url}?variant={index}",
            }
            for index, (name, price, stock) in enumerate(variants)
        ],
    }
    html = (
        "<!-- Synthetic variant page for tests; not a real seller. -->"
        '<script type="application/ld+json">' + json.dumps(product) + "</script>"
        "<main>LDR Photoresistor 5mm GL5528. Through hole, 2 leads.</main>"
    )
    return Page(page_url, 200, HTML, html.encode())


VARIANTS = [("Pack of 10", "40.00", "InStock"), ("Pack of 50", "150.00", "InStock")]


def test_variant_group_needs_the_judge_and_uses_the_chosen_variant_price():
    page = variant_page(VARIANTS)
    assert verify_page(page) is None  # two prices, no variant in the URL
    group = build_candidate(page, None)
    assert group.offer is None and len(group.options) == 2
    model = Model(
        reply(
            [
                verdict(
                    0,
                    "compatible",
                    [("LDR", "LDR Photoresistor 5mm GL5528")],
                    variant_id=1,
                    pack_qty=50,
                    pack_quote="Pack of 50",
                )
            ]
        )
    )
    offers = review_candidates(LDR, PROJECT, [group], model.judge())
    assert offers[0].price_inr == "150.00"
    assert str(offers[0].url).endswith("?variant=1")
    assert offers[0].match.variant == "Pack of 50" and offers[0].pack_qty == 50
    assert model.listings()[0]["variants"][1] == {
        "variant_id": 1,
        "name": "Pack of 50",
        "price_inr": "150.00",
        "stock": "in_stock",
    }


def test_all_matching_variants_take_the_lowest_price_in_stock():
    variants = [
        ("Pack of 10", "40.00", "OutOfStock"),
        ("Pack of 20", "70.00", "InStock"),
        ("Pack of 50", "150.00", "InStock"),
    ]
    model = Model(reply([verdict(0, "compatible", [("LDR", "GL5528")], all_variants_match=True)]))
    offers = review_candidates(
        LDR, PROJECT, [build_candidate(variant_page(variants), None)], model.judge()
    )
    assert offers[0].price_inr == "70.00" and offers[0].match.variant == "Pack of 20"


def test_variant_group_without_a_choice_is_skipped():
    model = Model(reply([verdict(0, "partial", [("LDR", "GL5528")])]))
    offers = review_candidates(
        LDR, PROJECT, [build_candidate(variant_page(VARIANTS), None)], model.judge()
    )
    assert offers == []


def test_structured_exact_hit_skips_the_model_call():
    ldr = candidate("zbotic_ldr_5mm_pack10.html")
    shortcut = shortcut_match(LDR, ldr)
    assert shortcut is not None and shortcut.method == "deterministic_shortcut"
    model = Model()  # any request would fail: no responses queued
    offers = review_candidates(LDR, PROJECT, [ldr], model.judge())
    assert model.requests == []
    assert offers[0].match.status == "exact" and offers[0].pack_qty == 10
    assert offers[0].price_inr == "28.91"


def test_no_shortcut_when_mount_or_value_is_not_stated():
    # Probots says "1/4 W 33kohm resistor" but not "through hole": the judge decides.
    assert shortcut_match(RESISTOR_33K, candidate("probots_resistor_33k_quarter_w.html")) is None
    assert shortcut_match(RESISTOR_33K, candidate("lioncircuits_smd_0603_33k.html")) is None
    seed = BuyableSpec(params=LDR.params, category="ldr")
    assert shortcut_match(seed, candidate("zbotic_ldr_5mm_pack10.html")) is None


def test_verdicts_are_cached_per_spec_url_and_content(capsys):
    model = Model(reply([verdict(0, "exact", [("value", "22uF 16V Electrolytic Capacitor")])]))
    judge = model.judge()
    first = review_candidates(CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], judge)
    second = review_candidates(CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], judge)
    assert len(model.requests) == 1
    # The cache keeps listing evidence (status, quotes), never model prose about the build.
    assert first[0].match.model_dump(exclude={"reasons"}) == second[0].match.model_dump(
        exclude={"reasons"}
    )
    assert second[0].match.reasons == ["Earlier verdict for this listing and spec."]
    usage = [line for line in capsys.readouterr().out.splitlines() if "GEMINI_USAGE" in line]
    assert len(usage) == 1 and '"site": "judge"' in usage[0] and '"prompt": 1800' in usage[0]


def test_a_changed_page_is_judged_again():
    model = Model(
        reply([verdict(0, "exact", [("value", "22uF 16V Electrolytic Capacitor")])]),
        reply([verdict(0, "mismatch", [("value", "22uF 16V Electrolytic Capacitor")])]),
    )
    judge = model.judge()
    first = candidate("sharvi_cap_22uf_16v.html")
    changed = candidate("sharvi_cap_22uf_16v.html")
    changed.snippet += " Now sold as 25V."
    assert review_candidates(CAP_22UF, PROJECT, [first], judge)
    assert review_candidates(CAP_22UF, PROJECT, [changed], judge) == []
    assert len(model.requests) == 2


def test_budget_exhaustion_skips_the_paid_call(monkeypatch):
    import bharat_sourcer.sourcing.judge as judge_module

    monkeypatch.setattr(judge_module, "paid_allowed", lambda: False)
    model = Model()
    result = review_candidates(
        CAP_22UF, PROJECT, [candidate("sharvi_cap_22uf_16v.html")], model.judge()
    )
    assert result is None and model.requests == []


def test_zero_candidates_make_no_call():
    model = Model()
    assert review_candidates(CAP_22UF, PROJECT, [], model.judge()) == []
    assert model.requests == []


def test_candidate_listing_is_bounded_and_carries_no_model_price_field():
    listing = candidate("zbotic_wire_30awg_ok_line.html").listing(0)
    assert len(listing["page_text"]) <= 800 and len(listing["spec_rows"]) <= 12
    assert listing["price_inr"] == "395.30"  # from JSON-LD, shown for context only


# --- service integration ---------------------------------------------------------------

LINE_PAGES = [
    "probots_resistor_33k_quarter_w.html",
    "lioncircuits_smd_0603_33k.html",
    "probots_smd_0603_10k.html",
]


class Discovery:
    def discover(self, query):
        return SearchAttribution(source_urls=[fixture_page(n).url for n in LINE_PAGES])


class Fetcher:
    def get(self, url, **_):
        for name in LINE_PAGES:
            page = fixture_page(name)
            if page.url == url:
                return page
        raise AssertionError(url)


def line_item():
    return BomItem(line_id="L02", raw_name="33kΩ resistor", buyable_spec=RESISTOR_33K)


def test_service_uses_the_spec_judge_and_exposes_the_spec():
    model = Model(
        reply(
            [
                verdict(0, "exact", [("33k", "1/4 W 33kohm resistor")]),
                verdict(1, "mismatch", [("SMD", "SMD Chip Resistor")]),
                verdict(2, "mismatch", [("10k", "10K OHM SMD Resistor")]),
            ]
        )
    )
    service = SourcingService(Discovery(), Fetcher(), judge=model.judge())
    line = service.source_for_project(line_item(), [line_item()], project=PROJECT)
    assert line.sourcing_status == "offers_found"
    assert [o.seller for o in line.offers] == ["probots.co.in"]
    assert line.offers[0].match.status == "exact"
    assert line.offers[0].compatibility is not None
    assert line.buyable_spec.mount == "tht"
    sent = json.loads(model.payload()["contents"][0]["parts"][0]["text"])
    assert sent["project"]["power"] == "3.6 V DC"
    assert len(sent["candidates"]) == 3


def test_service_falls_back_to_the_title_gate_when_the_judge_fails():
    model = Model(httpx.Response(400))
    service = SourcingService(Discovery(), Fetcher(), judge=model.judge())
    item = BomItem(line_id="L02", raw_name="SMD resistor")
    line = service.source_for_project(item, [item])
    # Legacy behaviour: titles containing every query token, unjudged (match is None).
    assert {o.seller for o in line.offers} == {"probots.co.in", "www.lioncircuits.com"}
    assert all(o.match is None for o in line.offers)
    assert line.buyable_spec.origin == "seed"


def test_service_without_judge_keeps_the_legacy_gate():
    service = SourcingService(Discovery(), Fetcher())
    item = BomItem(line_id="L02", raw_name="33kohm resistor")
    line = service.source(item)
    assert [o.title for o in line.offers] == ["33kohm  - 1/4 W Resistor"]
    assert line.buyable_spec.queries == ["33kohm resistor"]
