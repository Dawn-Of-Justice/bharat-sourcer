"""Build page: the parts checklist and the AI build guide.

Every BOM line, project and Gemini response here is SYNTHETIC test data, not verified
parts or build steps. No network call runs: Gemini answers come from httpx.MockTransport.
"""

import json
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from bharat_sourcer import build_guide as bg
from bharat_sourcer.config import Settings
from bharat_sourcer.dispatch import Work, work_once
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    BuildGuide,
    CreateJob,
    Evidence,
    ProjectContext,
    Report,
    ReportLine,
    now,
)
from bharat_sourcer.sourcing.cache import MemoryCache

REPO = "https://github.com/maker/synthetic-lamp"


def items():
    return [
        BomItem(
            line_id="L01",
            raw_name="Synthetic ESP32 board",
            evidence=[Evidence(timestamp="01:05", observation="Synthetic: board shown on desk")],
        ),
        BomItem(
            line_id="L02",
            raw_name="Synthetic LED ring",
            evidence=[Evidence(timestamp="02:30", observation="Synthetic: ring soldered")],
        ),
        BomItem(line_id="L03", raw_name="Synthetic USB cable"),
    ]


def step(title, line_ids=(), timestamp="", caution="", detail="Synthetic detail."):
    return {
        "title": title,
        "detail": detail,
        "line_ids": list(line_ids),
        "timestamp": timestamp,
        "caution": caution,
    }


GOOD = {
    "steps": [
        step("Check the parts", ["L01", "L02", "L03"], "1:05"),
        step("Solder the LED ring", ["L02", "L99"], "02:30", "Hot iron (synthetic)."),
        step("Flash the code", ["L01", "L03"], "09:59"),
        step("Test the lamp", [], "not a time"),
    ]
}


def reply(body, finish="STOP"):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": finish, "content": {"parts": [{"text": json.dumps(body)}]}}
            ],
            "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 600},
        },
    )


class Gemini:
    """Answers each call with the next scripted response; records what was sent."""

    def __init__(self, *responses):
        self.responses = list(responses) or [reply(GOOD)]
        self.sent: list[dict] = []

    def __call__(self, request):
        self.sent.append(json.loads(request.content))
        index = min(len(self.sent), len(self.responses)) - 1
        return self.responses[index]

    def document(self):
        return json.loads(self.sent[-1]["contents"][0]["parts"][0]["text"])


def setup(gemini=None, cache=None, status="done", lines=items, **settings):
    values = {"_env_file": None, "demo_mode": True, "gemini_api_key": "test"} | settings
    app = create_app(Settings(**values))
    service = app.state.job_service
    guides = app.state.build_guide_service
    guides.transport = httpx.MockTransport(gemini or Gemini())
    guides.cache = cache
    job, token = service.create(CreateJob(url=REPO))

    def seed(record):
        record.job.demo = False
        record.job.status = status
        record.job.items = lines()
        record.job.project = ProjectContext(summary="A synthetic desk lamp with an LED ring.")
        record.job.report = Report(
            demo=False,
            summary="Synthetic report.",
            lines=[
                ReportLine(item=item.model_copy(deep=True), sourcing_status="not_run")
                for item in record.job.items
            ],
        )

    service.store.mutate(job.job_id, seed)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, app, job.job_id


# -- parts checklist ------------------------------------------------------------------------
def test_checklist_ticks_untick_and_is_idempotent():
    client, _, job_id = setup()
    url = f"/v1/jobs/{job_id}/build-progress"
    first = client.post(url, json={"line_id": "L02", "received": True})
    assert first.status_code == 200 and first.json()["build_received"] == ["L02"]
    client.post(url, json={"line_id": "L01", "received": True})
    again = client.post(url, json={"line_id": "L02", "received": True}).json()
    assert again["build_received"] == ["L02", "L01"]  # unchanged order on a repeat
    off = client.post(url, json={"line_id": "L02", "received": False}).json()
    assert off["build_received"] == ["L01"]
    assert client.post(url, json={"line_id": "L02", "received": False}).json()[
        "build_received"
    ] == ["L01"]
    assert client.get(f"/v1/jobs/{job_id}").json()["build_received"] == ["L01"]


def test_checklist_errors():
    client, _, job_id = setup()
    url = f"/v1/jobs/{job_id}/build-progress"
    unknown = client.post(url, json={"line_id": "L42", "received": True})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "INVALID_LINE"
    stranger = client.post(
        url, json={"line_id": "L01", "received": True}, headers={"X-Job-Token": "x" * 40}
    )
    assert stranger.status_code == 404
    missing = client.post(
        "/v1/jobs/00000000-0000-0000-0000-000000000000/build-progress",
        json={"line_id": "L01", "received": True},
    )
    assert missing.status_code == 404
    review, _, other = setup(status="awaiting_confirmation")
    conflict = review.post(
        f"/v1/jobs/{other}/build-progress", json={"line_id": "L01", "received": True}
    )
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "INVALID_STATE"


def test_removed_lines_leave_the_checklist_and_make_the_guide_stale():
    client, _, job_id = setup()
    for line_id in ("L01", "L02"):
        client.post(
            f"/v1/jobs/{job_id}/build-progress", json={"line_id": line_id, "received": True}
        )
    client.post(f"/v1/jobs/{job_id}/build-guide")
    assert client.get(f"/v1/jobs/{job_id}/build-guide").json()["status"] == "ready"
    response = client.post(
        f"/v1/jobs/{job_id}/confirm", json={"edits": [{"op": "remove", "line_id": "L02"}]}
    )
    assert response.status_code == 202
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] == "done" and job["build_received"] == ["L01"]
    stale = client.get(f"/v1/jobs/{job_id}/build-guide").json()
    assert stale["status"] == "stale" and stale["message"] == bg.STALE and stale["steps"]


# -- build guide ----------------------------------------------------------------------------
def test_generation_validates_steps_and_records_cost():
    gemini = Gemini()
    client, app, job_id = setup(gemini)
    assert client.get(f"/v1/jobs/{job_id}/build-guide").status_code == 404
    started = client.post(f"/v1/jobs/{job_id}/build-guide")
    assert started.status_code == 200 and started.json()["status"] == "pending"
    guide = client.get(f"/v1/jobs/{job_id}/build-guide").json()
    assert guide["status"] == "ready" and guide["demo"] is False
    assert guide["message"] == bg.AI_NOTICE
    steps = guide["steps"]
    assert steps[0]["title"] == "Check the parts"
    # "1:05" matches the stored "01:05"; unknown or invented times are cleared.
    assert [s["timestamp"] for s in steps] == ["01:05", "02:30", None, None]
    assert steps[1]["line_ids"] == ["L02"]  # L99 is not on the job
    assert steps[1]["caution"] == "Hot iron (synthetic)." and steps[0]["caution"] is None
    assert all(s["origin"] == "ai_inferred" for s in steps)
    sent = gemini.document()
    assert [line["line_id"] for line in sent["lines"]] == ["L01", "L02", "L03"]
    assert sent["lines"][0]["evidence"] == [
        {"observation": "Synthetic: board shown on desk", "timestamp": "01:05"}
    ]
    assert "fileData" not in json.dumps(gemini.sent[0])  # text only, no video
    assert "untrusted data" in gemini.sent[0]["systemInstruction"]["parts"][0]["text"]
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["build_guide"]["status"] == "ready"
    assert job["cost_estimate"]["calls_by_site"] == {"build_guide": 1}
    stored = app.state.job_service.store.get(job_id)
    assert stored.build_guide_run_id is None and stored.build_guide_lease_until is None
    again = client.post(f"/v1/jobs/{job_id}/build-guide").json()
    assert again["status"] == "ready" and len(gemini.sent) == 1


def test_long_text_is_cut_and_too_few_steps_fail():
    long = {"steps": [step("T" * 300, detail="d" * 2000, caution="c" * 500)] * 3}
    client, _, job_id = setup(Gemini(reply(long)))
    client.post(f"/v1/jobs/{job_id}/build-guide")
    steps = client.get(f"/v1/jobs/{job_id}/build-guide").json()["steps"]
    assert len(steps[0]["title"]) == 120 and len(steps[0]["detail"]) == 600
    assert len(steps[0]["caution"]) == 200
    few = Gemini(reply({"steps": [step("Only one")]}))
    other, _, other_id = setup(few)
    other.post(f"/v1/jobs/{other_id}/build-guide")
    result = other.get(f"/v1/jobs/{other_id}/build-guide").json()
    assert result["status"] == "failed" and result["message"] == bg.GENERATION_FAILED
    assert len(few.sent) == 2  # retried once


def test_max_tokens_is_retried_once_then_fails_and_can_be_restarted():
    gemini = Gemini(reply(GOOD, finish="MAX_TOKENS"))
    client, _, job_id = setup(gemini)
    client.post(f"/v1/jobs/{job_id}/build-guide")
    result = client.get(f"/v1/jobs/{job_id}/build-guide").json()
    assert result["status"] == "failed" and result["message"] == bg.GENERATION_FAILED
    assert len(gemini.sent) == 2
    recovered = Gemini(reply(GOOD, finish="MAX_TOKENS"), reply(GOOD))
    second, _, other = setup(recovered)
    second.post(f"/v1/jobs/{other}/build-guide")
    assert second.get(f"/v1/jobs/{other}/build-guide").json()["status"] == "ready"
    assert len(recovered.sent) == 2
    # A failed guide can be requested again.
    assert client.post(f"/v1/jobs/{job_id}/build-guide").json()["status"] == "pending"


def test_cached_by_parts_and_input():
    cache = MemoryCache()
    gemini = Gemini()
    client, _, job_id = setup(gemini, cache=cache)
    client.post(f"/v1/jobs/{job_id}/build-guide")
    assert len(gemini.sent) == 1
    unused = Gemini()
    second, _, other = setup(unused, cache=cache)
    second.post(f"/v1/jobs/{other}/build-guide")
    hit = second.get(f"/v1/jobs/{other}/build-guide").json()
    assert hit["status"] == "ready" and hit["steps"][0]["timestamp"] == "01:05"
    assert unused.sent == []
    assert second.get(f"/v1/jobs/{other}").json()["cost_estimate"]["cache_hits"] == {
        "build_guide": 1
    }


# -- step timestamps ----------------------------------------------------------------------
def station():
    """A synthetic weather-station parts list: each part seen at its own video moment."""

    def line(line_id, name, timestamp, observation):
        return BomItem(
            line_id=line_id,
            raw_name=name,
            evidence=[Evidence(timestamp=timestamp, observation=f"Synthetic: {observation}")],
        )

    return [
        line("L01", "Synthetic ESP32 board", "00:12", "ESP32 board shown on the bench"),
        line("L02", "Synthetic BME280 sensor", "00:20", "sensor soldered to header pins"),
        line("L03", "Synthetic OLED display", "00:28", "display wired to the board"),
        line("L04", "Synthetic 3D printed case", "00:35", "black 3D printed compact enclosure"),
    ]


def guide_times(answer):
    client, _, job_id = setup(Gemini(reply(answer)), lines=station)
    client.post(f"/v1/jobs/{job_id}/build-guide")
    guide = client.get(f"/v1/jobs/{job_id}/build-guide").json()
    assert guide["status"] == "ready"
    return [s["timestamp"] for s in guide["steps"]]


def test_one_part_moment_copied_onto_every_step_is_dropped():
    # The reported bug: every step came back with the enclosure's evidence time (00:35),
    # which is where that part is seen, not where each step happens.
    answer = {
        "steps": [
            step("Check the parts", ["L01", "L02", "L03", "L04"], "00:35"),
            step("Solder the sensor headers", ["L02"], "00:35"),
            step("Wire the display to the board", ["L01", "L03"], "00:35"),
            step("Flash the weather station code", ["L01"], "00:35"),
            step("Test the readings", ["L01", "L02", "L03"], "00:35"),
            step("Fit everything into the case", ["L04"], "00:35"),
        ]
    }
    assert guide_times(answer) == [None] * 6


def test_each_step_keeps_its_own_moment_from_its_own_parts():
    answer = {
        "steps": [
            step("Solder the sensor headers", ["L02"], "00:20"),
            step("Wire the display to the board", ["L01", "L03"], "0:28"),
            step("Flash the weather station code", ["L01"], ""),
            step("Fit everything into the case", ["L04"], "00:35"),
        ]
    }
    assert guide_times(answer) == ["00:20", "00:28", None, "00:35"]


def test_shared_or_borrowed_moments_are_cleared():
    answer = {
        "steps": [
            # Two steps cannot both happen at one moment: neither keeps it.
            step("Solder the sensor headers", ["L02"], "00:20"),
            step("Test the sensor", ["L02"], "0:20"),
            # The case's moment does not show flashing the board, a part it does not use.
            step("Flash the weather station code", ["L01"], "00:35"),
            # A step with no parts has no evidence of its own to cite.
            step("Check the serial monitor", [], "00:12"),
            step("Wire the display to the board", ["L01", "L03"], "00:28"),
        ]
    }
    assert guide_times(answer) == [None, None, None, None, "00:28"]


def test_stored_guides_drop_timestamps_shared_by_several_steps():
    # Guides saved before the guard (as on the reported run) are cleaned when loaded.
    stored = {
        "status": "ready",
        "steps": [
            {"title": "Check the parts", "timestamp": "00:35"},
            {"title": "Solder the sensor", "timestamp": "00:35"},
            {"title": "Flash the code", "timestamp": "0:00:35"},
            {"title": "Fit the case", "timestamp": "01:10"},
        ],
    }
    guide = BuildGuide.model_validate(stored)
    assert [s.timestamp for s in guide.steps] == [None, None, None, "01:10"]


def test_prompt_asks_for_step_specific_distinct_moments():
    gemini = Gemini()
    client, _, job_id = setup(gemini)
    client.post(f"/v1/jobs/{job_id}/build-guide")
    prompt = " ".join(gemini.sent[0]["systemInstruction"]["parts"][0]["text"].split())
    assert "never give two steps the same timestamp" in prompt
    assert "this step's line_ids" in prompt


def test_owner_only_needs_a_finished_job_and_respects_settings():
    client, _, job_id = setup()
    stranger = {"X-Job-Token": "x" * 40}
    assert client.post(f"/v1/jobs/{job_id}/build-guide", headers=stranger).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/build-guide", headers=stranger).status_code == 404
    review, _, other = setup(status="awaiting_confirmation")
    response = review.post(f"/v1/jobs/{other}/build-guide")
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE"
    off, _, third = setup(build_guide_enabled=False)
    assert off.post(f"/v1/jobs/{third}/build-guide").json()["message"] == bg.DISABLED
    gemini = Gemini()
    keyless, _, fourth = setup(gemini, gemini_api_key=None)
    keyless.post(f"/v1/jobs/{fourth}/build-guide")
    assert keyless.get(f"/v1/jobs/{fourth}/build-guide").json()["message"] == bg.NOT_CONFIGURED
    assert gemini.sent == []


def test_expired_lease_fails_and_work_once_runs_build_guide_tasks():
    gemini = Gemini()
    client, app, job_id = setup(gemini)
    service, guides = app.state.job_service, app.state.build_guide_service

    def interrupted(record):
        record.job.build_guide = bg.pending(record.job)
        record.build_guide_run_id = "lost-worker"
        record.build_guide_lease_until = now() - timedelta(seconds=1)

    service.store.mutate(job_id, interrupted)
    result = client.get(f"/v1/jobs/{job_id}/build-guide").json()
    assert result["status"] == "failed" and result["message"] == bg.INTERRUPTED

    def queued(record):
        record.job.build_guide = bg.pending(record.job)
        record.build_guide_run_id = None
        record.build_guide_lease_until = now() + timedelta(seconds=60)

    service.store.mutate(job_id, queued)
    work = Work(job_id=job_id, kind="build_guide")
    assert work_once(service, None, work, None, guides) is True
    assert service.store.get(job_id).job.build_guide.status == "ready"


def test_demo_jobs_get_a_labelled_fixture_without_any_model_call():
    gemini = Gemini()
    app = create_app(Settings(_env_file=None, demo_mode=True, gemini_api_key="test"))
    app.state.build_guide_service.transport = httpx.MockTransport(gemini)
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
        headers = {"X-Job-Token": created["job_token"]}
        base = created["watch"]
        early = client.post(base + "/build-guide", headers=headers)
        assert early.status_code == 409
        client.post(base + "/confirm", json={"edits": []}, headers=headers)
        assert client.get(base, headers=headers).json()["status"] == "done"
        result = client.post(base + "/build-guide", headers=headers).json()
    assert result["status"] == "ready" and result["demo"] is True
    assert result["message"] == bg.DEMO
    assert all("(demo)" in s["title"] for s in result["steps"])
    assert {i for s in result["steps"] for i in s["line_ids"]} <= {"L01", "L02", "L03"}
    assert gemini.sent == []
