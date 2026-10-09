"""Offline evaluation of curated code patches for substituted parts (docs/contracts/code-adapt.md).

A case is a small project (``files``: path -> text) and a catalogue substitute edge
(``from`` -> ``to``) with the outcome a reviewer expects: a patch (the patched text of each
changed file, or the set of original lines that must change), a refusal (the recipe must
not patch this code: wrong library, a form it cannot change safely, nothing to change), or
``no_code_change`` (the edge needs no code change). Files a case does not list under
``expected_files`` must come back unchanged.

The scorer runs a *patcher* on every case and compares its output with the labels. The
default patcher is the production tier-1 code path (``code_adapt.apply_recipe``); another
tier (e.g. an AI draft) is scored by passing a callable with the same signature. Line diffs
use difflib and comment detection is the production ``uncommented`` scan, so the harness
never re-implements recipe matching. Nothing here calls a model or the network.

Metrics: exact-file match rate, line-level precision/recall of changed lines, outcome
accuracy (patch / refused / no code change), idempotence (re-applying the patcher to its
own output changes nothing), comment safety (no edits on whole-line comment lines), a
per-recipe breakdown and coverage (catalogue code edges with at least N cases).

A case set must declare ``synthetic`` and ``label_status`` (as in ``evaluation.py``).
Synthetic sets only check the recipes against hand-written expectations and the harness;
their numbers are never reported as accuracy. Only ``human_reviewed`` real sets allow an
accuracy headline. A case may carry ``known_failure`` (a note): it documents a recipe gap
the set exposed, is scored and listed, but is left out of the gated metrics; when it starts
passing the gate fails so the note is removed.
"""

import difflib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bharat_sourcer.catalog import load_catalog
from bharat_sourcer.code_adapt import apply_recipe, is_build, is_code, recipes
from bharat_sourcer.code_evidence import MAX_LINES, safe_path, uncommented
from bharat_sourcer.evaluation import DATE_PATTERN, LabelStatus

Expect = Literal["patch", "refused", "no_code_change"]
EXPECTS: tuple[str, ...] = ("patch", "refused", "no_code_change")
MIN_CASES_PER_EDGE = 3
# Gated rates, in report order. A rate with no basis (n/a) does not fail a threshold.
RATES: tuple[str, ...] = (
    "case_pass_rate",
    "outcome_accuracy",
    "exact_file_rate",
    "line_precision",
    "line_recall",
    "idempotence_rate",
    "comment_safety_rate",
)


def recipe_id(from_id: str, to_id: str) -> str:
    return f"{from_id}_to_{to_id}"


class _Model(BaseModel):
    # File texts are data: leading indentation and trailing newlines are significant.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False, populate_by_name=True)


def _check_path(path: str) -> str:
    if safe_path(path) != path:
        raise ValueError(f"Use a plain relative file path: {path!r}")
    return path


class ExpectedFile(_Model):
    """What one file must look like after the patch: its full text (``after``) or, when
    only the edited lines matter, the 1-based original line numbers that must change."""

    after: str | None = Field(default=None, max_length=200_000)
    changed_lines: list[int] | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def one_form(self):
        if (self.after is None) == (self.changed_lines is None):
            raise ValueError("Give exactly one of after or changed_lines")
        if self.changed_lines and min(self.changed_lines) < 1:
            raise ValueError("changed_lines are 1-based")
        return self


class CodeAdaptCase(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    from_id: str = Field(alias="from", min_length=1, max_length=100)
    to_id: str = Field(alias="to", min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    files: dict[str, str] = Field(min_length=1, max_length=8)
    expect: Expect
    # Paths not listed here must come back unchanged.
    expected_files: dict[str, ExpectedFile] = Field(default_factory=dict, max_length=8)
    known_failure: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        if (self.from_id, self.to_id) not in recipes():
            raise ValueError(f"No curated recipe for {self.from_id} -> {self.to_id}")
        for path in self.files:
            _check_path(path)
        unknown = set(self.expected_files) - set(self.files)
        if unknown:
            raise ValueError(f"Expected outcome names files not in the case: {sorted(unknown)}")
        for path, expected in self.expected_files.items():
            if expected.after is not None and expected.after == self.files[path]:
                raise ValueError(f"{path}: expected text equals the input; leave it unlisted")
            lines = len(self.files[path].splitlines())
            if expected.changed_lines and max(expected.changed_lines) > lines:
                raise ValueError(f"{path}: changed_lines past the end of the file")
        if self.expect == "patch" and not self.expected_files:
            raise ValueError("expect 'patch' needs at least one expected file change")
        if self.expect != "patch" and self.expected_files:
            raise ValueError(f"expect {self.expect!r} must not list expected file changes")
        return self

    @property
    def recipe_id(self) -> str:
        return recipe_id(self.from_id, self.to_id)


class CodeAdaptCaseSet(_Model):
    synthetic: bool = Field(
        description="True for hand-written sketches; such sets never yield accuracy claims",
        strict=True,
    )
    label_status: LabelStatus
    description: str = Field(min_length=1, max_length=2000)
    labelled_by: str | None = Field(default=None, max_length=200)
    labelled_on: str | None = Field(default=None, pattern=DATE_PATTERN)
    cases: list[CodeAdaptCase] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Case ids must be unique")
        if self.synthetic != (self.label_status == "synthetic"):
            raise ValueError("label_status 'synthetic' must match synthetic: true")
        return self

    def accuracy_claim_allowed(self) -> bool:
        return not self.synthetic and self.label_status == "human_reviewed"


def _read_ref(value, base: Path, where: str) -> str:
    """A file text given inline, or as {"ref": "relative/path"} next to the case set."""
    if isinstance(value, str):
        return value
    if not (isinstance(value, dict) and set(value) == {"ref"} and isinstance(value["ref"], str)):
        raise ValueError(f"{where}: give the text or {{'ref': 'relative/path'}}")
    ref = value["ref"]
    if safe_path(ref) != ref:
        raise ValueError(f"{where}: unsafe ref {ref!r}")
    path = base / ref
    if not path.is_file():
        raise ValueError(f"{where}: ref {ref!r} not found")
    # Text mode turns CRLF checkouts (git autocrlf) back into the LF the labels assume.
    return path.read_text(encoding="utf-8")


def load_case_set(path: Path) -> CodeAdaptCaseSet:
    """Load a case set; ``files`` values and ``expected_files[].after`` may be refs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    for case in data.get("cases", []) if isinstance(data, dict) else []:
        where = case.get("id", "?")
        if isinstance(case.get("files"), dict):
            case["files"] = {
                name: _read_ref(value, base, f"{where} {name}")
                for name, value in case["files"].items()
            }
        for name, expected in (case.get("expected_files") or {}).items():
            if isinstance(expected, dict) and "after" in expected:
                expected["after"] = _read_ref(expected["after"], base, f"{where} {name} after")
    return CodeAdaptCaseSet.model_validate(data)


# --- patchers ----------------------------------------------------------------------------


@dataclass
class PatchOutput:
    """What a patcher returns: the text of every file it changed (others are unchanged),
    and when it changed nothing, the refusal reason (``no_code_change_needed`` or another
    production reason) with its detail."""

    files: dict[str, str] = field(default_factory=dict)
    reason: str | None = None
    detail: str | None = None


Patcher = Callable[[str, str, dict[str, str]], PatchOutput]


def curated_patcher(from_id: str, to_id: str, sources: dict[str, str]) -> PatchOutput:
    """Tier 1 exactly as production runs it: the curated recipe applied by apply_recipe."""
    result = apply_recipe(sources, from_id, to_id)
    return PatchOutput(
        files={f.path: f.patched for f in result.files}, reason=result.reason, detail=result.detail
    )


# --- scoring -----------------------------------------------------------------------------

# ("~", original line, new text): line replaced; ("-", original line, old text): line
# removed; ("+", original line it is inserted before, new text): line added.
Change = tuple[str, int, str]
EDITS = frozenset({"~", "-"})  # kinds that alter an existing line


def line_changes(before: str, after: str) -> Counter[Change]:
    """Changed lines as a multiset. Replaced blocks are paired line by line, so editing
    one line of a block counts once whichever way difflib groups the block."""
    old, new = before.splitlines(), after.splitlines()
    changes: Counter[Change] = Counter()
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        paired = min(i2 - i1, j2 - j1)
        for k in range(paired):
            changes[("~", i1 + k + 1, new[j1 + k])] += 1
        for i in range(i1 + paired, i2):
            changes[("-", i + 1, old[i])] += 1
        for j in range(j1 + paired, j2):
            changes[("+", i2 + 1, new[j])] += 1
    return changes


def comment_lines(path: str, text: str) -> set[int]:
    """Whole-line comment lines (1-based) as production's code scan sees them: // and /* */
    in C/C++, # in Python, ; and # in build files (platformio.ini)."""
    if is_code(path):
        hash_comments = path.casefold().endswith(".py")
    elif is_build(path):
        hash_comments = True
    else:
        return set()
    lines = text.splitlines()
    code = {number for number, _ in uncommented(lines, hash_comments=hash_comments)}
    limit = min(len(lines), MAX_LINES)
    return {n for n in range(1, limit + 1) if n not in code and lines[n - 1].strip()}


def outcome_of(output: PatchOutput, sources: dict[str, str]) -> Expect:
    if any(text != sources.get(path) for path, text in output.files.items()):
        return "patch"
    return "no_code_change" if output.reason == "no_code_change_needed" else "refused"


class Counts(_Model):
    cases: int = 0
    cases_passed: int = 0
    outcome_ok: int = 0
    files_scored: int = 0
    files_exact: int = 0
    line_tp: int = 0
    line_fp: int = 0
    line_fn: int = 0
    idempotent: int = 0
    comment_safe: int = 0

    def add(self, other: "Counts") -> "Counts":
        return Counts(**{key: value + getattr(other, key) for key, value in self})


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


class Metrics(_Model):
    case_pass_rate: float | None
    outcome_accuracy: float | None
    exact_file_rate: float | None
    line_precision: float | None
    line_recall: float | None
    idempotence_rate: float | None
    comment_safety_rate: float | None

    @classmethod
    def of(cls, c: Counts) -> "Metrics":
        return cls(
            case_pass_rate=_ratio(c.cases_passed, c.cases),
            outcome_accuracy=_ratio(c.outcome_ok, c.cases),
            exact_file_rate=_ratio(c.files_exact, c.files_scored),
            line_precision=_ratio(c.line_tp, c.line_tp + c.line_fp),
            line_recall=_ratio(c.line_tp, c.line_tp + c.line_fn),
            idempotence_rate=_ratio(c.idempotent, c.cases),
            comment_safety_rate=_ratio(c.comment_safe, c.cases),
        )


class CaseResult(_Model):
    case_id: str
    recipe_id: str
    expect: Expect
    outcome: Expect | None
    detail: str | None = None
    passed: bool
    known_failure: str | None = None
    error: str | None = None
    counts: Counts
    file_mismatches: list[str] = Field(default_factory=list)
    missing_changes: list[str] = Field(default_factory=list)
    unexpected_changes: list[str] = Field(default_factory=list)
    comment_edits: list[str] = Field(default_factory=list)
    not_idempotent: list[str] = Field(default_factory=list)


def _describe(path: str, change: Change) -> str:
    kind, number, text = change
    verb = {"~": "changed to", "-": "removed", "+": "inserted before it"}[kind]
    return f"{path}:{number} {verb}: {text.strip()[:120]}"


def score_case(case: CodeAdaptCase, patcher: Patcher = curated_patcher) -> CaseResult:
    sources = dict(case.files)
    counts = Counts(cases=1)
    result = CaseResult(
        case_id=case.id,
        recipe_id=case.recipe_id,
        expect=case.expect,
        outcome=None,
        passed=False,
        known_failure=case.known_failure,
        counts=counts,
    )
    try:
        output = patcher(case.from_id, case.to_id, dict(sources))
        unknown = set(output.files) - set(sources)
        if unknown:
            raise ValueError(f"patcher returned files not in the case: {sorted(unknown)}")
        again = patcher(case.from_id, case.to_id, {**sources, **output.files})
    except Exception as exc:  # a patcher (e.g. a model draft) may fail; score it as a miss
        result.error = f"{type(exc).__name__}: {exc}"
        for path, before in sources.items():
            expected = case.expected_files.get(path)
            if expected is not None and expected.changed_lines is not None:
                counts.line_fn += len(set(expected.changed_lines))
                continue
            counts.files_scored += 1
            if expected is not None:
                counts.line_fn += sum(line_changes(before, expected.after).values())
        result.counts = counts
        return result

    result.outcome = outcome_of(output, sources)
    result.detail = None if result.outcome == "patch" else output.detail
    counts.outcome_ok = int(result.outcome == case.expect)
    for path, before in sources.items():
        after = output.files.get(path, before)
        expected = case.expected_files.get(path)
        got = line_changes(before, after)
        if expected is not None and expected.changed_lines is not None:
            # Only which original lines change is labelled; added lines are not scored.
            old = before.splitlines()
            want = Counter(("~", n, old[n - 1]) for n in set(expected.changed_lines))
            got = Counter(("~", n, old[n - 1]) for kind, n, _ in got if kind in EDITS)
        else:
            target = expected.after if expected is not None else before
            want = line_changes(before, target)
            counts.files_scored += 1
            if after == target:
                counts.files_exact += 1
            else:
                result.file_mismatches.append(path)
        hit, missing, extra = got & want, want - got, got - want
        counts.line_tp += sum(hit.values())
        counts.line_fn += sum(missing.values())
        counts.line_fp += sum(extra.values())
        result.missing_changes += [_describe(path, c) for c in sorted(missing)]
        result.unexpected_changes += [_describe(path, c) for c in sorted(extra)]
        comments = comment_lines(path, before)
        edited = {number for kind, number, _ in line_changes(before, after) if kind in EDITS}
        result.comment_edits += [f"{path}:{number}" for number in sorted(edited & comments)]
        if again.files.get(path, after) != after:
            result.not_idempotent.append(path)

    counts.idempotent = int(not result.not_idempotent)
    counts.comment_safe = int(not result.comment_edits)
    result.passed = bool(
        counts.outcome_ok
        and not result.file_mismatches
        and counts.line_fp == counts.line_fn == 0
        and counts.idempotent
        and counts.comment_safe
    )
    counts.cases_passed = int(result.passed)
    result.counts = counts
    return result


class Group(_Model):
    counts: Counts
    metrics: Metrics
    known_failures: int = 0


class EdgeCoverage(_Model):
    from_id: str
    to_id: str
    recipe_id: str | None
    cases: int  # cases that are not known failures
    covered: bool


class CodeAdaptReport(_Model):
    synthetic: bool
    label_status: str
    accuracy_claim_allowed: bool
    headline: str
    warning: str | None = None
    description: str
    patcher: str
    min_cases_per_edge: int
    cases_total: int
    cases_gated: int
    # Gated: every case except documented known failures.
    counts: Counts
    metrics: Metrics
    all_counts: Counts
    all_metrics: Metrics
    per_recipe: dict[str, Group]
    coverage: list[EdgeCoverage]
    coverage_rate: float | None
    known_failures: list[str]
    unexpected_passes: list[str]
    cases: list[CaseResult]


def code_edges() -> list[tuple[str, str]]:
    """Curated catalogue substitute edges that carry a code change (each needs a recipe)."""
    edges = []
    for entry in load_catalog().entries.values():
        for edge in entry.substitutes:
            if any(change.area == "code" for change in edge.changes):
                edges.append((entry.id, edge.id))
    return sorted(edges)


def _headline(cases: CodeAdaptCaseSet, gated: int, total: int) -> tuple[str, str | None]:
    if cases.synthetic:
        return (
            "HARNESS CHECK ONLY: synthetic sketches written for this harness. These numbers "
            "check the recipes against hand-written expectations and the scorer itself; they "
            "are not a measure of code adaptation on real projects.",
            None,
        )
    if cases.accuracy_claim_allowed():
        return (
            f"Code-adapt evaluation on {gated} of {total} human-reviewed real case(s); "
            "scoring is deterministic line comparison.",
            None,
        )
    warning = (
        f"Labels are not human-reviewed (label_status: {cases.label_status}). These numbers "
        "only check the labels and the harness; do not report them as accuracy."
    )
    return (
        f"UNREVIEWED LABELS: harness run on {total} real case(s) with label_status "
        f"{cases.label_status}. Not an accuracy measure.",
        warning,
    )


def evaluate(
    cases: CodeAdaptCaseSet,
    patcher: Patcher = curated_patcher,
    *,
    patcher_name: str = "curated",
    min_cases_per_edge: int = MIN_CASES_PER_EDGE,
) -> CodeAdaptReport:
    results = [score_case(case, patcher) for case in cases.cases]
    gated, everything = Counts(), Counts()
    groups: dict[str, tuple[Counts, int]] = {}
    for result in results:
        everything = everything.add(result.counts)
        counts, failures = groups.get(result.recipe_id, (Counts(), 0))
        if result.known_failure:
            groups[result.recipe_id] = (counts, failures + 1)
            continue
        gated = gated.add(result.counts)
        groups[result.recipe_id] = (counts.add(result.counts), failures)

    per_edge = Counter((c.from_id, c.to_id) for c in cases.cases if not c.known_failure)
    curated = recipes()
    coverage = []
    for from_id, to_id in code_edges():
        count = per_edge.get((from_id, to_id), 0)
        coverage.append(
            EdgeCoverage(
                from_id=from_id,
                to_id=to_id,
                recipe_id=recipe_id(from_id, to_id) if (from_id, to_id) in curated else None,
                cases=count,
                covered=count >= min_cases_per_edge,
            )
        )
    headline, warning = _headline(cases, gated.cases, len(results))
    return CodeAdaptReport(
        synthetic=cases.synthetic,
        label_status=cases.label_status,
        accuracy_claim_allowed=cases.accuracy_claim_allowed(),
        headline=headline,
        warning=warning,
        description=cases.description,
        patcher=patcher_name,
        min_cases_per_edge=min_cases_per_edge,
        cases_total=len(results),
        cases_gated=gated.cases,
        counts=gated,
        metrics=Metrics.of(gated),
        all_counts=everything,
        all_metrics=Metrics.of(everything),
        per_recipe={
            rid: Group(counts=c, metrics=Metrics.of(c), known_failures=failures)
            for rid, (c, failures) in sorted(groups.items())
        },
        coverage=coverage,
        coverage_rate=_ratio(sum(edge.covered for edge in coverage), len(coverage)),
        known_failures=[r.case_id for r in results if r.known_failure],
        unexpected_passes=[r.case_id for r in results if r.known_failure and r.passed],
        cases=results,
    )


def gate_failures(
    report: CodeAdaptReport,
    thresholds: dict[str, float] | None = None,
    *,
    require_coverage: bool = True,
) -> list[str]:
    """Reasons the report misses its thresholds (default: every gated rate 1.0)."""
    wanted = {name: 1.0 for name in RATES} | (thresholds or {})
    unknown = set(wanted) - set(RATES)
    if unknown:
        raise ValueError(f"Unknown metric(s): {', '.join(sorted(unknown))}")
    failures = []
    for name in RATES:
        value = getattr(report.metrics, name)
        if value is not None and value < wanted[name]:
            failures.append(f"{name} {value:.4f} < {wanted[name]:.4f}")
    if require_coverage:
        for edge in report.coverage:
            if not edge.covered:
                failures.append(
                    f"coverage: {edge.from_id} -> {edge.to_id} has {edge.cases} case(s), "
                    f"needs {report.min_cases_per_edge}"
                )
    for case_id in report.unexpected_passes:
        failures.append(f"{case_id} is marked known_failure but now passes; remove the note")
    return failures


# --- output ------------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _rows(c: Counts, m: Metrics) -> list[tuple[str, str, str]]:
    def of(tp: int, wrong: int) -> str:
        return f"{tp}/{tp + wrong}"

    return [
        ("Cases passed", _pct(m.case_pass_rate), f"{c.cases_passed}/{c.cases}"),
        (
            "Outcome (patch / refused / no change)",
            _pct(m.outcome_accuracy),
            f"{c.outcome_ok}/{c.cases}",
        ),
        ("Exact file match", _pct(m.exact_file_rate), f"{c.files_exact}/{c.files_scored} files"),
        ("Changed-line precision", _pct(m.line_precision), of(c.line_tp, c.line_fp)),
        ("Changed-line recall", _pct(m.line_recall), of(c.line_tp, c.line_fn)),
        (
            "Idempotent (re-run changes nothing)",
            _pct(m.idempotence_rate),
            f"{c.idempotent}/{c.cases}",
        ),
        (
            "Comment safe (no comment line edited)",
            _pct(m.comment_safety_rate),
            f"{c.comment_safe}/{c.cases}",
        ),
    ]


def render_markdown(report: CodeAdaptReport) -> str:
    if report.synthetic:
        title, label = "Code-adapt harness check (synthetic)", "Harness output (not accuracy)"
    elif report.accuracy_claim_allowed:
        title, label = "Code-adapt evaluation", "Aggregate"
    else:
        title = "Code-adapt evaluation (unreviewed labels)"
        label = "Harness output (labels not human-reviewed; not accuracy)"
    lines = [f"# {title}", "", f"**{report.headline}**", ""]
    if report.warning:
        lines += [f"> WARNING: {report.warning}", ""]
    known = len(report.known_failures)
    lines += [
        f"Set: {report.description}",
        "",
        f"Patcher: {report.patcher}. Cases: {report.cases_total} ({report.cases_gated} gated, "
        f"{known} known failure(s) reported separately).",
        "",
        f"## {label}",
        "",
        "| Metric | Gated | Basis | All cases |",
        "| --- | --- | --- | --- |",
    ]
    for (name, value, basis), (_, all_value, all_basis) in zip(
        _rows(report.counts, report.metrics),
        _rows(report.all_counts, report.all_metrics),
        strict=True,
    ):
        lines.append(f"| {name} | {value} | {basis} | {all_value} ({all_basis}) |")
    lines += [
        "",
        "## Per recipe (gated)",
        "",
        "| Recipe | Cases | Passed | Outcome | Exact files | Lines P / R | Idempotent "
        "| Comment safe | Known failures |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rid, group in report.per_recipe.items():
        c, m = group.counts, group.metrics
        lines.append(
            f"| {rid} | {c.cases} | {c.cases_passed} | {_pct(m.outcome_accuracy)} | "
            f"{_pct(m.exact_file_rate)} | {_pct(m.line_precision)} / {_pct(m.line_recall)} | "
            f"{_pct(m.idempotence_rate)} | {_pct(m.comment_safety_rate)} | "
            f"{group.known_failures} |"
        )
    lines += [
        "",
        f"## Coverage (catalogue code edges with at least {report.min_cases_per_edge} gated "
        f"cases: {_pct(report.coverage_rate)})",
        "",
        "| Edge | Recipe | Cases | Covered |",
        "| --- | --- | --- | --- |",
    ]
    for edge in report.coverage:
        lines.append(
            f"| {edge.from_id} -> {edge.to_id} | {edge.recipe_id or 'none'} | {edge.cases} | "
            f"{'yes' if edge.covered else 'NO'} |"
        )
    shown = [r for r in report.cases if not r.passed or r.known_failure]
    lines += ["", "## Failing and known-failure cases", ""]
    if not shown:
        lines.append("None.")
    for result in shown:
        tag = " (known failure)" if result.known_failure else ""
        status = "passes" if result.passed else "fails"
        lines += ["", f"### {result.case_id}{tag}", ""]
        lines.append(
            f"{result.recipe_id}: {status}; expected {result.expect}, got {result.outcome}."
        )
        if result.detail:
            lines.append(f"- recipe said: {result.detail}")
        if result.known_failure:
            lines.append(f"- note: {result.known_failure}")
        if result.error:
            lines.append(f"- patcher error: {result.error}")
        lines += [f"- file differs from expected: {path}" for path in result.file_mismatches]
        lines += [f"- missing change: {text}" for text in result.missing_changes]
        lines += [f"- unexpected change: {text}" for text in result.unexpected_changes]
        lines += [f"- edited a whole-line comment: {where}" for where in result.comment_edits]
        lines += [f"- not idempotent: {path}" for path in result.not_idempotent]
    if report.unexpected_passes:
        lines += [
            "",
            "Known failures that now pass (remove their known_failure note): "
            + ", ".join(report.unexpected_passes)
            + ".",
        ]
    return "\n".join(lines) + "\n"


def report_json(report: CodeAdaptReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
