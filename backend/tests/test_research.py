"""Labelled synthetic documents; no live web search, seller facts or prices."""

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import generation_schema
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    Compatibility,
    ConfirmJob,
    CreateJob,
    PartRequirement,
    PartResearch,
    PartSpecs,
    Report,
    ReportLine,
    ResearchFact,
    ResearchSource,
    SearchAttribution,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.research import (
    GeminiResearch,
    ResearchDraft,
    check_requirements,
    page_text,
    supported_fact,
)
from bharat_sourcer.sourcing.service import SourcingService

URL = "https://manufacturer.example/test-bearing"
SETTINGS = Settings(_env_file=None, gemini_api_key="test")
TEXT = "Synthetic Model B bearing. Bore diameter 8 mm. Color red. Test fixture only."
FACT = {"name": "bore diameter", "value": "8", "unit": "mm", "quote": "Bore diameter 8 mm."}


def page(text=TEXT, url=URL):
    return Page(url, 200, {"content-type": "text/html"}, f"<main>{text}</main>".encode())


def draft():
    return {
        "candidates": [
            {
                "source_id": 0,
                "title": "Synthetic Model B bearing",
                "category": "ball bearing",
                "kind": "manufacturer",
                "identity_quote": "Synthetic Model B bearing.",
                "match": "exact",
                "facts": [FACT],
                "assessment": {
                    "status": "potential_match",
                    "explanation": "The quoted bore matches the requirement.",
                    "conditions": ["Confirm the other dimensions and load rating."],
                    "questions": [],
                },
            }
        ],
        "questions": [],
    }


def response(data):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(data)}]},
                }
            ]
        },
    )


def research(data=None, item=None, text=TEXT):
    reader = GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: response(data or draft())))
    item = item or BomItem(
        line_id="L01",
        raw_name="bearing",
        requirements=[PartRequirement(name="bore diameter", value="0.8", unit="cm")],
    )
    return reader.research(item, [page(text)], [ResearchSource(url=URL, status="read")], [item])


@pytest.mark.parametrize(
    "name,category",
    [
        ("LED", "indicator LED"),
        ("Push button switch", "momentary switch"),
        ("Bearing", "ball bearing"),
        ("Motor", "DC motor"),
        ("PLA", "filament"),
        ("New unfamiliar part", "novel component category"),
    ],
)
def test_any_category_has_cited_research_without_product_schema(name, category):
    data = draft()
    data["candidates"][0].update(title=name, category=category, identity_quote=name + " fixture.")
    result = research(
        data,
        item=BomItem(line_id="L01", raw_name=name),
        text=name + " fixture. Bore diameter 8 mm.",
    )
    assert result.status == "ready"
    assert result.candidates[0].category == category
    assert str(result.candidates[0].url) == URL
    assert result.candidates[0].facts[0].quote == FACT["quote"]
    assert result.candidates[0].assessment.questions
    assert result.sources[0].reviewed


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": 9},
        {"identity_quote": "Invented model claim"},
        {"facts": [{**FACT, "quote": "Unseen evidence"}]},
        {"facts": [{**FACT, "value": "80"}]},
        {"facts": [{**FACT, "unit": "V"}]},
    ],
)
def test_hallucinated_source_quotes_values_and_units_are_not_retained(change):
    data = draft()
    data["candidates"][0].update(change)
    result = research(data)
    if "facts" in change:
        assert result.candidates[0].facts == []
        assert result.candidates[0].assessment.status == "needs_information"
    else:
        assert result.status == "no_evidence"
        assert result.candidates == []
    assert result.sources


def test_quote_from_other_source_cannot_be_used_as_this_candidate_evidence():
    reader = GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: response(draft())))
    result = reader.research(
        BomItem(line_id="L01", raw_name="bearing"),
        [
            page("Synthetic Model B bearing."),
            page(TEXT, URL + "-other"),
        ],
        [],
        [],
    )
    assert result.candidates[0].facts == []
    assert result.candidates[0].assessment.status == "needs_information"


@pytest.mark.parametrize(
    "requested,value,unit,operator,status",
    [
        ("0.8", "8", "mm", "equals", "meets"),
        ("1", "8", "mm", "at_least", "does_not_meet"),
        ("1", "8", "mm", "at_most", "meets"),
        ("1", "8", "V", "equals", "unknown"),
        ("1", "8-10", "mm", "equals", "unknown"),
    ],
)
def test_unit_checks_compute_real_comparisons(requested, value, unit, operator, status):
    required = PartRequirement(name="bore diameter", value=requested, unit="cm", operator=operator)
    fact = ResearchFact(**(FACT | {"value": value, "unit": unit}))
    assert check_requirements([required], [fact])[0].status == status


def test_conflicting_values_and_si_prefix_case_do_not_get_a_positive_check():
    required = PartRequirement(name="bore diameter", value="8", unit="mm")
    facts = [ResearchFact(**FACT), ResearchFact(**(FACT | {"value": "9"}))]
    assert check_requirements([required], facts)[0].status == "unknown"
    required = PartRequirement(name="voltage", value="1", unit="mV")
    fact = ResearchFact(name="voltage", value="1", unit="MV", quote="Voltage 1 MV")
    assert check_requirements([required], [fact])[0].status == "unknown"
    assert not supported_fact(ResearchFact(**(FACT | {"value": "8"})), "Bore diameter 18 mm.")


def test_numeric_failure_overrides_model_positive_assessment():
    item = BomItem(
        line_id="L01",
        raw_name="bearing",
        requirements=[
            PartRequirement(name="bore diameter", value="10", unit="mm", operator="at_least")
        ],
    )
    assessment = research(item=item).candidates[0].assessment
    assert assessment.status == "not_suitable"
    assert assessment.checks[0].status == "does_not_meet"


def test_possible_identity_never_becomes_potential_match_on_numeric_checks_alone():
    data = draft()
    data["candidates"][0]["match"] = "possible"
    assert research(data).candidates[0].assessment.status == "needs_information"


def test_research_has_bounded_project_context_and_ignores_provider_check_claims():
    def handle(request):
        body = json.loads(request.content)
        context = json.loads(body["contents"][0]["parts"][0]["text"])
        assert context["project_parts"][1]["name"] == "motor"
        assert "untrusted" in body["systemInstruction"]["parts"][0]["text"]
        assert "tools" not in body  # reuse sources, no hidden extra paid web search
        return response(draft())

    reader = GeminiResearch(SETTINGS, httpx.MockTransport(handle))
    item = BomItem(line_id="L01", raw_name="bearing")
    result = reader.research(item, [page()], [], [item, BomItem(line_id="L02", raw_name="motor")])
    assert result.status == "ready"


def test_unreadable_sources_do_not_call_model_and_are_preserved():
    def handle(request):
        raise AssertionError("Should not call Gemini")

    reader = GeminiResearch(SETTINGS, httpx.MockTransport(handle))
    result = reader.research(
        BomItem(line_id="L01", raw_name="bearing"),
        [],
        [ResearchSource(url=URL, status="unavailable", reason="Blocked")],
        [],
    )
    assert result.status == "no_evidence"
    assert result.sources[0].reason == "Blocked"


class Discovery:
    def discover(self, query):
        return SearchAttribution(source_urls=[URL])


class Fetcher:
    def get(self, url):
        return page()


def test_unstructured_source_survives_no_verified_offers_and_model_outages():
    reader = GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: response(draft())))
    service = SourcingService(Discovery(), Fetcher(), reader)
    item = BomItem(line_id="L01", raw_name="bearing")
    result = service.source(item)
    assert result.sourcing_status == "no_verified_offers"
    assert result.offers == []
    assert result.research.status == "ready"
    assert result.research.candidates[0].title == "Synthetic Model B bearing"
    assert "1 cited candidates" in result.sourcing_error.message
    service.researcher = GeminiResearch(
        SETTINGS, httpx.MockTransport(lambda _: httpx.Response(400))
    )
    assert service.source(item).research.status == "failed"


def test_guarded_fetch_failure_is_a_link_with_no_invented_evidence():
    class Blocked:
        def get(self, url):
            raise FetchError("Test private/internal raw error must not reach public data")

    reader = GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: pytest.fail("No model call")))
    line = SourcingService(Discovery(), Blocked(), reader).source(
        BomItem(line_id="L01", raw_name="x")
    )
    assert line.research.status == "no_evidence"
    assert "raw error" not in line.model_dump_json()
    assert str(line.research.sources[0].url) == URL


def test_html_input_bounds_and_script_stripping():
    source = page(
        "<style>hidden css</style><script>hidden js</script>"
        '<h1>Visible part</h1><script type="application/ld+json">'
        '{"name":"Structured spec"}</script>'
    )
    text = page_text(source, 2000)
    assert "hidden" not in text
    assert "Visible part" in text and "Structured spec" in text
    assert len(page_text(page("x" * 10000), 2000)) <= 2000


def test_pdf_datasheet_text_and_malformed_pdf():
    writer = PdfWriter()
    sheet = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    sheet[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Synthetic bearing bore 8 mm) Tj ET")
    sheet[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    pdf = Page(URL + ".pdf", 200, {"content-type": "application/pdf"}, output.getvalue())
    assert "Synthetic bearing bore 8 mm" in page_text(pdf, 2000)
    pdf.body = b"%PDF-invalid"
    assert page_text(pdf, 2000) == ""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("test", 12)):
        assert page_text(pdf, 2000) == ""


def test_api_generic_requirements_persist_and_invalidate_all_project_assessments():
    app = create_app(Settings(_env_file=None))
    service = app.state.job_service

    class Extractor:
        def extract(self, url):
            return [
                BomItem(line_id="L01", raw_name="bearing"),
                BomItem(line_id="L02", raw_name="motor"),
            ]

    service.extractor = Extractor()
    reader = GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: response(draft())))
    service.sourcing = SourcingService(Discovery(), Fetcher(), reader)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    req = {"name": "bore diameter", "value": "8", "unit": "mm"}
    service.confirm(
        job.job_id,
        token,
        ConfirmJob.model_validate(
            {"edits": [{"op": "update", "line_id": "L01", "requirements": [req]}]}
        ),
    )
    service.finish(job.job_id)
    before = service.get(job.job_id, token)
    assert before.report.lines[0].research.candidates
    client = TestClient(app)
    path = f"/v1/jobs/{job.job_id}/specs"
    headers = {"X-Job-Token": token}
    updated = client.post(
        path,
        headers=headers,
        json={"updates": [{"line_id": "L01", "requirements": [req | {"value": "10"}]}]},
    )
    assert updated.status_code == 200
    result = updated.json()
    assert result["items"][0]["requirements"][0]["value"] == "10"
    assert all(line["research"]["status"] == "stale" for line in result["report"]["lines"])
    checks = result["report"]["lines"][0]["research"]["candidates"][0]["assessment"]["checks"]
    assert checks[0]["status"] == "does_not_meet"
    rollback = client.post(
        path,
        headers=headers,
        json={
            "updates": [
                {"line_id": "L01", "requirements": []},
                {"line_id": "bad", "requirements": []},
            ]
        },
    )
    assert rollback.status_code == 422
    assert service.get(job.job_id, token).items[0].requirements[0].value == "10"
    assert (
        client.post(
            path, headers=headers, json={"updates": [{"line_id": "L01", "requirements": []}]}
        ).json()["items"][0]["requirements"]
        == []
    )


def test_old_snapshots_and_arbitrary_family_names_remain_valid():
    item = BomItem.model_validate({"line_id": "L01", "raw_name": "unknown widget"})
    assert item.requirements == []
    assert PartSpecs(family="arbitrary new category").family == "arbitrary new category"
    assert PartResearch.model_validate(research().model_dump(mode="json")).status == "ready"


def test_frontend_fixture_matches_current_contract_and_is_labelled():
    path = Path(__file__).resolve().parents[2] / "docs/contracts/fixtures/part-research.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert fixture["fixture"] is True
    line = ReportLine.model_validate(fixture["line"])
    assert line.research.candidates and not line.offers


def test_provider_schema_preserves_property_names_matching_schema_keywords():
    candidate = generation_schema(ResearchDraft)["properties"]["candidates"]["items"]
    assert "title" in candidate["properties"]
    assert "title" not in candidate
    assert set(candidate["required"]).issubset(candidate["properties"])


def selection_setup(grade=None):
    app = create_app(Settings(_env_file=None))
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://example.com"))
    item = BomItem(
        line_id="L01",
        raw_name="Synthetic bearing",
        requirements=[PartRequirement(name="bore diameter", value="8", unit="mm")],
    )
    result = research(item=item)
    candidate = result.candidates[0]
    offer = VerifiedOffer(
        url=URL,
        title=candidate.title,
        seller="manufacturer.example",
        price_inr="10.00",
        stock="in_stock",
        compatibility=Compatibility(
            status="compatible" if grade == "A" else "unknown", grade=grade
        ),
        research_assessment=candidate.assessment.model_copy(deep=True),
    )

    def seed(record):
        record.job.demo = False
        record.job.status = "done"
        record.job.items = [item, BomItem(line_id="L02", raw_name="shaft")]
        record.job.report = Report(
            demo=False,
            summary="Synthetic fixture",
            lines=[
                ReportLine(
                    item=item, sourcing_status="offers_found", offers=[offer], research=result
                ),
                ReportLine(item=record.job.items[1], sourcing_status="no_verified_offers"),
            ],
        )

    service.store.mutate(job.job_id, seed)
    return TestClient(app), service, job.job_id, {"X-Job-Token": token}


def test_research_selection_requires_explicit_review_and_is_invalidated_by_sibling_edit():
    client, service, job_id, headers = selection_setup()
    path = f"/v1/jobs/{job_id}/selections"
    body = {"selections": [{"line_id": "L01", "offer_url": URL}]}
    assert client.post(path, headers=headers, json=body).status_code == 422
    body["selections"][0]["accept_research_assessment"] = True
    selected = client.post(path, headers=headers, json=body)
    assert selected.status_code == 200
    line = selected.json()["report"]["lines"][0]
    assert line["research_accepted"] and line["grade"] is None
    assert selected.json()["report"]["selected_parts_subtotal_inr"] == "10.00"
    updated = client.post(
        f"/v1/jobs/{job_id}/specs",
        headers=headers,
        json={
            "updates": [
                {
                    "line_id": "L02",
                    "requirements": [{"name": "diameter", "value": "10", "unit": "mm"}],
                }
            ]
        },
    )
    assert updated.status_code == 200
    line = updated.json()["report"]["lines"][0]
    assert not line["research_accepted"] and line["selected_offer_url"] is None
    assert line["research"]["status"] == "stale"
    assert client.post(path, headers=headers, json=body).status_code == 422


@pytest.mark.parametrize("state", ["incompatible", "needs_information", "stale", "unverified"])
def test_research_selection_cannot_override_mismatches_or_select_unverified_candidate(state):
    client, service, job_id, headers = selection_setup()

    def change(record):
        line = record.job.report.lines[0]
        if state == "incompatible":
            line.offers[0].compatibility = Compatibility(status="incompatible", grade="X")
        elif state == "unverified":
            line.offers = []
        else:
            line.offers[0].research_assessment.status = state

    service.store.mutate(job_id, change)
    assert (
        client.post(
            f"/v1/jobs/{job_id}/selections",
            headers=headers,
            json={
                "selections": [
                    {"line_id": "L01", "offer_url": URL, "accept_research_assessment": True}
                ]
            },
        ).status_code
        == 422
    )


def test_legacy_grade_a_cannot_bypass_new_generic_requirements():
    client, service, job_id, headers = selection_setup(grade="A")

    def change(record):
        record.job.report.lines[0].item.requirements[0].value = "10"

    service.store.mutate(job_id, change)
    reply = client.post(
        f"/v1/jobs/{job_id}/selections",
        headers=headers,
        json={
            "selections": [{"line_id": "L01", "offer_url": URL, "accept_research_assessment": True}]
        },
    )
    assert reply.json()["error"]["code"] == "REQUIREMENTS_UNRESOLVED"
