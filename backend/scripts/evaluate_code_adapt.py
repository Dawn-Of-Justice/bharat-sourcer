"""Evaluate curated code changes for substituted parts against a labelled case set.

Offline and deterministic: every case is patched by the production tier-1 code path
(``code_adapt.apply_recipe``) and compared with its expected outcome (patch, refused or no
code change) and expected files. No network, no model calls.

    python scripts/evaluate_code_adapt.py
    python scripts/evaluate_code_adapt.py --cases evaluation/code_adapt/synthetic_cases.json \
        --min-rate 0.9 --min line_recall=1.0 --min-cases-per-edge 6

Exits non-zero when a gated rate is below its threshold (default 1.0 for every rate), when
a catalogue code edge has fewer than --min-cases-per-edge gated cases, or when a case
marked known_failure now passes. Known failures are reported but left out of the gated
rates. Rates with no basis (n/a) do not fail.

Reports are written to backend/.data/evaluation/code-adapt/ (ignored by git) and printed to
stdout: <stem>.md and <stem>.json. The stem is harness-check for synthetic sets,
unreviewed-check when labels are not human-reviewed (a warning is printed and no accuracy
headline is produced) and report otherwise.
"""

import argparse
import sys
from pathlib import Path

from bharat_sourcer.code_adapt_eval import (
    MIN_CASES_PER_EDGE,
    RATES,
    evaluate,
    gate_failures,
    load_case_set,
    render_markdown,
    report_json,
)

BACKEND = Path(__file__).resolve().parents[1]


def threshold(text: str) -> tuple[str, float]:
    name, _, value = text.partition("=")
    if name not in RATES:
        raise argparse.ArgumentTypeError(f"unknown metric {name!r}; one of {', '.join(RATES)}")
    try:
        return name, float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r}: use METRIC=VALUE, e.g. line_recall=0.9"
        ) from None


parser = argparse.ArgumentParser(description="Evaluate curated code-adapt recipes")
parser.add_argument(
    "--cases",
    type=Path,
    default=BACKEND / "evaluation" / "code_adapt" / "synthetic_cases.json",
    help="Labelled case set JSON (default: the synthetic harness-check set)",
)
parser.add_argument("--out", type=Path, default=BACKEND / ".data" / "evaluation" / "code-adapt")
parser.add_argument("--min-rate", type=float, default=1.0, help="Threshold for every rate")
parser.add_argument(
    "--min",
    type=threshold,
    action="append",
    default=[],
    metavar="METRIC=VALUE",
    help=f"Override one rate's threshold; metrics: {', '.join(RATES)}",
)
parser.add_argument("--min-cases-per-edge", type=int, default=MIN_CASES_PER_EDGE)
parser.add_argument(
    "--no-coverage-gate", action="store_true", help="Report coverage without failing on it"
)
args = parser.parse_args()
sys.stdout.reconfigure(errors="backslashreplace")

try:
    cases = load_case_set(args.cases)
except (OSError, ValueError) as exc:
    sys.exit(f"Cannot load {args.cases}: {exc}")

report = evaluate(cases, min_cases_per_edge=args.min_cases_per_edge)
thresholds = {name: args.min_rate for name in RATES} | dict(args.min)
failures = gate_failures(report, thresholds, require_coverage=not args.no_coverage_gate)

if report.synthetic:
    stem = "harness-check"
elif report.accuracy_claim_allowed:
    stem = "report"
else:
    stem = "unreviewed-check"
args.out.mkdir(parents=True, exist_ok=True)
markdown = render_markdown(report)
(args.out / f"{stem}.md").write_text(markdown, encoding="utf-8")
(args.out / f"{stem}.json").write_text(report_json(report), encoding="utf-8")
print(markdown)
if report.warning:
    print(f"WARNING: {report.warning}", file=sys.stderr)
print(f"Saved {stem}.md and {stem}.json in {args.out}")
if failures:
    print("Gate FAILED:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    sys.exit(1)
print("Gate passed.")
