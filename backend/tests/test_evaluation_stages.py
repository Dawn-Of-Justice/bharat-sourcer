"""Gold-set loading, label-status gating and the post-extraction stage metrics."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from bharat_sourcer.evaluation import (
    EvaluationCase,
    EvaluationSet,
    GoldProject,
    GoldSubstitution,
    Prediction,
    evaluate,
    evaluate_case,
    load_cases,
    load_gold_projects,
    metrics_json,
    render_markdown,
    score_stages,
    url_key,
)
from bharat_sourcer.schemas import BomItem

BACKEND = Path(__file__).resolve().parents[1]
GOLD = BACKEND / "evaluation" / "gold"
PAGE = "https://learn.adafruit.com/example-guide"


def item(line, name, qty=None):
    return BomItem(line_id=line, raw_name=name, qty=qty)


def page_case(*parts, case_id="c1", **extra):
    return EvaluationCase(id=case_id, url=PAGE, source_type="page", parts=list(parts), **extra)


def a_set(*cases, label_status="human_reviewed"):
    return EvaluationSet(
        synthetic=False, description="test labels", label_status=label_status, cases=list(cases)
    )


# --- quantity rules and page cases ---------------------------------------------------------


def test_quantity_exact_for_pieces_and_ten_percent_for_lengths():
    case = page_case(
        {"name": "74LS00", "qty": 2},
        {"name": "Tubing", "qty": 30, "qty_unit": "cm"},
        {"name": "Wire", "qty": 100, "qty_unit": "cm"},
        {"name": "Strip", "qty": 2, "qty_unit": "m"},
    )
    result = evaluate_case(
        case,
        [
            item("L1", "74LS00", 3),
            item("L2", "Tubing", 33),
            item("L3", "Wire", 89),
            item("L4", "Strip", 2),
        ],
    )
    assert [m.qty_correct for m in result.matches] == [False, True, False, True]
    assert [m.qty_rule for m in result.matches] == [
        "exact",
        "within_10pct",
        "within_10pct",
        "within_10pct",
    ]
    assert result.matches[1].qty_unit == "cm"
    assert result.metrics.quantity_accuracy == 0.5


def test_page_cases_accept_public_pages_only():
    assert page_case().source_type == "page"
    for bad in ("ftp://example.com/x", "https://user:pw@example.com/x", "https://:8080/x"):
        with pytest.raises(ValidationError):
            EvaluationCase(id="c1", url=bad, source_type="page", parts=[])
    with pytest.raises(ValidationError):  # video stays the default and needs YouTube
        EvaluationCase(id="c1", url=PAGE, parts=[])
    with pytest.raises(ValidationError):
        page_case({"name": "Tube", "qty": 1, "qty_unit": "ft"})


# --- safety flags --------------------------------------------------------------------------


def test_safety_flag_recall_per_code_and_gate():
    cases = a_set(
        page_case({"name": "Relay"}, case_id="a", must_flag=["MAINS", "LIPO"]),
        page_case({"name": "Strip"}, case_id="b", must_flag=["LIPO"]),
        page_case({"name": "Sensor"}, case_id="c", must_flag=["MAINS"]),
    )
    predictions = {
        "a": Prediction(case_id="a", safety_flags=[{"code": "MAINS"}, {"code": "LEVEL_SHIFT"}]),
        "b": Prediction(case_id="b", safety_flags=[{"code": "LIPO", "line_id": "L1"}]),
        "c": Prediction(case_id="c"),  # stage not produced: not scored
    }
    report = evaluate(cases, predictions)
    a = report.cases[0]
    assert a.safety_missed == ["LIPO"] and a.safety_unexpected == ["LEVEL_SHIFT"]
    assert a.stage_metrics.safety_gate_passed is False
    assert report.cases[1].stage_metrics.safety_gate_passed is True
    assert report.cases[2].stage_counts.safety_cases == 0
    sc, sm = report.stage_counts, report.stage_metrics
    assert sc.safety_cases == 2 and sc.safety_false_flags == 1
    assert sc.safety_expected == {"MAINS": 1, "LIPO": 2}
    assert sm.safety_recall_by_code == {"MAINS": 1.0, "LIPO": 0.5}
    assert sm.safety_recall == round(2 / 3, 4)
    assert sm.safety_gate_passed is False
    markdown = render_markdown(report)
    assert "gate FAILED" in markdown and "safety flag missed: LIPO" in markdown


def test_safety_gate_is_none_without_expected_flags():
    result = score_stages(page_case(), Prediction(case_id="c1", safety_flags=[]))
    assert result.stage_metrics.safety_recall is None
    assert result.stage_metrics.safety_gate_passed is None


# --- substitution grades -------------------------------------------------------------------


def test_grade_range_order_and_distance():
    gold = GoldSubstitution(original="PowerSwitch Tail II", grade_range=["C", "X"])
    assert [gold.distance(g) for g in "ABCDX"] == [2, 1, 0, 0, 0]
    assert GoldSubstitution(original="x", grade_range=["B"]).distance("C") == 1
    with pytest.raises(ValidationError):
        GoldSubstitution(original="x", grade_range=["D", "B"])
    with pytest.raises(ValidationError):
        GoldSubstitution(original="x", grade_range=[])


def test_grade_accuracy_exact_within_one_and_missing():
    case = page_case(
        gold_substitutions=[
            {"original": "PowerSwitch Tail II", "grade_range": ["C", "X"]},
            {"original": "A4988 stepper driver", "aliases": ["A4988"], "grade_range": ["B"]},
            {"original": "BME280 sensor", "grade_range": ["B", "C"]},
            {"original": "MagTag", "grade_range": ["A"]},
        ]
    )
    prediction = Prediction(
        case_id="c1",
        substitutions=[
            {"original": "PowerSwitch Tail II", "substitute": "SSR", "grade": "D"},
            {"original": "A4988", "substitute": "DRV8825", "grade": "C"},
            {"original": "BME280 sensor module", "substitute": "GY-BME280", "grade": "X"},
            {"original": "MagTag", "grade": None},  # ungraded counts as missing
        ],
    )
    result = score_stages(case, prediction)
    assert [(g.exact, g.within_one) for g in result.grades] == [
        (True, True),
        (False, True),
        (False, False),
        (False, False),
    ]
    assert result.grades[3].predicted is None
    c, m = result.stage_counts, result.stage_metrics
    assert (c.grades_considered, c.grades_exact, c.grades_within_one, c.grades_missing) == (
        4,
        1,
        2,
        1,
    )
    assert m.grade_exact_accuracy == 0.25 and m.grade_within_one_accuracy == 0.5
    # No gold substitutions: the stage is not scored for the case.
    assert score_stages(page_case(), prediction).stage_counts.grade_cases == 0


def test_each_predicted_substitution_is_used_once():
    case = page_case(
        gold_substitutions=[
            {"original": "LED strip", "grade_range": ["A"]},
            {"original": "LED strip", "grade_range": ["B"]},
        ]
    )
    prediction = Prediction(case_id="c1", substitutions=[{"original": "LED strip", "grade": "A"}])
    result = score_stages(case, prediction)
    assert [g.predicted for g in result.grades] == ["LED strip", None]


# --- offer links ---------------------------------------------------------------------------


def test_url_key_normalises_case_fragment_and_trailing_slash():
    assert url_key("HTTPS://Robu.in/Product/x/#reviews") == url_key("https://robu.in/Product/x")
    assert url_key("https://robu.in:443/a") == url_key("https://robu.in/a")
    assert url_key("https://robu.in/a?v=1") != url_key("https://robu.in/a?v=2")


def test_hallucinated_url_rate_and_link_validity():
    ok = {"http_status": 200, "title_match": True, "inr_price": True}
    prediction = Prediction(
        case_id="c1",
        offers=[
            {"url": "https://robu.in/p/a/"},
            {"url": "https://robu.in/p/b"},
            {"url": "https://robu.in/p/c"},
            {"url": "https://invented.example/p"},
        ],
        listings=[
            {"url": "https://robu.in/p/a", **ok},
            {"url": "https://robu.in/p/b", **ok, "inr_price": False},
            {"url": "https://robu.in/p/c"},  # never checked
        ],
    )
    result = score_stages(page_case(), prediction)
    c, m = result.stage_counts, result.stage_metrics
    assert (c.offers, c.offers_hallucinated, c.offers_checked, c.offers_valid) == (4, 1, 2, 1)
    assert m.hallucinated_url_rate == 0.25 and m.link_validity == 0.5
    assert result.hallucinated_urls == ["https://invented.example/p"]
    assert result.invalid_links == ["https://robu.in/p/b"]
    # Offers without any listings set are all hallucinated.
    bare = score_stages(page_case(), Prediction(case_id="c1", offers=[{"url": "https://x.in"}]))
    assert bare.stage_metrics.hallucinated_url_rate == 1.0
    assert bare.stage_metrics.link_validity is None


def test_failed_extraction_skips_stages():
    cases = a_set(page_case(case_id="a", must_flag=["MAINS"]))
    report = evaluate(
        cases,
        {"a": Prediction(case_id="a", error_code="UPSTREAM_TIMEOUT", safety_flags=[])},
    )
    assert report.stage_counts.safety_cases == 0
    assert report.stage_metrics.safety_gate_passed is None


# --- label status gating -------------------------------------------------------------------


@pytest.mark.parametrize("status", [None, "agent_draft_needs_human_review"])
def test_unreviewed_labels_never_get_an_accuracy_headline(status):
    cases = a_set(page_case({"name": "LED"}), label_status=status)
    report = evaluate(cases, {"c1": Prediction(case_id="c1", items=[item("L1", "LED")])})
    assert not report.accuracy_claim_allowed
    assert report.headline.startswith("UNREVIEWED LABELS")
    assert report.warning and "do not report them as accuracy" in report.warning
    markdown = render_markdown(report)
    assert markdown.startswith("# Extraction evaluation (unreviewed labels)")
    assert "> WARNING:" in markdown and "## Aggregate" not in markdown
    metrics = json.loads(metrics_json(report))
    assert metrics["accuracy_claim_allowed"] is False
    assert metrics["cases"]["c1"]["metrics"]["recall"] == 1.0


def test_reviewed_labels_allow_the_headline():
    report = evaluate(a_set(page_case({"name": "LED"})), {"c1": Prediction(case_id="c1")})
    assert report.accuracy_claim_allowed and report.warning is None
    assert "labelled real-project case(s)" in report.headline
    assert "## Aggregate" in render_markdown(report)


def test_synthetic_label_status_must_match_flag():
    with pytest.raises(ValidationError, match="synthetic"):
        a_set(page_case(), label_status="synthetic")
    with pytest.raises(ValidationError, match="synthetic"):
        EvaluationSet(
            synthetic=True,
            description="x",
            label_status="human_reviewed",
            cases=[page_case()],
        )


# --- gold files ----------------------------------------------------------------------------


def gold(project_id="p1", status="agent_draft_needs_human_review", **extra):
    data = {
        "project_id": project_id,
        "title": "T",
        "creator": "C",
        "kind": "text",
        "label_status": status,
        "inputs": {"url": PAGE},
        "gold_bom": [{"name": "LED", "qty": 1}],
    }
    data.update(extra)
    return data


def write_gold(tmp_path, projects, index_status="agent_draft_needs_human_review", entries=None):
    for project in projects:
        (tmp_path / f"{project['project_id']}.json").write_text(json.dumps(project))
    entries = entries or [
        {
            "project_id": p["project_id"],
            "file": f"{p['project_id']}.json",
            "kind": p["kind"],
            "label_status": p["label_status"],
        }
        for p in projects
    ]
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"description": "d", "label_status": index_status, "projects": entries})
    )
    return index


def test_gold_project_status_rules():
    assert GoldProject.model_validate(gold()).case().source_type == "page"
    with pytest.raises(ValidationError, match="non-empty gold_bom"):
        GoldProject.model_validate(gold(gold_bom=[]))
    with pytest.raises(ValidationError, match="must not carry gold labels"):
        GoldProject.model_validate(gold(status="needs_human_labelling"))
    with pytest.raises(ValidationError, match="two independent reviewers"):
        GoldProject.model_validate(gold(status="human_reviewed", reviewed_by=["a"]))
    reviewed = gold(status="human_reviewed", reviewed_by=["a", "b"])
    assert GoldProject.model_validate(reviewed).label_status == "human_reviewed"
    with pytest.raises(ValidationError):  # video projects need a YouTube URL
        GoldProject.model_validate(gold(kind="video"))


def test_gold_index_loads_excludes_unlabelled_and_takes_weakest_status(tmp_path):
    video = gold(
        "v1",
        status="needs_human_labelling",
        kind="video",
        inputs={"url": "https://www.youtube.com/watch?v=abcdefghijk"},
        gold_bom=[],
    )
    reviewed = gold("p2", status="human_reviewed", reviewed_by=["a", "b"])
    index = write_gold(tmp_path, [gold(), reviewed, video], index_status="human_reviewed")
    cases = load_cases(index)
    assert [c.id for c in cases.cases] == ["p1", "p2"]
    assert cases.excluded_cases == ["v1"]
    assert cases.label_status == "agent_draft_needs_human_review"
    assert not cases.accuracy_claim_allowed()


def test_gold_index_all_reviewed_allows_accuracy(tmp_path):
    index = write_gold(
        tmp_path,
        [gold(status="human_reviewed", reviewed_by=["a", "b"])],
        index_status="human_reviewed",
    )
    assert load_cases(index).accuracy_claim_allowed()


def test_gold_index_rejects_mismatch_traversal_and_unlabelled_only(tmp_path):
    project = gold()
    entry = {"project_id": "p1", "file": "p1.json", "kind": "text"}
    index = write_gold(tmp_path, [project], entries=[{**entry, "label_status": "human_reviewed"}])
    with pytest.raises(ValueError, match="does not match"):
        load_cases(index)
    index = write_gold(
        tmp_path,
        [project],
        entries=[{**entry, "file": "../p1.json", "label_status": project["label_status"]}],
    )
    with pytest.raises(ValueError):
        load_cases(index)
    video = gold(
        "v1",
        status="needs_human_labelling",
        kind="video",
        inputs={"url": "https://www.youtube.com/watch?v=abcdefghijk"},
        gold_bom=[],
    )
    with pytest.raises(ValueError, match="no labelled projects"):
        load_cases(write_gold(tmp_path, [video]))


# --- shipped gold set ----------------------------------------------------------------------


def test_shipped_gold_set_is_an_unreviewed_draft():
    index, projects = load_gold_projects(GOLD / "index.json")
    assert index.label_status == "agent_draft_needs_human_review"
    assert "not human gold" in index.description.lower()
    text = [p for p in projects if p.kind == "text"]
    videos = [p for p in projects if p.kind == "video"]
    assert len(text) == 14 and len(videos) >= 5
    for project in text:
        assert project.label_status == "agent_draft_needs_human_review"
        assert project.source and project.source.fetched_on and project.source.url
        assert project.reviewed_by == []
    for project in videos:
        assert project.label_status == "needs_human_labelling" and not project.gold_bom
    assert {p.plan_row for p in text} == set(range(1, 15))
    files = {path.name for path in GOLD.glob("*.json")} - {"index.json"}
    assert files == {entry.file for entry in index.projects}

    cases = load_cases(GOLD / "index.json")
    assert not cases.accuracy_claim_allowed()
    report = evaluate(cases, {c.id: Prediction(case_id=c.id) for c in cases.cases})
    assert report.headline.startswith("UNREVIEWED LABELS")
    assert report.metrics.recall == 0.0


def test_script_scores_gold_set_with_a_warning(tmp_path):
    cases = load_cases(GOLD / "index.json")
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    for case in cases.cases:
        prediction = Prediction(
            case_id=case.id,
            items=[item("L01", case.parts[0].name, case.parts[0].qty)],
            safety_flags=[{"code": code} for code in case.must_flag],
        )
        (predictions / f"{case.id}.json").write_text(prediction.model_dump_json())
    out = tmp_path / "out"
    done = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts" / "evaluate_extraction.py"),
            "--cases",
            str(GOLD / "index.json"),
            "--predictions",
            str(predictions),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=BACKEND,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "UNREVIEWED LABELS" in done.stdout and "WARNING" in done.stderr
    assert not (out / "report.md").exists()
    metrics = json.loads((out / "unreviewed-check-metrics.json").read_text(encoding="utf-8"))
    assert metrics["accuracy_claim_allowed"] is False
    assert metrics["stage_metrics"]["safety_gate_passed"] is True
    assert len(metrics["excluded_cases"]) >= 5
    assert (out / "unreviewed-check.md").exists() and (out / "unreviewed-check.json").exists()
