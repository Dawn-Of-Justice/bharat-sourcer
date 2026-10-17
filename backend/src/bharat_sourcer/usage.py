"""Structured Gemini token-usage logs, per-job cost attribution and the job budget guard.

Every `record_usage` call logs one `GEMINI_USAGE` line. When the call runs inside
`attribute(ledger, line_id)`, the line also names the job and BOM line and the call is added
to that job's ledger, which estimates USD from the dated price table in `config.py`.
Estimates are for budgeting only; they are not Google's bill.
"""

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from threading import RLock
from urllib.parse import urlsplit

from bharat_sourcer.config import (
    GEMINI_PRICES,
    GEMINI_PRICES_CHECKED,
    GEMINI_SEARCH_QUERY_USD,
)
from bharat_sourcer.observability import elapsed_ms, log_event, stdout_handler

log = logging.getLogger("bharat_sourcer.usage")

BUDGET_MESSAGE = (
    "Skipped paid search to stay within the job budget. Refresh this line to try again."
)

# Usage lines always reach stdout at INFO (which Cloud Run ships to Cloud Logging), whatever
# the rest of the logging setup: plain `GEMINI_USAGE {json}` locally, a structured JSON line
# with the same message on Cloud Run (observability.py).
if not log.handlers:
    log.addHandler(stdout_handler("%(message)s"))
    log.setLevel(logging.INFO)
    log.propagate = False


def prices_for(model: str, on: date | None = None) -> dict[str, float]:
    """Per-1M-token prices for a model on a date; unknown models use gemini-3.8-flash."""
    on = on or datetime.now(UTC).date()
    table = GEMINI_PRICES.get(model) or GEMINI_PRICES["gemini-3.8-flash"]
    current = table[0][1]
    for since, prices in table:
        if since <= on:
            current = prices
    return current


def estimate_usd(model: str, fields: dict, on: date | None = None) -> float:
    """Estimated USD for one call from its logged token and search-query counts."""
    prices = prices_for(model, on)
    prompt = int(fields.get("prompt") or 0) + int(fields.get("tool_prompt") or 0)
    cached = min(int(fields.get("cached") or 0), prompt)
    output = int(fields.get("output") or 0) + int(fields.get("thoughts") or 0)
    tokens = (
        (prompt - cached) * prices["input"] + cached * prices["cached"] + output * prices["output"]
    ) / 1_000_000
    return round(tokens + int(fields.get("search_queries") or 0) * GEMINI_SEARCH_QUERY_USD, 6)


class JobLedger:
    """Thread-safe running cost of one job. `run_usd` resets for each sourcing run."""

    def __init__(self, job_id: str, budget_usd: float | None = None, previous=None):
        self.job_id, self.budget_usd = job_id, budget_usd
        self.lock = RLock()
        self.total_usd = self.run_usd = 0.0
        self.calls, self.search_queries = 0, 0
        self.calls_by_site: dict[str, int] = {}
        self.usd_by_site: dict[str, float] = {}
        self.cache_hits: dict[str, int] = {}
        self.budget_reached = False
        if previous is not None:
            self.total_usd, self.run_usd = previous.total_usd, previous.run_usd
            self.calls, self.search_queries = previous.calls, previous.search_queries
            self.calls_by_site = dict(previous.calls_by_site)
            self.usd_by_site = dict(previous.usd_by_site)
            self.cache_hits = dict(previous.cache_hits)
            self.budget_reached = previous.budget_reached

    def add(self, site: str, usd: float, queries: int) -> None:
        with self.lock:
            self.calls += 1
            self.search_queries += queries
            self.total_usd = round(self.total_usd + usd, 6)
            self.run_usd = round(self.run_usd + usd, 6)
            self.calls_by_site[site] = self.calls_by_site.get(site, 0) + 1
            self.usd_by_site[site] = round(self.usd_by_site.get(site, 0.0) + usd, 6)

    def hit(self, namespace: str) -> None:
        with self.lock:
            self.cache_hits[namespace] = self.cache_hits.get(namespace, 0) + 1

    def exhausted(self) -> bool:
        with self.lock:
            if self.budget_usd is not None and self.run_usd >= self.budget_usd:
                self.budget_reached = True
            return self.budget_reached and self.budget_usd is not None

    def snapshot(self):
        from bharat_sourcer.schemas import CostEstimate

        with self.lock:
            return CostEstimate(
                total_usd=self.total_usd,
                run_usd=self.run_usd,
                budget_usd=self.budget_usd,
                budget_reached=self.budget_reached,
                calls=self.calls,
                search_queries=self.search_queries,
                calls_by_site=dict(self.calls_by_site),
                usd_by_site=dict(self.usd_by_site),
                cache_hits=dict(self.cache_hits),
                prices_checked=GEMINI_PRICES_CHECKED,
            )


_current: ContextVar[tuple[JobLedger | None, str | None]] = ContextVar(
    "gemini_attribution", default=(None, None)
)


@contextmanager
def attribute(ledger: JobLedger | None, line_id: str | None = None) -> Iterator[None]:
    """Attribute Gemini calls and cache hits in this context (and thread) to a job line.

    Context variables do not cross thread pools: enter this inside the worker function.
    """
    token = _current.set((ledger, line_id))
    try:
        yield
    finally:
        _current.reset(token)


def current_ledger() -> JobLedger | None:
    return _current.get()[0]


def paid_allowed() -> bool:
    """False once the attributed job's run reached its budget; call before a paid stage."""
    ledger = current_ledger()
    return ledger is None or not ledger.exhausted()


def record_cache_hit(namespace: str) -> None:
    """Count a shared-cache hit for the attributed job and log it; never raises."""
    try:
        ledger, line_id = _current.get()
        if ledger is not None:
            ledger.hit(namespace)
        values = {"namespace": namespace, "job_id": ledger.job_id if ledger else None}
        values["line_id"] = line_id
        log.info(
            "GEMINI_CACHE_HIT %s",
            json.dumps(values, sort_keys=True),
            extra={"bs_event": "GEMINI_CACHE_HIT", "bs_fields": values},
        )
    except Exception:  # Metering must never break a request
        log.debug("GEMINI_CACHE_HIT unavailable for %s", namespace)


def usage_fields(site: str, model: str, data: object, queries: int | None = None) -> dict:
    """Token, grounding and estimated-USD fields of one generateContent response."""
    meta = data.get("usageMetadata") or {} if isinstance(data, dict) else {}
    candidates = data.get("candidates") or [] if isinstance(data, dict) else []
    grounding = [c.get("groundingMetadata") or {} for c in candidates if isinstance(c, dict)]
    grounded = any(g.get("groundingChunks") for g in grounding)
    # Gemini 3 bills grounding per executed search query, so count them.
    if queries is None:
        queries = sum(len(g.get("webSearchQueries") or []) for g in grounding)
    values = {
        "site": site,
        "model": model,
        "prompt": meta.get("promptTokenCount", 0),
        "output": meta.get("candidatesTokenCount", 0),
        "thoughts": meta.get("thoughtsTokenCount", 0),
        "cached": meta.get("cachedContentTokenCount", 0),
        "tool_prompt": meta.get("toolUsePromptTokenCount", 0),
        "total": meta.get("totalTokenCount", 0),
        "grounded": grounded,
        "search_queries": queries,
        "by_modality": {
            d.get("modality", "?"): d.get("tokenCount", 0)
            for d in meta.get("promptTokensDetails") or []
            if isinstance(d, dict)
        },
    }
    values["usd_est"] = estimate_usd(model, values)
    return values


def record_usage(site: str, model: str, data: object, queries: int | None = None) -> None:
    """Log one GEMINI_USAGE line from a generateContent response; never raises.

    `queries` overrides the counted search queries, for tools (Google Maps grounding) whose
    executed queries are not listed in `webSearchQueries`.
    """
    try:
        values = usage_fields(site, model, data, queries)
        ledger, line_id = _current.get()
        values["job_id"] = ledger.job_id if ledger else None
        values["line_id"] = line_id
        if ledger is not None:
            ledger.add(site, values["usd_est"], values["search_queries"])
        log.info(
            "GEMINI_USAGE %s",
            json.dumps(values, sort_keys=True),
            extra={"bs_event": "GEMINI_USAGE", "bs_fields": values},
        )
    except Exception:  # Metering must never break a request
        log.debug("GEMINI_USAGE unavailable for %s", site)


# The model in a generateContent URL (Gemini API and Vertex AI paths alike).
URL_MODEL = re.compile(r"/models/([^/:]+):generateContent$")


def call_route(url: str) -> tuple[str, str]:
    """(route, model) of a generateContent URL; route is `vertex`, `api_key` or `other`."""
    parts = urlsplit(str(url))
    host = (parts.hostname or "").lower()
    if host.endswith("aiplatform.googleapis.com"):
        route = "vertex"
    elif host == "generativelanguage.googleapis.com":
        route = "api_key"
    else:
        route = "other"
    match = URL_MODEL.search(parts.path)
    return route, match[1] if match else "unknown"


def call_outcome(response, error: BaseException | None) -> tuple[str, dict | None]:
    """(outcome, parsed body of a 2xx answer) for one finished call."""
    import httpx

    if error is not None:
        return ("timeout" if isinstance(error, httpx.TimeoutException) else "error"), None
    if response.status_code == 429:
        return "quota", None
    if response.status_code >= 400:
        return "error", None
    try:
        data = response.json()
    except ValueError:
        return "invalid", None
    if not isinstance(data, dict):
        return "invalid", None
    candidates = data.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else None
    if not isinstance(candidate, dict):
        return "invalid", data
    # Sites accept only a complete answer; a model that stopped early is an invalid call.
    return ("ok" if candidate.get("finishReason") in {"STOP", None} else "invalid"), data


def record_call(
    site: str | None,
    url: str,
    started: float,
    attempts: int,
    *,
    response=None,
    error: BaseException | None = None,
) -> None:
    """Log one GEMINI_CALL line for a finished generateContent call; never raises.

    One line per routed call (`resilience.post_with_retry`), its retries on the same route
    included; a Vertex-to-API-key fallback logs one line per route. Unlike GEMINI_USAGE it is
    also logged for timeouts, quota and HTTP errors, so latency and outcome share one event.
    `usd_est` here counts tokens and web-search queries only; GEMINI_USAGE stays the cost record.
    """
    try:
        route, model = call_route(url)
        outcome, data = call_outcome(response, error)
        values = None
        if data is not None:
            try:
                values = usage_fields(site or "unknown", model, data)
            except Exception:  # Malformed usage metadata: log the call without tokens
                values = None
        ledger, line_id = _current.get()
        log_event(
            "GEMINI_CALL",
            site=site or "unknown",
            model=model,
            route=route,
            duration_ms=elapsed_ms(started),
            outcome=outcome,
            http_status=response.status_code if response is not None else None,
            attempts=attempts,
            tokens=values["total"] if values else None,
            usd_est=values["usd_est"] if values else None,
            job_id=ledger.job_id if ledger else None,
            line_id=line_id,
        )
    except Exception:  # Telemetry must never break a request
        log.debug("GEMINI_CALL unavailable for %s", site)
