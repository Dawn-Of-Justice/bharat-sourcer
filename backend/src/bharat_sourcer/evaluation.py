"""Offline extraction quality evaluation against labelled video BOMs.

Labelled cases describe what a human reviewer established for a video: the parts, their
quantities when known, and optional time windows where each part is visible or spoken.
Predictions are saved extraction results (or live GeminiExtractor output). Matching is
deterministic string alignment; no model judges another model's output.

A case set must declare ``synthetic``. Synthetic sets only check the file format and the
harness; their numbers are never reported as extraction accuracy.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from bharat_sourcer.extraction import ExtractionError, youtube_url
from bharat_sourcer.schemas import BomItem, Model, Name, Quantity

TIMESTAMP_PATTERN = r"^\d{2,}:[0-5]\d$"


def seconds(timestamp: str) -> int:
    """Convert the extraction ``MM:SS`` timestamp format (minutes may exceed 59)."""
    if not re.fullmatch(TIMESTAMP_PATTERN, timestamp):
        raise ValueError(f"Invalid MM:SS timestamp: {timestamp!r}")
    minutes, secs = timestamp.split(":")
    return int(minutes) * 60 + int(secs)


class TimeWindow(Model):
    start: str = Field(pattern=TIMESTAMP_PATTERN)
    end: str = Field(pattern=TIMESTAMP_PATTERN)

    @model_validator(mode="after")
    def ordered(self):
        if seconds(self.end) < seconds(self.start):
            raise ValueError("Evidence window end must not precede its start")
        return self

    def contains(self, timestamp: str, tolerance_s: int = 0) -> bool:
        value = seconds(timestamp)
        return seconds(self.start) - tolerance_s <= value <= seconds(self.end) + tolerance_s


class ExpectedPart(Model):
    name: Name
    aliases: list[Name] = Field(default_factory=list, max_length=20)
    qty: Quantity | None = None
    evidence_windows: list[TimeWindow] = Field(default_factory=list, max_length=20)

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


class EvaluationCase(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    url: str
    notes: str | None = Field(default=None, max_length=2000)
    parts: list[ExpectedPart] = Field(max_length=100)

    @model_validator(mode="after")
    def supported_url(self):
        try:
            youtube_url(self.url)
        except ExtractionError as exc:
            raise ValueError(exc.message) from exc
        return self


class EvaluationSet(Model):
    synthetic: bool = Field(
        description="True for format examples; such sets never yield accuracy claims",
        strict=True,
    )
    description: str = Field(min_length=1, max_length=2000)
    labelled_by: str | None = Field(default=None, max_length=200)
    labelled_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Case ids must be unique")
        return self


class Prediction(Model):
    """One saved extraction for a case, as produced by the evaluation script."""

    case_id: str
    synthetic: bool = False
    source: Literal["saved", "live"] = "saved"
    extraction_model: str | None = None
    error_code: str | None = None
    items: list[BomItem] = Field(default_factory=list, max_length=100)


def load_cases(path: Path) -> EvaluationSet:
    return EvaluationSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_prediction(path: Path) -> Prediction:
    return Prediction.model_validate_json(path.read_text(encoding="utf-8"))


def _singular(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(name: str) -> tuple[str, ...]:
    """Lowercase, Unicode-normalize, split on non-alphanumerics, trim simple plurals."""
    text = unicodedata.normalize("NFKC", name).casefold()
    return tuple(_singular(token) for token in re.findall(r"[0-9a-z]+", text))


MatchKind = Literal["exact", "contains"]


def name_match(expected: str, predicted: str, allow_contains: bool = True) -> MatchKind | None:
    """Exact when normalized tokens (or their joined form) agree; contains when every
    expected token appears in the predicted name, e.g. "ESP32" in "ESP32 dev board"."""
    want, got = tokens(expected), tokens(predicted)
    if not want or not got:
        return None
    if want == got or "".join(want) == "".join(got):
        return "exact"
    if allow_contains and set(want) <= set(got):
        return "contains"
    return None


class Match(Model):
    expected: str
    predicted: str
    line_id: str
    kind: MatchKind
    expected_qty: int | None
    predicted_qty: int | None
    qty_correct: bool | None
    evidence_hit: bool | None


class Extra(Model):
    predicted: str
    line_id: str
    duplicate_of: str | None = None


class Counts(Model):
    expected: int = 0
    predicted: int = 0
    matched: int = 0
    duplicates: int = 0
    qty_considered: int = 0
    qty_correct: int = 0
    qty_null_predicted: int = 0
    qty_asserted_label_unknown: int = 0
    evidence_considered: int = 0
    evidence_hits: int = 0

    def add(self, other: "Counts") -> "Counts":
        return Counts(**{key: value + getattr(other, key) for key, value in self})


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


class Metrics(Model):
    recall: float | None
    precision: float | None
    quantity_accuracy: float | None
    evidence_hit_rate: float | None

    @classmethod
    def of(cls, counts: Counts) -> "Metrics":
        return cls(
            recall=_ratio(counts.matched, counts.expected),
            precision=_ratio(counts.matched, counts.predicted),
            quantity_accuracy=_ratio(counts.qty_correct, counts.qty_considered),
            evidence_hit_rate=_ratio(counts.evidence_hits, counts.evidence_considered),
        )


class CaseResult(Model):
    case_id: str
    status: Literal["evaluated", "extraction_failed"]
    error_code: str | None = None
    counts: Counts = Field(default_factory=Counts)
    metrics: Metrics | None = None
    matches: list[Match] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    extras: list[Extra] = Field(default_factory=list)


class EvaluationReport(Model):
    synthetic: bool
    headline: str
    description: str
    cases_total: int
    cases_evaluated: int
    allow_contains: bool
    evidence_tolerance_s: int
    counts: Counts
    metrics: Metrics
    cases: list[CaseResult]


def _best_kind(part: ExpectedPart, item: BomItem, allow_contains: bool):
    """Return a sortable score (higher is better) or None when nothing matches."""
    best = None
    for name in part.names():
        kind = name_match(name, item.raw_name, allow_contains)
        if kind:
            score = (2 if kind == "exact" else 1, len(tokens(name)))
            if best is None or score > best[0]:
                best = (score, kind)
    return best


def evaluate_case(
    case: EvaluationCase,
    items: list[BomItem],
    *,
    allow_contains: bool = True,
    evidence_tolerance_s: int = 0,
) -> CaseResult:
    """Align predictions to expected parts one-to-one, greedily by match strength.

    Ties are broken by expected-part order, then prediction order, so results are
    reproducible. Unmatched predictions that still name an already matched part are
    reported as duplicates; they count against precision like any other extra.
    """
    candidates = []
    for i, part in enumerate(case.parts):
        for j, item in enumerate(items):
            best = _best_kind(part, item, allow_contains)
            if best:
                candidates.append((best[0], i, j, best[1]))
    candidates.sort(key=lambda c: (-c[0][0], -c[0][1], c[1], c[2]))

    assigned: dict[int, tuple[int, MatchKind]] = {}
    used: set[int] = set()
    for _score, i, j, kind in candidates:
        if i not in assigned and j not in used:
            assigned[i] = (j, kind)
            used.add(j)

    counts = Counts(expected=len(case.parts), predicted=len(items), matched=len(assigned))
    matches, omissions = [], []
    for i, part in enumerate(case.parts):
        if i not in assigned:
            omissions.append(part.name)
            continue
        j, kind = assigned[i]
        item = items[j]
        qty_correct = None
        if part.qty is not None:
            counts.qty_considered += 1
            if item.qty is None:
                counts.qty_null_predicted += 1
            qty_correct = item.qty == part.qty
            counts.qty_correct += qty_correct
        elif item.qty is not None:
            counts.qty_asserted_label_unknown += 1
        evidence_hit = None
        if part.evidence_windows:
            counts.evidence_considered += 1
            evidence_hit = any(
                window.contains(evidence.timestamp, evidence_tolerance_s)
                for window in part.evidence_windows
                for evidence in item.evidence
            )
            counts.evidence_hits += evidence_hit
        matches.append(
            Match(
                expected=part.name,
                predicted=item.raw_name,
                line_id=item.line_id,
                kind=kind,
                expected_qty=part.qty,
                predicted_qty=item.qty,
                qty_correct=qty_correct,
                evidence_hit=evidence_hit,
            )
        )

    extras = []
    for j, item in enumerate(items):
        if j in used:
            continue
        duplicate_of = next(
            (
                case.parts[i].name
                for i in sorted(assigned)
                if _best_kind(case.parts[i], item, allow_contains)
            ),
            None,
        )
        counts.duplicates += duplicate_of is not None
        extras.append(
            Extra(predicted=item.raw_name, line_id=item.line_id, duplicate_of=duplicate_of)
        )

    return CaseResult(
        case_id=case.id,
        status="evaluated",
        counts=counts,
        metrics=Metrics.of(counts),
        matches=matches,
        omissions=omissions,
        extras=extras,
    )


def evaluate(
    cases: EvaluationSet,
    predictions: dict[str, Prediction],
    *,
    allow_contains: bool = True,
    evidence_tolerance_s: int = 0,
) -> EvaluationReport:
    """Evaluate every case. ``NO_BOM`` predictions count as empty extractions; any other
    extraction error is reported and excluded from the aggregate."""
    missing = [case.id for case in cases.cases if case.id not in predictions]
    if missing:
        raise ValueError(f"Missing predictions for cases: {', '.join(missing)}")
    if evidence_tolerance_s < 0:
        raise ValueError("Evidence tolerance must not be negative")
    if not cases.synthetic and any(predictions[c.id].synthetic for c in cases.cases):
        raise ValueError("Synthetic predictions cannot be scored against a real labelled set")

    results = []
    total = Counts()
    for case in cases.cases:
        prediction = predictions[case.id]
        if prediction.error_code and prediction.error_code != "NO_BOM":
            results.append(
                CaseResult(
                    case_id=case.id,
                    status="extraction_failed",
                    error_code=prediction.error_code,
                )
            )
            continue
        result = evaluate_case(
            case,
            prediction.items,
            allow_contains=allow_contains,
            evidence_tolerance_s=evidence_tolerance_s,
        )
        result.error_code = prediction.error_code
        total = total.add(result.counts)
        results.append(result)

    evaluated = sum(result.status == "evaluated" for result in results)
    if cases.synthetic:
        headline = (
            "FORMAT CHECK ONLY: synthetic example cases. These numbers exercise the harness "
            "and are not a measure of extraction quality."
        )
    else:
        headline = (
            f"Extraction evaluation on {evaluated} of {len(results)} labelled real-video "
            "case(s). Labels are human-reviewed; matching is deterministic name alignment."
        )
    return EvaluationReport(
        synthetic=cases.synthetic,
        headline=headline,
        description=cases.description,
        cases_total=len(results),
        cases_evaluated=evaluated,
        allow_contains=allow_contains,
        evidence_tolerance_s=evidence_tolerance_s,
        counts=total,
        metrics=Metrics.of(total),
        cases=results,
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: EvaluationReport) -> str:
    title = "Extraction format check (synthetic)" if report.synthetic else "Extraction evaluation"
    metric_label = "Harness output (not accuracy)" if report.synthetic else "Aggregate"
    c, m = report.counts, report.metrics
    lines = [
        f"# {title}",
        "",
        f"**{report.headline}**",
        "",
        f"Set: {report.description}",
        "",
        f"Cases evaluated: {report.cases_evaluated} of {report.cases_total}. "
        f"Name containment matching: {'on' if report.allow_contains else 'off'}. "
        f"Evidence tolerance: {report.evidence_tolerance_s}s.",
        "",
        f"## {metric_label}",
        "",
        "| Metric | Value | Basis |",
        "| --- | --- | --- |",
        f"| Recall (1 - omission rate) | {_pct(m.recall)} | {c.matched}/{c.expected} expected |",
        f"| Precision | {_pct(m.precision)} | {c.matched}/{c.predicted} predicted "
        f"({c.duplicates} duplicates) |",
        f"| Quantity agreement | {_pct(m.quantity_accuracy)} | {c.qty_correct}/"
        f"{c.qty_considered} matched with labelled qty ({c.qty_null_predicted} predicted null) |",
        f"| Evidence in window | {_pct(m.evidence_hit_rate)} | {c.evidence_hits}/"
        f"{c.evidence_considered} matched with labelled windows |",
        "",
        f"Quantities asserted where the label has none: {c.qty_asserted_label_unknown}.",
        "",
        "## Cases",
    ]
    for result in report.cases:
        lines += ["", f"### {result.case_id}", ""]
        if result.status == "extraction_failed":
            lines.append(f"Extraction failed ({result.error_code}); excluded from aggregate.")
            continue
        rm = result.metrics
        lines.append(
            f"Recall {_pct(rm.recall)}, precision {_pct(rm.precision)}, quantity "
            f"{_pct(rm.quantity_accuracy)}, evidence {_pct(rm.evidence_hit_rate)}."
        )
        if result.error_code:
            lines.append(f"Extraction returned {result.error_code}; scored as empty.")
        for match in result.matches:
            qty = {True: "qty ok", False: "qty wrong", None: "qty unlabelled"}[match.qty_correct]
            ev = {True: "evidence ok", False: "evidence miss", None: "no window"}[
                match.evidence_hit
            ]
            lines.append(
                f"- matched ({match.kind}) {match.expected} <- {match.line_id} "
                f"{match.predicted!r}: {qty} ({match.predicted_qty} vs {match.expected_qty}), {ev}"
            )
        lines += [f"- omitted: {name}" for name in result.omissions]
        for extra in result.extras:
            note = f" (duplicate of {extra.duplicate_of})" if extra.duplicate_of else ""
            lines.append(f"- extra: {extra.line_id} {extra.predicted!r}{note}")
    return "\n".join(lines) + "\n"


def report_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
