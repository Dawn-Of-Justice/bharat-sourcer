from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import ConfirmJob, CreateJob


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, demo_mode=True))) as client:
        yield client


def create_job(client):
    response = client.post("/v1/jobs", json={"url": "https://example.com/build"})
    assert response.status_code == 202
    created = response.json()
    return created["watch"], {"X-Job-Token": created["job_token"]}


def test_job_lifecycle_and_edits(client):
    path, headers = create_job(client)
    draft = client.get(path, headers=headers).json()
    assert draft["status"] == "awaiting_confirmation"
    assert draft["demo"] is True
    response = client.post(
        f"{path}/confirm",
        headers=headers,
        json={
            "edits": [
                {"op": "update", "line_id": "L03", "qty": 8},
                {"op": "have_it", "line_id": "L01"},
                {"op": "remove", "line_id": "L02"},
                {"op": "add", "raw_name": "Breadboard", "qty": 1},
            ]
        },
    )
    assert response.status_code == 202
    job = client.get(path, headers=headers).json()
    assert job["status"] == "done"
    assert [item["line_id"] for item in job["items"]] == ["L01", "L03", "L04"]
    assert job["items"][1]["qty"] == 8
    assert job["report"]["lines"][0]["sourcing_status"] == "already_owned"
    assert job["report"]["total_inr"] is None
    assert all(line["grade"] is None for line in job["report"]["lines"])
    assert [event["seq"] for event in job["events"]] == list(range(1, 6))
    # A finished list can be edited and confirmed again.
    again = {"edits": [{"op": "remove", "line_id": "L04"}]}
    assert client.post(f"{path}/confirm", headers=headers, json=again).status_code == 202
    assert [
        line["item"]["line_id"]
        for line in client.get(path, headers=headers).json()["report"]["lines"]
    ] == ["L01", "L03"]


def test_jobs_require_their_own_token(client):
    path, headers = create_job(client)
    _, other_headers = create_job(client)
    for bad_headers in ({}, other_headers):
        assert client.get(path, headers=bad_headers).status_code == 404
        assert client.post(f"{path}/confirm", headers=bad_headers, json={}).status_code == 404
    assert client.get(path, headers=headers).status_code == 200
    assert "job_token" not in client.get(path, headers=headers).json()


def test_invalid_edit_rolls_back_all_changes(client):
    path, headers = create_job(client)
    before = client.get(path, headers=headers).json()
    response = client.post(
        f"{path}/confirm",
        headers=headers,
        json={
            "edits": [
                {"op": "update", "line_id": "L01", "qty": 20},
                {"op": "remove", "line_id": "missing"},
            ]
        },
    )
    assert response.status_code == 422
    assert client.get(path, headers=headers).json() == before


@pytest.mark.parametrize(
    "edit",
    [
        {"op": "update", "line_id": "L01"},
        {"op": "update", "line_id": "L01", "qty": 0},
        {"op": "add", "raw_name": "   "},
        {"op": "add", "raw_name": "Wire", "qty": True},
        {"op": "add", "raw_name": "Wire", "qty": 1.5},
        {"op": "unknown", "line_id": "L01"},
    ],
)
def test_invalid_edits_are_rejected(client, edit):
    path, headers = create_job(client)
    response = client.post(f"{path}/confirm", headers=headers, json={"edits": [edit]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_bom_rejected(client):
    path, headers = create_job(client)
    response = client.post(
        f"{path}/confirm",
        headers=headers,
        json={"edits": [{"op": "remove", "line_id": line} for line in ["L01", "L02", "L03"]]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_BOM"


@pytest.mark.parametrize(
    "body",
    [
        {"url": "file:///etc/passwd"},
        {"url": "https://example.com", "country": "US"},
        {"url": "https://example.com", "country": "india"},
        {"url": "https://example.com", "surprise": True},
    ],
)
def test_input_validation(client, body):
    assert client.post("/v1/jobs", json=body).status_code == 422


def test_cors_for_teammate(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-job-token",
    }
    response = client.options("/v1/jobs", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    headers["Origin"] = "https://unrelated.example"
    assert client.options("/v1/jobs", headers=headers).status_code == 400


def test_confirmation_race_has_one_winner():
    service = JobService()
    job, token = service.create(CreateJob(url="https://example.com"))
    service.extract(job.job_id)

    def confirm():
        try:
            service.confirm(job.job_id, token, ConfirmJob())
            return 202
        except JobError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: confirm(), range(2))) == [202, 409]


def test_live_mode_fails_explicitly():
    with pytest.raises(RuntimeError, match="BS_GEMINI_API_KEY"):
        create_app(Settings(_env_file=None, demo_mode=False, gemini_api_key=None))
