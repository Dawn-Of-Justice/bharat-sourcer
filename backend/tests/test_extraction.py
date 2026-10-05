import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractionError, GeminiExtractor, youtube_url
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import CreateJob

URL = "https://www.youtube.com/watch?v=abcdefghijk"
PART = {
    "raw_name": "ESP32 board",
    "qty": None,
    "evidence": [{"timestamp": "01:12", "observation": "ESP32 marking is visible"}],
}


def provider(handler):
    return GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(handler),
    )


def result(items):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps({"items": items})}]},
                }
            ]
        },
    )


@pytest.mark.parametrize(
    "url",
    [
        URL,
        "https://youtu.be/abcdefghijk?t=10",
        "https://m.youtube.com/watch?v=abcdefghijk&list=ignored",
        "https://youtube.com/shorts/abcdefghijk",
        "https://www.youtube.com/embed/abcdefghijk",
    ],
)
def test_canonical_url(url):
    assert youtube_url(url) == URL


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.test/watch?v=abcdefghijk",
        "https://user:secret@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com/watch?v=abc",
        "https://youtube.com/playlist?list=abcdefghijk",
        "http://127.0.0.1/video",
        "https://youtu.be/abcdefghijk/extra",
        "https://youtube.com:8443/watch?v=abcdefghijk",
    ],
)
def test_reject_unsupported_url(url):
    with pytest.raises(ExtractionError, match="UNSUPPORTED_URL"):
        youtube_url(url)


def test_outgoing_request_and_validated_output():
    def handle(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-secret"
        assert "test-secret" not in str(request.url)
        payload = json.loads(request.content)
        assert payload["contents"][0]["parts"][0]["fileData"]["fileUri"] == URL
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        schema = payload["generationConfig"]["responseJsonSchema"]
        part_schema = schema["properties"]["items"]["items"]
        assert set(part_schema["required"]) == {"raw_name", "qty", "evidence"}
        assert part_schema["properties"]["qty"]["anyOf"] == [{"type": "integer"}, {"type": "null"}]
        assert "$ref" not in json.dumps(schema)
        assert "maxItems" not in json.dumps(schema)
        return result([PART])

    items = provider(handle).extract("https://youtu.be/abcdefghijk?t=12").items
    assert items[0].line_id == "L01"
    # No stated or suggested count: decided as one, labelled inferred.
    assert (items[0].qty, items[0].qty_source) == (1, "inferred")
    assert items[0].qty_reason
    assert items[0].evidence[0].timestamp == "01:12"


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(429, text="secret upstream detail"), "UPSTREAM_QUOTA"),
        (httpx.Response(403, text="secret upstream detail"), "UPSTREAM_ERROR"),
        (httpx.Response(200, json={}), "INVALID_EXTRACTION"),
        (httpx.Response(200, text="not json"), "INVALID_EXTRACTION"),
        (result([]), "NO_BOM"),
        (result([{**PART, "qty": -1}]), "INVALID_EXTRACTION"),
        (result([{**PART, "evidence": []}]), "INVALID_EXTRACTION"),
        (result([PART] * 101), "INVALID_EXTRACTION"),
        (result([{**PART, "qty": 10001}]), "INVALID_EXTRACTION"),
        (result([{**PART, "raw_name": "x" * 201}]), "INVALID_EXTRACTION"),
        (result([{**PART, "unexpected": True}]), "INVALID_EXTRACTION"),
        (
            result([{**PART, "evidence": [{"timestamp": "00:99", "observation": "A board"}]}]),
            "INVALID_EXTRACTION",
        ),
    ],
)
def test_provider_errors_are_sanitized(response, code):
    with pytest.raises(ExtractionError) as captured:
        provider(lambda request: response).extract(URL)
    assert captured.value.code == code
    assert "secret" not in captured.value.message


def test_timeout_is_sanitized():
    def timeout(request):
        raise httpx.ReadTimeout("secret", request=request)

    with pytest.raises(ExtractionError) as captured:
        provider(timeout).extract(URL)
    assert captured.value.code == "UPSTREAM_TIMEOUT"


def test_live_api_infers_missing_quantity_and_confirms():
    app = create_app(
        Settings(_env_file=None, demo_mode=False, sourcing_enabled=False),
        provider(lambda request: result([PART])),
    )
    with TestClient(app) as client:
        assert client.get("/healthz").json()["mode"] == "live"
        rejected = client.post("/v1/jobs", json={"url": "https://example.com"})
        assert rejected.status_code == 400
        created = client.post("/v1/jobs", json={"url": URL}).json()
        assert created["demo"] is False
        path = created["watch"]
        headers = {"X-Job-Token": created["job_token"]}
        job = client.get(path, headers=headers).json()
        assert job["status"] == "awaiting_confirmation"
        assert job["extraction_model"] == "gemini-3.8-flash"
        assert job["items"][0]["qty_source"] == "inferred"
        assert job["items"][0]["qty"] == 1
        accepted = client.post(
            f"{path}/confirm",
            headers=headers,
            json={
                "edits": [
                    {"op": "update", "line_id": "L01", "qty": 1},
                ]
            },
        )
        assert accepted.status_code == 202
        job = client.get(path, headers=headers).json()
        assert job["report"]["demo"] is False
        assert job["report"]["lines"][0]["item"]["user_edited"] is True
        assert job["report"]["lines"][0]["sourcing_status"] == "not_run"


def test_failure_is_visible_and_does_not_fall_back_to_demo():
    service = JobService(provider(lambda request: httpx.Response(429)))
    job, token = service.create(CreateJob(url=URL))
    service.extract(job.job_id)
    snapshot = service.get(job.job_id, token)
    assert snapshot.status == "failed"
    assert snapshot.error.code == "UPSTREAM_QUOTA"
    assert snapshot.items == []
    assert snapshot.demo is False


def test_polling_during_extraction_does_not_wait_for_provider():
    started, release = Event(), Event()

    def handle(request):
        started.set()
        assert release.wait(5)
        return result([PART])

    service = JobService(provider(handle))
    job, token = service.create(CreateJob(url=URL))
    with ThreadPoolExecutor(max_workers=2) as pool:
        extraction = pool.submit(service.extract, job.job_id)
        try:
            assert started.wait(5)
            snapshot = pool.submit(service.get, job.job_id, token).result(timeout=2)
            assert snapshot.status == "extracting"
        finally:
            release.set()
        extraction.result(timeout=5)
