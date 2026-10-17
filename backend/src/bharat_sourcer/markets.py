"""Nearby electronics markets via Gemini grounding with Google Maps (roadmap S2).

One Gemini call with the `googleMaps` tool per (rounded location, part-category set),
shared through the cross-job cache for 7 days. The prompt carries only a short list of
part categories from the BOM, never project text. Places come from the grounding chunks,
not from the generated text; review chunks are kept only as attribution links.

Google Maps grounding terms: the sources must immediately follow the generated content,
stay viewable within one user interaction, and the text "Google Maps" must not be
modified. `MarketsResult.attribution` returns the exact source list, in order, for that.
The results describe shops, not stock: nothing here confirms a part is available.
"""

import hashlib
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from fastapi import Query

from bharat_sourcer.access import ProjectAccess
from bharat_sourcer.config import Settings, site_generation, site_model
from bharat_sourcer.countries import Country, country
from bharat_sourcer.jobs import JobError
from bharat_sourcer.resilience import post_with_retry
from bharat_sourcer.schemas import ErrorResponse, Job, Model
from bharat_sourcer.sourcing.cache import MemoryCache, SharedCache, cache_key
from bharat_sourcer.usage import JobLedger, attribute, paid_allowed, record_usage

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/"
SUMMARY_LABEL = "Shops likely to carry these parts — call first; stock is not confirmed"
PROVIDER = "Google Maps"
ATTRIBUTION_RULES = (
    "Show these Google Maps sources immediately after the summary, viewable within one "
    'interaction; link each title to its URI and do not modify the text "Google Maps".'
)
MAX_PLACES = 10
MAX_SOURCES = 20

CATEGORY_LABELS = {
    "resistor": "resistors",
    "capacitor_electrolytic": "capacitors",
    "capacitor_ceramic": "capacitors",
    "led": "LEDs",
    "ldr": "sensors",
    "wire": "wires",
    "diode": "diodes",
    "transistor": "transistors",
    "ic": "ICs",
    "module": "modules",
    "board": "development boards",
    "sensor": "sensors",
    "connector": "connectors",
    "switch": "switches",
    "battery": "batteries",
}
# Name keywords for lines without an AI or user category (seed specs are "other").
KEYWORDS = [
    (re.compile(r"(?i)resist|\bohm|Ω"), "resistors"),
    (re.compile(r"(?i)capacit|\d\s*[uµnp]f\b"), "capacitors"),
    (re.compile(r"(?i)\bleds?\b"), "LEDs"),
    (re.compile(r"(?i)sensor|\bldr\b|\bbme\d|\bdht\d|thermistor"), "sensors"),
    (re.compile(r"(?i)arduino|esp32|esp8266|raspberry|\bboard\b|nodemcu"), "development boards"),
    (re.compile(r"(?i)\bmodule\b"), "modules"),
    (re.compile(r"(?i)\bwires?\b|jumper|cable"), "wires"),
    (re.compile(r"(?i)batter|\bcell\b|18650|li-?po"), "batteries"),
    (re.compile(r"(?i)switch|button"), "switches"),
    (re.compile(r"(?i)connector|header|terminal"), "connectors"),
    (re.compile(r"(?i)transistor|mosfet"), "transistors"),
    (re.compile(r"(?i)diode"), "diodes"),
    (re.compile(r"(?i)motor|servo"), "motors"),
    (re.compile(r"(?i)\blcd\b|oled|display"), "displays"),
]
MAX_CATEGORIES = 6
ADDRESS = re.compile(r"\*\*Address:\*\*\s*([^\n]+)")


# Public response models.


class MarketLocation(Model):
    source: Literal["city", "coordinates"]
    city: str | None = None
    # Rounded to 2 decimals (about 1 km); this is what is sent to Gemini and cached.
    latitude: float
    longitude: float
    approximate: bool
    label: str


class MarketPlace(Model):
    title: str
    uri: str | None = None
    address: str | None = None
    place_id: str | None = None


class MapsSource(Model):
    title: str
    uri: str
    kind: Literal["place", "review", "web"]


class MarketsAttribution(Model):
    provider: Literal["Google Maps"] = PROVIDER
    sources: list[MapsSource]
    rules: str = ATTRIBUTION_RULES


class MarketsResult(Model):
    demo: bool
    location: MarketLocation
    categories: list[str]
    summary: str | None = None
    summary_label: str = SUMMARY_LABEL
    places: list[MarketPlace]
    attribution: MarketsAttribution
    cached: bool
    model: str | None = None
    label: str


# Deterministic helpers.


def resolve_location(
    where: Country, city: str | None, lat: float | None, lng: float | None
) -> MarketLocation:
    """A market city (approximate centre) or coordinates inside the job's country, rounded
    to 2 decimals."""
    if city is not None and (lat is not None or lng is not None):
        raise JobError(422, "INVALID_LOCATION", "Send either city or lat and lng, not both")
    if city is not None:
        found = where.city(city)
        if found is None:
            raise JobError(
                422,
                "CITY_NOT_SUPPORTED",
                f"Choose a city from GET /v1/countries for {where.name}, or share your "
                "location (lat and lng) instead",
            )
        return MarketLocation(
            source="city",
            city=found.name,
            latitude=found.latitude,
            longitude=found.longitude,
            approximate=True,
            label=f"Approximate: the centre of {found.name}.",
        )
    if lat is None or lng is None:
        raise JobError(422, "INVALID_LOCATION", "Send city, or both lat and lng")
    if not where.contains(lat, lng):
        raise JobError(422, "LOCATION_OUTSIDE_COUNTRY", f"Nearby markets cover {where.name} only")
    return MarketLocation(
        source="coordinates",
        latitude=round(lat, 2),
        longitude=round(lng, 2),
        approximate=True,
        label="Your location, rounded to about 1 km.",
    )


def part_categories(job: Job) -> list[str]:
    """Short category list from the BOM (lines still to buy); no names or project text."""
    found: list[str] = []
    for item in job.items:
        if item.user_has_it:
            continue
        spec = item.buyable_spec
        label = CATEGORY_LABELS.get(spec.category) if spec else None
        if label is None:
            label = next(
                (name for pattern, name in KEYWORDS if pattern.search(item.raw_name)), None
            )
        if label and label not in found:
            found.append(label)
    return found[:MAX_CATEGORIES] or ["electronic components"]


def prompt_for(categories: list[str]) -> str:
    return (
        "List up to 5 electronics component markets or shops near this location where a "
        f"hobby maker can buy {', '.join(categories)} today. One line each with the shop or "
        "market name and the area name. Do not claim that any shop has a part in stock."
    )


def _https(uri: object) -> str | None:
    if isinstance(uri, str) and uri.startswith(("https://", "http://")) and len(uri) <= 2000:
        return uri
    return None


def _review(uri: str, title: str) -> bool:
    return "/maps/reviews/" in uri or title.startswith("Review of")


def parse_grounding(candidate: dict) -> tuple[list[MarketPlace], list[MapsSource]]:
    """Places and the ordered source list from `groundingMetadata.groundingChunks`."""
    chunks = (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []
    places: list[MarketPlace] = []
    sources: list[MapsSource] = []
    seen_sources, seen_places = set(), set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        maps, web = chunk.get("maps"), chunk.get("web")
        entry = maps if isinstance(maps, dict) else web if isinstance(web, dict) else None
        uri = _https(entry.get("uri")) if entry else None
        title = str(entry.get("title") or "").strip()[:300] if entry else ""
        if not uri or not title:
            continue
        kind = "web" if entry is web else "review" if _review(uri, title) else "place"
        if uri in seen_sources:
            continue
        seen_sources.add(uri)
        if len(sources) < MAX_SOURCES:
            sources.append(MapsSource(title=title, uri=uri, kind=kind))
        if kind != "place":
            continue
        name = title.removesuffix(" - Google Maps").strip() or title
        if name.casefold() in seen_places or len(places) >= MAX_PLACES:
            continue
        seen_places.add(name.casefold())
        address = ADDRESS.search(str(maps.get("text") or ""))
        place_id = maps.get("placeId")
        places.append(
            MarketPlace(
                title=name,
                uri=uri,
                address=address.group(1).strip()[:300] if address else None,
                place_id=place_id[:200] if isinstance(place_id, str) and place_id else None,
            )
        )
    return places, sources


def grounding_queries(candidate: dict) -> int:
    """Executed grounding queries; a Maps-grounded answer counts at least one."""
    meta = candidate.get("groundingMetadata") or {}
    listed = len(meta.get("webSearchQueries") or []) + len(meta.get("retrievalQueries") or [])
    return max(listed, 1) if meta.get("groundingChunks") else listed


def nearby_markets(
    location: MarketLocation,
    categories: list[str],
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
) -> MarketsResult:
    """One Maps-grounded Gemini call; raises JobError on upstream failure."""
    model = site_model(settings, "markets")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_for(categories)}]}],
        "tools": [{"googleMaps": {}}],
        "toolConfig": {
            "retrievalConfig": {
                "latLng": {"latitude": location.latitude, "longitude": location.longitude}
            }
        },
        "generationConfig": {"maxOutputTokens": 2048, **site_generation(settings, "markets")},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(45, connect=10), transport=transport) as client:
            response = post_with_retry(
                client,
                API + f"{model}:generateContent",
                site="markets",
                headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise JobError(504, "UPSTREAM_TIMEOUT", "Gemini timed out; try again") from exc
    except httpx.HTTPError as exc:
        raise JobError(502, "UPSTREAM_ERROR", "Gemini connection failed") from exc
    if response.status_code == 429:
        raise JobError(503, "UPSTREAM_QUOTA", "Gemini quota exceeded; try again later")
    if response.is_error:
        log.warning("MARKETS_FAILED http_status=%s", response.status_code)
        raise JobError(502, "UPSTREAM_ERROR", "Gemini could not process this request")
    try:
        data = response.json()
        candidate = data["candidates"][0]
        queries = grounding_queries(candidate)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise JobError(502, "INVALID_OUTPUT", "Gemini returned an incomplete answer") from exc
    record_usage("markets", model, data, queries=queries)
    try:
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete output")
        text = "".join(
            p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought", False)
        ).strip()
        places, sources = parse_grounding(candidate)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise JobError(502, "INVALID_OUTPUT", "Gemini returned an incomplete answer") from exc
    # Ungrounded text could name shops that do not exist: show it only with Maps sources.
    summary = text[:4000] if sources and text else None
    return MarketsResult(
        demo=False,
        location=location,
        categories=categories,
        summary=summary,
        places=places,
        attribution=MarketsAttribution(sources=sources),
        cached=False,
        model=model,
        label="AI summary grounded in Google Maps"
        if summary
        else "No Google Maps results were found near this location.",
    )


def demo_result(location: MarketLocation, categories: list[str]) -> MarketsResult:
    return MarketsResult(
        demo=True,
        location=location,
        categories=categories,
        summary="Demo sample: Sample Electronics Market (demo) — a fictional shop for "
        "testing the card. No map lookup was made.",
        places=[
            MarketPlace(title="Sample Electronics Market (demo)", address="Demo address, not real"),
            MarketPlace(title="Sample Component Shop (demo)", address="Demo address, not real"),
        ],
        attribution=MarketsAttribution(sources=[]),
        cached=False,
        label="Demo sample; fictional shops, no Google Maps lookup was made.",
    )


class MarketsService:
    def __init__(
        self,
        settings: Settings,
        jobs,
        cache: SharedCache | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings, self.jobs, self.transport = settings, jobs, transport
        self.cache = cache if cache is not None else MemoryCache(256)

    def _keys(self, job_id: str) -> dict[str, int]:
        record = self.jobs.store.get(job_id)
        scope = (record.owner_id if record else None) or job_id
        day = datetime.now(UTC).strftime("%Y%m%d")
        owner = hashlib.sha256(scope.encode()).hexdigest()
        return {
            f"markets-global-{day}": self.settings.markets_global_daily_limit,
            f"markets-owner-{day}-{owner}": self.settings.markets_daily_limit,
        }

    def _charge(self, job_id: str) -> None:
        if not self.jobs.store.consume(self._keys(job_id)):
            midnight = (datetime.now(UTC) + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            raise JobError(
                429,
                "FEATURE_QUOTA",
                "Daily limit for nearby markets reached; try again tomorrow",
                retry_after=max(1, int(midnight.timestamp() - time.time())),
            )

    @staticmethod
    def cache_key(location: MarketLocation, categories: list[str]) -> str:
        return cache_key(
            "markets", f"{location.latitude:.2f}", f"{location.longitude:.2f}", sorted(categories)
        )

    def lookup(
        self, job_id: str, token, city: str | None, lat: float | None, lng: float | None
    ) -> MarketsResult:
        job = self.jobs.get(job_id, token)
        if not self.settings.markets_enabled:
            raise JobError(503, "FEATURE_DISABLED", "This feature is not enabled")
        location = resolve_location(country(job.input.country), city, lat, lng)
        if not job.items:
            raise JobError(409, "NOTHING_TO_SOURCE", "Wait until the parts list is ready")
        categories = part_categories(job)
        if job.demo:
            return demo_result(location, categories)
        if self.settings.gemini_api_key is None:
            raise JobError(503, "FEATURE_UNAVAILABLE", "This feature is unavailable right now")
        key = self.cache_key(location, categories)
        start = job.cost_estimate
        ledger = JobLedger(job_id, self.settings.job_gemini_budget_usd, previous=start)
        with attribute(ledger):
            cached = self.cache.get(key)
            if isinstance(cached, dict):
                try:
                    return MarketsResult.model_validate(
                        cached
                        | {
                            "demo": False,
                            "location": location.model_dump(),
                            "categories": categories,
                            "cached": True,
                        }
                    )
                except ValueError:
                    pass
            if not paid_allowed():
                raise JobError(
                    409,
                    "JOB_BUDGET_REACHED",
                    "This project's AI budget for the current run is used up",
                )
            self._charge(job_id)
            result = nearby_markets(location, categories, self.settings, self.transport)
        # Shared across jobs and owners: places, summary and attribution only.
        self.cache.set(
            key,
            result.model_dump(
                mode="json", include={"summary", "places", "attribution", "model", "label"}
            ),
            self.settings.markets_cache_ttl_s,
        )
        self._save_cost(job_id, start, ledger)
        return result

    def _save_cost(self, job_id: str, start, ledger: JobLedger) -> None:
        def save(record):
            # Skip if a sourcing run wrote a newer estimate meanwhile; it owns the ledger.
            if record.job.cost_estimate == start:
                record.job.cost_estimate = ledger.snapshot()

        try:
            self.jobs.store.mutate(job_id, save)
        except Exception:  # Accounting must never fail the lookup
            log.warning("MARKETS_COST_NOT_SAVED job_id=%s", job_id, exc_info=True)


def add_markets_routes(app, markets: MarketsService) -> None:
    errors = {
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    }

    @app.get(
        "/v1/jobs/{job_id}/markets",
        response_model=MarketsResult,
        tags=["markets"],
        responses=errors,
    )
    def nearby(
        job_id: str,
        city: str | None = Query(default=None, max_length=80),
        lat: float | None = None,
        lng: float | None = None,
        x_job_token: ProjectAccess = None,
    ):
        return markets.lookup(job_id, x_job_token, city, lat, lng)
