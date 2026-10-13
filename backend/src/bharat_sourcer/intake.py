"""Multi-source intake: validate a job's sources, extract each one, fuse one BOM.

The primary URL and up to three extra `sources` are extracted in parallel with the existing
extractor (one model call per source; GitHub code hints add none). A failing extra source
is reported and skipped; the job fails only when no source yields parts.

When a source is a YouTube video and BS_YOUTUBE_API_KEY is set, the extractor
also reads the video's description (youtube_meta.py) inside the same video call. Links in
the description to supported project pages are added as extra sources (within the limit
of three extras and the usual dedupe), and the description gets its own source report.
"""

import contextvars
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from urllib.parse import urlsplit

from bharat_sourcer.extraction import (
    ExtractionError,
    ExtractionResult,
    Extractor,
    supported_source,
)
from bharat_sourcer.fusion import fuse
from bharat_sourcer.schemas import ErrorDetail, JobVideoMeta, SourceReport
from bharat_sourcer.youtube_meta import DESCRIPTION_SOURCE, description_page_source

MAX_EXTRA_SOURCES = 3

# progress(key, status, label, detail): live steps for the job page (jobs.py stores them).
Progress = Callable[[str, str, str | None, str | None], None]


def _no_progress(key: str, status: str, label: str | None, detail: str | None) -> None:
    return None


def source_label(kind: str, canonical: str) -> str:
    if kind == "video":
        return "Reading the video"
    if report_kind(kind, canonical) == "github":
        return "Reading the GitHub repository"
    host = urlsplit(canonical).hostname or "a project page"
    return f"Reading {host.removeprefix('www.')}"


def found(result) -> str:
    items = result if isinstance(result, list) else [*result.items, *result.code_items]
    return f"{len(items)} {'part' if len(items) == 1 else 'parts'} found"


log = logging.getLogger(__name__)


def validate_sources(urls: list[str]) -> list[tuple[str, str, str]]:
    """(kind, canonical URL, submitted URL) per distinct source, primary first.

    Sources with the same canonical URL as an earlier one are dropped.
    """
    result: list[tuple[str, str, str]] = []
    for url in urls:
        kind, canonical = supported_source(url)
        if all(canonical != seen for _, seen, _ in result):
            result.append((kind, canonical, url))
    if sum(kind == "video" for kind, _, _ in result) > 1:
        raise ExtractionError("UNSUPPORTED_SOURCES", "Add at most one video per project")
    return result


def report_kind(kind: str, canonical: str) -> str:
    return "video" if kind == "video" else description_page_source(canonical).kind


class IntakeResult(ExtractionResult):
    sources: list[SourceReport]


def description_report(canonical: str, result: ExtractionResult) -> SourceReport | None:
    if result.description_failed:
        return SourceReport(
            url=canonical,
            kind=DESCRIPTION_SOURCE,
            role="additional",
            status="failed",
            error=ErrorDetail(
                code="DESCRIPTION_UNAVAILABLE",
                message="The video description could not be read; the video was still used",
            ),
        )
    if result.video_meta is None:
        return None
    count = sum(
        any(evidence.source == DESCRIPTION_SOURCE for evidence in item.evidence)
        for item in result.items
    )
    return SourceReport(
        url=canonical, kind=DESCRIPTION_SOURCE, role="additional", status="read", item_count=count
    )


def add_description_links(
    sources: list[tuple[str, str, str]], meta: JobVideoMeta, linked: set[str]
) -> None:
    """Append description links to supported project pages as extra sources, in order."""
    for link in meta.links:
        if link.kind != "project_source":
            continue
        source = description_page_source(link.url)
        if source is None:
            continue
        canonical = source.url
        kind = "project_page"
        known = any(seen == canonical for _, seen, _ in sources)
        if not known and len(sources) <= MAX_EXTRA_SOURCES:
            sources.append((kind, canonical, canonical))
            linked.add(canonical)
            known = True
        link.followed = known


def _prefetch_links(
    extractor: Extractor,
    sources: list[tuple[str, str, str]],
    linked: set[str],
    progress: Progress,
):
    """Add a video's description links before any model call, so they are read alongside
    the video instead of after it. Optional: extractors without `video_links` skip this."""
    video_links = getattr(extractor, "video_links", None)
    if video_links is None:
        return
    for kind, _, submitted in list(sources):
        if kind != "video":
            continue
        progress("description", "running", "Reading the video description", None)
        try:
            meta = video_links(submitted)
        except Exception:  # The video read fetches the description again and reports it.
            log.info("Description prefetch failed", exc_info=True)
            progress("description", "failed", None, "Could not read the description")
            continue
        if meta is None:
            progress("description", "skipped", None, "No description available")
            continue
        before = len(sources)
        add_description_links(sources, meta.model_copy(deep=True), linked)
        added = len(sources) - before
        progress(
            "description",
            "done",
            None,
            f"{added} project {'link' if added == 1 else 'links'} found" if added else None,
        )


def extract_sources(
    extractor: Extractor, urls: list[str], progress: Progress = _no_progress
) -> IntakeResult:
    """Extract every source in parallel and fuse the per-source BOMs into one (fusion.py).

    Sources are read at the same time (a 4-minute video takes 10 to 50 s, each linked page
    about 25 s; read one by one they added up). Results are processed in source order, so
    fusion and reports are the same as a sequential read.
    """
    sources = validate_sources(urls)
    groups, reports, project, first_error = [], [], None, None
    video_meta, linked = None, set[str]()
    _prefetch_links(extractor, sources, linked, progress)
    index = 0
    with ThreadPoolExecutor(max_workers=MAX_EXTRA_SOURCES + 1) as pool:
        futures: dict[int, Future] = {}

        def submit_new() -> None:
            for position, (kind, canonical, submitted) in enumerate(sources):
                if position not in futures:
                    key = f"source:{canonical}"
                    progress(key, "running", source_label(kind, canonical), None)
                    context = contextvars.copy_context()  # keeps the job's cost attribution
                    future = pool.submit(context.run, _attempt, extractor, submitted)
                    # Ticks off as each source finishes, in whatever order they finish.
                    future.add_done_callback(partial(_finished, progress, key))
                    futures[position] = future

        submit_new()
        while index < len(sources):  # Description links may append sources while reading.
            kind, canonical, _ = sources[index]
            outcome = futures[index].result()
            index += 1
            report = {
                "url": canonical,
                "kind": report_kind(kind, canonical),
                "role": "primary" if index == 1 else "additional",
            }
            if canonical in linked:
                report["found_in"] = DESCRIPTION_SOURCE
            if isinstance(outcome, BaseException):
                if len(sources) == 1:
                    raise outcome  # Single-source jobs fail exactly as before.
                error = (
                    outcome
                    if isinstance(outcome, ExtractionError)
                    else ExtractionError("EXTRACTION_FAILED", "Extraction of this source failed")
                )
                log.info("Source %d of %d failed: %s", index, len(sources), error.code)
                first_error = first_error or error
                reports.append(
                    SourceReport(
                        **report,
                        status="failed",
                        error=ErrorDetail(code=error.code, message=error.message),
                    )
                )
                continue
            result = outcome
            # Simple extractors (and tests) may return only the item list.
            items = result if isinstance(result, list) else result.items
            code_items = [] if isinstance(result, list) else result.code_items
            if project is None and not isinstance(result, list):
                project = result.project
            groups += [group for group in (items, code_items) if group]
            reports.append(
                SourceReport(
                    **report,
                    status="read",
                    item_count=len(items),
                    code_item_count=len(code_items),
                )
            )
            if kind == "video" and not isinstance(result, list):
                described = description_report(canonical, result)
                if described is not None:
                    reports.append(described)
                if result.video_meta is not None and video_meta is None:
                    video_meta = result.video_meta.model_copy(deep=True)
                    add_description_links(sources, video_meta, linked)
                    submit_new()
    if not groups:
        raise first_error or ExtractionError("NO_BOM", "No supported parts found")
    return IntakeResult(items=fuse(groups), project=project, sources=reports, video_meta=video_meta)


def _finished(progress: Progress, key: str, future: Future) -> None:
    outcome = future.result()
    if isinstance(outcome, BaseException):
        message = outcome.message if isinstance(outcome, ExtractionError) else None
        progress(key, "failed", None, (message or "Could not be read")[:200])
    else:
        progress(key, "done", None, found(outcome))


def _attempt(extractor: Extractor, url: str):
    """The source's result, or the exception it raised (handled in source order)."""
    try:
        return extractor.extract(url)
    except Exception as exc:
        return exc
