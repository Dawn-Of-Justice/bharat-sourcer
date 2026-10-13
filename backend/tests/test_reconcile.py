"""Reconcile: one AI pass merges lines that are the same part and drops non-purchases.

Every BOM line, project and Gemini response here is SYNTHETIC test data, not verified
parts. No network call runs: Gemini answers come from httpx.MockTransport and the job
tests use a fake reconciler.
"""

import json

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobService
from bharat_sourcer.reconcile import (
    GeminiReconciler,
    MergeDraft,
    ReconcileDraft,
    RemovalDraft,
    apply,
    reconcile_items,
)
from bharat_sourcer.schemas import BomItem, CreateJob, Evidence, ProjectContext

PROJECT = ProjectContext(
    summary="Synthetic desk buddy: an ESP32-C3 drives one I2C OLED and reads a touch pad.",
    controller="ESP32-C3 Super Mini",
)


def line(line_id, name, source="video", **extra):
    if source == "code":
        evidence = Evidence(
            source="code",
            observation="Synthetic code evidence",
            file="main.ino",
            line=3,
            quote="#include <U8g2lib.h>",
            url="https://github.com/example/desk/blob/main/main.ino#L3",
        )
    else:
        evidence = Evidence(timestamp="00:10", observation=f"Synthetic video shows {name}")
    return BomItem(line_id=line_id, raw_name=name, evidence=[evidence], **extra)


def desk():
    return [
        line("L01", "ESP32-C3 Super Mini development board"),
        line("L02", "1.3-inch I2C OLED display module (SH1106)"),
        line("L03", "TTP223 capacitive touch switch module"),
        line("L04", "SSD1306 OLED display", source="code"),
        line("L05", "Onboard status LED"),
        line("L06", "Soldering iron"),
    ]


def test_merges_the_same_part_and_keeps_the_variant_conflict():
    draft = ReconcileDraft(
        merges=[MergeDraft(keep=1, same_as=[3], reason="The project has a single screen.")]
    )
    kept, changes = apply(desk(), draft)
    assert [item.line_id for item in kept] == ["L01", "L02", "L03", "L04", "L05"]
    oled = kept[1]
    assert oled.raw_name == "1.3-inch I2C OLED display module (SH1106)"
    assert {e.source for e in oled.evidence} == {"video", "code"}
    # SH1106 and SSD1306 are different chips: the maker still picks the variant.
    assert oled.conflicts[0].kind == "identity_mismatch" and oled.confidence == "check"
    assert changes[0].model_dump(exclude_none=True) == {
        "raw_name": "SSD1306 OLED display",
        "action": "merged",
        "into": "1.3-inch I2C OLED display module (SH1106)",
        "reason": "The project has a single screen.",
    }


def test_removes_built_in_parts_and_tools_within_the_guards():
    draft = ReconcileDraft(
        removals=[
            RemovalDraft(id=4, kind="built_in", part_of=0, reason="The board has this LED."),
            RemovalDraft(id=5, kind="tool", reason="A tool, not a part of the build."),
            # Built into a part that is not on the list: kept.
            RemovalDraft(id=2, kind="built_in", reason="Unclear host."),
        ]
    )
    kept, changes = apply(desk(), draft)
    assert [item.raw_name for item in kept][-1] == "SSD1306 OLED display"
    assert [(c.raw_name, c.kind, c.into) for c in changes] == [
        ("Onboard status LED", "built_in", "ESP32-C3 Super Mini development board"),
        ("Soldering iron", "tool", None),
    ]


def test_ignores_bad_ids_locked_lines_and_too_many_removals():
    items = desk()
    items[3].user_has_it = True
    draft = ReconcileDraft(
        merges=[
            MergeDraft(keep=1, same_as=[3], reason="Owned line: not merged."),
            MergeDraft(keep=1, same_as=[9], reason="Unknown id."),
            MergeDraft(keep=2, same_as=[2], reason="Self merge."),
        ],
        removals=[RemovalDraft(id=i, kind="not_a_part", reason="Too many.") for i in range(6)],
    )
    kept, changes = apply(items, draft)
    # A third of six lines at most; the owned line stays.
    assert len(changes) == 2 and all(c.action == "removed" for c in changes)
    assert "SSD1306 OLED display" in [item.raw_name for item in kept]


class FakeReconciler:
    def __init__(self, draft=None, error=None):
        self.draft, self.error, self.calls = draft, error, 0

    def review(self, items, project):
        self.calls += 1
        if self.error:
            raise self.error
        return self.draft


def test_failures_leave_the_list_unchanged():
    items = desk()
    assert reconcile_items(FakeReconciler(error=RuntimeError("boom")), items, PROJECT) == (
        items,
        [],
    )
    assert reconcile_items(FakeReconciler(None), items, PROJECT) == (items, [])
    assert reconcile_items(None, items, PROJECT) == (items, [])


class Extractor:
    def extract(self, url):
        return [
            line("L01", "1.3-inch I2C OLED display module (SH1106)"),
            line("L02", "TTP223 capacitive touch switch module"),
            line("L03", "SSD1306 OLED display"),
        ]


def test_job_extraction_saves_the_reconciled_list():
    reconciler = FakeReconciler(
        ReconcileDraft(merges=[MergeDraft(keep=0, same_as=[2], reason="One screen.")])
    )
    service = JobService(Extractor(), "synthetic-model", reconciler=reconciler)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    job = service.get(job.job_id, token)
    assert reconciler.calls == 1
    assert [item.line_id for item in job.items] == ["L01", "L02"]
    assert [(r.action, r.raw_name) for r in job.reconciled] == [("merged", "SSD1306 OLED display")]


def test_demo_jobs_never_reconcile():
    reconciler = FakeReconciler(ReconcileDraft())
    service = JobService(reconciler=reconciler)
    job, _ = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    assert reconciler.calls == 0


def test_gemini_reconciler_sends_the_whole_list_and_caches():
    bodies = []
    answer = {
        "parts": [{"id": 0, "function": "display", "connects_to": [1]}],
        "merges": [{"keep": 1, "same_as": [3], "name": None, "reason": "One screen."}],
        "removals": [],
    }

    def handle(request):
        bodies.append(json.loads(request.content))
        text = json.dumps(answer)
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    class DictCache(dict):
        def set(self, key, value, ttl_s):
            self[key] = value

    cache = DictCache()
    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    reconciler = GeminiReconciler(settings, transport=httpx.MockTransport(handle), cache=cache)
    first = reconciler.review(desk(), PROJECT)
    second = reconciler.review(desk(), PROJECT)
    assert first == second and first is not None and first.merges[0].same_as == [3]
    assert len(bodies) == 1
    sent = json.loads(bodies[0]["contents"][0]["parts"][0]["text"])
    assert [entry["id"] for entry in sent["lines"]] == list(range(6))
    assert sent["lines"][3]["evidence"][0].startswith("[code main.ino:3]")


def test_a_duplicate_removal_is_applied_as_a_merge():
    draft = ReconcileDraft(
        removals=[
            RemovalDraft(id=3, kind="duplicate", part_of=1, reason="The single OLED again."),
            RemovalDraft(id=2, kind="duplicate", reason="No part_of: kept."),
        ]
    )
    kept, changes = apply(desk(), draft)
    assert len(kept) == 5 and "TTP223 capacitive touch switch module" in [i.raw_name for i in kept]
    assert {e.source for e in kept[1].evidence} == {"video", "code"}
    assert [(c.action, c.raw_name, c.into) for c in changes] == [
        ("merged", "SSD1306 OLED display", "1.3-inch I2C OLED display module (SH1106)")
    ]
