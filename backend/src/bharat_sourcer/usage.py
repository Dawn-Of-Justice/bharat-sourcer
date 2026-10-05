"""Structured Gemini token-usage logs so cost per call site can be measured, not guessed."""

import json
import logging
import sys

log = logging.getLogger("bharat_sourcer.usage")


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
        log.info("GEMINI_USAGE %s", json.dumps(fields, sort_keys=True))
    except Exception:  # noqa: BLE001 - metering must never break a request
        log.debug("GEMINI_USAGE unavailable for %s", site)
