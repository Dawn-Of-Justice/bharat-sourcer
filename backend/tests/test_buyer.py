"""The AI buyer (sourcing/buyer.py) with fake model replies and synthetic seller pages.

Pages, prices and model decisions below are invented test data, not real listings.
"""

import json

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem, BuyableSpec, OfferMatch, ProjectContext, SpecParam
from bharat_sourcer.sourcing.buyer import (
    ChoiceDraft,
    GeminiBuyer,
    PickDraft,
    ValueDraft,
    apply_value,
    project_brief,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import BlockedError, Politeness
from bharat_sourcer.sourcing.seller_search import Candidate as SearchCandidate
from bharat_sourcer.sourcing.seller_search import SearchResult
from bharat_sourcer.sourcing.service import SourcingService

PROJECT = ProjectContext(
    title="Freeform light-activated LED (synthetic)",
    summary="Dead-bug LED circuit on a bare copper rail, 3.6 V supply; the LED lights in the dark.",
    power="3.6 V DC",
    assumptions=["The second resistor's colour bands are not readable."],
)


def page(url: str, title: str, price: str, extra: str = "") -> Page:
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "INR",
            "availability": "https://schema.org/InStock",
        },
    }
    html = (
        f"<html><head><title>{title}</title><script type='application/ld+json'>"
        f"{json.dumps(data)}</script></head><body><h1>{title}</h1><p>{extra}</p></body></html>"
    )
    return Page(url, 200, {"content-type": "text/html"}, html.encode())


ENAMELLED = page(
    "https://seller-a.example/products/22-swg-enamelled-copper-wire",
    "22 SWG Enamelled Copper Wire (10 Meter)",
    "160.00",
    "Solid copper conductor with enamel insulation, 22 SWG.",
)
JUMPERS = page("https://seller-b.example/products/jumper-kit", "Jumper Wire Kit 120 pcs", "99.00")
TINNED = page(
    "https://seller-c.example/products/22-swg-tinned-copper-wire",
    "22 SWG Tinned Copper Wire 10m",
    "120.00",
    "Bare tinned copper wire, solid, 22 SWG.",
)
R220 = page(
    "https://seller-a.example/products/220-ohm-resistor",
    "220 Ohm Resistor 1/4 Watt (Pack of 10)",
    "8.00",
    "Carbon film, through hole, 220 ohm, 1/4 W.",
)
PAGES = {p.url: p for p in [ENAMELLED, JUMPERS, TINNED, R220]}


class Fetcher:
    def get(self, url, **_):
        if url not in PAGES:
            raise AssertionError(url)
        return PAGES[url]


class Discovery:
    def __init__(self, urls=()):
        self.urls = list(urls)

    def discover(self, query):
        from bharat_sourcer.schemas import SearchAttribution

        return SearchAttribution(source_urls=self.urls)


class Sellers:
    """Fake seller search: each call returns the next URL batch and records the queries."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.queries = []
        self.politeness = Politeness()

    def search(self, queries, limit, budget):
        self.queries.append([str(q) for q in queries])
        urls = self.batches.pop(0) if self.batches else []
        candidates = [
            SearchCandidate(url=u, seller="seller.example", title="", query="q") for u in urls
        ]
        return SearchResult(
            queries=[str(q) for q in queries], candidates=candidates, diagnostics=[]
        )


class RejectAll:
    """A spec judge that accepts nothing, so the buyer has to decide."""

    def judge_candidates(self, spec, project, candidates):
        return [
            OfferMatch(status="mismatch", score=0.1, reasons=["strict check"]) for _ in candidates
        ]


class AcceptExact:
    def judge_candidates(self, spec, project, candidates):
        return [
            OfferMatch(status="exact", score=0.95, method="deterministic_shortcut")
            for _ in candidates
        ]


class Buyer:
    """Scripted buyer decisions; records what it was shown."""

    model = "test-buyer"

    def __init__(self, value=None, choices=()):
        self.value, self.choices = value, list(choices)
        self.shown = []

    def decide_value(self, line, spec, project, items):
        return self.value

    def choose(self, line, spec, project, items, candidates, tried):
        self.shown.append(([c.title for c in candidates], list(tried)))
        return self.choices.pop(0) if self.choices else None


WIRE = BuyableSpec(
    origin="ai_inferred",
    part_name="Bare copper wire",
    category="wire",
    params=[SpecParam(name="wire_type", value="bare copper", origin="stated", reason="named")],
    exclude=["enameled", "insulated"],
    queries=["bare copper wire 20 awg"],
)


def wire_line():
    return BomItem(line_id="L01", raw_name="Bare copper wire", buyable_spec=WIRE)


def test_substitute_pick_is_grade_b_with_changes_and_quotes():
    buyer = Buyer(
        choices=[
            ChoiceDraft(
                pick=PickDraft(
                    candidate_id=0,
                    fit="substitute",
                    reason="Solid 22 SWG copper works as the rail once the enamel is scraped.",
                    changes=["Scrape the enamel off where you solder."],
                    claims=[{"claim": "22 SWG copper", "quote": "22 SWG Enamelled Copper Wire"}],
                )
            )
        ]
    )
    service = SourcingService(
        Discovery(),
        Fetcher(),
        judge=RejectAll(),
        seller_search=Sellers([ENAMELLED.url, JUMPERS.url]),
        buyer=buyer,
    )
    line = service.source_for_project(wire_line(), [wire_line()], project=PROJECT)
    assert line.sourcing_status == "offers_found"
    offer = line.offers[0]
    assert offer.title.startswith("22 SWG Enamelled")
    assert offer.match.method == "llm_buyer" and offer.match.status == "compatible"
    assert offer.match.claims and offer.price_inr == "160.00"
    assert offer.compatibility.grade == "B" and offer.compatibility.status == "changes_required"
    assert offer.compatibility.changes == ["Scrape the enamel off where you solder."]
    assert line.buyer.fit == "substitute" and str(line.buyer.offer_url) == ENAMELLED.url
    assert "buyer" in line.stages
    # The buyer saw every fetched listing, including the ones the judge rejected.
    assert buyer.shown[0][0] == [
        "22 SWG Enamelled Copper Wire (10 Meter)",
        "Jumper Wire Kit 120 pcs",
    ]


def test_buyer_searches_again_in_its_own_words_then_picks():
    sellers = Sellers([JUMPERS.url], [TINNED.url])
    buyer = Buyer(
        choices=[
            ChoiceDraft(search=["22 swg tinned copper wire"]),
            ChoiceDraft(
                pick=PickDraft(
                    candidate_id=1,
                    fit="exact",
                    reason="Bare tinned copper wire is what the rail needs.",
                    claims=[{"claim": "bare tinned copper", "quote": "Bare tinned copper wire"}],
                )
            ),
        ]
    )
    service = SourcingService(
        Discovery(), Fetcher(), judge=RejectAll(), seller_search=sellers, buyer=buyer
    )
    line = service.source_for_project(wire_line(), [wire_line()], project=PROJECT)
    assert sellers.queries[-1] == ["22 swg tinned copper wire"]
    assert line.offers[0].title == "22 SWG Tinned Copper Wire 10m"
    assert line.offers[0].match.status == "exact" and line.offers[0].compatibility.grade != "B"
    assert line.buyer.searched == ["22 swg tinned copper wire"]
    assert "22 swg tinned copper wire" not in [q.lower() for q in buyer.shown[0][1]]
    assert "22 swg tinned copper wire" in buyer.shown[1][1]
    assert line.stages.count("buyer") == 2 and "buyer_search" in line.stages


def test_unverified_quotes_leave_the_pick_partial_so_it_is_not_auto_selected():
    buyer = Buyer(
        choices=[
            ChoiceDraft(
                pick=PickDraft(
                    candidate_id=0,
                    fit="exact",
                    reason="Looks right.",
                    claims=[{"claim": "made up", "quote": "not on the page at all"}],
                )
            )
        ]
    )
    service = SourcingService(
        Discovery(), Fetcher(), judge=RejectAll(), seller_search=Sellers([TINNED.url]), buyer=buyer
    )
    line = service.source_for_project(wire_line(), [wire_line()], project=PROJECT)
    assert line.offers[0].match.status == "partial"
    assert line.offers[0].match.dropped_claims == 1


def test_an_invented_candidate_id_or_no_decision_changes_nothing():
    buyer = Buyer(choices=[ChoiceDraft(pick=PickDraft(candidate_id=9, fit="exact", reason="x"))])
    service = SourcingService(
        Discovery(), Fetcher(), judge=RejectAll(), seller_search=Sellers([TINNED.url]), buyer=buyer
    )
    line = service.source_for_project(wire_line(), [wire_line()], project=PROJECT)
    assert line.sourcing_status == "no_verified_offers" and line.buyer is None


def test_buyer_is_not_asked_when_the_judge_accepted_an_offer():
    buyer = Buyer(choices=[ChoiceDraft(search=["should not run"])])
    service = SourcingService(
        Discovery(),
        Fetcher(),
        judge=AcceptExact(),
        seller_search=Sellers([TINNED.url]),
        buyer=buyer,
    )
    line = service.source_for_project(wire_line(), [wire_line()], project=PROJECT)
    assert line.offers and buyer.shown == [] and "buyer" not in line.stages


RESISTOR = BuyableSpec(
    origin="ai_inferred",
    part_name="Through-hole resistor",
    category="resistor",
    mount="tht",
    mount_origin="inferred",
    mount_reason="Hand-soldered freeform build.",
    params=[
        SpecParam(
            name="resistance",
            value="1k ohm",
            operator="between",
            value_max="10k ohm",
            unit="ohm",
            reason="range",
        )
    ],
    queries=["resistor through hole"],
)


def test_unstated_value_is_decided_from_the_circuit_before_searching():
    value = ValueDraft(
        param="resistance",
        value="220 ohm",
        unit="ohm",
        reason="Limits the LED to about 7 mA from 3.6 V.",
        confidence="medium",
        queries=["220 ohm resistor 1/4 watt"],
    )
    sellers = Sellers([R220.url])
    item = BomItem(line_id="L05", raw_name="Through-hole resistor", buyable_spec=RESISTOR)
    service = SourcingService(
        Discovery(), Fetcher(), judge=AcceptExact(), seller_search=sellers, buyer=Buyer(value=value)
    )
    line = service.source_for_project(item, [item], project=PROJECT)
    assert line.buyable_spec.needs_value is False
    decided = line.buyable_spec.params[0]
    assert (decided.value, decided.operator, decided.si_value) == ("220 ohm", "equals", 220.0)
    assert "LED" in decided.reason
    assert any("220 ohm" in q for q in sellers.queries[0])
    assert line.buyer.value == "resistance: 220 ohm" and line.buyer.value_confidence == "medium"
    assert line.stages[0] == "buyer_value" and line.offers


def test_apply_value_keeps_other_params_and_records_the_reason():
    spec = RESISTOR.model_copy(
        update={
            "needs_value": True,
            "params": [
                *RESISTOR.params,
                SpecParam(
                    name="power_rating",
                    value="1/4W",
                    operator="at_least",
                    required=False,
                    reason="hobby",
                ),
            ],
        }
    )
    decided = apply_value(
        spec, ValueDraft(param="resistance", value="1k", unit="ohm", reason="divider with the LDR")
    )
    assert [p.name for p in decided.params] == ["resistance", "power_rating"]
    assert decided.needs_value is False and decided.reasons[0].startswith(
        "Value decided by the AI buyer"
    )


def test_project_brief_lists_every_part_and_marks_this_one():
    items = [
        BomItem(line_id="L01", raw_name="Bare copper wire"),
        BomItem(line_id="L02", raw_name="33kΩ resistor"),
        BomItem(line_id="L05", raw_name="Through-hole resistor"),
    ]
    brief = project_brief(PROJECT, items, items[2])
    assert [p["name"] for p in brief["parts"]] == [
        "Bare copper wire",
        "33kΩ resistor",
        "Through-hole resistor",
    ]
    assert [p["this_part"] for p in brief["parts"]] == [False, False, True]
    assert brief["power"] == "3.6 V DC"


def test_gemini_buyer_parses_a_reply_and_sends_the_whole_project():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        body = json.dumps(
            {"param": "resistance", "value": "220 ohm", "reason": "LED limit", "confidence": "high"}
        )
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": body}]}}],
                "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 80},
            },
        )

    buyer = GeminiBuyer(
        Settings(_env_file=None, gemini_api_key="test"), httpx.MockTransport(handler)
    )
    item = BomItem(line_id="L05", raw_name="Through-hole resistor")
    draft = buyer.decide_value(
        item, RESISTOR, PROJECT, [BomItem(line_id="L03", raw_name="5mm clear LED"), item]
    )
    assert draft.value == "220 ohm" and draft.confidence == "high"
    payload = json.loads(sent[0]["contents"][0]["parts"][0]["text"])
    assert [p["name"] for p in payload["project"]["parts"]] == [
        "5mm clear LED",
        "Through-hole resistor",
    ]


def test_gemini_buyer_failure_returns_no_decision():
    buyer = GeminiBuyer(
        Settings(_env_file=None, gemini_api_key="test"),
        httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    assert (
        buyer.decide_value(BomItem(line_id="L1", raw_name="resistor"), RESISTOR, PROJECT, [])
        is None
    )


def test_a_challenge_behind_googles_redirect_blocks_only_the_seller():
    politeness = Politeness()
    challenge = Page(
        "https://www.digikey.in/en/products/x", 403, {"cf-mitigated": "challenge"}, b"Just a moment"
    )

    class Redirecting:
        def get(self, url, **_):
            return challenge

    fetcher = politeness.wrap(Redirecting())
    try:
        fetcher.get("https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc")
    except BlockedError:
        pass
    assert politeness.blocked_reason("www.digikey.in")
    assert not politeness.blocked_reason("vertexaisearch.cloud.google.com")
