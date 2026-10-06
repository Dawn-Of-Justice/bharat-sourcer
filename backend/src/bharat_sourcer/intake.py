"""Multi-source intake: validate a job's sources, extract each one, fuse one BOM.

The primary URL and up to three extra `sources` are extracted one by one with the existing
extractor (one model call per source; GitHub code hints add none). A failing extra source
is reported and skipped; the job fails only when no source yields parts.
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
from bharat_sourcer.schemas import ErrorDetail, SourceReport

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


def extract_sources(extractor: Extractor, urls: list[str]) -> IntakeResult:
    """Extract every source and fuse the per-source BOMs into one (see fusion.py)."""
    sources = validate_sources(urls)
    groups, reports, project, first_error = [], [], None, None
    for index, (kind, canonical, submitted) in enumerate(sources):
        report = {
            "url": canonical,
            "kind": report_kind(kind, canonical),
            "role": "primary" if index == 0 else "additional",
        }
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
            log.info("Source %d of %d failed: %s", index + 1, len(sources), error.code)
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
    if not groups:
        raise first_error or ExtractionError("NO_BOM", "No supported parts found")
    return IntakeResult(items=fuse(groups), project=project, sources=reports)
