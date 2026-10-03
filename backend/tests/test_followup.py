"""Synthetic coverage and reassessment flows; no network calls."""

import httpx
import pytest
from test_research import SETTINGS, URL, draft, page, response

from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    PartResearch,
    RefreshOffers,
    ResearchSource,
    SearchAttribution,
    UpdateJobSpecs,
)
from bharat_sourcer.sourcing.fetch import FetchError, Page
from bharat_sourcer.sourcing.research import GeminiResearch
from bharat_sourcer.sourcing.service import DiscoveryError, SourcingService


class Discovery:
    def __init__(self, batches):
        self.batches, self.queries = batches, []

    def discover(self, query):
        self.queries.append(query)
        batch = self.batches[len(self.queries) - 1]
        if isinstance(batch, Exception):
            raise batch
        return SearchAttribution(source_urls=batch, search_queries=[query])


class Fetcher:
    def __init__(self):
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if "blocked" in url:
            raise FetchError("Test fixture block")
        return page(url=url)


def reader():
    return GeminiResearch(SETTINGS, httpx.MockTransport(lambda _: response(draft())))


def test_followup_recovers_with_new_source_and_preserves_failed_source():
    blocked = "https://blocked.example/fixture"
    discovery = Discovery([[blocked], [blocked, URL]])
    fetcher = Fetcher()
    result = SourcingService(discovery, fetcher, reader(), True).source(
        BomItem(line_id="L01", raw_name="bearing")
    )
    assert result.research.status == "ready"
    assert len(discovery.queries) == 2
    assert "alternative accessible" in discovery.queries[1]
    assert fetcher.calls == [blocked, URL]
    assert len(result.research.sources) == 2
    assert result.research.sources[0].status == "unavailable"
    assert result.attribution.source_urls == [blocked, URL]


@pytest.mark.parametrize(
    "second", [[], ["https://blocked.example/fixture"], DiscoveryError("test")]
)
def test_followup_stops_after_two_discoveries_even_when_empty_repeated_or_failed(second):
    blocked = "https://blocked.example/fixture"
    discovery, fetcher = Discovery([[blocked], second]), Fetcher()
    result = SourcingService(discovery, fetcher, reader(), True).source(
        BomItem(line_id="L01", raw_name="bearing")
    )
    assert len(discovery.queries) == 2
    assert fetcher.calls == [blocked]
    assert result.research.status == "no_evidence"
    assert result.research.sources[0].status == "unavailable"


@pytest.mark.parametrize("state", ["ready", "failed"])
def test_success_or_provider_failure_does_not_trigger_extra_search(state):
    class Research:
        def research(self, *args):
            return PartResearch(status=state, summary="Synthetic")

    discovery = Discovery([[URL]])
    SourcingService(discovery, Fetcher(), Research(), True).source(
        BomItem(line_id="L01", raw_name="bearing")
    )
    assert len(discovery.queries) == 1


def test_feature_disabled_and_owned_parts_never_follow_up():
    discovery = Discovery([["https://blocked.example/fixture"]])
    service = SourcingService(discovery, Fetcher(), reader(), False)
    service.source(BomItem(line_id="L01", raw_name="bearing"))
    service.source(BomItem(line_id="L02", raw_name="bearing", user_has_it=True))
    assert len(discovery.queries) == 1


def test_unreadable_pages_do_not_consume_readable_document_budget():
    pages = [Page(URL + str(i), 403, {"content-type": "text/html"}, b"") for i in range(3)]
    pages.append(page())
    item = BomItem(line_id="L01", raw_name="bearing")
    result = reader().research(item, pages, [ResearchSource(url=URL, status="read")], [item])
    assert result.status == "ready"


def test_verified_offer_on_followup_survives_research_failure():
    import json

    from test_sourcing import PRODUCT

    blocked = "https://blocked.example/fixture"
    discovery = Discovery([[blocked], [URL]])

    class Offers(Fetcher):
        def get(self, url):
            if "blocked" in url:
                return super().get(url)
            return page('<script type="application/ld+json">' + json.dumps(PRODUCT) + "</script>")

    class Research:
        def research(self, item, pages, sources, project):
            return PartResearch(status="failed" if pages else "no_evidence", summary="Fixture")

    result = SourcingService(discovery, Offers(), Research(), True).source(
        BomItem(line_id="L01", raw_name="TTP223")
    )
    assert result.sourcing_status == "offers_found"
    assert len(result.offers) == 1
    assert result.research.status == "failed"


def test_extraction_confirmation_followup_requirements_and_refresh_workflow():
    class Extractor:
        calls = 0

        def extract(self, url):
            self.calls += 1
            return [BomItem(line_id="L01", raw_name="bearing")]

    discovery = Discovery([["https://blocked.example/fixture"], [URL], [URL]])
    extractor = Extractor()
    service = JobService(extractor, sourcing=SourcingService(discovery, Fetcher(), reader(), True))
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    assert service.get(job.job_id, token).status == "awaiting_confirmation"
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    before = service.get(job.job_id, token)
    assert before.report.lines[0].research.status == "ready"
    service.update_specs(
        job.job_id,
        token,
        UpdateJobSpecs.model_validate(
            {
                "updates": [
                    {
                        "line_id": "L01",
                        "requirements": [
                            {
                                "name": "bore diameter",
                                "value": "10",
                                "unit": "mm",
                                "operator": "equals",
                            }
                        ],
                    }
                ]
            }
        ),
    )
    assert service.get(job.job_id, token).report.lines[0].research.status == "stale"
    service.refresh_offers(job.job_id, token, RefreshOffers(line_ids=["L01"]))
    service.finish(job.job_id)
    after = service.get(job.job_id, token)
    assert after.status == "done"
    candidate = after.report.lines[0].research.candidates[0]
    assert candidate.assessment.status == "not_suitable"
    assert candidate.assessment.checks[0].status == "does_not_meet"
    assert extractor.calls == 1
    assert after.refresh_count == 1  # automatic follow-up did not spend a user refresh
    assert len(discovery.queries) == 3
    assert '"value": "10"' in discovery.queries[-1]
