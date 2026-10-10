import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from typing import ClassVar

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import PROJECT_ONLY, GeminiAssistant
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    ChatMessage,
    ConfirmJob,
    CreateJob,
    Job,
    ReportLine,
    SearchAttribution,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import variant_url, verify_page
from bharat_sourcer.sourcing.service import SourcingService


@pytest.mark.parametrize("result", ['{"allowed":false}', "invalid"])
def test_off_topic_or_failed_gate_never_calls_answer_model(result):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": result}]}}]
            },
        )

    assistant = GeminiAssistant(
        Settings(_env_file=None, gemini_api_key="test"), httpx.MockTransport(handler)
    )
    job = Job(
        job_id="test",
        input=CreateJob(url="https://example.com"),
        messages=[ChatMessage(message_id="m", role="user", text="Write a celebrity biography")],
    )
    reply = assistant.reply(job)
    assert len(calls) == 1
    assert not reply.edits and reply.refresh is None
    assert reply.text == PROJECT_ONLY if result.startswith("{") else "retry" in reply.text


def test_three_searches_overlap_pause_saves_all_active_results():
    barrier, release = Barrier(4), Event()
    calls = []

    class Extractor:
        def extract(self, url):
            return [BomItem(line_id=f"L0{i}", raw_name="Synthetic") for i in range(1, 5)]

    class Source:
        def source(self, item):
            calls.append(item.line_id)
            if item.line_id != "L04":
                barrier.wait(timeout=5)
                assert release.wait(5)
            return ReportLine(item=item, sourcing_status="no_verified_offers")

    jobs = JobService(Extractor(), sourcing=Source(), sourcing_parallelism=3)
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    jobs.confirm(job.job_id, token, ConfirmJob())
    with ThreadPoolExecutor() as pool:
        running = pool.submit(jobs.finish, job.job_id)
        barrier.wait(timeout=5)
        jobs.pause(job.job_id, token)
        release.set()
        running.result(timeout=5)
    paused = jobs.get(job.job_id, token)
    assert paused.status == "paused"
    assert [line.item.line_id for line in paused.report.lines] == ["L01", "L02", "L03"]
    jobs.resume(job.job_id, token)
    jobs.finish(job.job_id)
    assert sorted(calls) == ["L01", "L02", "L03", "L04"]


def test_explicit_variant_is_fetched_before_price_accepted():
    base = "https://seller.example/products/led"
    variant = base + "?variant=123"
    product = {
        "@type": "Product",
        "name": "Red LED",
        "offers": {
            "@type": "Offer",
            "priceCurrency": "INR",
            "price": "2.00",
            "availability": "https://schema.org/InStock",
            "url": variant,
        },
    }
    body = ('<script type="application/ld+json">' + json.dumps(product) + "</script>").encode()

    def page(url):
        return Page(url, 200, {"content-type": "text/html"}, body)

    assert verify_page(page(base), "LED") is None
    assert variant_url(page(base), "LED") == variant

    class Discovery:
        def discover(self, query):
            return SearchAttribution(source_urls=[base])

    class Fetcher:
        calls: ClassVar[list] = []

        def get(self, url):
            self.calls.append(url)
            return page(url)

    fetcher = Fetcher()
    result = SourcingService(Discovery(), fetcher).source(BomItem(line_id="L01", raw_name="LED"))
    assert fetcher.calls == [base, variant]
    assert str(result.offers[0].url) == variant
    assert result.offers[0].price_inr == "2.00"
