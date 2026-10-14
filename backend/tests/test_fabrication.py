"""Made-to-order lines: the reconcile flag, fabrication service discovery and the plan.

Every BOM line, project, page and Gemini response here is SYNTHETIC test data, not a
verified service or part. No network call runs: Gemini answers come from
httpx.MockTransport and pages from a fake fetcher.
"""

import json

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobService, same_part
from bharat_sourcer.recommend import apply_recommendations
from bharat_sourcer.reconcile import PartRoleDraft, ReconcileDraft, reconcile_items
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Job,
    JobVideoMeta,
    Report,
    ReportLine,
    SearchAttribution,
    VideoLink,
    now,
)
from bharat_sourcer.sourcing.fabrication import (
    CURATED,
    FabricationFinder,
    design_links,
)
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.service import SourcingService

PRINT_A = "https://print-a.example/upload"
PRINT_B = "https://print-b.example/"
BLOG = "https://blog.example/best-3d-printing-services"
REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"


class DictCache(dict):
    def set(self, key, value, ttl_s):
        self[key] = (value, ttl_s)

    def get(self, key):
        found = super().get(key)
        return found[0] if found else None


def html(title, text):
    body = f"<html><head><title>{title}</title></head><body><p>{text}</p></body></html>"
    return body.encode()


class Pages:
    """Fake fetcher: the grounding redirect lands on PRINT_A; one page cannot be read."""

    def __init__(self):
        self.fetched = []

    def get(self, url, **kwargs):
        self.fetched.append(url)
        final = PRINT_A if url == REDIRECT else url
        if url == "https://down.example/":
            raise FetchError("Synthetic fetch failure")
        texts = {
            PRINT_A: ("Print A - upload STL", "Synthetic: upload your STL, we ship across India."),
            PRINT_B: ("Print B", "Synthetic online 3D printing, instant quote."),
            BLOG: ("Top 10 services", "Synthetic blog list of printing services."),
        }
        title, text = texts[final]
        return Page(final, 200, {"content-type": "text/html"}, html(title, text))


def gemini(answers, calls):
    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        answer = answers[len(calls) - 1]
        if isinstance(answer, int):
            return httpx.Response(answer, json={"error": {"status": "UNAVAILABLE"}})
        return httpx.Response(200, json=answer)

    return httpx.MockTransport(handle)


def grounded(urls, prose=""):
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": prose or "Synthetic answer."}]},
                "groundingMetadata": {"groundingChunks": [{"web": {"uri": u}} for u in urls]},
            }
        ]
    }


def verdicts(pages):
    text = json.dumps({"pages": pages})
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}


def finder(answers, cache=None):
    calls: list = []
    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    pages = Pages()
    found = FabricationFinder(settings, pages, cache=cache, transport=gemini(answers, calls))
    return found, calls, pages


SEARCH = grounded(
    [REDIRECT, PRINT_B, BLOG, "https://down.example/"],
    prose="See https://invented.example/ for prints.",
)
VERDICTS = verdicts(
    [
        {"id": 0, "is_service": True, "name": "Print A", "ships_to_india": "yes", "note": "STL"},
        {"id": 1, "is_service": True, "name": "Print B", "ships_to_india": "unknown"},
        {"id": 2, "is_service": False, "name": "Top 10", "ships_to_india": "unknown"},
    ]
)


def test_reconcile_flags_made_to_order_lines():
    class Reconciler:
        def review(self, items, project):
            return ReconcileDraft(
                parts=[
                    PartRoleDraft(id=0, function="controller"),
                    PartRoleDraft(id=1, function="enclosure", as_needed=True, made="3d_print"),
                    PartRoleDraft(id=2, function="controller", made="pcb"),
                ]
            )

    items = [
        BomItem(line_id="L01", raw_name="ESP32-C3 Super Mini"),
        BomItem(line_id="L02", raw_name="3D printed enclosure (PLA)"),
        BomItem(line_id="L03", raw_name="Custom carrier PCB"),
    ]
    kept, changes = reconcile_items(Reconciler(), items, None)
    assert [item.fabrication for item in kept] == ["none", "3d_print", "pcb"]
    assert kept[1].qty_as_needed and not changes
    assert items[1].fabrication == "none"  # the input list is never changed


def test_services_come_from_grounding_and_checked_pages_then_the_cache():
    cache = DictCache()
    fab, calls, pages = finder([SEARCH, VERDICTS], cache)
    services, live = fab.services("3d_print")
    assert live
    assert [(s.name, str(s.url), s.ships_to_india) for s in services] == [
        ("Print A", PRINT_A, "yes"),
        ("Print B", PRINT_B, "unknown"),
    ]
    assert all(s.checked_live and s.checked_at for s in services)
    # The grounded search uses Google Search; the verdicts call reads only fetched pages.
    assert calls[0]["tools"] == [{"google_search": {}}]
    judged = json.loads(calls[1]["contents"][0]["parts"][0]["text"])
    assert [p["url"] for p in judged["pages"]] == [PRINT_A, PRINT_B, BLOG]
    # A URL that appears only in generated prose is never fetched or linked.
    assert "https://invented.example/" not in pages.fetched
    (key,) = cache
    assert cache[key][1] == 30 * 24 * 3600
    # Later lines and later jobs reuse the result without another call.
    assert fab.services("3d_print")[0] == services and len(calls) == 2
    other, more_calls, _ = finder([], cache)
    assert [s.name for s in other.services("3d_print")[0]] == ["Print A", "Print B"]
    assert more_calls == []


def test_services_that_do_not_ship_to_india_or_repeat_a_domain_are_left_out():
    answer = verdicts(
        [
            {"id": 0, "is_service": True, "name": "Print A", "ships_to_india": "no"},
            {"id": 1, "is_service": True, "name": "Print B", "ships_to_india": "unknown"},
            {"id": 2, "is_service": True, "name": "", "ships_to_india": "yes"},
        ]
    )
    fab, _, _ = finder([SEARCH, answer])
    assert [s.name for s in fab.services("3d_print")[0]] == ["Print B"]


def test_failed_discovery_uses_the_labelled_curated_list_and_is_not_cached():
    cache = DictCache()
    fab, calls, _ = finder([503, 503, 503, 503], cache)
    services, live = fab.services("pcb")
    assert not live and not cache
    assert [str(s.url) for s in services] == [url for _, url, _ in CURATED["pcb"]]
    assert not any(s.checked_live for s in services)
    # Not retried for every line: the next line gets the fallback without a call.
    count = len(calls)
    assert fab.services("pcb")[1] is False and len(calls) == count


def test_no_key_means_no_call_and_the_fallback():
    settings = Settings(_env_file=None, demo_mode=False)
    fab = FabricationFinder(settings, Pages())
    services, live = fab.services("3d_print")
    assert not live and services


def test_line_is_a_fabrication_service_line_with_upload_and_design_links():
    fab, _, _ = finder([SEARCH, VERDICTS])
    item = BomItem(line_id="L07", raw_name="3D printed enclosure", fabrication="3d_print")
    line = fab.line(item, ["https://www.printables.com/model/1-synthetic"])
    assert line.sourcing_status == "fabrication_service" and line.stages == ["fabrication"]
    plan = line.fabrication
    assert plan.kind == "3d_print" and plan.method == "grounded_search_page_checked"
    assert "STL" in plan.upload
    assert [str(u) for u in plan.design_links] == ["https://www.printables.com/model/1-synthetic"]


def test_design_links_come_only_from_the_projects_own_sources():
    job = Job(
        job_id="synthetic",
        input=CreateJob(
            url="https://youtu.be/abcdefghijk", sources=["https://github.com/example/desk"]
        ),
        video_meta=JobVideoMeta(
            video_id="abcdefghijk",
            fetched_at=now(),
            links=[
                VideoLink(url="https://www.printables.com/model/1-desk", kind="other"),
                VideoLink(url="https://oshwlab.com/example/desk-board", kind="other"),
                VideoLink(url="https://shop.example/esp32", kind="store"),
            ],
        ),
    )
    assert design_links(job, "3d_print") == [
        "https://github.com/example/desk",
        "https://www.printables.com/model/1-desk",
    ]
    assert design_links(job, "pcb") == [
        "https://github.com/example/desk",
        "https://oshwlab.com/example/desk-board",
    ]


class Discovery:
    calls = 0

    def discover(self, query):
        self.calls += 1
        return SearchAttribution(source_urls=[])


def test_job_sourcing_links_services_and_keeps_the_line_out_of_carts_and_unsourced():
    class Extractor:
        def extract(self, url):
            return [
                BomItem(line_id="L01", raw_name="3D printed enclosure", fabrication="3d_print"),
            ]

    discovery = Discovery()
    fab, _, _ = finder([SEARCH, VERDICTS])
    sourcing = SourcingService(discovery, Pages(), fabrication=fab)
    service = JobService(Extractor(), sourcing=sourcing)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    report = service.get(job.job_id, token).report
    (line,) = report.lines
    assert line.sourcing_status == "fabrication_service" and discovery.calls == 0
    assert line.recommendation is None and line.selected_offer_url is None
    plan = report.order_plan
    assert plan.unsourced == [] and plan.sellers == []
    assert [m.line_id for m in plan.made_to_order] == ["L01"]
    assert plan.made_to_order[0].fabrication.services[0].name == "Print A"
    # The service sets the price, so estimates say they exclude the line.
    assert plan.costing.excluded_line_ids == ["L01"] and not plan.costing.complete
    assert report.unselected_line_ids == [] and report.parts_subtotal_inr is None


def test_without_a_finder_the_line_is_searched_as_before():
    sourcing = SourcingService(Discovery(), Pages())
    item = BomItem(line_id="L01", raw_name="3D printed enclosure", fabrication="3d_print")
    assert sourcing.fabrication_line(item, []) is None


def test_owned_made_to_order_lines_are_not_planned():
    fab, _, _ = finder([SEARCH, VERDICTS])
    line = fab.line(BomItem(line_id="L01", raw_name="Printed case", fabrication="3d_print"), [])
    line.item.user_has_it = True
    report = Report(demo=False, summary="Synthetic", lines=[line])
    apply_recommendations(report)
    assert report.order_plan.made_to_order == []


def test_a_changed_fabrication_flag_searches_the_line_again():
    before = BomItem(line_id="L01", raw_name="Case", fabrication="3d_print")
    assert not same_part(before, before.model_copy(update={"fabrication": "none"}))
    assert same_part(before, before.model_copy())


def test_refresh_result_and_report_line_accept_the_new_status():
    line = ReportLine(item=BomItem(line_id="L01", raw_name="x"), sourcing_status="not_run")
    line.sourcing_status = "fabrication_service"
    assert ReportLine.model_validate(line.model_dump()).sourcing_status == "fabrication_service"
