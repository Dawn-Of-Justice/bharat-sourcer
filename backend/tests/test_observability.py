"""Structured Cloud Logging lines, trace propagation and the app events (observability.md).

Every job, URL, token and response here is SYNTHETIC test data; no network call runs.
"""

import io
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractionError
from bharat_sourcer.intake import extract_sources
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.observability import (
    SPAN_KEY,
    TRACE_KEY,
    StdoutHandler,
    StructuredFormatter,
    Trace,
    configure_logging,
    fields,
    json_enabled,
    log_event,
    parse_cloud_trace,
    parse_traceparent,
    scrub,
    set_project,
    trace_from_headers,
    use_trace,
)
from bharat_sourcer.resilience import post_with_retry
from bharat_sourcer.schemas import BomItem, ConfirmJob, CreateJob
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.usage import JobLedger, attribute, record_usage

TRACE_ID = "105445aa7843bc8bf206b12000100000"
W3C_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
VERTEX = (
    "https://aiplatform.googleapis.com/v1/projects/p/locations/global"
    "/publishers/google/models/gemini-test:generateContent"
)
ANSWER = {
    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}],
    "usageMetadata": {
        "promptTokenCount": 1000,
        "candidatesTokenCount": 100,
        "totalTokenCount": 1100,
    },
}


class ListHandler(logging.Handler):
    """Formats each record at emit time (as a real handler would, trace included)."""

    def __init__(self):
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(StructuredFormatter(json_mode=True))

    def emit(self, record):
        self.lines.append(self.format(record))

    def entries(self, event=None):
        parsed = [json.loads(line) for line in self.lines]
        return [entry for entry in parsed if event is None or entry.get("event") == event]


@pytest.fixture
def json_logs(monkeypatch):
    """JSON lines of the app loggers (events and usage), formatted when they are logged."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-project")
    handler = ListHandler()
    loggers = [logging.getLogger("bharat_sourcer"), logging.getLogger("bharat_sourcer.usage")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    yield handler
    for logger, level in zip(loggers, levels, strict=True):
        logger.removeHandler(handler)
        logger.setLevel(level)
    set_project(None)


def event_fields(caplog, event):
    return [r.bs_fields for r in caplog.records if getattr(r, "bs_event", None) == event]


def record(message, *args, level=logging.INFO, extra=None):
    entry = logging.LogRecord("bharat_sourcer.test", level, __file__, 1, message, args, None)
    for key, value in (extra or {}).items():
        setattr(entry, key, value)  # what logging does with `extra=`
    return entry


# -- trace headers ---------------------------------------------------------------------------
def test_cloud_trace_header_is_parsed_with_a_hex_span():
    trace = parse_cloud_trace(f"{TRACE_ID}/1;o=1")
    assert trace == Trace(TRACE_ID, "0000000000000001", True)
    assert parse_cloud_trace(TRACE_ID) == Trace(TRACE_ID, None, None)
    assert parse_cloud_trace(f"{TRACE_ID.upper()}/18446744073709551615;o=0").sampled is False


def test_traceparent_header_is_parsed():
    trace = parse_traceparent(f"00-{W3C_TRACE}-00f067aa0ba902b7-01")
    assert trace == Trace(W3C_TRACE, "00f067aa0ba902b7", True)
    assert parse_traceparent(f"00-{W3C_TRACE}-00f067aa0ba902b7-00").sampled is False


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not-a-trace",
        "0" * 32 + "/1",
        f"{TRACE_ID}/1;o=1\nINJECTED",
        f"{TRACE_ID[:-1]}/1",
    ],
)
def test_malformed_cloud_trace_headers_are_ignored(value):
    assert parse_cloud_trace(value) is None


@pytest.mark.parametrize(
    "value",
    [
        f"ff-{W3C_TRACE}-00f067aa0ba902b7-01",
        f"00-{'0' * 32}-00f067aa0ba902b7-01",
        f"00-{W3C_TRACE}-{'0' * 16}-01",
        f"00-{W3C_TRACE}-00f067aa0ba902b7",
    ],
)
def test_malformed_traceparent_headers_are_ignored(value):
    assert parse_traceparent(value) is None


def test_cloud_trace_header_wins_over_traceparent():
    headers = {
        "traceparent": f"00-{W3C_TRACE}-00f067aa0ba902b7-01",
        "X-Cloud-Trace-Context": f"{TRACE_ID}/5;o=1",
    }
    assert trace_from_headers(headers).trace_id == TRACE_ID
    assert trace_from_headers({"Traceparent": headers["traceparent"]}).trace_id == W3C_TRACE
    assert trace_from_headers([("x-cloud-trace-context", "bad")]) is None


# -- formatter -------------------------------------------------------------------------------
def test_json_line_has_cloud_logging_fields_and_top_level_values():
    set_project("synthetic-project")
    try:
        with use_trace(Trace(TRACE_ID, "000000000000000a", True)):
            line = StructuredFormatter(json_mode=True).format(
                record(
                    "GEMINI_USAGE %s",
                    '{"site": "discovery"}',
                    extra={"bs_fields": {"site": "discovery", "usd_est": 0.01, "message": "x"}},
                )
            )
    finally:
        set_project(None)
    entry = json.loads(line)
    assert entry["severity"] == "INFO"
    assert entry["message"] == 'GEMINI_USAGE {"site": "discovery"}'
    assert entry["event"] == "GEMINI_USAGE"
    assert entry[TRACE_KEY] == f"projects/synthetic-project/traces/{TRACE_ID}"
    assert entry[SPAN_KEY] == "000000000000000a"
    assert entry["logging.googleapis.com/trace_sampled"] is True
    assert (entry["site"], entry["usd_est"]) == ("discovery", 0.01)
    assert entry["logger"] == "bharat_sourcer.test" and entry["time"].endswith("Z")


def test_json_line_takes_the_event_from_a_legacy_tag_and_maps_severity():
    entry = json.loads(
        StructuredFormatter(json_mode=True).format(
            record("QUEUE_AGE_EXCEEDED job=%s age_s=%d", "j1", 900, level=logging.WARNING)
        )
    )
    assert entry["event"] == "QUEUE_AGE_EXCEEDED"
    assert entry["message"] == "QUEUE_AGE_EXCEEDED job=j1 age_s=900"
    assert entry["severity"] == "WARNING"
    assert TRACE_KEY not in entry  # no request trace outside a request
    plain = json.loads(StructuredFormatter(json_mode=True).format(record("Recovery failed")))
    assert "event" not in plain


def test_json_line_keeps_the_traceback_in_the_message():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        failing = logging.LogRecord(
            "bharat_sourcer.test", logging.ERROR, __file__, 1, "UNHANDLED", (), sys.exc_info()
        )
    entry = json.loads(StructuredFormatter(json_mode=True).format(failing))
    assert entry["severity"] == "ERROR"
    assert (
        entry["message"].startswith("UNHANDLED\nTraceback") and "RuntimeError" in entry["message"]
    )


SECRETS = [
    "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLXZhbHVl",
    "x-goog-api-key=AIzaSyA1234567890abcdefghijklmnopqrstu",
    "Cookie: bs_session=s3cr3t-cookie-value",
    "X-Job-Token: job-token-value-123",
    '{"job_token": "another-token-value"}',
    "owner maker@example.com asked",
    "https://www.youtube.com/watch?v=abcdefghijk&si=tracking-token",
    "id token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLXZhbHVl",
]
LEAKS = [
    "eyJzdWIiOiIxMjMifQ",
    "AIzaSyA1234567890",
    "s3cr3t-cookie-value",
    "job-token-value-123",
    "another-token-value",
    "maker@example.com",
    "si=tracking-token",
    "v=abcdefghijk",
]


@pytest.mark.parametrize("json_mode", [True, False])
def test_secrets_never_reach_a_log_line(json_mode):
    formatter = StructuredFormatter(json_mode=json_mode)
    for text in SECRETS:
        line = formatter.format(record("PROBE %s", text, extra=fields(detail=text, nested=[text])))
        for leak in LEAKS:
            assert leak not in line, (text, line)
    kept = scrub("https://www.youtube.com/watch?v=abcdefghijk")
    assert kept == "https://www.youtube.com/watch?[redacted]"
    # Ordinary diagnostics are left alone.
    ordinary = 'GEMINI_USAGE {"prompt": 1000, "tokens": 5, "max_tokens": 7} basic sensor'
    assert scrub(ordinary) == ordinary


def test_plain_text_locally_and_json_on_cloud_run(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("BS_LOG_FORMAT", raising=False)
    assert json_enabled() is False
    line = StructuredFormatter().format(record("SWEEP_TRUNCATED limit=%d", 5))
    assert line == "INFO bharat_sourcer.test SWEEP_TRUNCATED limit=5"
    monkeypatch.setenv("K_SERVICE", "bharat-sourcer-integration")
    assert json_enabled() is True
    assert json.loads(StructuredFormatter().format(record("SWEEP_TRUNCATED")))["severity"]
    monkeypatch.setenv("BS_LOG_FORMAT", "text")
    assert json_enabled() is False
    monkeypatch.delenv("K_SERVICE")
    monkeypatch.setenv("BS_LOG_FORMAT", "json")
    assert json_enabled() is True


def test_usage_lines_stay_plain_locally(capsys):
    record_usage("discovery", "gemini-test", ANSWER)
    line = capsys.readouterr().out.strip()
    assert line.startswith("GEMINI_USAGE {")
    assert json.loads(line.removeprefix("GEMINI_USAGE "))["total"] == 1100


def test_usage_lines_are_json_on_cloud_run(monkeypatch, capsys):
    monkeypatch.setenv("K_SERVICE", "bharat-sourcer-integration")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-project")
    with use_trace(Trace(TRACE_ID, "0000000000000001", True)):
        record_usage("discovery", "gemini-test", ANSWER)
    entry = json.loads(capsys.readouterr().out.strip())
    assert entry["message"].startswith("GEMINI_USAGE {")
    assert entry["event"] == "GEMINI_USAGE" and entry["site"] == "discovery"
    assert entry["total"] == 1100 and entry["usd_est"] > 0
    assert entry[TRACE_KEY] == f"projects/synthetic-project/traces/{TRACE_ID}"


@pytest.fixture
def restore_uvicorn_loggers():
    names = ["uvicorn", "uvicorn.error", "uvicorn.access", "bharat_sourcer"]
    saved = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            logging.getLogger(name).disabled,
            logging.getLogger(name).level,
        )
        for name in names
    }
    yield
    for name, (handlers, propagate, disabled, level) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate, logger.disabled = handlers, propagate, disabled
        logger.setLevel(level)
    set_project(None)


def test_cloud_run_routes_uvicorn_through_the_formatter(monkeypatch, restore_uvicorn_loggers):
    monkeypatch.setenv("K_SERVICE", "bharat-sourcer-integration")
    logging.getLogger("uvicorn.access").addHandler(logging.StreamHandler(io.StringIO()))
    configure_logging("synthetic-project")
    configure_logging("synthetic-project")  # idempotent
    server = logging.getLogger("uvicorn")
    assert len(server.handlers) == 1 and isinstance(server.handlers[0], StdoutHandler)
    assert logging.getLogger("uvicorn.error").propagate is True
    access = logging.getLogger("uvicorn.access")
    assert access.disabled is True and access.handlers == []


def test_local_logging_leaves_uvicorn_alone(monkeypatch, restore_uvicorn_loggers):
    monkeypatch.delenv("K_SERVICE", raising=False)
    access = logging.getLogger("uvicorn.access")
    access.disabled = False
    configure_logging(None)
    assert access.disabled is False


# -- events ----------------------------------------------------------------------------------
def test_log_event_message_keeps_the_tag_and_json(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    log_event("STAGE_FINISHED", job_id="j1", duration_ms=12)
    (entry,) = [r for r in caplog.records if getattr(r, "bs_event", None) == "STAGE_FINISHED"]
    assert entry.getMessage() == 'STAGE_FINISHED {"duration_ms": 12, "job_id": "j1"}'
    assert entry.bs_fields == {"job_id": "j1", "duration_ms": 12}


def call(handler, url=GEMINI, **kwargs):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return post_with_retry(client, url, json={}, **kwargs)


def test_gemini_call_logs_an_ok_call_with_tokens_and_cost(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    with attribute(JobLedger("job-1"), "L02"):
        call(lambda request: httpx.Response(200, json=ANSWER), site="discovery")
    (logged,) = event_fields(caplog, "GEMINI_CALL")
    assert logged["site"] == "discovery" and logged["model"] == "gemini-test"
    assert logged["route"] == "api_key" and logged["outcome"] == "ok"
    assert logged["http_status"] == 200 and logged["attempts"] == 1
    assert logged["tokens"] == 1100 and logged["usd_est"] > 0
    assert isinstance(logged["duration_ms"], int) and logged["duration_ms"] >= 0
    assert (logged["job_id"], logged["line_id"]) == ("job-1", "L02")


def test_gemini_call_outcomes(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    monkeypatch.setattr("bharat_sourcer.resilience.time.sleep", lambda _: None)
    call(lambda request: httpx.Response(429), site="judge")
    call(lambda request: httpx.Response(400), site="judge")
    incomplete = {"candidates": [{"finishReason": "MAX_TOKENS"}], "usageMetadata": {}}
    call(lambda request: httpx.Response(200, json=incomplete), site="judge")
    call(lambda request: httpx.Response(200, content=b"not json"), site="judge")

    def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)

    with pytest.raises(httpx.ReadTimeout):
        call(timeout, site="judge", attempts=2)
    call(lambda request: httpx.Response(200, json=ANSWER), url=VERTEX, site="overview_judge")
    logged = event_fields(caplog, "GEMINI_CALL")
    assert [(f["outcome"], f["attempts"]) for f in logged] == [
        ("quota", 3),
        ("error", 1),
        ("invalid", 1),
        ("invalid", 1),
        ("timeout", 2),
        ("ok", 1),
    ]
    assert logged[0]["tokens"] is None and logged[0]["usd_est"] is None
    assert logged[4]["http_status"] is None
    assert logged[5]["route"] == "vertex" and logged[5]["site"] == "overview_judge"


def test_gemini_call_is_json_with_the_request_trace(json_logs):
    with use_trace(Trace(TRACE_ID, "0000000000000003", None)):
        call(lambda request: httpx.Response(200, json=ANSWER), site="spec_fill")
    (entry,) = json_logs.entries("GEMINI_CALL")
    assert entry["message"].startswith("GEMINI_CALL {")
    assert entry["outcome"] == "ok" and entry["site"] == "spec_fill"
    assert entry[TRACE_KEY] == f"projects/synthetic-project/traces/{TRACE_ID}"
    assert entry[SPAN_KEY] == "0000000000000003"


def test_job_finished_carries_the_request_trace(json_logs):
    app = create_app(Settings(_env_file=None, demo_mode=True))
    header = {"X-Cloud-Trace-Context": f"{TRACE_ID}/7;o=1"}
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": "https://example.com/b"}, headers=header)
        job_id, token = created.json()["job_id"], created.json()["job_token"]
        headers = {"X-Job-Token": token, "traceparent": f"00-{W3C_TRACE}-00f067aa0ba902b7-01"}
        assert (
            client.post(f"/v1/jobs/{job_id}/confirm", headers=headers, json={}).status_code == 202
        )
        again = {"edits": [{"op": "remove", "line_id": "L03"}]}
        client.post(f"/v1/jobs/{job_id}/confirm", headers=headers, json=again)
    first, second = json_logs.entries("JOB_FINISHED")
    assert first["job_id"] == job_id and first["status"] == "done" and first["code"] is None
    assert first["demo"] is True and first["part_count"] == 3 and first["prior_finishes"] == 0
    assert isinstance(first["total_duration_ms"], int) and first["total_duration_ms"] >= 0
    # Confirm ran in a sync route and its background task: the request's traceparent.
    assert first[TRACE_KEY] == f"projects/synthetic-project/traces/{W3C_TRACE}"
    assert first[SPAN_KEY] == "00f067aa0ba902b7"
    assert second["part_count"] == 2 and second["prior_finishes"] == 1


class Extractor:
    def __init__(self, error=None):
        self.error = error

    def extract(self, url):
        if self.error:
            raise self.error
        return [BomItem(line_id="L01", raw_name="Synthetic sensor")]


def test_job_finished_logs_a_failed_extraction(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    error = ExtractionError("UPSTREAM_TIMEOUT", "Video extraction timed out")
    service = JobService(Extractor(error), "synthetic-model")
    job, _ = service.create(CreateJob(url="https://www.youtube.com/watch?v=abcdefghijk"))
    service.extract(job.job_id)
    (finished,) = event_fields(caplog, "JOB_FINISHED")
    assert finished["status"] == "failed" and finished["code"] == "UPSTREAM_TIMEOUT"
    assert finished["demo"] is False and finished["part_count"] == 0
    (stage,) = event_fields(caplog, "STAGE_FINISHED")
    assert (stage["stage"], stage["kind"], stage["outcome"]) == ("extraction", "video", "failed")
    assert stage["code"] == "UPSTREAM_TIMEOUT" and stage["job_id"] == job.job_id


def test_job_finished_is_not_logged_while_work_continues(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    service = JobService(Extractor(), "synthetic-model")
    job, token = service.create(CreateJob(url="https://www.youtube.com/watch?v=abcdefghijk"))
    service.extract(job.job_id)  # awaiting confirmation: not finished
    assert event_fields(caplog, "JOB_FINISHED") == []
    service.confirm(job.job_id, token, ConfirmJob())
    service.finish(job.job_id)
    service.finish(job.job_id)  # already done: nothing new
    assert [f["status"] for f in event_fields(caplog, "JOB_FINISHED")] == ["done"]


def test_stage_finished_for_an_attributed_extraction(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    with attribute(JobLedger("job-7")):
        extract_sources(Extractor(), ["https://www.instructables.com/Synthetic/"])
    (stage,) = event_fields(caplog, "STAGE_FINISHED")
    assert stage["job_id"] == "job-7" and stage["stage"] == "extraction"
    assert stage["outcome"] == "ok" and stage["kind"] != "video"
    assert isinstance(stage["duration_ms"], int)


class Fetcher:
    def __init__(self, status=200, body=b"<html>product</html>"):
        self.status, self.body = status, body

    def get(self, url, **kwargs):
        return Page(url, self.status, {}, self.body)


def test_seller_fetch_logs_the_host_never_the_url(caplog):
    caplog.set_level(logging.INFO, logger="bharat_sourcer")
    polite = Politeness(sleep=lambda _: None)
    url = "https://seller.example/item?q=private-query&token=abc"
    polite.get(Fetcher(), url)
    polite.get(Fetcher(), url)  # served from the page cache
    polite.get(Fetcher(404), "https://other.example/missing")
    challenge = b"<title>Just a moment...</title>"
    with pytest.raises(Exception, match="blocked"):
        polite.get(Fetcher(403, challenge), "https://guarded.example/p")
    with pytest.raises(Exception, match="blocked"):
        polite.get(Fetcher(), "https://guarded.example/q")
    logged = event_fields(caplog, "SELLER_FETCH")
    assert [(f["host"], f["outcome"]) for f in logged] == [
        ("seller.example", "ok"),
        ("seller.example", "cache"),
        ("other.example", "http_error"),
        ("guarded.example", "blocked"),
        ("guarded.example", "cooldown"),
    ]
    assert logged[0]["http_status"] == 200 and logged[0]["attempts"] == 1
    assert logged[0]["kind"] == "page" and isinstance(logged[0]["duration_ms"], int)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "private-query" not in text and "/item" not in text
