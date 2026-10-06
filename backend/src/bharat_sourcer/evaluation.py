"""Offline extraction quality evaluation against labelled video and project-page BOMs.

Labelled cases describe what a reviewer established for a video or project page: the
parts, their quantities when known, and optional time windows where each part is visible
or spoken. Cases may also carry gold substitution grades and safety flags that must be
raised. Predictions are saved pipeline results (or live GeminiExtractor output). Matching
is deterministic string alignment; no model judges another model's output.

A case set must declare ``synthetic``. Synthetic sets only check the file format and the
harness; their numbers are never reported as extraction accuracy. Real sets also carry a
``label_status``; only ``human_reviewed`` labels allow an accuracy headline.
"""

import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator

from bharat_sourcer.extraction import ExtractionError, youtube_url
from bharat_sourcer.schemas import BomItem, Model, Name, Quantity

TIMESTAMP_PATTERN = r"^\d{2,}:[0-5]\d$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

# Safety codes the gold set can require (evaluation plan: safety-flag recall must be 1.0).
SafetyCode = Literal["MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT"]
SAFETY_CODES: tuple[str, ...] = ("MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT")
Grade = Literal["A", "B", "C", "D", "X"]
GRADES: tuple[str, ...] = ("A", "B", "C", "D", "X")
# Weakest first: a set's status is the weakest status among its scored cases.
LabelStatus = Literal[
    "synthetic", "needs_human_labelling", "agent_draft_needs_human_review", "human_reviewed"
]
LABEL_ORDER: tuple[str, ...] = (
    "synthetic",
    "needs_human_labelling",
    "agent_draft_needs_human_review",
    "human_reviewed",
)
QtyUnit = Literal["pcs", "mm", "cm", "m"]
LENGTH_UNITS = frozenset({"mm", "cm", "m"})
LENGTH_QTY_TOLERANCE = 0.10


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
    # pcs quantities must match exactly; length quantities (mm/cm/m) within 10%.
    qty_unit: QtyUnit = "pcs"
    evidence_windows: list[TimeWindow] = Field(default_factory=list, max_length=20)
    # Optional gold-format detail (evaluation plan section 2); not used for matching.
    canonical_chip: str | None = Field(default=None, max_length=100)
    module: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)

    def names(self) -> list[str]:
        return [self.name, *self.aliases]

    def qty_rule(self) -> Literal["exact", "within_10pct"]:
        return "within_10pct" if self.qty_unit in LENGTH_UNITS else "exact"

    def qty_matches(self, predicted: int | None) -> bool:
        if self.qty is None or predicted is None:
            return False
        if self.qty_rule() == "exact":
            return predicted == self.qty
        return abs(predicted - self.qty) <= LENGTH_QTY_TOLERANCE * self.qty


class GoldSubstitution(Model):
    """An expected compatibility verdict: substitutes for ``original`` should be graded
    within ``grade_range`` (inclusive, ordered A < B < C < D < X)."""

    original: Name
    aliases: list[Name] = Field(default_factory=list, max_length=20)
    acceptable: list[str] = Field(default_factory=list, max_length=20)
    required_changes: list[str] = Field(default_factory=list, max_length=30)
    grade_range: list[Grade] = Field(min_length=1, max_length=2)
    case_ref: int | None = Field(default=None, ge=1, le=13)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def ordered_range(self):
        if GRADES.index(self.grade_range[0]) > GRADES.index(self.grade_range[-1]):
            raise ValueError("grade_range must be ordered from better to worse grade")
        return self

    def names(self) -> list[str]:
        return [self.original, *self.aliases]

    def distance(self, grade: str) -> int:
        """Steps outside the gold range; 0 when the grade is inside it."""
        low, high = GRADES.index(self.grade_range[0]), GRADES.index(self.grade_range[-1])
        value = GRADES.index(grade)
        return max(low - value, value - high, 0)


def _page_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Use a public http(s) project page URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 80, 443)
    ):
        raise ValueError("Use a public http(s) project page URL")


class EvaluationCase(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    url: str
    # video: a YouTube URL; page: any public project page (gold sets cover sites the
    # live pipeline does not fetch yet, such as Adafruit Learn).
    source_type: Literal["video", "page"] = "video"
    notes: str | None = Field(default=None, max_length=2000)
    parts: list[ExpectedPart] = Field(max_length=100)
    must_flag: list[SafetyCode] = Field(default_factory=list, max_length=4)
    gold_substitutions: list[GoldSubstitution] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def supported_url(self):
        if self.source_type == "page":
            _page_url(self.url)
            return self
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
    # None (legacy files) is treated as unreviewed: no accuracy headline.
    label_status: LabelStatus | None = None
    labelled_by: str | None = Field(default=None, max_length=200)
    labelled_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)
    # Gold-index projects left out because they have no labels yet.
    excluded_cases: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Case ids must be unique")
        if self.synthetic != (self.label_status == "synthetic") and self.label_status:
            raise ValueError("label_status 'synthetic' must match synthetic: true")
        return self

    def accuracy_claim_allowed(self) -> bool:
        return not self.synthetic and self.label_status == "human_reviewed"


class PredictedFlag(Model):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    line_id: str | None = None
    reason: str | None = Field(default=None, max_length=500)


class PredictedSubstitution(Model):
    original: Name
    substitute: str | None = Field(default=None, max_length=200)
    grade: Grade | None = None


class PredictedOffer(Model):
    url: str = Field(min_length=1, max_length=2000)
    line_id: str | None = None


class ListingCheck(Model):
    """A listing the pipeline actually retrieved, with eval-time link checks
    (HTTP 200, title match, INR price); None means the check was not run."""

    url: str = Field(min_length=1, max_length=2000)
    http_status: int | None = Field(default=None, ge=100, le=599)
    title_match: bool | None = None
    inr_price: bool | None = None

    def checked(self) -> bool:
        return None not in (self.http_status, self.title_match, self.inr_price)

    def valid(self) -> bool:
        return self.http_status == 200 and self.title_match is True and self.inr_price is True


class Prediction(Model):
    """One saved pipeline result for a case, as produced by the evaluation script.

    The optional stage fields are None when the run did not produce that stage; such
    stages are not scored for the case (an empty list is scored).
    """

    case_id: str
    synthetic: bool = False
    source: Literal["saved", "live"] = "saved"
    extraction_model: str | None = None
    error_code: str | None = None
    items: list[BomItem] = Field(default_factory=list, max_length=100)
    safety_flags: list[PredictedFlag] | None = Field(default=None, max_length=100)
    substitutions: list[PredictedSubstitution] | None = Field(default=None, max_length=200)
    offers: list[PredictedOffer] | None = Field(default=None, max_length=500)
    listings: list[ListingCheck] | None = Field(default=None, max_length=2000)


# --- gold set (evaluation/gold) ----------------------------------------------------------


class GoldSource(Model):
    url: str
    fetched_on: str = Field(pattern=DATE_PATTERN)
    http_status: int | None = Field(default=None, ge=100, le=599)
    robots_txt: str | None = Field(default=None, max_length=300)
    method: str | None = Field(default=None, max_length=300)


class GoldInputs(Model):
    url: str
    video_url: str | None = None


class GoldProject(Model):
    """One project file in the evaluation-plan gold format, plus provenance."""

    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    plan_row: int | None = Field(default=None, ge=1, le=100)
    title: str = Field(min_length=1, max_length=300)
    creator: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "video"]
    label_status: Literal[
        "needs_human_labelling", "agent_draft_needs_human_review", "human_reviewed"
    ]
    inputs: GoldInputs
    source: GoldSource | None = None
    gold_bom: list[ExpectedPart] = Field(default_factory=list, max_length=100)
    gold_substitutions: list[GoldSubstitution] = Field(default_factory=list, max_length=50)
    must_flag: list[SafetyCode] = Field(default_factory=list, max_length=4)
    notes: str | None = Field(default=None, max_length=2000)
    ambiguities: list[str] = Field(default_factory=list, max_length=50)
    drafted_by: str | None = Field(default=None, max_length=200)
    reviewed_by: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.label_status == "needs_human_labelling":
            if self.gold_bom or self.gold_substitutions or self.must_flag:
                raise ValueError("Projects needing labelling must not carry gold labels")
        elif not self.gold_bom:
            raise ValueError("Labelled projects need a non-empty gold_bom")
        if self.label_status == "human_reviewed" and len(self.reviewed_by) < 2:
            raise ValueError("human_reviewed needs two independent reviewers in reviewed_by")
        self.case()  # validates the URL for the project kind
        return self

    def case(self) -> EvaluationCase:
        return EvaluationCase(
            id=self.project_id,
            url=self.inputs.url,
            source_type="video" if self.kind == "video" else "page",
            notes=self.notes,
            parts=self.gold_bom,
            must_flag=self.must_flag,
            gold_substitutions=self.gold_substitutions,
        )


class GoldIndexEntry(Model):
    project_id: str
    file: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.json$")
    plan_row: int | None = None
    kind: Literal["text", "video"]
    label_status: Literal[
        "needs_human_labelling", "agent_draft_needs_human_review", "human_reviewed"
    ]


class GoldIndex(Model):
    description: str = Field(min_length=1, max_length=2000)
    label_status: LabelStatus
    drafted_by: str | None = Field(default=None, max_length=200)
    drafted_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    notes: str | None = Field(default=None, max_length=4000)
    projects: list[GoldIndexEntry] = Field(min_length=1, max_length=1000)


def load_gold_projects(index_path: Path) -> tuple[GoldIndex, list[GoldProject]]:
    index = GoldIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    projects = []
    for entry in index.projects:
        if PurePosixPath(entry.file).name != entry.file or entry.file.startswith("."):
            raise ValueError(f"Gold file must sit next to the index: {entry.file!r}")
        path = index_path.parent / entry.file
        project = GoldProject.model_validate_json(path.read_text(encoding="utf-8"))
        if (project.project_id, project.kind, project.label_status) != (
            entry.project_id,
            entry.kind,
            entry.label_status,
        ):
            raise ValueError(f"{entry.file} does not match its index entry")
        projects.append(project)
    ids = [project.project_id for project in projects]
    if len(ids) != len(set(ids)):
        raise ValueError("Gold project ids must be unique")
    return index, projects


def load_gold_set(index_path: Path) -> EvaluationSet:
    """Build a case set from a gold index; unlabelled projects are excluded and listed."""
    index, projects = load_gold_projects(index_path)
    labelled = [p for p in projects if p.label_status != "needs_human_labelling"]
    if not labelled:
        raise ValueError("The gold set has no labelled projects to score")
    weakest = min([index.label_status, *(p.label_status for p in labelled)], key=LABEL_ORDER.index)
    return EvaluationSet(
        synthetic=False,
        description=index.description,
        label_status=weakest,
        labelled_by=index.drafted_by,
        labelled_on=index.drafted_on,
        cases=[project.case() for project in labelled],
        excluded_cases=[p.project_id for p in projects if p not in labelled],
    )


def load_cases(path: Path) -> EvaluationSet:
    """Load a case set, or a gold index (a JSON object with ``projects``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "projects" in data:
        return load_gold_set(path)
    return EvaluationSet.model_validate(data)


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
    qty_unit: QtyUnit = "pcs"
    qty_rule: Literal["exact", "within_10pct"] | None = None


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


class StageCounts(Model):
    """Counts for the stages after extraction. A case contributes to a stage only when
    its prediction includes that stage (``*_cases`` says how many did)."""

    safety_cases: int = 0
    safety_expected: dict[str, int] = Field(default_factory=dict)
    safety_flagged: dict[str, int] = Field(default_factory=dict)
    safety_false_flags: int = 0
    grade_cases: int = 0
    grades_considered: int = 0
    grades_exact: int = 0
    grades_within_one: int = 0
    grades_missing: int = 0
    link_cases: int = 0
    offers: int = 0
    offers_hallucinated: int = 0
    offers_checked: int = 0
    offers_valid: int = 0

    def add(self, other: "StageCounts") -> "StageCounts":
        merged = {}
        for key, value in self:
            theirs = getattr(other, key)
            if isinstance(value, dict):
                merged[key] = {
                    code: value.get(code, 0) + theirs.get(code, 0)
                    for code in sorted(set(value) | set(theirs), key=SAFETY_CODES.index)
                }
            else:
                merged[key] = value + theirs
        return StageCounts(**merged)


class StageMetrics(Model):
    safety_recall: float | None
    safety_recall_by_code: dict[str, float]
    # The plan's gate: every gold safety flag raised. None when nothing was expected.
    safety_gate_passed: bool | None
    grade_exact_accuracy: float | None
    grade_within_one_accuracy: float | None
    hallucinated_url_rate: float | None
    link_validity: float | None

    @classmethod
    def of(cls, counts: StageCounts) -> "StageMetrics":
        expected = sum(counts.safety_expected.values())
        flagged = sum(counts.safety_flagged.values())
        return cls(
            safety_recall=_ratio(flagged, expected),
            safety_recall_by_code={
                code: _ratio(counts.safety_flagged.get(code, 0), total)
                for code, total in counts.safety_expected.items()
                if total
            },
            safety_gate_passed=None if not expected else flagged == expected,
            grade_exact_accuracy=_ratio(counts.grades_exact, counts.grades_considered),
            grade_within_one_accuracy=_ratio(counts.grades_within_one, counts.grades_considered),
            hallucinated_url_rate=_ratio(counts.offers_hallucinated, counts.offers),
            link_validity=_ratio(counts.offers_valid, counts.offers_checked),
        )


class GradeResult(Model):
    original: str
    grade_range: list[str]
    predicted: str | None
    predicted_grade: str | None
    exact: bool
    within_one: bool


class CaseResult(Model):
    case_id: str
    status: Literal["evaluated", "extraction_failed"]
    error_code: str | None = None
    counts: Counts = Field(default_factory=Counts)
    metrics: Metrics | None = None
    matches: list[Match] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    extras: list[Extra] = Field(default_factory=list)
    stage_counts: StageCounts = Field(default_factory=StageCounts)
    stage_metrics: StageMetrics | None = None
    safety_missed: list[str] = Field(default_factory=list)
    safety_unexpected: list[str] = Field(default_factory=list)
    grades: list[GradeResult] = Field(default_factory=list)
    hallucinated_urls: list[str] = Field(default_factory=list)
    invalid_links: list[str] = Field(default_factory=list)


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
    label_status: str | None = None
    accuracy_claim_allowed: bool = False
    warning: str | None = None
    excluded_cases: list[str] = Field(default_factory=list)
    stage_counts: StageCounts = Field(default_factory=StageCounts)
    stage_metrics: StageMetrics | None = None


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
        qty_correct = qty_rule = None
        if part.qty is not None:
            counts.qty_considered += 1
            if item.qty is None:
                counts.qty_null_predicted += 1
            qty_rule = part.qty_rule()
            qty_correct = part.qty_matches(item.qty)
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
                qty_unit=part.qty_unit,
                qty_rule=qty_rule,
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


def url_key(url: str) -> str:
    """Comparison form of a URL: lowercase scheme and host, no fragment, no default port,
    no trailing slash. Query strings are kept because sellers use them for variants."""
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return url.strip()
    if port and port not in (80, 443):
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), host, path, parsed.query, ""))


def score_stages(
    case: EvaluationCase, prediction: Prediction, *, allow_contains: bool = True
) -> CaseResult:
    """Score safety flags, substitution grades and offer links; returns a partial result
    whose stage fields the caller merges into the extraction result."""
    counts = StageCounts()
    result = CaseResult(case_id=case.id, status="evaluated")

    if prediction.safety_flags is not None:
        counts.safety_cases = 1
        raised = {flag.code for flag in prediction.safety_flags}
        for code in sorted(set(case.must_flag), key=SAFETY_CODES.index):
            counts.safety_expected[code] = 1
            counts.safety_flagged[code] = int(code in raised)
            if code not in raised:
                result.safety_missed.append(code)
        result.safety_unexpected = sorted(raised - set(case.must_flag))
        counts.safety_false_flags = len(result.safety_unexpected)

    if prediction.substitutions is not None and case.gold_substitutions:
        counts.grade_cases = 1
        used: set[int] = set()
        for gold in case.gold_substitutions:
            best = None
            for j, sub in enumerate(prediction.substitutions):
                if j in used or sub.grade is None:
                    continue
                for name in gold.names():
                    kind = name_match(name, sub.original, allow_contains)
                    if kind:
                        score = (2 if kind == "exact" else 1, len(tokens(name)))
                        if best is None or score > best[0]:
                            best = (score, j)
            counts.grades_considered += 1
            if best is None:
                counts.grades_missing += 1
                result.grades.append(
                    GradeResult(
                        original=gold.original,
                        grade_range=list(gold.grade_range),
                        predicted=None,
                        predicted_grade=None,
                        exact=False,
                        within_one=False,
                    )
                )
                continue
            used.add(best[1])
            sub = prediction.substitutions[best[1]]
            distance = gold.distance(sub.grade)
            counts.grades_exact += distance == 0
            counts.grades_within_one += distance <= 1
            result.grades.append(
                GradeResult(
                    original=gold.original,
                    grade_range=list(gold.grade_range),
                    predicted=sub.original,
                    predicted_grade=sub.grade,
                    exact=distance == 0,
                    within_one=distance <= 1,
                )
            )

    if prediction.offers is not None:
        counts.link_cases = 1
        listings = {url_key(listing.url): listing for listing in prediction.listings or []}
        for offer in prediction.offers:
            counts.offers += 1
            listing = listings.get(url_key(offer.url))
            if listing is None:
                counts.offers_hallucinated += 1
                result.hallucinated_urls.append(offer.url)
            elif listing.checked():
                counts.offers_checked += 1
                counts.offers_valid += listing.valid()
                if not listing.valid():
                    result.invalid_links.append(offer.url)

    result.stage_counts = counts
    result.stage_metrics = StageMetrics.of(counts)
    return result


def _headline(cases: EvaluationSet, evaluated: int, total: int) -> tuple[str, str | None]:
    if cases.synthetic:
        return (
            "FORMAT CHECK ONLY: synthetic example cases. These numbers exercise the harness "
            "and are not a measure of extraction quality.",
            None,
        )
    kind = "video" if all(c.source_type == "video" for c in cases.cases) else "project"
    if cases.accuracy_claim_allowed():
        return (
            f"Extraction evaluation on {evaluated} of {total} labelled real-{kind} "
            "case(s). Labels are human-reviewed; matching is deterministic name alignment.",
            None,
        )
    status = cases.label_status or "unspecified"
    warning = (
        f"Labels are not human-reviewed (label_status: {status}). These numbers only "
        "check the labels and the harness; do not report them as accuracy."
    )
    return (
        f"UNREVIEWED LABELS: harness run on {evaluated} of {total} real-{kind} case(s) "
        f"with label_status {status}. Not an accuracy measure.",
        warning,
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
    stage_total = StageCounts()
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
        stages = score_stages(case, prediction, allow_contains=allow_contains)
        result = result.model_copy(
            update={
                key: getattr(stages, key)
                for key in (
                    "stage_counts",
                    "stage_metrics",
                    "safety_missed",
                    "safety_unexpected",
                    "grades",
                    "hallucinated_urls",
                    "invalid_links",
                )
            }
        )
        total = total.add(result.counts)
        stage_total = stage_total.add(result.stage_counts)
        results.append(result)

    evaluated = sum(result.status == "evaluated" for result in results)
    headline, warning = _headline(cases, evaluated, len(results))
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
        label_status=cases.label_status,
        accuracy_claim_allowed=cases.accuracy_claim_allowed(),
        warning=warning,
        excluded_cases=cases.excluded_cases,
        stage_counts=stage_total,
        stage_metrics=StageMetrics.of(stage_total),
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _stage_rows(sc: StageCounts, sm: StageMetrics) -> list[str]:
    expected = sum(sc.safety_expected.values())
    flagged = sum(sc.safety_flagged.values())
    gate = {True: "passed", False: "FAILED", None: "n/a"}[sm.safety_gate_passed]
    rows = [
        f"| Safety-flag recall (gate {gate}) | {_pct(sm.safety_recall)} | {flagged}/{expected} "
        f"gold flags in {sc.safety_cases} case(s); {sc.safety_false_flags} unexpected |",
    ]
    for code, total in sc.safety_expected.items():
        rows.append(
            f"| - {code} | {_pct(sm.safety_recall_by_code.get(code))} | "
            f"{sc.safety_flagged.get(code, 0)}/{total} |"
        )
    rows += [
        f"| Grade accuracy (exact) | {_pct(sm.grade_exact_accuracy)} | {sc.grades_exact}/"
        f"{sc.grades_considered} gold substitutions ({sc.grades_missing} without a graded "
        "prediction) |",
        f"| Grade accuracy (within one) | {_pct(sm.grade_within_one_accuracy)} | "
        f"{sc.grades_within_one}/{sc.grades_considered} |",
        f"| Hallucinated-URL rate | {_pct(sm.hallucinated_url_rate)} | "
        f"{sc.offers_hallucinated}/{sc.offers} offers not in listings |",
        f"| Link validity | {_pct(sm.link_validity)} | {sc.offers_valid}/{sc.offers_checked} "
        "checked listed offers (HTTP 200, title match, INR price) |",
    ]
    return rows


def render_markdown(report: EvaluationReport) -> str:
    if report.synthetic:
        title, metric_label = "Extraction format check (synthetic)", "Harness output (not accuracy)"
    elif report.accuracy_claim_allowed:
        title, metric_label = "Extraction evaluation", "Aggregate"
    else:
        title = "Extraction evaluation (unreviewed labels)"
        metric_label = "Harness output (labels not human-reviewed; not accuracy)"
    c, m = report.counts, report.metrics
    lines = [
        f"# {title}",
        "",
        f"**{report.headline}**",
        "",
    ]
    if report.warning:
        lines += [f"> WARNING: {report.warning}", ""]
    lines += [
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
        *_stage_rows(report.stage_counts, report.stage_metrics),
        "",
        f"Quantities asserted where the label has none: {c.qty_asserted_label_unknown}. "
        "Piece counts must match exactly; lengths (mm/cm/m) within 10%.",
        "",
    ]
    if report.excluded_cases:
        lines += [
            "Not scored (no labels yet): " + ", ".join(report.excluded_cases) + ".",
            "",
        ]
    lines.append("## Cases")
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
        lines += [f"- safety flag missed: {code}" for code in result.safety_missed]
        lines += [f"- safety flag not in gold: {code}" for code in result.safety_unexpected]
        for grade in result.grades:
            span = "-".join(dict.fromkeys(grade.grade_range))
            if grade.predicted is None:
                lines.append(f"- grade missing: {grade.original} (gold {span})")
            else:
                verdict = "exact" if grade.exact else "within one" if grade.within_one else "off"
                lines.append(
                    f"- grade {verdict}: {grade.original} <- {grade.predicted!r} "
                    f"{grade.predicted_grade} (gold {span})"
                )
        lines += [f"- hallucinated URL: {url}" for url in result.hallucinated_urls]
        lines += [f"- invalid link: {url}" for url in result.invalid_links]
    return "\n".join(lines) + "\n"


def report_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def metrics_json(report: EvaluationReport) -> str:
    """Compact metrics file: aggregate and per-case metrics without match details."""
    data = {
        "synthetic": report.synthetic,
        "label_status": report.label_status,
        "accuracy_claim_allowed": report.accuracy_claim_allowed,
        "warning": report.warning,
        "headline": report.headline,
        "cases_total": report.cases_total,
        "cases_evaluated": report.cases_evaluated,
        "excluded_cases": report.excluded_cases,
        "metrics": report.metrics.model_dump(mode="json"),
        "stage_metrics": report.stage_metrics.model_dump(mode="json"),
        "cases": {
            result.case_id: {
                "status": result.status,
                "metrics": result.metrics and result.metrics.model_dump(mode="json"),
                "stage_metrics": result.stage_metrics
                and result.stage_metrics.model_dump(mode="json"),
            }
            for result in report.cases
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
