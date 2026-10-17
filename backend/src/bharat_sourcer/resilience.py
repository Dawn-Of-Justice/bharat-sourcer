"""Bounded retries for Gemini generation requests; may repeat billable work."""

import logging
import random
import time
from collections.abc import Callable

import httpx

from bharat_sourcer.usage import record_call


def post_with_retry(
    client: httpx.Client, url: str, *, attempts: int = 3, site: str | None = None, **kwargs
) -> httpx.Response:
    """POST with bounded retries. Logs one GEMINI_CALL line (usage.record_call) for the whole
    call, retries included; `site` names the call site in it."""
    started = time.perf_counter()
    tried = 0

    def post() -> httpx.Response:
        nonlocal tried
        tried += 1
        return client.post(url, **kwargs)

    try:
        response = _retry(post, attempts)
    except Exception as exc:
        record_call(site, url, started, tried, error=exc)
        raise
    record_call(site, url, started, tried, response=response)
    return response


def _retry(post: Callable[[], httpx.Response], attempts: int) -> httpx.Response:
    last = attempts - 1
    for attempt in range(attempts):
        response = None
        try:
            response = post()
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == last:
                return response
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == last:
                raise
        delay = 2**attempt + random.uniform(0, 0.5)  # noqa: S311 - retry jitter, not crypto
        if response is not None:
            # Honor numeric Retry-After up to our wait budget; longer delays stop retries.
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    requested = float(retry_after)
                except ValueError:
                    return response
                if not 0 <= requested <= 10:
                    return response
                delay = max(delay, requested)
        logging.getLogger(__name__).warning(
            "Retrying Gemini request, attempt %d of %d", attempt + 2, attempts
        )
        time.sleep(delay)
    raise RuntimeError("Retry budget exhausted")
