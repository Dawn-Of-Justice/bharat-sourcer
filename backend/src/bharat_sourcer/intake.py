"""Multi-source intake: validate a job's sources, extract each one, fuse one BOM.

The primary URL and up to three extra `sources` are extracted one by one with the existing
extractor (one model call per source; GitHub code hints add none). A failing extra source
is reported and skipped; the job fails only when no source yields parts.

When a source is a YouTube video and BS_YOUTUBE_API_KEY is set, the extractor
also reads the video's description (youtube_meta.py) inside the same video call. Links in
the description to supported project pages are added as extra sources (within the limit
of three extras and the usual dedupe), and the description gets its own source report.
"""

import logging

from bharat_sourcer.extraction import (
    ExtractionError,
    ExtractionResult,
    Extractor,
    supported_source,
)
from bharat_sourcer.fusion import fuse
from bharat_sourcer.project_pages import project_page_source
from bharat_sourcer.schemas import ErrorDetail, JobVideoMeta, SourceReport
from bharat_sourcer.youtube_meta import DESCRIPTION_SOURCE

MAX_EXTRA_SOURCES = 3

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
    return "video" if kind == "video" else project_page_source(canonical).kind


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
        try:
            kind, canonical = supported_source(link.url)
        except ExtractionError:
            continue
        known = any(seen == canonical for _, seen, _ in sources)
        if not known and kind == "project_page" and len(sources) <= MAX_EXTRA_SOURCES:
            sources.append((kind, canonical, canonical))
            linked.add(canonical)
            known = True
        link.followed = known


def extract_sources(extractor: Extractor, urls: list[str]) -> IntakeResult:
    """Extract every source and fuse the per-source BOMs into one (see fusion.py)."""
    sources = validate_sources(urls)
    groups, reports, project, first_error = [], [], None, None
    video_meta, linked = None, set[str]()
    index = 0
    while index < len(sources):  # Description links may append sources while reading.
        kind, canonical, submitted = sources[index]
        index += 1
        report = {
            "url": canonical,
            "kind": report_kind(kind, canonical),
            "role": "primary" if index == 1 else "additional",
        }
        if canonical in linked:
            report["found_in"] = DESCRIPTION_SOURCE
        try:
            result = extractor.extract(submitted)
        except Exception as exc:
            if len(sources) == 1:
                raise  # Single-source jobs fail exactly as before.
            error = (
                exc
                if isinstance(exc, ExtractionError)
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
    if not groups:
        raise first_error or ExtractionError("NO_BOM", "No supported parts found")
    return IntakeResult(items=fuse(groups), project=project, sources=reports, video_meta=video_meta)
