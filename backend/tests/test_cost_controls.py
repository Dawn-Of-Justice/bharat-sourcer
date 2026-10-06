"""Cost controls: shared cache, research skip rules, refresh without rediscovery, the job
budget guard and cost attribution. Synthetic fixtures only; Gemini is always mocked."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from test_research import SETTINGS, URL, draft, page, response
from test_sourcing import PRODUCT

from bharat_sourcer.config import Settings, site_generation, site_model
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    Compatibility,
    ConfirmJob,
    CreateJob,
    PartRequirement,
    PartResearch,
    RefreshOffers,
    ReportLine,
    ResearchSource,
    SearchAttribution,
    VerifiedOffer,
)
from bharat_sourcer.sourcing import service as service_module
from bharat_sourcer.sourcing.cache import (
    TTL,
    FirestoreCache,
    MemoryCache,
    build_cache,
    cache_key,
    normalise_part,
    part_key,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.research import (
    GeminiResearch,
    needs_followup,
    review_or_skip,
    sufficient_offer,
)
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.usage import JobLedger, attribute, estimate_usd, paid_allowed, record_usage

USAGE = {
    "usageMetadata": {"promptTokenCount": 10000, "candidatesTokenCount": 1000},
    "candidates": [
        {
            "finishReason": "STOP",
            "groundingMetadata": {"groundingChunks": [{"web": {}}], "webSearchQueries": ["a"]},
        }
    ],
}


# Shared cache backends.


class FakeSnapshot:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return dict(self.data) if self.data is not None else None


class FakeDocument:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self):
        return FakeSnapshot(self.store.get(self.key))

    def set(self, data):
        self.store[self.key] = dict(data)


class FakeCollection:
    def __init__(self, name):
        self.id, self.docs = name, {}

    def document(self, key):
        return FakeDocument(self.docs, key)


class FakeClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection(name))


class FakeStore:
    def __init__(self):
        self.client = FakeClient()
        self.collection = self.client.collection("backend_jobs")


@pytest.fixture(params=["memory", "firestore"])
def cache(request):
    if request.param == "memory":
        return MemoryCache()
    return FirestoreCache.for_store(FakeStore())


def test_cache_round_trip_miss_and_expiry(cache):
    key = cache_key("discovery", "ttp223")
    assert cache.get(key) is None
    cache.set(key, {"urls": ["https://seller.example/a"]}, TTL["discovery"])
    assert cache.get(key) == {"urls": ["https://seller.example/a"]}
    cache.set(key, {"urls": []}, -1)  # non-positive TTLs are not stored
    assert cache.get(key) == {"urls": ["https://seller.example/a"]}


def test_expired_entries_are_ignored_on_read():
    memory = MemoryCache()
    memory.set("page-x", {"a": 1}, 60)
    memory.records["page-x"] = (datetime.now(UTC) - timedelta(seconds=1), "{}")
    assert memory.get("page-x") is None
    firestore = FirestoreCache.for_store(FakeStore())
    firestore.set("page-x", {"a": 1}, 60)
    firestore.collection.docs["page-x"]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    assert firestore.get("page-x") is None


def test_firestore_cache_layout_and_chunking():
    store = FakeStore()
    firestore = FirestoreCache.for_store(store)
    assert "backend_jobs_cache" in store.client.collections
    firestore.CHUNK = 100  # force chunking with a small value
    value = {"text": "Ω" * 400}
    firestore.set("judge-abc", value, 60)
    docs = firestore.collection.docs
    assert docs["judge-abc"]["chunks"] > 1 and "value" not in docs["judge-abc"]
    assert all(len(docs[f"judge-abc-{i}"]["data"].encode()) <= 100 for i in range(3))
    assert docs["judge-abc"]["namespace"] == "judge"
    assert isinstance(docs["judge-abc"]["expires_at"], datetime)
    assert firestore.get("judge-abc") == value
    del docs["judge-abc-1"]  # a missing chunk is a miss, never partial data
    assert firestore.get("judge-abc") is None


def test_firestore_failures_are_misses():
    class Broken:
        id = "x"

        def document(self, key):
            raise RuntimeError("Firestore unavailable")

    firestore = FirestoreCache(FakeClient(), "jobs")
    firestore.collection = Broken()
    firestore.set("page-x", {"a": 1}, 60)
    assert firestore.get("page-x") is None


def test_build_cache_follows_storage_and_switch():
    assert isinstance(build_cache(Settings(_env_file=None)), MemoryCache)
    assert build_cache(Settings(_env_file=None, cache_enabled=False)) is None
    firestore = Settings(_env_file=None, storage_backend="firestore", gcp_project="p")
    assert isinstance(build_cache(firestore, FakeStore()), FirestoreCache)


@pytest.mark.parametrize(
    "a,b",
    [
        ("33kΩ resistor", "33K resistor"),
        ("33 k ohm  Resistor", "33k resistor"),
        ("10 Kohms resistor", "10k resistor"),
        ("5 Volt relay", "5v relay"),
        ("100 nF capacitor", "100nf CAPACITOR"),
        ("1MΩ resistor", "1M resistor"),
    ],
)
def test_part_names_share_cache_entries(a, b):
    assert normalise_part(a) == normalise_part(b)
    assert part_key("discovery", a) == part_key("discovery", b)


def test_mega_and_milli_never_collide():
    assert normalise_part("1MΩ resistor") != normalise_part("1mΩ resistor")
    assert normalise_part("33kΩ resistor") == "33k resistor"


def test_cache_keys_are_namespaced_and_stable():
    assert cache_key("judge", "a", {"b": 1}) == cache_key("judge", "a", {"b": 1})
    assert cache_key("judge", "a").startswith("judge-")
    assert cache_key("judge", "a") != cache_key("page", "a")
    with pytest.raises(ValueError):
        cache_key("unknown", "a")


# Research skip rules.


def offer(stock="in_stock", status="compatible", grade="A"):
    return VerifiedOffer(
        url=URL,
        seller="seller.example",
        title="Synthetic Model B bearing",
        price_inr="10.00",
        stock=stock,
        compatibility=Compatibility(status=status, grade=grade),
    )


class CountingResearch:
    def __init__(self):
        self.calls = 0

    def research(self, item, pages, sources, project):
        self.calls += 1
        return PartResearch(status="no_evidence", summary="Fixture")


@pytest.mark.parametrize(
    "offers,skips",
    [
        ([offer()], True),
        ([offer(stock="out_of_stock")], False),
        ([offer(stock="unknown")], False),
        ([offer(status="unknown", grade=None)], False),
        ([offer(status="changes_required", grade="C")], False),
        ([], False),
    ],
)
def test_research_review_skipped_only_for_verified_in_stock_compatible_offer(offers, skips):
    researcher = CountingResearch()
    item = BomItem(line_id="L01", raw_name="bearing")
    sources = [ResearchSource(url=URL, status="read")]
    result = review_or_skip(researcher, item, [page()], sources, [item], offers)
    assert (sufficient_offer(offers) is not None) is skips
    assert researcher.calls == (0 if skips else 1)
    if skips:
        assert result.status == "skipped" and result.sources == sources


def test_service_skips_review_when_offer_is_compatible(monkeypatch):
    monkeypatch.setattr(
        service_module, "assess_offer", lambda resolution, o: Compatibility(status="compatible")
    )

    class Discovery:
        def discover(self, query):
            return SearchAttribution(source_urls=[URL])

    class Fetcher:
        def get(self, url):
            return page('<script type="application/ld+json">' + json.dumps(PRODUCT) + "</script>")

    researcher = CountingResearch()
    line = SourcingService(Discovery(), Fetcher(), researcher, True).source(
        BomItem(line_id="L01", raw_name="TTP223")
    )
    assert line.sourcing_status == "offers_found"
    assert researcher.calls == 0
    assert line.research.status == "skipped"


def test_followup_needs_no_offer_and_no_candidate():
    item = BomItem(line_id="L01", raw_name="bearing")
    empty = PartResearch(status="no_evidence", summary="x")
    assert needs_followup(ReportLine(item=item, sourcing_status="failed", research=empty))
    assert not needs_followup(
        ReportLine(item=item, sourcing_status="offers_found", research=empty, offers=[offer()])
    )
    for status in ["ready", "failed", "skipped"]:
        line = ReportLine(
            item=item,
            sourcing_status="no_verified_offers",
            research=PartResearch(status=status, summary="x"),
        )
        assert not needs_followup(line)
    assert not needs_followup(ReportLine(item=item, sourcing_status="no_verified_offers"))
    spent = JobLedger("job", budget_usd=0.01)
    spent.add("discovery", 0.02, 1)
    with attribute(spent):
        assert not needs_followup(
            ReportLine(item=item, sourcing_status="no_verified_offers", research=empty)
        )


def test_research_documents_are_capped_by_total_characters():
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return response(draft())

    settings = Settings(
        _env_file=None,
        gemini_api_key="test",
        research_pages_per_part=5,
        research_page_chars=5000,
        research_total_chars=6000,
    )
    long = "Synthetic Model B bearing. Bore diameter 8 mm. " + "filler " * 2000
    pages = [page(long, url=f"{URL}/{i}") for i in range(4)]
    item = BomItem(line_id="L01", raw_name="bearing")
    GeminiResearch(settings, httpx.MockTransport(handle)).research(item, pages, [], [item])
    sent = json.loads(seen[0]["contents"][0]["parts"][0]["text"])
    assert sum(len(d["text"]) for d in sent["documents"]) <= 6000
    assert len(sent["documents"]) < 4  # four 5,000-char pages did not all fit
    # Stable prefix first: project context precedes this line's part and documents.
    assert list(sent) == ["project_parts", "project_context_truncated", "part", "documents"]


def test_research_cache_reuses_evidence_without_project_text_and_rechecks_quotes():
    calls = []

    def handle(request):
        calls.append(1)
        return response(draft())

    shared = MemoryCache()
    reader = GeminiResearch(SETTINGS, httpx.MockTransport(handle), cache=shared)
    item = BomItem(
        line_id="L01",
        raw_name="Bearing",
        requirements=[PartRequirement(name="bore diameter", value="8", unit="mm")],
    )
    sources = [ResearchSource(url=URL, status="read")]
    first = reader.research(item, [page()], sources, [item])
    assert first.status == "ready" and len(calls) == 1
    stored = next(iter(shared.records.values()))[1]
    assert "explanation" not in stored and "questions" not in stored
    other_job = item.model_copy(update={"line_id": "L07", "raw_name": "bearing "})
    ledger = JobLedger("job-2")
    with attribute(ledger, "L07"):
        second = reader.research(other_job, [page()], sources, [other_job])
    assert len(calls) == 1
    assert ledger.cache_hits == {"research": 1}
    assert second.status == "ready"
    assert "Reused cached evidence" in second.summary
    candidate = second.candidates[0]
    assert candidate.assessment.checks[0].status == "meets"
    assert candidate.assessment.status == "potential_match"
    # Quotes no longer on the page are not retained; the model is asked again.
    reader.research(other_job, [page("Different page text entirely.")], sources, [other_job])
    assert len(calls) == 2


def test_research_stops_at_budget_but_still_uses_cache():
    reader = GeminiResearch(
        SETTINGS, httpx.MockTransport(lambda _: pytest.fail("No paid call over budget"))
    )
    item = BomItem(line_id="L01", raw_name="bearing")
    spent = JobLedger("job", budget_usd=0.0)
    with attribute(spent, "L01"):
        result = reader.research(item, [page()], [], [item])
    assert result.status == "skipped"
    assert "job budget" in result.summary


# Call-site configuration.


def test_site_settings_default_to_low_thinking_for_cheap_sites():
    settings = Settings(_env_file=None)
    for site in ["chat_scope", "discovery", "judge", "spec"]:
        assert site_generation(settings, site) == {"thinkingConfig": {"thinkingLevel": "low"}}
    assert site_generation(settings, "research") == {}
    assert site_model(settings, "research") == settings.gemini_model
    override = Settings(_env_file=None, gemini_site_models={"chat_scope": "gemini-3.1-flash-lite"})
    assert site_model(override, "chat_scope") == "gemini-3.1-flash-lite"
    with pytest.raises(ValueError):
        Settings(_env_file=None, gemini_site_models={"chat_scope": "bad/model"})


def test_env_overrides_site_maps(monkeypatch):
    monkeypatch.setenv("BS_GEMINI_SITE_THINKING", '{"research": "low"}')
    monkeypatch.setenv("BS_JOB_GEMINI_BUDGET_USD", "0.10")
    settings = Settings(_env_file=None)
    assert settings.gemini_site_thinking == {"research": "low"}
    assert settings.job_gemini_budget_usd == 0.10


def test_discovery_and_scope_requests_use_low_thinking():
    from bharat_sourcer.conversation import GeminiAssistant
    from bharat_sourcer.schemas import Job

    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"allowed": true}'}]},
                        "groundingMetadata": {
                            "groundingChunks": [{"web": {"uri": URL, "title": "x.in"}}]
                        },
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    service_module.GeminiDiscovery(SETTINGS, transport).discover("bearing")
    job = Job(job_id="j", input=CreateJob(url="https://youtu.be/abcdefghijk"))
    GeminiAssistant(SETTINGS, transport).in_scope(job)
    for body in sent:
        assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


# Cost attribution.


def test_usage_lines_are_attributed_and_priced(capsys):
    ledger = JobLedger("job-1", budget_usd=1.0)
    with attribute(ledger, "L02"):
        record_usage("discovery", "gemini-3.8-flash", USAGE)
    record_usage("research", "gemini-3.8-flash", USAGE)  # unattributed
    lines = [
        json.loads(x.removeprefix("GEMINI_USAGE "))
        for x in capsys.readouterr().out.split("\n")
        if x
    ]
    assert lines[0]["job_id"] == "job-1" and lines[0]["line_id"] == "L02"
    assert lines[1]["job_id"] is None
    # 10K input at $0.75/M + 1K output at $3.75/M + one $0.014 query.
    assert lines[0]["usd_est"] == pytest.approx(0.0075 + 0.00375 + 0.014)
    assert ledger.calls == 1 and ledger.calls_by_site == {"discovery": 1}
    assert ledger.search_queries == 1
    estimate = ledger.snapshot()
    assert estimate.total_usd == pytest.approx(0.02525)
    assert estimate.prices_checked == "2026-10-05"


def test_price_table_is_dated():
    fields = {"prompt": 1_000_000, "output": 0}
    from datetime import date

    assert estimate_usd("gemini-3.8-flash", fields, date(2026, 12, 31)) == 0.75
    assert estimate_usd("gemini-3.8-flash", fields, date(2027, 1, 1)) == 1.5
    assert estimate_usd("unknown-model", {"prompt": 1_000_000, "cached": 1_000_000}) > 0


def test_usage_report_breaks_down_sites_and_cache_savings():
    sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
    try:
        import usage_report
    finally:
        sys.path.pop(0)
    lines = [
        'GEMINI_USAGE {"site": "discovery", "model": "gemini-3.8-flash", "prompt": 1000, '
        '"output": 100, "search_queries": 2, "usd_est": 0.03, "job_id": "j1"}',
        'GEMINI_USAGE {"site": "research", "model": "gemini-3.8-flash", "prompt": 8000, '
        '"output": 500, "job_id": "j2"}',
        'GEMINI_CACHE_HIT {"namespace": "discovery", "job_id": "j2"}',
    ]
    report = usage_report.summarise(lines)
    assert "discovery (gemini-3.8-flash)" in report and "est USD" in report
    assert "Attributed jobs: 2" in report
    assert "0.0300" in report.split("cache namespace")[1]  # one hit saves one discovery
    assert "research" not in usage_report.summarise(lines, job="j1")


# Jobs: refresh without rediscovery, budget guard and persisted estimates.


class Discovery:
    def __init__(self, urls, spend=0.0):
        self.urls, self.queries, self.spend = urls, [], spend

    def discover(self, query):
        self.queries.append(query)
        record_usage(
            "discovery",
            "gemini-3.8-flash",
            {"usageMetadata": {"promptTokenCount": int(self.spend * 1_000_000 / 0.75)}},
        )
        return SearchAttribution(source_urls=self.urls, search_queries=[query])


class ProductFetcher:
    def __init__(self, availability="InStock"):
        self.calls, self.availability = [], availability

    def get(self, url):
        self.calls.append(url)
        product = json.loads(json.dumps(PRODUCT))
        product["offers"]["availability"] = "https://schema.org/" + self.availability
        html = '<script type="application/ld+json">' + json.dumps(product) + "</script>"
        return Page(url, 200, {"content-type": "text/html"}, html.encode())


class Extractor:
    def extract(self, url):
        return [BomItem(line_id=f"L0{i}", raw_name="TTP223 touch sensor") for i in [1, 2, 3]]


def sourced_job(discovery, fetcher, budget=None, parallelism=1):
    sourcing = SourcingService(discovery, fetcher, None, True)
    service = JobService(
        Extractor(), sourcing=sourcing, gemini_budget_usd=budget, sourcing_parallelism=parallelism
    )
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    return service, job.job_id, token


SELLER = "https://seller.example/ttp223"


def test_refresh_refetches_known_offer_pages_without_discovery():
    discovery, fetcher = Discovery([SELLER]), ProductFetcher()
    service, job_id, token = sourced_job(discovery, fetcher)
    assert len(discovery.queries) == 3
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L02"]))
    assert service.store.get(job_id).refresh_urls == {"L02": [SELLER]}
    service.finish(job_id)
    result = service.get(job_id, token)
    assert len(discovery.queries) == 3  # no paid rediscovery
    assert fetcher.calls[-1] == SELLER
    line = result.report.lines[1]
    assert line.sourcing_status == "offers_found" and line.offers[0].stock == "in_stock"
    assert line.attribution.search_queries == []
    assert service.store.get(job_id).refresh_urls is None


def test_refresh_rediscovers_when_known_pages_are_out_of_stock():
    discovery, fetcher = Discovery([SELLER]), ProductFetcher()
    service, job_id, token = sourced_job(discovery, fetcher)
    fetcher.availability = "OutOfStock"
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L01"]))
    service.finish(job_id)
    assert len(discovery.queries) == 4


def test_budget_guard_stops_paid_stages_and_refresh_gets_a_new_budget():
    discovery = Discovery([], spend=0.3)
    service, job_id, token = sourced_job(discovery, ProductFetcher(), budget=0.25)
    job = service.get(job_id, token)
    statuses = [line.sourcing_error.code for line in job.report.lines]
    # L01's search crosses the ceiling; L02 and L03 skip paid stages.
    assert statuses == ["NO_VERIFIED_OFFERS", "JOB_BUDGET_REACHED", "JOB_BUDGET_REACHED"]
    assert len(discovery.queries) == 1
    assert job.report.lines[2].sourcing_status == "not_run"
    assert "job budget" in job.report.lines[2].sourcing_error.message
    assert "within the job budget" in job.report.summary
    assert job.cost_estimate.budget_reached and job.cost_estimate.budget_usd == 0.25
    assert job.cost_estimate.calls_by_site == {"discovery": 1}
    assert job.cost_estimate.total_usd == pytest.approx(0.3, rel=0.01)
    # The user can refresh a skipped line: each refresh run gets a fresh budget.
    service.refresh_offers(job_id, token, RefreshOffers(line_ids=["L02"]))
    assert service.get(job_id, token).cost_estimate.run_usd == 0
    service.finish(job_id)
    after = service.get(job_id, token)
    assert after.report.lines[1].sourcing_error.code == "NO_VERIFIED_OFFERS"
    assert after.cost_estimate.total_usd == pytest.approx(0.6, rel=0.01)
    assert after.cost_estimate.calls_by_site == {"discovery": 2}


def test_no_budget_means_no_guard():
    service, job_id, token = sourced_job(Discovery([SELLER]), ProductFetcher())
    job = service.get(job_id, token)
    assert all(line.sourcing_status == "offers_found" for line in job.report.lines)
    assert job.cost_estimate is not None and job.cost_estimate.budget_usd is None
    assert paid_allowed()  # outside any attributed job
