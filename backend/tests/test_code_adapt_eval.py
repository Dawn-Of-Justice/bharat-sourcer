"""Code-adapt evaluation harness. Every sketch here and in evaluation/code_adapt/ is a short
synthetic example written for these tests (not copied from a real project); no network, no
model calls. The synthetic-set gate is a harness check, not an accuracy claim."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from bharat_sourcer.code_adapt import recipes
from bharat_sourcer.code_adapt_eval import (
    MIN_CASES_PER_EDGE,
    CodeAdaptCase,
    CodeAdaptCaseSet,
    PatchOutput,
    code_edges,
    comment_lines,
    curated_patcher,
    evaluate,
    gate_failures,
    line_changes,
    load_case_set,
    recipe_id,
    render_markdown,
    report_json,
    score_case,
)

BACKEND = Path(__file__).resolve().parents[1]
SYNTHETIC = BACKEND / "evaluation" / "code_adapt" / "synthetic_cases.json"

DHT_BEFORE = """\
#include "DHT.h"
// Pick DHT22 or DHT11 below.
#define DHTTYPE DHT22
DHT dht(2, DHTTYPE);
const char *NAME = "DHT22";
"""
DHT_AFTER = DHT_BEFORE.replace("#define DHTTYPE DHT22", "#define DHTTYPE DHT11")


def dht_case(**overrides):
    data = {
        "id": "dht-tiny",
        "from": "dht22",
        "to": "dht11",
        "description": "Tiny synthetic DHT sketch.",
        "files": {"a.ino": DHT_BEFORE},
        "expect": "patch",
        "expected_files": {"a.ino": {"after": DHT_AFTER}},
    }
    return CodeAdaptCase.model_validate(data | overrides)


def case_set(*cases, synthetic=True, label_status="synthetic"):
    return CodeAdaptCaseSet(
        synthetic=synthetic,
        label_status=label_status,
        description="Synthetic test set.",
        cases=list(cases),
    )


# --- model validation ------------------------------------------------------------------


def test_case_set_requires_a_strict_synthetic_flag_matching_label_status():
    base = {"label_status": "synthetic", "description": "x", "cases": [dht_case()]}
    with pytest.raises(ValidationError, match="synthetic"):
        CodeAdaptCaseSet.model_validate(base)  # flag missing
    with pytest.raises(ValidationError):
        CodeAdaptCaseSet.model_validate(base | {"synthetic": "true"})  # strict bool
    with pytest.raises(ValidationError, match="must match synthetic"):
        CodeAdaptCaseSet.model_validate(
            base | {"synthetic": True, "label_status": "human_reviewed"}
        )
    with pytest.raises(ValidationError, match="must match synthetic"):
        CodeAdaptCaseSet.model_validate(base | {"synthetic": False})
    with pytest.raises(ValidationError, match="unique"):
        case_set(dht_case(), dht_case())
    assert not case_set(dht_case()).accuracy_claim_allowed()
    real = case_set(dht_case(), synthetic=False, label_status="human_reviewed")
    assert real.accuracy_claim_allowed()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"from": "dht22", "to": "sh1106_13_i2c"}, "No curated recipe"),
        ({"from": "esp32", "to": "esp8266"}, "No curated recipe"),
        ({"files": {"../a.ino": DHT_BEFORE}}, "plain relative file path"),
        ({"expected_files": {"b.ino": {"after": DHT_AFTER}}}, "not in the case"),
        ({"expected_files": {"a.ino": {"after": DHT_BEFORE}}}, "equals the input"),
        ({"expected_files": {"a.ino": {"changed_lines": [99]}}}, "past the end"),
        ({"expected_files": {"a.ino": {}}}, "exactly one of"),
        ({"expected_files": {}}, "needs at least one expected file change"),
        ({"expect": "refused"}, "must not list expected file changes"),
        ({"expect": "no_code_change"}, "must not list expected file changes"),
        ({"expect": "manual_only", "expected_files": {}}, "expect"),
    ],
)
def test_case_validation_rejects_inconsistent_labels(overrides, message):
    with pytest.raises(ValidationError, match=message):
        dht_case(**overrides)


def test_file_texts_keep_whitespace_and_cases_name_their_recipe():
    case = dht_case(files={"a.ino": "  indented\n\n"}, expected_files={"a.ino": {"after": "x\n"}})
    assert case.files["a.ino"] == "  indented\n\n"
    assert dht_case().recipe_id == "dht22_to_dht11"


def test_load_case_set_resolves_refs_and_refuses_unsafe_ones(tmp_path):
    (tmp_path / "sk").mkdir()
    (tmp_path / "sk" / "a.ino").write_text(DHT_BEFORE, encoding="utf-8")
    (tmp_path / "sk" / "a.after.ino").write_bytes(DHT_AFTER.replace("\n", "\r\n").encode())
    data = {
        "synthetic": True,
        "label_status": "synthetic",
        "description": "Synthetic.",
        "cases": [
            {
                "id": "ref-case",
                "from": "dht22",
                "to": "dht11",
                "description": "Refs.",
                "files": {"a.ino": {"ref": "sk/a.ino"}},
                "expect": "patch",
                "expected_files": {"a.ino": {"after": {"ref": "sk/a.after.ino"}}},
            }
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_case_set(path)
    assert loaded.cases[0].files["a.ino"] == DHT_BEFORE
    # A CRLF checkout (git autocrlf) reads back as the LF text the labels assume.
    assert loaded.cases[0].expected_files["a.ino"].after == DHT_AFTER
    for bad, message in [("../a.ino", "unsafe ref"), ("sk/missing.ino", "not found")]:
        data["cases"][0]["files"] = {"a.ino": {"ref": bad}}
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_case_set(path)


# --- scoring primitives ----------------------------------------------------------------


def test_line_changes_pairs_replaced_lines_and_places_inserts():
    before = "a\nb\nc\n"
    assert line_changes(before, before) == Counter()
    assert line_changes(before, "a\nB\nc\n") == Counter({("~", 2, "B"): 1})
    assert line_changes(before, "a\nb\nnew\nc\n") == Counter({("+", 3, "new"): 1})
    assert line_changes(before, "a\nc\n") == Counter({("-", 2, "b"): 1})
    assert line_changes(before, "A\nB\nnew\nc\n") == Counter(
        {("~", 1, "A"): 1, ("~", 2, "B"): 1, ("+", 3, "new"): 1}
    )


def test_comment_lines_follow_the_production_code_scan():
    cpp = "// one\ncode();\n/*\n two\n*/\n  // three\n\n#include <x.h>\n"
    assert comment_lines("a.ino", cpp) == {1, 3, 4, 5, 6}
    assert comment_lines("code.py", "# one\nx = 1\n") == {1}
    assert comment_lines("platformio.ini", "; one\n# two\n[env]\n") == {1, 2}
    assert comment_lines("README.md", "// not code\n") == set()


# --- scorer correctness ----------------------------------------------------------------


def test_curated_patcher_scores_a_correct_case_as_passing():
    result = score_case(dht_case())
    assert result.passed and result.outcome == "patch" and result.error is None
    c = result.counts
    assert (c.files_exact, c.files_scored) == (1, 1)
    assert (c.line_tp, c.line_fp, c.line_fn) == (1, 0, 0)
    assert c.idempotent == c.comment_safe == 1


def test_changed_lines_labels_score_only_which_original_lines_change():
    case = dht_case(expected_files={"a.ino": {"changed_lines": [3]}})
    result = score_case(case)
    assert result.passed and result.counts.files_scored == 0
    wrong = score_case(dht_case(expected_files={"a.ino": {"changed_lines": [4]}}))
    assert not wrong.passed
    assert (wrong.counts.line_tp, wrong.counts.line_fp, wrong.counts.line_fn) == (0, 1, 1)


def naive_replace(from_id, to_id, sources):
    """Deliberately wrong: rewrites every DHT22, comments and strings included."""
    return PatchOutput(
        files={path: text.replace("DHT22", "DHT11") for path, text in sources.items()}
    )


def growing(from_id, to_id, sources):
    """Deliberately wrong: correct first edit, but appends a line every time it runs."""
    output = curated_patcher(from_id, to_id, sources)
    files = {path: output.files.get(path, text) + "// again\n" for path, text in sources.items()}
    return PatchOutput(files=files, reason=output.reason)


def test_a_deliberately_wrong_patcher_is_caught_on_every_metric_it_breaks():
    result = score_case(dht_case(), naive_replace)
    assert not result.passed
    assert result.file_mismatches == ["a.ino"]
    assert result.comment_edits == ["a.ino:2"]
    c = result.counts
    # Line 3 is right; lines 2 (comment) and 5 (string) are not wanted.
    assert (c.line_tp, c.line_fp, c.line_fn) == (1, 2, 0)
    assert result.unexpected_changes == [
        "a.ino:2 changed to: // Pick DHT11 or DHT11 below.",
        'a.ino:5 changed to: const char *NAME = "DHT11";',
    ]
    assert c.idempotent == 1 and c.comment_safe == 0

    growing_result = score_case(dht_case(), growing)
    assert growing_result.not_idempotent == ["a.ino"] and not growing_result.passed


def test_patcher_errors_and_stray_files_count_as_misses():
    def broken(*_):
        raise RuntimeError("model said no")

    def stray(from_id, to_id, sources):
        return PatchOutput(files={"other.ino": "x\n"})

    for patcher, message in [(broken, "model said no"), (stray, "not in the case")]:
        result = score_case(dht_case(), patcher)
        assert not result.passed and message in result.error and result.outcome is None
        c = result.counts
        assert (c.line_fn, c.files_scored, c.files_exact) == (1, 1, 0)


def test_outcome_and_unchanged_files_are_scored():
    lazy = score_case(dht_case(), lambda *_: PatchOutput(reason="recipe_not_applicable"))
    assert lazy.outcome == "refused" and not lazy.passed
    assert lazy.counts.outcome_ok == 0 and lazy.counts.line_fn == 1
    # A refusal is right when the label says refused; "no change needed" is its own outcome.
    refused = dht_case(expect="refused", expected_files={})
    assert score_case(refused, lambda *_: PatchOutput(reason="recipe_not_applicable")).passed
    unchanged = score_case(refused, lambda *_: PatchOutput(reason="no_code_change_needed"))
    assert unchanged.outcome == "no_code_change" and not unchanged.passed
    # Patching code that should be refused is a wrong outcome and an unexpected change.
    wrong = score_case(refused)
    assert wrong.outcome == "patch" and wrong.counts.line_fp == 1 and not wrong.passed
    # An unrelated file that is changed counts against exactness and precision.
    case = dht_case(files={"a.ino": DHT_BEFORE, "b.ino": "// DHT22 notes\nint x;\n"})
    result = score_case(case, naive_replace)
    assert "b.ino" in result.file_mismatches and "b.ino:1" in result.comment_edits


def test_report_gate_known_failures_and_coverage():
    # Mislabelled: says line 4 changes; the recipe (rightly) changes line 3.
    bad = dht_case(id="naive-label", expected_files={"a.ino": {"changed_lines": [4]}})
    report = evaluate(case_set(dht_case(), bad), min_cases_per_edge=1)
    assert report.counts.cases == 2 and report.metrics.case_pass_rate == 0.5
    failures = gate_failures(report, require_coverage=False)
    assert any(f.startswith("case_pass_rate") for f in failures)
    assert any(f.startswith("line_precision") for f in failures)
    relaxed = {"case_pass_rate": 0.5, "line_precision": 0.5, "line_recall": 0.5}
    assert gate_failures(report, relaxed, require_coverage=False) == []

    noted = bad.model_copy(update={"known_failure": "Label documents a bug."})
    report = evaluate(case_set(dht_case(), noted), min_cases_per_edge=1)
    assert report.cases_gated == 1 and report.metrics.case_pass_rate == 1.0
    assert report.all_metrics.case_pass_rate == 0.5
    assert report.known_failures == ["naive-label"] and report.unexpected_passes == []
    assert report.per_recipe["dht22_to_dht11"].known_failures == 1
    # Only the DHT edge has a case, so every other code edge is uncovered.
    uncovered = [f for f in gate_failures(report) if f.startswith("coverage")]
    assert len(uncovered) == len(code_edges()) - 1

    passing = dht_case().model_copy(update={"known_failure": "Fixed since."})
    report = evaluate(case_set(passing), min_cases_per_edge=1)
    assert report.unexpected_passes == ["dht-tiny"]
    assert any("now passes" in f for f in gate_failures(report, require_coverage=False))
    with pytest.raises(ValueError, match="Unknown metric"):
        gate_failures(report, {"accuracy": 1.0})


def test_headlines_never_claim_accuracy_for_synthetic_or_unreviewed_labels():
    synthetic = evaluate(case_set(dht_case()))
    assert synthetic.headline.startswith("HARNESS CHECK ONLY")
    assert not synthetic.accuracy_claim_allowed and synthetic.warning is None
    assert "(not accuracy)" in render_markdown(synthetic)
    draft = evaluate(
        case_set(dht_case(), synthetic=False, label_status="agent_draft_needs_human_review")
    )
    assert draft.headline.startswith("UNREVIEWED LABELS") and draft.warning
    reviewed = evaluate(case_set(dht_case(), synthetic=False, label_status="human_reviewed"))
    assert reviewed.accuracy_claim_allowed and reviewed.warning is None
    assert json.loads(report_json(reviewed))["accuracy_claim_allowed"] is True


# --- CI gate: synthetic set against production recipes ----------------------------------


def test_synthetic_set_passes_production_recipes_as_a_harness_check():
    """Harness check, not an accuracy claim: the sketches and labels are synthetic, so 100 %
    here only says the recipes still do what their hand-written expectations say."""
    cases = load_case_set(SYNTHETIC)
    assert cases.synthetic and cases.label_status == "synthetic"
    report = evaluate(cases)
    assert report.headline.startswith("HARNESS CHECK ONLY") and not report.accuracy_claim_allowed
    assert gate_failures(report) == []
    assert {edge.recipe_id for edge in report.coverage} == {recipe_id(*k) for k in recipes()}
    assert all(edge.cases >= MIN_CASES_PER_EDGE for edge in report.coverage)
    assert {result.outcome for result in report.cases} == {"patch", "refused", "no_code_change"}
    for result in report.cases:
        # Known failures document real recipe bugs; each must still fail (else remove it).
        assert result.passed != bool(result.known_failure), result.case_id


def test_synthetic_sketches_say_they_are_synthetic():
    for case in load_case_set(SYNTHETIC).cases:
        for path, text in case.files.items():
            assert "ynthetic" in text.splitlines()[0], f"{case.id} {path}"


# --- CLI -------------------------------------------------------------------------------


def run_script(*args):
    return subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "evaluate_code_adapt.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=BACKEND,
        check=False,
    )


def test_script_runs_the_synthetic_gate(tmp_path):
    done = run_script("--out", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "HARNESS CHECK ONLY" in done.stdout and "Gate passed." in done.stdout
    assert (tmp_path / "harness-check.md").exists()
    assert json.loads((tmp_path / "harness-check.json").read_text("utf-8"))["synthetic"] is True


def test_script_fails_below_thresholds_and_rejects_bad_options(tmp_path):
    data = {
        "synthetic": False,
        "label_status": "agent_draft_needs_human_review",
        "description": "Synthetic sketch with a draft label, for the CLI test.",
        "cases": [
            {
                "id": "wrong-label",
                "from": "dht22",
                "to": "dht11",
                "description": "Label names the wrong line.",
                "files": {"a.ino": DHT_BEFORE},
                "expect": "patch",
                "expected_files": {"a.ino": {"changed_lines": [4]}},
            }
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "out"
    failed = run_script("--cases", str(path), "--out", str(out), "--no-coverage-gate")
    assert failed.returncode == 1
    assert "line_precision" in failed.stderr and "WARNING" in failed.stderr
    assert (out / "unreviewed-check.md").exists()
    relaxed = run_script(
        "--cases", str(path), "--out", str(out), "--no-coverage-gate", "--min-rate", "0"
    )
    assert relaxed.returncode == 0, relaxed.stderr
    assert run_script("--min", "accuracy=1").returncode == 2
    assert run_script("--cases", str(tmp_path / "missing.json")).returncode == 1
