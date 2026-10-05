"""Evaluate BOM extraction against a labelled case set.

Offline (default, no network): score saved prediction files, one ``<case_id>.json`` per
case in --predictions, e.g. from an earlier --live run.

    python scripts/evaluate_extraction.py --cases evaluation/example_cases.json \
        --predictions evaluation/example_predictions

Live (--live): call GeminiExtractor once per case with BS_GEMINI_API_KEY. This incurs
Gemini usage charges (with bounded HTTP retries). Predictions are saved under the output
directory so the run can be re-scored offline. Synthetic sets are refused in live mode.

Reports are written to backend/.data/evaluation/ (ignored by git) and printed to stdout.
"""

import argparse
import sys
from pathlib import Path

from bharat_sourcer.evaluation import (
    Prediction,
    evaluate,
    load_cases,
    load_prediction,
    render_markdown,
    report_json,
)

BACKEND = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser(description="Evaluate BOM extraction against labelled cases")
parser.add_argument("--cases", type=Path, required=True, help="Labelled case set JSON")
parser.add_argument("--predictions", type=Path, help="Directory of saved <case_id>.json")
parser.add_argument("--live", action="store_true", help="Run paid Gemini extraction per case")
parser.add_argument("--out", type=Path, default=BACKEND / ".data" / "evaluation")
parser.add_argument("--evidence-tolerance-s", type=int, default=0)
parser.add_argument("--exact-names", action="store_true", help="Disable name-containment matches")
args = parser.parse_args()

cases = load_cases(args.cases)
predictions: dict[str, Prediction] = {}

if args.live:
    if cases.synthetic:
        sys.exit("Refusing --live on a synthetic set: it would spend Gemini usage for no signal")
    from bharat_sourcer.config import Settings
    from bharat_sourcer.extraction import ExtractionError, GeminiExtractor

    settings = Settings()
    extractor = GeminiExtractor(settings)
    saved = args.out / "predictions"
    saved.mkdir(parents=True, exist_ok=True)
    for case in cases.cases:
        try:
            items, error_code = extractor.extract(case.url), None
        except ExtractionError as exc:
            items, error_code = [], exc.code
        prediction = Prediction(
            case_id=case.id,
            source="live",
            extraction_model=settings.gemini_model,
            error_code=error_code,
            items=items,
        )
        (saved / f"{case.id}.json").write_text(
            prediction.model_dump_json(indent=2), encoding="utf-8"
        )
        predictions[case.id] = prediction
        print(f"extracted {case.id}: {len(items)} item(s) {error_code or ''}".rstrip())
else:
    if args.predictions is None:
        sys.exit("Pass --predictions <dir> for offline scoring, or --live to extract")
    for case in cases.cases:
        path = args.predictions / f"{case.id}.json"
        if path.exists():
            prediction = load_prediction(path)
            if prediction.case_id != case.id:
                sys.exit(f"{path} declares case_id {prediction.case_id!r}, expected {case.id!r}")
            predictions[case.id] = prediction

try:
    report = evaluate(
        cases,
        predictions,
        allow_contains=not args.exact_names,
        evidence_tolerance_s=args.evidence_tolerance_s,
    )
except ValueError as exc:
    sys.exit(str(exc))

stem = "format-check" if report.synthetic else "report"
args.out.mkdir(parents=True, exist_ok=True)
markdown = render_markdown(report)
(args.out / f"{stem}.md").write_text(markdown, encoding="utf-8")
(args.out / f"{stem}.json").write_text(report_json(report), encoding="utf-8")
print(markdown)
print(f"Saved {args.out / (stem + '.md')} and {args.out / (stem + '.json')}")
