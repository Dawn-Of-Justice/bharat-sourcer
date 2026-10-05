"""Project understanding, inferred quantities and requirements; all model output is synthetic."""

import json

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractedBom, GeminiExtractor, generation_schema
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import ConfirmJob, CreateJob, Job, PartRequirement

URL = "https://www.youtube.com/watch?v=abcdefghijk"
PROJECT = {
    "title": "Obstacle-avoiding robot car",
    "description": "A two-wheel Arduino robot that steers around obstacles (synthetic).",
    "summary": "Synthetic two-wheel obstacle-avoiding robot driven by an Arduino UNO.",
    "power": "2x 18650 cells (7.4 V)",
    "controller": "Arduino UNO (5 V logic)",
    "interfaces": ["PWM to motor driver", "GPIO trigger/echo"],
    "assumptions": ["Motor driver is fed from the battery pack"],
}
WHEELS = {
    "raw_name": "Geared DC motor wheel",
    "qty": None,
    "suggested_qty": 2,
    "qty_reason": "Two-wheel drive chassis needs one wheel per motor.",
    "requirements": [
        {
            "name": "operating voltage",
            "value": "6",
            "unit": "V",
            "operator": "at_least",
            "reason": "Driven from a 7.4 V pack through the L298N.",
        }
    ],
    "evidence": [{"timestamp": "00:42", "observation": "Wheels attached to both motors"}],
}
UNO = {
    "raw_name": "Arduino UNO",
    "qty": 1,
    "evidence": [{"timestamp": "00:10", "observation": "UNO board shown"}],
}


def extractor(body):
    def handle(request):
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(body)}]}}
                ]
            },
        )

    return GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(handle),
    )


def test_inferred_quantity_requirements_and_project_are_labelled():
    result = extractor({"project": PROJECT, "items": [UNO, WHEELS]}).extract(URL)
    uno, wheels = result.items
    assert (uno.qty, uno.qty_source, uno.qty_reason) == (1, "stated", None)
    assert (wheels.qty, wheels.qty_source) == (2, "inferred")
    assert "Two-wheel" in wheels.qty_reason
    [requirement] = wheels.requirements
    assert requirement.origin == "inferred"
    assert requirement.operator == "at_least" and "7.4 V" in requirement.reason
    assert result.project.summary.startswith("Synthetic")
    assert result.project.origin == "ai_inferred"


def test_job_saves_project_and_user_qty_edit_overrides_inference():
    jobs = JobService(extractor({"project": PROJECT, "items": [UNO, WHEELS]}))
    job, token = jobs.create(CreateJob(url=URL))
    jobs.extract(job.job_id)
    saved = jobs.get(job.job_id, token)
    assert saved.project.controller == "Arduino UNO (5 V logic)"
    assert saved.items[1].qty_source == "inferred"
    jobs.confirm(
        job.job_id, token, ConfirmJob(edits=[{"op": "update", "line_id": "L02", "qty": 4}])
    )
    confirmed = jobs.get(job.job_id, token)
    assert (confirmed.items[1].qty, confirmed.items[1].qty_source) == (4, "user")
    assert confirmed.items[1].qty_reason is None
    # Inferred requirements survive confirmation and reach sourcing/research.
    assert confirmed.items[1].requirements[0].origin == "inferred"


def test_unchanged_qty_edit_keeps_inferred_label():
    jobs = JobService(extractor({"items": [WHEELS]}))
    job, token = jobs.create(CreateJob(url=URL))
    jobs.extract(job.job_id)
    jobs.confirm(
        job.job_id, token, ConfirmJob(edits=[{"op": "update", "line_id": "L01", "qty": 2}])
    )
    assert jobs.get(job.job_id, token).items[0].qty_source == "inferred"


def test_older_snapshots_and_user_requirements_default_safely():
    legacy = {
        "job_id": "legacy",
        "input": {"url": URL},
        "items": [
            {
                "line_id": "L01",
                "raw_name": "LED",
                "qty": None,
                "requirements": [{"name": "colour", "value": "red"}],
            }
        ],
    }
    job = Job.model_validate(legacy)
    assert job.project is None
    assert job.items[0].qty_source == "stated"
    assert job.items[0].requirements[0].origin == "user"
    assert PartRequirement(name="x", value="y").reason is None


def test_generation_schema_asks_for_project_and_inference_fields():
    schema = json.dumps(generation_schema(ExtractedBom))
    for field in ("project", "suggested_qty", "qty_reason", "requirements", "assumptions"):
        assert field in schema


def test_title_and_description_are_ai_written_then_owner_editable():
    from fastapi.testclient import TestClient

    from bharat_sourcer.main import create_app

    app = create_app(
        Settings(_env_file=None, demo_mode=False, sourcing_enabled=False, gemini_api_key="x"),
        extractor({"project": PROJECT, "items": [UNO]}),
    )
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": URL}).json()
        path, headers = created["watch"], {"X-Job-Token": created["job_token"]}
        project = client.get(path, headers=headers).json()["project"]
        assert project["title"] == "Obstacle-avoiding robot car"
        assert (project["title_source"], project["description_source"]) == ("ai", "ai")
        edited = client.post(
            f"{path}/project", headers=headers, json={"title": "  My robot  "}
        ).json()["project"]
        assert (edited["title"], edited["title_source"]) == ("My robot", "user")
        assert edited["description_source"] == "ai"
        assert edited["summary"] == PROJECT["summary"]
        assert client.post(f"{path}/project", headers=headers, json={}).status_code == 422
        assert (
            client.post(f"{path}/project", headers=headers, json={"title": "   "}).status_code
            == 422
        )
        assert client.post(f"{path}/project", json={"title": "x"}).status_code in {401, 403, 404}


def test_project_edit_on_legacy_job_creates_context_and_list_shows_title():
    from fastapi.testclient import TestClient

    from bharat_sourcer.main import create_app
    from bharat_sourcer.storage import MemoryJobStore

    store = MemoryJobStore()
    jobs = JobService(extractor({"items": [UNO]}), store=store)
    job, token = jobs.create(CreateJob(url=URL))
    jobs.extract(job.job_id)
    assert jobs.get(job.job_id, token).project is None
    from bharat_sourcer.schemas import UpdateProject

    updated = jobs.update_project(job.job_id, token, UpdateProject(description="Desk lamp"))
    assert updated.project.description == "Desk lamp"
    assert updated.project.title is None and updated.project.summary is None

    from bharat_sourcer.access import ProjectSummary

    assert {"title", "description", "summary"} <= set(ProjectSummary.model_fields)
    demo = TestClient(create_app(Settings(_env_file=None, demo_mode=True)))
    created = demo.post("/v1/jobs", json={"url": "https://example.com"}).json()
    shown = demo.get(created["watch"], headers={"X-Job-Token": created["job_token"]}).json()
    assert shown["project"]["title"].startswith("Demo:")


def test_prompts_ask_for_measurable_requirements_not_restated_types():
    from bharat_sourcer.extraction import PAGE_PROMPT, PROMPT

    for prompt in (PROMPT, PAGE_PROMPT):
        assert "measurable specs" in prompt
        assert "Do not restate the part name" in prompt
        assert "do not add\nthem as items" in prompt
