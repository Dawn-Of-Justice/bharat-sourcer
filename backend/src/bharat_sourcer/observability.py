"""Structured logs for Cloud Logging, request trace context and the app event helpers.

On Cloud Run (`K_SERVICE` set) or with `BS_LOG_FORMAT=json`, every line is one JSON object
in the shape Cloud Logging parses: `severity`, `message` (the event tag stays first, so
filters such as `jsonPayload.message:"QUEUE_AGE_EXCEEDED"` keep working), the request's
`logging.googleapis.com/trace` and `logging.googleapis.com/spanId`, and any structured
fields as top-level keys. Elsewhere lines stay plain text. `BS_LOG_FORMAT=text` forces plain
text on Cloud Run too.

The trace comes from the `X-Cloud-Trace-Context` (preferred, as Cloud Run's request log uses
it) or W3C `traceparent` request header and is carried in a context variable, so it follows
the request into sync routes, background tasks and thread pools started with
`contextvars.copy_context()`.

Secrets never reach a log line: bearer tokens, API keys, JWTs, cookie/token assignments and
email addresses are redacted and URL query strings are dropped, in both formats.

Event names and fields are the contract for log-based metrics: backend/infra/observability.md.
"""

import json
import logging
import os
import re
import sys
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

PLAIN_FORMAT = "%(levelname)s %(name)s %(message)s"
TRACE_KEY = "logging.googleapis.com/trace"
SPAN_KEY = "logging.googleapis.com/spanId"
SAMPLED_KEY = "logging.googleapis.com/trace_sampled"
# Keys the formatter owns; structured fields never overwrite them.
RESERVED = frozenset(
    {"severity", "message", "time", "logger", "event", TRACE_KEY, SPAN_KEY, SAMPLED_KEY}
)
SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}
# A leading UPPER_SNAKE tag such as QUEUE_AGE_EXCEEDED becomes the `event` field.
TAG = re.compile(r"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?=\s|$)")

events = logging.getLogger("bharat_sourcer.events")


# -- trace context ------------------------------------------------------------------------
@dataclass(frozen=True)
class Trace:
    trace_id: str  # 32 lowercase hex characters
    span_id: str | None = None  # 16 lowercase hex characters
    sampled: bool | None = None


_trace: ContextVar[Trace | None] = ContextVar("bs_trace", default=None)
# The GCP project for trace fields, set by configure_logging (create_app).
_settings: dict[str, str | None] = {"project": None}

CLOUD_TRACE = re.compile(r"([0-9a-fA-F]{32})(?:/(\d{1,20}))?(?:;o=([0-9]))?")
TRACEPARENT = re.compile(r"([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")
ZERO_TRACE, ZERO_SPAN = "0" * 32, "0" * 16


def parse_cloud_trace(value: str | None) -> Trace | None:
    """`TRACE_ID/SPAN_ID;o=1` (span id decimal); None unless well formed."""
    match = CLOUD_TRACE.fullmatch((value or "").strip())
    if match is None or match[1] == ZERO_TRACE:
        return None
    span = None
    if match[2] is not None and 0 < int(match[2]) < 2**64:
        span = f"{int(match[2]):016x}"
    sampled = None if match[3] is None else match[3] == "1"
    return Trace(match[1].lower(), span, sampled)


def parse_traceparent(value: str | None) -> Trace | None:
    """W3C `version-traceid-parentid-flags`; None unless well formed."""
    match = TRACEPARENT.fullmatch((value or "").strip().lower())
    if match is None or match[1] == "ff" or match[2] == ZERO_TRACE or match[3] == ZERO_SPAN:
        return None
    return Trace(match[2], match[3], bool(int(match[4], 16) & 1))


def trace_from_headers(headers: Mapping[str, str] | Iterable[tuple[str, str]]) -> Trace | None:
    """The trace from `X-Cloud-Trace-Context`, else `traceparent`; header names any case."""
    pairs = headers.items() if isinstance(headers, Mapping) else headers
    found = {name.lower(): value for name, value in pairs}
    return parse_cloud_trace(found.get("x-cloud-trace-context")) or parse_traceparent(
        found.get("traceparent")
    )


def current_trace() -> Trace | None:
    return _trace.get()


@contextmanager
def use_trace(trace: Trace | None) -> Iterator[None]:
    token = _trace.set(trace)
    try:
        yield
    finally:
        _trace.reset(token)


def scope_trace(scope) -> Trace | None:
    """The trace of an ASGI scope (header names and values are bytes)."""
    return trace_from_headers(
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in scope.get("headers") or []
    )


class TraceMiddleware:
    """Pure ASGI middleware: sets the request's trace for everything the request runs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with use_trace(scope_trace(scope)):
            await self.app(scope, receive, send)


# -- redaction ----------------------------------------------------------------------------
CREDENTIAL_NAMES = r"[\w-]*(?:token|secret|password|passwd|api[_-]?key|authorization|cookie)"
REDACTIONS = (
    # name=value / "name": "value" pairs whose name says they hold a credential.
    (
        re.compile(
            rf"(?i)\b({CREDENTIAL_NAMES})([\"']?\s*[:=]\s*[\"']?)(?:bearer\s+)?[^\s\"',;&]+"
        ),
        r"\1\2[redacted]",
    ),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{6,}"), r"\1 [redacted]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "[redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"), "[redacted]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "[email]"),
    # Keep scheme, host and path of a URL; drop its query string and fragment.
    (re.compile(r"(?i)\b((?:https?|wss?)://[^\s?#\"'<>]+)[?#][^\s\"'<>]*"), r"\1?[redacted]"),
)


def scrub(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def scrub_value(value):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, Mapping):
        return {str(key): scrub_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [scrub_value(item) for item in value]
    return value


# -- formatting ---------------------------------------------------------------------------
def json_enabled() -> bool:
    chosen = os.getenv("BS_LOG_FORMAT", "").strip().lower()
    if chosen == "json":
        return True
    if chosen in {"text", "plain"}:
        return False
    return bool(os.getenv("K_SERVICE"))


def set_project(project: str | None) -> None:
    """The GCP project named in trace fields (`projects/<project>/traces/<id>`)."""
    _settings["project"] = project or None


def trace_project() -> str | None:
    return (
        _settings["project"]
        or os.getenv("BS_GCP_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or None
    )


class StructuredFormatter(logging.Formatter):
    """JSON for Cloud Logging when `json_enabled()`, else `plain` text; both redacted."""

    def __init__(self, plain: str = PLAIN_FORMAT, *, json_mode: bool | None = None):
        super().__init__(plain)
        self.json_mode = json_mode

    def format(self, record: logging.LogRecord) -> str:
        use_json = json_enabled() if self.json_mode is None else self.json_mode
        return self.format_json(record) if use_json else scrub(super().format(record))

    def format_json(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        message = text
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            message += "\n" + self.formatStack(record.stack_info)
        entry: dict[str, object] = {
            "severity": SEVERITY.get(record.levelno, record.levelname),
            "message": scrub(message),
            "time": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "logger": record.name,
        }
        event = getattr(record, "bs_event", None)
        if event is None:
            tag = TAG.match(text)
            event = tag[1] if tag else None
        if event:
            entry["event"] = event
        extra = getattr(record, "bs_fields", None)
        if isinstance(extra, Mapping):
            for key, value in extra.items():
                if str(key) not in RESERVED:
                    entry[str(key)] = scrub_value(value)
        trace, project = current_trace(), trace_project()
        if trace is not None and project:
            entry[TRACE_KEY] = f"projects/{project}/traces/{trace.trace_id}"
            if trace.span_id:
                entry[SPAN_KEY] = trace.span_id
            if trace.sampled is not None:
                entry[SAMPLED_KEY] = trace.sampled
        return json.dumps(entry, default=str)


class StdoutHandler(logging.StreamHandler):
    """Resolve sys.stdout at write time (servers and test runners may replace it)."""

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value):
        pass


def stdout_handler(plain: str = PLAIN_FORMAT) -> logging.Handler:
    handler = StdoutHandler()
    handler.setFormatter(StructuredFormatter(plain))
    return handler


def configure_logging(project: str | None = None, level: str = "INFO") -> None:
    """Idempotent: route the app loggers (and uvicorn's on Cloud Run) through one formatter.

    The app handler is added only when nothing else (pytest, an embedding app) configured
    logging. In JSON mode uvicorn's error logger uses the same handler and its access log is
    off: Cloud Run's request log already records every request (and access lines would carry
    raw paths such as share tokens).
    """
    set_project(project)
    app_logger = logging.getLogger("bharat_sourcer")
    app_logger.setLevel(level.upper())
    for handler in list(app_logger.handlers):
        if isinstance(handler, StdoutHandler):
            app_logger.removeHandler(handler)
    if not app_logger.handlers and not logging.getLogger().handlers:
        app_logger.addHandler(stdout_handler())
    if not json_enabled():
        return
    server = logging.getLogger("uvicorn")
    server.handlers = [stdout_handler()]
    server.propagate = False
    error = logging.getLogger("uvicorn.error")
    error.handlers = []
    error.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


# -- events -------------------------------------------------------------------------------
def fields(**values) -> dict[str, dict]:
    """`extra=` for a plain log call whose values should also be top-level JSON keys."""
    return {"bs_fields": values}


def log_event(event: str, level: int = logging.INFO, /, **values) -> None:
    """Log `EVENT {json}`; in JSON mode the values are also top-level keys. Never raises."""
    try:
        events.log(
            level,
            "%s %s",
            event,
            json.dumps(values, sort_keys=True, default=str),
            extra={"bs_event": event, "bs_fields": values},
        )
    except Exception:  # Telemetry must never break a request
        events.debug("%s unavailable", event)


def elapsed_ms(started: float) -> int:
    """Milliseconds since a `time.perf_counter()` reading."""
    return max(0, round((time.perf_counter() - started) * 1000))


def attributed_job_id() -> str | None:
    """The job of the current Gemini cost attribution (usage.attribute), if any."""
    from bharat_sourcer.usage import current_ledger

    ledger = current_ledger()
    return ledger.job_id if ledger is not None else None


def stage_finished(
    stage: str, started: float, outcome: str, *, job_id: str | None = None, **values
) -> None:
    """Log STAGE_FINISHED for one pipeline stage timed from `started` (perf_counter)."""
    log_event(
        "STAGE_FINISHED",
        job_id=job_id or attributed_job_id(),
        stage=stage,
        duration_ms=elapsed_ms(started),
        outcome=outcome,
        **values,
    )
