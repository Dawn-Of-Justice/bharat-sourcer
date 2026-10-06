"""Bounded retries for Gemini generation requests; may repeat billable work."""

import logging
import random
import time

import httpx


def post_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    for attempt in range(3):
        response = None
        try:
            response = client.post(url, **kwargs)
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                return response
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise
        delay = 2**attempt + random.uniform(0, 0.5)
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
        logging.getLogger(__name__).warning("Retrying Gemini request, attempt %d of 3", attempt + 2)
        time.sleep(delay)
    raise RuntimeError("Retry budget exhausted")
