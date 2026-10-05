import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from bharat_sourcer.evaluation import (
    EvaluationCase,
    EvaluationSet,
    Prediction,
    TimeWindow,
    evaluate,
    evaluate_case,
    load_cases,
    load_prediction,
    name_match,
    render_markdown,
    report_json,
    seconds,
    tokens,
)
from bharat_sourcer.schemas import BomItem

BACKEND = Path(__file__).resolve().parents[1]
EXAMPLES = BACKEND / "evaluation"
URL = "https://www.youtube.com/watch?v=abcdefghijk"


def item(line, name, qty=None, *stamps):
    return BomItem(
        line_id=line,
        raw_name=name,
        qty=qty,
        evidence=[{"timestamp": s, "observation": "seen"} for s in stamps],
    )


def case(*parts, case_id="c1"):
    return EvaluationCase(id=case_id, url=URL, parts=list(parts))


def real_set(*cases):
    return EvaluationSet(synthetic=False, description="test labels", cases=list(cases))


# --- normalization and name matching ---------------------------------------------------


def test_tokens_normalize_case_punctuation_unicode_and_plurals():
    assert tokens("  ESP-32 Dev Boards ") == ("esp", "32", "dev", "board")
    assert tokens("ＬＥＤｓ") == ("led",)
    assert tokens("Glass") == ("glass",)  # "ss" is not treated as a plural
    assert tokens("bus") == ("bus",)  # short words untouched
    assert tokens("---") == ()


def test_name_match_exact_joined_and_contains():
    assert name_match("ESP32", "esp-32") == "exact"
    assert name_match("Red LED", "red leds") == "exact"
    assert name_match("ESP32", "ESP32 dev board") == "contains"
    assert name_match("ESP32", "ESP32 dev board", allow_contains=False) is None
    # Containment is one-directional: a vaguer prediction is not a match.
    assert name_match("Arduino Nano", "Arduino") is None
    assert name_match("LED", "") is None
    assert name_match("Servo", "Stepper motor") is None


# --- labelled-case schema ----------------------------------------------------------------


def test_timestamps_and_windows():
    assert seconds("01:05") == 65
    assert seconds("120:00") == 7200
    with pytest.raises(ValueError):
        seconds("1:5")
    window = TimeWindow(start="00:10", end="00:20")
    assert window.contains("00:10") and window.contains("00:20")
    assert not window.contains("00:21")
    assert window.contains("00:22", tolerance_s=2)
    assert window.contains("00:08", tolerance_s=2)
    with pytest.raises(ValidationError):
        TimeWindow(start="00:20", end="00:10")
    with pytest.raises(ValidationError):
        TimeWindow(start="0:20", end="00:30")


def test_case_schema_validation():
    with pytest.raises(ValidationError):
        EvaluationCase(id="c1", url="https://example.com/video", parts=[])
    with pytest.raises(ValidationError):
        EvaluationCase(id="Bad Id", url=URL, parts=[])
    with pytest.raises(ValidationError):
        case({"name": "LED", "qty": 0})
    with pytest.raises(ValidationError):
        case({"name": "LED", "unexpected": True})
    with pytest.raises(ValidationError, match="unique"):
        real_set(case(), case())
    with pytest.raises(ValidationError):  # synthetic must be declared explicitly
        EvaluationSet(description="x", cases=[case()])
    with pytest.raises(ValidationError):
        EvaluationSet(synthetic="no", description="x", cases=[case()])


# --- matching and metrics ----------------------------------------------------------------


def test_perfect_case():
    result = evaluate_case(
        case(
            {"name": "ESP32", "qty": 1, "evidence_windows": [{"start": "00:10", "end": "00:20"}]},
            {"name": "OLED display", "aliases": ["SSD1306"], "qty": 1},
        ),
        [item("L01", "esp32", 1, "00:15"), item("L02", "SSD1306 0.96in module", 1, "00:30")],
    )
    assert result.omissions == [] and result.extras == []
    assert [m.kind for m in result.matches] == ["exact", "contains"]
    assert result.metrics.model_dump() == {
        "recall": 1.0,
        "precision": 1.0,
        "quantity_accuracy": 1.0,
        "evidence_hit_rate": 1.0,
    }


def test_omissions_extras_and_duplicates():
    result = evaluate_case(
        case({"name": "LED", "qty": 2}, {"name": "Buzzer"}, {"name": "Battery"}),
        [
            item("L01", "LED", 2),
            item("L02", "LED"),  # repeated view of the same part
            item("L03", "Potentiometer"),
            item("L04", "9V battery clip"),  # contains "battery"
        ],
    )
    assert result.omissions == ["Buzzer"]
    assert [(e.line_id, e.duplicate_of) for e in result.extras] == [
        ("L02", "LED"),
        ("L03", None),
    ]
    assert result.counts.duplicates == 1
    assert result.metrics.recall == round(2 / 3, 4)
    assert result.metrics.precision == 0.5


def test_one_to_one_assignment_prefers_exact_over_contains():
    # The contains match would steal "Arduino Nano" if assignment were order-based.
    result = evaluate_case(
        case({"name": "Arduino"}, {"name": "Arduino Nano"}),
        [item("L01", "Arduino Nano"), item("L02", "Arduino")],
    )
    pairs = {(m.expected, m.line_id, m.kind) for m in result.matches}
    assert pairs == {("Arduino Nano", "L01", "exact"), ("Arduino", "L02", "exact")}
    assert result.extras == []


def test_aliases_match():
    result = evaluate_case(
        case({"name": "Microcontroller board", "aliases": ["Nano", "Arduino Nano"]}),
        [item("L01", "Arduino Nano clone")],
    )
    assert result.matches[0].kind == "contains"
    assert result.counts.matched == 1


def test_assignment_is_deterministic_on_ties():
    parts = ({"name": "LED"}, {"name": "LED strip", "aliases": ["LED"]})
    predicted = [item("L01", "LED"), item("L02", "LED")]
    first = evaluate_case(case(*parts), predicted)
    assert first == evaluate_case(case(*parts), predicted)
    assert [(m.expected, m.line_id) for m in first.matches] == [
        ("LED", "L01"),
        ("LED strip", "L02"),
    ]


def test_exact_names_mode_disables_containment():
    result = evaluate_case(
        case({"name": "ESP32"}), [item("L01", "ESP32 dev board")], allow_contains=False
    )
    assert result.omissions == ["ESP32"] and result.metrics.precision == 0.0


def test_quantity_metrics():
    result = evaluate_case(
        case(
            {"name": "LED", "qty": 3},
            {"name": "Resistor", "qty": 3},
            {"name": "Button", "qty": 2},
            {"name": "Wire"},  # quantity unknown to the labeller
        ),
        [
            item("L01", "LED", 3),
            item("L02", "Resistor", 1),
            item("L03", "Button"),
            item("L04", "Wire", 5),
        ],
    )
    c = result.counts
    assert (c.qty_considered, c.qty_correct, c.qty_null_predicted) == (3, 1, 1)
    assert c.qty_asserted_label_unknown == 1
    assert result.metrics.quantity_accuracy == round(1 / 3, 4)
    assert [m.qty_correct for m in result.matches] == [True, False, False, None]


def test_evidence_window_hits_and_tolerance():
    windows = [{"start": "00:10", "end": "00:20"}, {"start": "02:00", "end": "02:05"}]
    parts = (
        {"name": "Motor", "evidence_windows": windows},
        {"name": "Driver", "evidence_windows": [{"start": "01:00", "end": "01:05"}]},
        {"name": "Fan"},
    )
    predicted = [
        item("L01", "Motor", None, "00:50", "02:03"),  # any evidence in any window hits
        item("L02", "Driver", None, "01:07"),
        item("L03", "Fan", None, "00:00"),
    ]
    strict = evaluate_case(case(*parts), predicted)
    assert [m.evidence_hit for m in strict.matches] == [True, False, None]
    assert strict.metrics.evidence_hit_rate == 0.5
    lenient = evaluate_case(case(*parts), predicted, evidence_tolerance_s=2)
    assert lenient.metrics.evidence_hit_rate == 1.0


def test_empty_prediction_and_empty_label():
    result = evaluate_case(case({"name": "LED"}), [])
    assert result.metrics.recall == 0.0 and result.metrics.precision is None
    result = evaluate_case(case(), [item("L01", "LED")])
    assert result.metrics.recall is None and result.metrics.precision == 0.0


# --- aggregate report --------------------------------------------------------------------


def test_aggregate_is_micro_averaged_and_failed_cases_excluded():
    cases = real_set(
        case({"name": "LED", "qty": 1}, {"name": "Buzzer"}, case_id="a"),
        case({"name": "Servo"}, case_id="b"),
        case({"name": "Relay"}, case_id="c"),
        case({"name": "Motor"}, case_id="d"),
    )
    predictions = {
        "a": Prediction(case_id="a", items=[item("L01", "LED", 1)]),
        "b": Prediction(case_id="b", items=[item("L01", "Servo"), item("L02", "Horn")]),
        "c": Prediction(case_id="c", error_code="UPSTREAM_TIMEOUT"),
        "d": Prediction(case_id="d", error_code="NO_BOM"),
    }
    report = evaluate(cases, predictions)
    assert report.cases_total == 4 and report.cases_evaluated == 3
    assert [r.status for r in report.cases] == [
        "evaluated",
        "evaluated",
        "extraction_failed",
        "evaluated",
    ]
    assert report.cases[2].error_code == "UPSTREAM_TIMEOUT" and report.cases[2].metrics is None
    assert report.cases[3].error_code == "NO_BOM"
    assert (report.counts.expected, report.counts.predicted, report.counts.matched) == (4, 3, 2)
    assert report.metrics.recall == 0.5
    assert report.metrics.precision == round(2 / 3, 4)
    assert report.metrics.quantity_accuracy == 1.0
    assert report.metrics.evidence_hit_rate is None
    assert not report.synthetic
    assert "labelled real-video" in report.headline
    markdown = render_markdown(report)
    assert "# Extraction evaluation" in markdown
    assert "Extraction failed (UPSTREAM_TIMEOUT)" in markdown
    assert "scored as empty" in markdown
    assert json.loads(report_json(report))["metrics"]["recall"] == 0.5


def test_evaluate_rejects_missing_predictions_bad_tolerance_and_synthetic_mix():
    cases = real_set(case({"name": "LED"}, case_id="a"), case(case_id="b"))
    with pytest.raises(ValueError, match="Missing predictions for cases: b"):
        evaluate(cases, {"a": Prediction(case_id="a")})
    both = {"a": Prediction(case_id="a"), "b": Prediction(case_id="b")}
    with pytest.raises(ValueError, match="tolerance"):
        evaluate(cases, both, evidence_tolerance_s=-1)
    both["b"] = Prediction(case_id="b", synthetic=True)
    with pytest.raises(ValueError, match="Synthetic predictions"):
        evaluate(cases, both)


def test_synthetic_sets_never_report_accuracy():
    cases = EvaluationSet(synthetic=True, description="format", cases=[case({"name": "LED"})])
    report = evaluate(cases, {"c1": Prediction(case_id="c1", items=[item("L01", "LED")])})
    assert report.synthetic
    assert report.headline.startswith("FORMAT CHECK ONLY")
    assert "accuracy" not in report.headline.lower()
    markdown = render_markdown(report)
    assert markdown.startswith("# Extraction format check (synthetic)")
    assert "not accuracy" in markdown
    assert "## Aggregate" not in markdown


# --- shipped example and script ----------------------------------------------------------


def test_shipped_example_is_labelled_synthetic():
    cases = load_cases(EXAMPLES / "example_cases.json")
    assert cases.synthetic is True
    assert "SYNTHETIC" in cases.description
    assert cases.labelled_by is None
    for example in cases.cases:
        prediction = load_prediction(EXAMPLES / "example_predictions" / f"{example.id}.json")
        assert prediction.synthetic is True
    report = evaluate(
        cases,
        {
            c.id: load_prediction(EXAMPLES / "example_predictions" / f"{c.id}.json")
            for c in cases.cases
        },
    )
    assert report.synthetic and report.headline.startswith("FORMAT CHECK ONLY")
    result = report.cases[0]
    assert result.omissions == ["Breadboard"]
    assert [e.predicted for e in result.extras] == ["Jumper wires"]


def run_script(*args):
    return subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "evaluate_extraction.py"), *args],
        capture_output=True,
        text=True,
        cwd=BACKEND,
        check=False,
    )


def test_script_offline_format_check(tmp_path):
    done = run_script(
        "--cases",
        str(EXAMPLES / "example_cases.json"),
        "--predictions",
        str(EXAMPLES / "example_predictions"),
        "--out",
        str(tmp_path),
    )
    assert done.returncode == 0, done.stderr
    assert "FORMAT CHECK ONLY" in done.stdout
    assert (tmp_path / "format-check.md").exists()
    assert json.loads((tmp_path / "format-check.json").read_text())["synthetic"] is True
    assert not (tmp_path / "report.md").exists()


def test_script_refuses_live_on_synthetic_and_requires_predictions(tmp_path):
    cases = str(EXAMPLES / "example_cases.json")
    done = run_script("--cases", cases, "--live", "--out", str(tmp_path))
    assert done.returncode != 0 and "Refusing --live" in done.stderr
    done = run_script("--cases", cases, "--out", str(tmp_path))
    assert done.returncode != 0 and "--predictions" in done.stderr
    done = run_script("--cases", cases, "--predictions", str(tmp_path), "--out", str(tmp_path))
    assert done.returncode != 0 and "Missing predictions" in done.stderr
