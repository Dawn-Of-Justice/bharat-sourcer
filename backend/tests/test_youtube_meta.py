"""YouTube description intake tests (youtube_meta.py, extraction, intake, retention).

The videos.list response fixture is SYNTHETIC: it follows the documented API shape but is
not a real video, channel or parts list. Gemini responses and BOM lines below are synthetic
too; none of it is verified evidence. No network call runs: YouTube and Gemini are served by
httpx.MockTransport and project pages by a fake fetcher.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from bharat_sourcer.config import Settings
from bharat_sourcer.export import redact
from bharat_sourcer.extraction import (
    DESCRIPTION_PROMPT,
    ExtractionError,
    ExtractionResult,
    GeminiExtractor,
)
from bharat_sourcer.intake import extract_sources
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    CreateJob,
    Evidence,
    Job,
    JobVideoMeta,
    VideoLink,
)
from bharat_sourcer.youtube_meta import (
    apply_retention,
    classify_link,
    description_links,
    description_page_source,
    fetch_description,
    job_video_meta,
    video_id,
)

FIXTURE = Path(__file__).parent / "fixtures" / "youtube" / "videos-list-synthetic.json"
VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
REPO = "https://github.com/maker/synthetic-station"
INSTRUCTABLES = "https://www.instructables.com/Synthetic-Weather-Station/"
KEY = "synthetic-youtube-key-DO-NOT-LOG"


def youtube_body():
    return json.loads(FIXTURE.read_text("utf-8"))


def youtube_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_youtube(calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json=youtube_body())

    return handler


def gemini(body):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(body)}]}}
            ]
        },
    )


class NoFetcher:
    def get(self, url, **kwargs):
        raise AssertionError(f"unexpected fetch {url}")


def extractor(gemini_handler, youtube_handler=None, key=KEY):
    return GeminiExtractor(
        Settings(
            _env_file=None, demo_mode=False, gemini_api_key="test-secret", youtube_api_key=key
        ),
        transport=httpx.MockTransport(gemini_handler),
        fetcher=NoFetcher(),
        youtube_client=youtube_client(youtube_handler) if youtube_handler else None,
    )


# --- video id, links and classification ---------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        VIDEO,
        "https://youtu.be/abcdefghijk",
        "https://www.youtube.com/shorts/abcdefghijk",
        "https://m.youtube.com/watch?v=abcdefghijk&t=30",
    ],
)
def test_video_id_covers_watch_short_and_shorts_urls(url):
    assert video_id(url) == "abcdefghijk"


def test_video_id_rejects_other_urls():
    assert video_id("https://example.com/watch?v=abcdefghijk") is None
    assert video_id(REPO) is None


def test_description_links_and_classification():
    text = youtube_body()["items"][0]["snippet"]["description"]
    links = description_links(text)
    assert links[0] == REPO and len(links) == 6
    kinds = {url: classify_link(url)[0] for url in links}
    assert kinds[REPO] == "project_source"
    assert kinds[INSTRUCTABLES] == "project_source"
    assert kinds["https://amzn.to/3synthX"] == "store"
    assert kinds["https://robu.in/product/synthetic-bme280-module/"] == "store"
    assert kinds["https://youtu.be/bbbbbbbbbbb"] == "video"
    assert kinds["https://www.instagram.com/synthetic.maker/"] == "other"
    # Trailing punctuation is not part of a link.
    assert description_links("See https://github.com/a/b.") == ["https://github.com/a/b"]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/project",
        "https://[::1]/project",
        "https://localhost/project",
        "https://maker.local/project",
        "https://user:secret@maker.example/project",
        "https://maker.example:8443/project",
        "ftp://maker.example/project",
        "https://instagram.com/maker",
        "https://bit.ly/project",
        "https://amzn.to/item",
    ],
)
def test_creator_pages_reject_unsafe_or_non_project_links(url):
    assert description_page_source(url) is None


def test_personal_blog_accepted_directly_and_in_description():
    from bharat_sourcer.extraction import supported_source

    url = "http://maker.example/?project=weather#parts"
    canonical = "https://maker.example/?project=weather"
    assert supported_source(url) == ("project_page", canonical)
    assert classify_link(url) == ("project_source", canonical)


@pytest.mark.parametrize("failed_page", [False, True])
def test_creator_description_page_is_read_with_quotes_and_failure_is_nonfatal(failed_page):
    from bharat_sourcer.sourcing.fetch import FetchError, Page

    url = "https://maker.example/weather"
    body = youtube_body()
    body["items"][0]["snippet"]["description"] = "Build details: " + url
    calls = []

    class CreatorFetcher:
        def get(self, address, **kwargs):
            calls.append(address)
            if failed_page:
                raise FetchError("Robots policy prevents verification")
            return Page(
                address,
                200,
                {"content-type": "text/html"},
                b"<article><p>Synthetic 830 point breadboard</p></article>",
            )

    def generate(request):
        payload = json.loads(request.content)
        if "fileData" in payload["contents"][0]["parts"][0]:
            return gemini(
                {
                    "items": [
                        {
                            "raw_name": "Jumper wires",
                            "qty": 1,
                            "evidence": [
                                {
                                    "source": "video",
                                    "timestamp": "00:10",
                                    "observation": "Synthetic video",
                                }
                            ],
                        }
                    ]
                }
            )
        return gemini(
            {
                "items": [
                    {
                        "raw_name": "Breadboard",
                        "qty": 1,
                        "evidence": [
                            {"quote": "830 point breadboard", "observation": "Synthetic page"}
                        ],
                    }
                ]
            }
        )

    reader = extractor(generate, lambda request: httpx.Response(200, json=body))
    reader.fetcher = CreatorFetcher()
    result = extract_sources(reader, [VIDEO])
    assert calls == [url]
    report = result.sources[-1]
    assert (report.kind, report.found_in) == ("blog", "youtube_description")
    assert report.status == ("failed" if failed_page else "read")
    assert result.video_meta.links[0].followed
    if not failed_page:
        evidence = result.items[-1].evidence[0]
        assert str(evidence.url) == url and evidence.quote == "830 point breadboard"
        direct = reader.extract(url)
        assert str(direct.items[0].evidence[0].url) == url


def test_empty_video_can_use_parts_from_description_link():
    reader = extractor(lambda request: gemini({"items": []}), ok_youtube())
    result = reader.extract(VIDEO)
    assert result.items == [] and result.video_meta.links
    fake = SourceExtractor(
        {
            VIDEO: result,
            REPO: ExtractionResult(items=[line("Breadboard", [page_ev("830 point breadboard")])]),
            INSTRUCTABLES: ExtractionError("SOURCE_UNAVAILABLE", "Synthetic failure"),
        }
    )
    assert extract_sources(fake, [VIDEO]).items[0].raw_name == "Breadboard"


# --- fetch_description --------------------------------------------------------------


def test_fetch_parses_snippet_and_sends_key_in_header_only():
    calls = []
    meta = fetch_description("abcdefghijk", KEY, youtube_client(ok_youtube(calls)))
    assert meta.title.startswith("Synthetic ESP32")
    assert meta.channel == "Synthetic Maker Channel"
    assert meta.published_at == datetime(2026, 9, 14, 12, 30, tzinfo=UTC)
    assert "BME280 temperature" in meta.description and REPO in meta.links
    (request,) = calls
    assert request.url.path == "/youtube/v3/videos"
    assert dict(request.url.params) == {"part": "snippet", "id": "abcdefghijk"}
    assert KEY not in str(request.url) and request.headers["x-goog-api-key"] == KEY


def test_no_key_makes_no_call():
    def handler(request):
        raise AssertionError("no call expected")

    for key in (None, "", "   "):
        assert fetch_description("abcdefghijk", key, youtube_client(handler)) is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, json={"error": {"code": 403, "message": "synthetic forbidden"}}),
        httpx.Response(404),
        httpx.Response(200, json={"kind": "youtube#videoListResponse", "items": []}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"items": [{"snippet": {"title": "", "description": ""}}]}),
    ],
)
def test_http_errors_and_empty_results_return_none(response):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    assert fetch_description("abcdefghijk", KEY, youtube_client(handler)) is None
    assert len(calls) == 1  # No retry on a 4xx or a parsed response.


def test_retries_once_on_server_error_or_network_failure():
    calls = []

    def flaky(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json=youtube_body())

    assert fetch_description("abcdefghijk", KEY, youtube_client(flaky)) is not None
    assert len(calls) == 2

    calls.clear()

    def down(request):
        calls.append(request)
        return httpx.Response(503)

    assert fetch_description("abcdefghijk", KEY, youtube_client(down)) is None
    assert len(calls) == 2


def test_key_never_appears_in_logs(caplog):
    caplog.set_level(logging.DEBUG)

    def broken(request):
        raise httpx.ConnectError(f"synthetic failure for {request.url}", request=request)

    for handler in (
        broken,
        lambda request: httpx.Response(403, json={"error": {"message": "bad key"}}),
        lambda request: httpx.Response(500),
        ok_youtube(),
    ):
        fetch_description("abcdefghijk", KEY, youtube_client(handler))
    assert "YouTube videos.list" in caplog.text
    assert KEY not in caplog.text


# --- extraction: one Gemini call reads the video and the description -----------------

DESCRIBED_BOM = {
    "project": {"summary": "Synthetic: an ESP32 reads a BME280 and shows it on an OLED."},
    "items": [
        {
            "raw_name": "ESP32 DevKit V1 development board",
            "qty": 1,
            "evidence": [
                {"source": "video", "timestamp": "00:42", "observation": "Board shown."},
                {
                    "source": "youtube_description",
                    "quote": "ESP32 DevKit V1 development board x1",
                    "observation": "Listed in the description parts list.",
                },
            ],
        },
        {
            "raw_name": "BME280 sensor module",
            "qty": None,
            "evidence": [
                {
                    "source": "youtube_description",
                    "quote": "BME280 temperature,   humidity and pressure sensor module",
                    "observation": "Listed in the description.",
                }
            ],
        },
        {
            "raw_name": "3D printer",
            "qty": 1,
            "evidence": [
                {
                    "source": "youtube_description",
                    "quote": "a 3D printer is required",
                    "observation": "Fabricated quote; not in the description.",
                }
            ],
        },
    ],
}


def test_description_is_extra_context_in_the_single_video_call():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return gemini(DESCRIBED_BOM)

    result = extractor(handler, ok_youtube()).extract("https://youtu.be/abcdefghijk")
    (payload,) = requests  # No extra Gemini call for the description.
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"fileData": {"fileUri": VIDEO, "mimeType": "video/*"}}
    context = json.loads(parts[1]["text"])["youtube_description"]
    assert "BME280 temperature" in context["description"]
    assert DESCRIPTION_PROMPT.strip() in payload["systemInstruction"]["parts"][0]["text"]

    names = [item.raw_name for item in result.items]
    assert names == ["ESP32 DevKit V1 development board", "BME280 sensor module"]
    board, sensor = result.items
    assert [e.source for e in board.evidence] == ["video", "youtube_description"]
    quote = sensor.evidence[0]
    assert quote.source == "youtube_description" and str(quote.url) == VIDEO
    assert quote.quote == "BME280 temperature, humidity and pressure sensor module"
    assert result.video_meta.video_id == "abcdefghijk"
    assert "description" not in result.video_meta.model_dump()
    assert not result.description_failed


def test_long_description_quotes_are_cut_to_300_characters():
    long_line = "Parts: " + "resistor " * 60
    body = youtube_body()
    body["items"][0]["snippet"]["description"] = long_line
    bom = {
        "items": [
            {
                "raw_name": "Resistor",
                "qty": None,
                "evidence": [
                    {"source": "youtube_description", "quote": long_line, "observation": "x"}
                ],
            }
        ]
    }
    result = extractor(lambda r: gemini(bom), lambda r: httpx.Response(200, json=body)).extract(
        VIDEO
    )
    assert len(result.items[0].evidence[0].quote) <= 300
    with pytest.raises(ValidationError):
        Evidence(source="youtube_description", quote="x" * 301, observation="o", url=VIDEO)


def test_without_key_the_video_prompt_is_unchanged():
    requests = []
    plain = {
        "items": [
            {
                "raw_name": "Servo",
                "qty": 1,
                "evidence": [{"timestamp": "00:10", "observation": "Servo shown."}],
            }
        ]
    }

    def handler(request):
        requests.append(json.loads(request.content))
        return gemini(plain)

    result = extractor(handler, key=None).extract(VIDEO)
    assert requests[0]["contents"][0]["parts"] == [
        {"fileData": {"fileUri": VIDEO, "mimeType": "video/*"}}
    ]
    assert DESCRIPTION_PROMPT.strip() not in requests[0]["systemInstruction"]["parts"][0]["text"]
    assert result.video_meta is None and not result.description_failed


def test_failed_description_call_is_not_fatal():
    plain = {
        "items": [
            {
                "raw_name": "Servo",
                "qty": 1,
                "evidence": [{"timestamp": "00:10", "observation": "Servo shown."}],
            }
        ]
    }
    result = extractor(lambda r: gemini(plain), lambda r: httpx.Response(403)).extract(VIDEO)
    assert [item.raw_name for item in result.items] == ["Servo"]
    assert result.video_meta is None and result.description_failed


# --- intake: description links become sources; fusion merges them --------------------


def video_ev(stamp="00:42"):
    return Evidence(timestamp=stamp, observation="Synthetic video evidence.")


def description_ev(quote):
    return Evidence(source="youtube_description", quote=quote, observation="Synthetic.", url=VIDEO)


def page_ev(quote, url=REPO):
    return Evidence(source="project_page", quote=quote, observation="Synthetic.", url=url)


def line(name, evidence):
    return BomItem(line_id="L01", raw_name=name, evidence=evidence)


def synthetic_meta(**changes):
    from bharat_sourcer.youtube_meta import VideoMeta

    snippet = youtube_body()["items"][0]["snippet"]
    meta = VideoMeta(
        video_id="abcdefghijk",
        title=snippet["title"],
        description=snippet["description"],
        channel=snippet["channelTitle"],
        published_at=None,
        fetched_at=datetime.now(UTC),
        links=description_links(snippet["description"]),
    )
    return job_video_meta(meta, set()).model_copy(update=changes)


class SourceExtractor:
    """Synthetic extractor: canned results per canonical URL, recording calls."""

    def __init__(self, results):
        self.results, self.calls = results, []

    def extract(self, url):
        self.calls.append(url)
        value = self.results[url]
        if isinstance(value, Exception):
            raise value
        return value


def video_result(**changes):
    return ExtractionResult(
        items=[
            line("Breadboard", [description_ev("830 point breadboard")]),
            line("ESP32 DevKit V1 development board", [video_ev()]),
        ],
        **({"video_meta": synthetic_meta()} | changes),
    )


def test_description_links_are_followed_and_fused():
    fake = SourceExtractor(
        {
            VIDEO: video_result(),
            REPO: ExtractionResult(items=[line("830 point breadboard", [page_ev("breadboard")])]),
            INSTRUCTABLES: ExtractionError("SOURCE_UNAVAILABLE", "Synthetic fetch failure"),
        }
    )
    result = extract_sources(fake, [VIDEO])
    assert fake.calls == [VIDEO, REPO, INSTRUCTABLES]  # Store and social links not followed.
    reports = [(r.kind, r.role, r.status, r.item_count, r.found_in) for r in result.sources]
    assert reports == [
        ("video", "primary", "read", 2, None),
        ("youtube_description", "additional", "read", 1, None),
        ("github", "additional", "read", 1, "youtube_description"),
        ("instructables", "additional", "failed", 0, "youtube_description"),
    ]
    sensor = result.items[0]
    assert {e.source for e in sensor.evidence} == {"youtube_description", "project_page"}
    assert sensor.confidence == "verified"
    followed = {link.url: link.followed for link in result.video_meta.links}
    assert followed[REPO] and followed[INSTRUCTABLES]
    assert not followed["https://amzn.to/3synthX"]
    assert not followed["https://robu.in/product/synthetic-bme280-module/"]


def test_description_only_line_is_likely():
    fake = SourceExtractor({VIDEO: video_result(video_meta=synthetic_meta(links=[]))})
    result = extract_sources(fake, [VIDEO])
    sensor = result.items[0]
    assert sensor.confidence == "likely" and "description" in sensor.confidence_reason


def test_description_links_respect_the_extra_source_limit_and_dedupe():
    blog = "https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/"
    adafruit = "https://learn.adafruit.com/magtag-weather"  # Never reached: limit is 3.
    empty = ExtractionResult(items=[line("Jumper wires", [page_ev("Jumper wires", blog)])])
    fake = SourceExtractor(
        {VIDEO: video_result(), REPO: empty, blog: empty, INSTRUCTABLES: empty, adafruit: empty}
    )
    result = extract_sources(fake, [VIDEO, REPO, blog])
    # REPO was already submitted (deduped); the one free slot goes to the next new link.
    assert fake.calls == [VIDEO, REPO, blog, INSTRUCTABLES]
    assert len(result.sources) == 5  # Three extras, the video and its description.
    assert [r.found_in for r in result.sources if r.url == REPO] == [None]


def test_description_failure_is_reported_but_not_fatal():
    fake = SourceExtractor(
        {VIDEO: ExtractionResult(items=[line("Servo", [video_ev()])], description_failed=True)}
    )
    result = extract_sources(fake, [VIDEO])
    assert [item.raw_name for item in result.items] == ["Servo"]
    failed = result.sources[1]
    assert failed.kind == "youtube_description" and failed.status == "failed"
    assert failed.error.code == "DESCRIPTION_UNAVAILABLE"


# --- retention: description data older than 30 days is not served --------------------


def described_job(fetched_at):
    return Job(
        job_id="00000000-0000-4000-8000-000000000000",
        input=CreateJob(url=VIDEO),
        items=[line("BME280 sensor module", [description_ev("BME280 sensor"), video_ev()])],
        video_meta=JobVideoMeta(
            video_id="abcdefghijk",
            title="Synthetic title",
            channel="Synthetic channel",
            fetched_at=fetched_at,
            links=[VideoLink(url=REPO, kind="project_source", followed=True)],
        ),
    )


def test_retention_keeps_fresh_and_drops_expired_description_data():
    fresh = apply_retention(described_job(datetime.now(UTC) - timedelta(days=29)))
    assert [e.source for e in fresh.items[0].evidence] == ["youtube_description", "video"]
    assert fresh.video_meta.links and not fresh.video_meta.expired

    old = apply_retention(described_job(datetime.now(UTC) - timedelta(days=31)))
    assert [e.source for e in old.items[0].evidence] == ["video"]
    meta = old.video_meta
    assert meta.expired and meta.title is None and meta.channel is None and meta.links == []
    assert meta.video_id == "abcdefghijk"

    view = redact(described_job(datetime.now(UTC) - timedelta(days=31)))
    assert [e.source for e in view.items[0].evidence] == ["video"]


def test_job_service_stores_video_meta_and_filters_on_read():
    fake = SourceExtractor({VIDEO: video_result(video_meta=synthetic_meta(links=[]))})
    service = JobService(fake)
    job, token = service.create(CreateJob(url=VIDEO))
    service.extract(job.job_id)
    snapshot = service.get(job.job_id, token)
    assert snapshot.video_meta.video_id == "abcdefghijk"
    assert snapshot.items[0].evidence[0].source == "youtube_description"
    assert [r.kind for r in snapshot.source_reports] == ["video", "youtube_description"]

    def age(record):
        record.job.video_meta.fetched_at = datetime.now(UTC) - timedelta(days=31)

    service.store.mutate(job.job_id, age)
    expired = service.get(job.job_id, token)
    assert expired.video_meta.expired
    assert all(e.source != "youtube_description" for i in expired.items for e in i.evidence)
