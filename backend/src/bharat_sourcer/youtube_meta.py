"""YouTube Data API v3 `videos.list` description intake (docs/contracts/multi-source-intake.md §8).

One `videos.list?part=snippet` call per video job (1 quota unit) returns the title, channel,
publish date and description. The description is handed to the video extraction prompt as
extra context; it is never stored. Only short server-checked quotes (at most 300
characters each) and the links found in it are kept on the job, with `fetched_at`.

YouTube API Services policy: stored API data must be refreshed or deleted after 30 days.
`apply_retention` drops description-derived data older than that from every response.

The API key is sent in the `x-goog-api-key` header, never in the URL, so it cannot appear
in httpx request logs, exception messages or any stored URL. Failures are logged by
category only and are never fatal to extraction.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import httpx

from bharat_sourcer.project_pages import project_page_source
from bharat_sourcer.schemas import Job, JobVideoMeta, VideoLink

log = logging.getLogger(__name__)

ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
TIMEOUT_S = 5.0
RETENTION = timedelta(days=30)
MAX_LINKS = 20
MAX_QUOTE = 300
DESCRIPTION_SOURCE = "youtube_description"
LINK = re.compile(r"https?://[^\s<>\"'(){}\[\]]+", re.IGNORECASE)
# Store and affiliate hosts: listed for display, never followed as project sources.
STORE_HOSTS = frozenset(
    {
        "amazon.in",
        "amazon.com",
        "amzn.to",
        "amzn.eu",
        "flipkart.com",
        "robu.in",
        "robocraze.com",
        "quartzcomponents.com",
        "evelta.com",
        "electronicscomp.com",
        "flyrobo.in",
        "sharvielectronics.com",
        "probots.co.in",
        "thingbits.in",
        "hubtronics.in",
        "ktron.in",
        "zbotic.in",
        "aliexpress.com",
        "banggood.com",
        "adafruit.com",
        "sparkfun.com",
        "digikey.com",
        "digikey.in",
        "mouser.com",
        "mouser.in",
        "lcsc.com",
        "pcbway.com",
        "jlcpcb.com",
    }
)


@dataclass(frozen=True)
class VideoMeta:
    """One video's snippet. `description` is held in memory only; it is never stored."""

    video_id: str
    title: str
    description: str
    channel: str
    published_at: datetime | None
    fetched_at: datetime
    links: list[str] = field(default_factory=list)


def video_id(url: str) -> str | None:
    """The 11-character id of a supported YouTube URL (watch, youtu.be, Shorts, embed)."""
    from bharat_sourcer.extraction import ExtractionError, youtube_url

    try:
        canonical = youtube_url(url)
    except ExtractionError:
        return None
    return parse_qs(urlsplit(canonical).query)["v"][0]


def description_links(text: str) -> list[str]:
    """Distinct http(s) links in a description, in order, at most MAX_LINKS."""
    links: list[str] = []
    for match in LINK.finditer(text):
        url = match.group(0).rstrip(".,;:!?*")
        if url not in links and len(url) <= 500:
            links.append(url)
        if len(links) == MAX_LINKS:
            break
    return links


def host_matches(host: str, hosts: frozenset[str]) -> bool:
    return any(host == known or host.endswith("." + known) for known in hosts)


def classify_link(url: str) -> tuple[Literal["project_source", "video", "store", "other"], str]:
    """Kind and canonical URL of one description link.

    Supported project pages (Instructables, Hackster, GitHub, Adafruit Learn, listed blogs)
    become extra sources; videos, stores, affiliate links and everything else are listed only.
    """
    from bharat_sourcer.extraction import ExtractionError, youtube_url

    source = project_page_source(url)
    if source is not None:
        return "project_source", source.url
    try:
        return "video", youtube_url(url)
    except ExtractionError:
        pass
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return "other", url
    return ("store" if host_matches(host, STORE_HOSTS) else "other"), url


def parse_time(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_description(
    video_id: str, api_key: str | None, client: httpx.Client | None = None
) -> VideoMeta | None:
    """Fetch one video's snippet; None when the key is unset or the call fails or is empty.

    At most one retry, on a timeout, network error or 5xx. Never raises.
    """
    if not api_key or not api_key.strip() or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return None
    params = {"part": "snippet", "id": video_id}
    headers = {"x-goog-api-key": api_key.strip(), "accept": "application/json"}
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)
    try:
        response = None
        for _attempt in range(2):
            try:
                response = client.get(ENDPOINT, params=params, headers=headers, timeout=TIMEOUT_S)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                log.warning("YouTube videos.list failed (%s)", type(exc).__name__)
                response = None
                continue
            if response.status_code < 500:
                break
            log.warning("YouTube videos.list returned HTTP %d", response.status_code)
        if response is None:
            return None
        if response.status_code != 200:
            if response.status_code < 500:  # 5xx responses were logged in the loop.
                log.warning("YouTube videos.list returned HTTP %d", response.status_code)
            return None
        data = response.json()
        items = data.get("items") or []
        if not items:
            log.info("YouTube videos.list returned no video")
            return None
        snippet = items[0].get("snippet") or {}
        description = str(snippet.get("description") or "")
        title = str(snippet.get("title") or "")
        if not description.strip() and not title.strip():
            return None
        return VideoMeta(
            video_id=video_id,
            title=title[:200],
            description=description[:10000],
            channel=str(snippet.get("channelTitle") or "")[:200],
            published_at=parse_time(snippet.get("publishedAt")),
            fetched_at=datetime.now(UTC),
            links=description_links(description),
        )
    except Exception as exc:  # Never fatal; never log the request (it carries the key).
        log.warning("YouTube videos.list failed (%s)", type(exc).__name__)
        return None
    finally:
        if owned:
            client.close()


def job_video_meta(meta: VideoMeta, followed: set[str]) -> JobVideoMeta:
    """The stored, policy-bounded record: no description, only links and metadata."""
    links = []
    for url in meta.links:
        kind, canonical = classify_link(url)
        links.append(
            VideoLink(
                url=canonical if kind == "project_source" else url,
                kind=kind,
                followed=kind == "project_source" and canonical in followed,
            )
        )
    return JobVideoMeta(
        video_id=meta.video_id,
        title=meta.title or None,
        channel=meta.channel or None,
        published_at=meta.published_at,
        fetched_at=meta.fetched_at,
        links=links,
    )


def expired(meta: JobVideoMeta | None, at: datetime | None = None) -> bool:
    return meta is not None and (at or datetime.now(UTC)) - meta.fetched_at > RETENTION


def apply_retention(job: Job, at: datetime | None = None) -> Job:
    """Drop YouTube API data older than 30 days from a job copy (mutates and returns it).

    Description quotes are removed from BOM evidence, and the stored title, channel,
    publish date and links are cleared; `video_meta.expired` becomes true. Jobs whose
    description quotes have no `video_meta` (none are written that way) are treated as
    expired too.
    """
    has_quotes = any(
        evidence.source == DESCRIPTION_SOURCE for item in job.items for evidence in item.evidence
    )
    if job.video_meta is None and not has_quotes:
        return job
    if job.video_meta is not None and not expired(job.video_meta, at):
        return job
    items = list(job.items) + ([line.item for line in job.report.lines] if job.report else [])
    for item in items:
        item.evidence = [e for e in item.evidence if e.source != DESCRIPTION_SOURCE]
        for conflict in item.conflicts:
            for value in conflict.values:
                if value.source == DESCRIPTION_SOURCE:
                    value.locator = None
    if job.video_meta is not None:
        job.video_meta = JobVideoMeta(
            video_id=job.video_meta.video_id, fetched_at=job.video_meta.fetched_at, expired=True
        )
    return job
