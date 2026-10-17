"""Where a Gemini generateContent call goes: the Gemini API (API key) or Vertex AI.

Vertex AI serves the same models from the GCP project (billed there, authorised by the
service account's Application Default Credentials, no API key) on the `global` endpoint,
which spreads load across regions and answered when the API-key route was overloaded.
Sites listed in `BS_GEMINI_VERTEX_SITES` use Vertex when `BS_GCP_PROJECT` is set; every
other call keeps the API key. Callers fall back to the API key when Vertex refuses them
(no credentials, API disabled, missing `roles/aiplatform.user`).
"""

import logging
import threading

from bharat_sourcer.config import Settings

log = logging.getLogger(__name__)

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_lock = threading.Lock()
_credentials = None


class VertexUnavailable(Exception):
    """No usable Google credentials for Vertex AI on this machine."""


def uses_vertex(settings: Settings, site: str) -> bool:
    return bool(settings.gcp_project) and site in settings.gemini_vertex_sites


def vertex_url(settings: Settings, model: str) -> str:
    location = settings.vertex_location
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{settings.gcp_project}/locations/{location}"
        f"/publishers/google/models/{model}:generateContent"
    )


def vertex_token() -> str:
    """A fresh access token from Application Default Credentials (shared, thread-safe)."""
    global _credentials
    try:
        import google.auth
        from google.auth.transport.requests import Request

        with _lock:
            if _credentials is None:
                _credentials, _ = google.auth.default(scopes=[SCOPE])
            if not _credentials.valid:
                _credentials.refresh(Request())
            return str(_credentials.token)
    except Exception as exc:  # Missing ADC or a refresh failure: the caller uses the API key
        raise VertexUnavailable(type(exc).__name__) from exc


def endpoint(settings: Settings, site: str, model: str, *, vertex: bool | None = None):
    """(url, headers) for one call. `vertex=False` forces the API-key route."""
    if vertex is None:
        vertex = uses_vertex(settings, site)
    if vertex:
        return vertex_url(settings, model), {"Authorization": f"Bearer {vertex_token()}"}
    if settings.gemini_api_key is None:
        raise VertexUnavailable("no API key")
    return GEMINI_API.format(model=model), {
        "x-goog-api-key": settings.gemini_api_key.get_secret_value()
    }


FALLBACK_STATUS = {400, 401, 403, 404, 429, 500, 502, 503, 504}


def post_generate(client, settings: Settings, site: str, model: str, payload: dict, **kwargs):
    """POST a generateContent payload: Vertex AI first when enabled for `site`, then the
    API key. The API key is used when Vertex refuses (400/401/403/404, no credentials) and
    also when it stays overloaded (429/5xx after two tries) or times out, since the two
    run on separate capacity. Extra kwargs go to `post_with_retry` for the API-key call.
    Each route tried logs its own GEMINI_CALL line under `site` (usage.record_call)."""
    import httpx

    from bharat_sourcer.resilience import post_with_retry

    if uses_vertex(settings, site):
        try:
            url, headers = endpoint(settings, site, model)
            response = post_with_retry(
                client, url, headers=headers, json=payload, attempts=2, site=site
            )
            if response.status_code not in FALLBACK_STATUS:
                return response
            log.warning("GEMINI_VERTEX_FALLBACK site=%s http_status=%s", site, response.status_code)
        except (VertexUnavailable, httpx.TimeoutException, httpx.NetworkError) as exc:
            log.warning("GEMINI_VERTEX_FALLBACK site=%s reason=%s", site, type(exc).__name__)
    url, headers = endpoint(settings, site, model, vertex=False)
    return post_with_retry(client, url, headers=headers, json=payload, site=site, **kwargs)
