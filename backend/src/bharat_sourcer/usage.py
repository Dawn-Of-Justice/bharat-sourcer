"""Structured Gemini token-usage logs, per-job cost attribution and the job budget guard.

Every `record_usage` call logs one `GEMINI_USAGE` line. When the call runs inside
`attribute(ledger, line_id)`, the line also names the job and BOM line and the call is added
to that job's ledger, which estimates USD from the dated price table in `config.py`.
Estimates are for budgeting only; they are not Google's bill.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from threading import RLock

from bharat_sourcer.config import (
    GEMINI_PRICES,
    GEMINI_PRICES_CHECKED,
    GEMINI_SEARCH_QUERY_USD,
)

log = logging.getLogger("bharat_sourcer.usage")

BUDGET_MESSAGE = (
    "Skipped paid search to stay within the job budget. Refresh this line to try again."
)


class _Stdout(logging.StreamHandler):
    """Resolve sys.stdout at write time (servers and test runners may replace it)."""

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value):
        pass


# The app has no logging config, so INFO would be dropped by the root logger's WARNING
# default. Usage lines go to stdout, which Cloud Run ships to Cloud Logging.
if not log.handlers:
    _handler = _Stdout()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_handler)
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
        fields = {"namespace": namespace, "job_id": ledger.job_id if ledger else None}
        fields["line_id"] = line_id
        log.info("GEMINI_CACHE_HIT %s", json.dumps(fields, sort_keys=True))
    except Exception:  # noqa: BLE001 - metering must never break a request
        log.debug("GEMINI_CACHE_HIT unavailable for %s", namespace)


def record_usage(site: str, model: str, data: object) -> None:
    """Log one GEMINI_USAGE line from a generateContent response; never raises."""
    try:
        meta = data.get("usageMetadata") or {} if isinstance(data, dict) else {}
        candidates = data.get("candidates") or [] if isinstance(data, dict) else []
        grounding = [c.get("groundingMetadata") or {} for c in candidates if isinstance(c, dict)]
        grounded = any(g.get("groundingChunks") for g in grounding)
        # Gemini 3 bills grounding per executed search query, so count them.
        queries = sum(len(g.get("webSearchQueries") or []) for g in grounding)
        fields = {
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
        fields["usd_est"] = estimate_usd(model, fields)
        ledger, line_id = _current.get()
        fields["job_id"] = ledger.job_id if ledger else None
        fields["line_id"] = line_id
        if ledger is not None:
            ledger.add(site, fields["usd_est"], queries)
        log.info("GEMINI_USAGE %s", json.dumps(fields, sort_keys=True))
    except Exception:  # noqa: BLE001 - metering must never break a request
        log.debug("GEMINI_USAGE unavailable for %s", site)
