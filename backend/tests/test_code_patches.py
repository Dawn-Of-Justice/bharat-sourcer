"""Code patch service and routes; synthetic repo files served by a fake fetcher."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.export import redact
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    CompatFinding,
    Compatibility,
    CreateJob,
    Evidence,
    Report,
    ReportLine,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.fetch import FetchError, Page

FIXTURES = Path(__file__).parent / "fixtures" / "code_adapt"
RAW = "https://raw.githubusercontent.com/maker/synthetic-oled/HEAD/"
OFFER = "https://seller.example/sh1106-oled"


class FakeFetcher:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        if url not in self.files:
            raise FetchError("not found")
        return Page(url, 200, {"content-type": "text/plain"}, self.files[url].encode())


def offer(from_id="ssd1306_096_i2c", to_id="sh1106_13_i2c", findings=()):
    return VerifiedOffer(
        url=OFFER,
        seller="seller.example",
        title="1.3 inch SH1106 OLED (synthetic)",
        price_inr="250.00",
        compatibility=Compatibility(
            status="changes_required",
            grade="B",
            method="catalog_rules",
            required_catalog_id=from_id,
            offered_catalog_id=to_id,
            findings=list(findings),
        ),
    )


def setup(files=None, offers=None, **settings):
    sketch = (FIXTURES / "ssd1306.ino").read_text()
    files = files if files is not None else {RAW + "src/main.ino": sketch}
    app = create_app(Settings(_env_file=None, demo_mode=True, **settings))
    service = app.state.job_service
    fetcher = FakeFetcher(files)
    app.state.code_patch_service.fetcher = fetcher
    job, token = service.create(CreateJob(url="https://github.com/maker/synthetic-oled"))
    evidence = Evidence(
        source="code",
        observation="src/main.ino line 4 includes Adafruit_SSD1306.h (synthetic)",
        quote="#include <Adafruit_SSD1306.h>",
        url="https://github.com/maker/synthetic-oled/blob/HEAD/src/main.ino#L4",
        file="src/main.ino",
        line=4,
    )

    def seed(record):
        item = BomItem(line_id="L01", raw_name="SSD1306 OLED display", evidence=[evidence])
        record.job.demo = False
        record.job.status = "done"
        record.job.items = [item]
        record.job.report = Report(
            demo=False,
            summary="Synthetic report",
            lines=[
                ReportLine(
                    item=item,
                    sourcing_status="offers_found",
                    offers=list(offers if offers is not None else [offer()]),
                    selected_offer_url=OFFER,
                )
            ],
        )

    service.store.mutate(job.job_id, seed)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, app, job.job_id, fetcher


def path(job_id):
    return f"/v1/jobs/{job_id}/lines/L01/code-patch"


def test_curated_patch_is_stored_downloadable_and_owner_only():
    client, app, job_id, _ = setup()
    patch = client.post(path(job_id), json={}).json()
    assert patch["status"] == "ready" and patch["origin"] == "curated"
    assert patch["check"] == "not_checked" and patch["accepted"] is True
    [file] = patch["files"]
    assert file["path"] == "src/main.ino" and "+#include <Adafruit_SH110X.h>" in file["diff"]
    saved = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert saved["files"][0]["sha256"] == file["sha256"]
    response = client.get(path(job_id) + ".zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "Adafruit_SH1106G display" in archive.read("src/main.ino").decode()
    readme = archive.read("README-BHARAT-SOURCER.txt").decode()
    assert "NOT COMPILED" in readme and "no LICENSE file" in readme
    job = app.state.job_service.store.get(job_id).job
    assert redact(job).report.lines[0].code_patch is None


def test_download_refuses_when_source_changed_and_includes_license():
    client, _, job_id, fetcher = setup()
    client.post(path(job_id), json={})
    fetcher.files[RAW + "LICENSE"] = "MIT License (synthetic)"
    ok = zipfile.ZipFile(io.BytesIO(client.get(path(job_id) + ".zip").content))
    assert ok.read("LICENSE").decode().startswith("MIT")
    fetcher.files[RAW + "src/main.ino"] += "\n// changed upstream\n"
    changed = client.get(path(job_id) + ".zip")
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "SOURCE_CHANGED"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"files": {}}, "file_not_read"),
        ({"offers": [offer(to_id="ssd1306_096_i2c")]}, "no_substitute"),
        (
            {
                "offers": [
                    offer(
                        findings=[
                            CompatFinding(rule="board_chip", grade="D", area="code", message="x")
                        ]
                    )
                ]
            },
            "out_of_scope_mcu",
        ),
        ({"offers": [offer("dht22", "dht11")]}, "recipe_not_applicable"),
    ],
)
def test_unavailable_patches_carry_reasons(kwargs, reason):
    client, _, job_id, _ = setup(**kwargs)
    patch = client.post(path(job_id), json={}).json()
    assert patch["status"] == "unavailable" and patch["reason"] == reason
    assert patch["files"] == []
    assert client.get(path(job_id) + ".zip").status_code == 404


def test_offer_required_and_unknown_line():
    client, _, job_id, _ = setup()
    missing = client.post(path(job_id), json={"offer_url": "https://other.example/x"})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "OFFER_REQUIRED"
    unknown = client.post(f"/v1/jobs/{job_id}/lines/L99/code-patch", json={})
    assert unknown.status_code == 404
    assert client.post(path(job_id), json={}, headers={"X-Job-Token": "x" * 40}).status_code in {
        401,
        404,
    }


def without_recipe(monkeypatch, edge):
    """Hide the curated recipe for an edge, so the AI tier is the only way to patch it."""
    from bharat_sourcer import code_adapt

    curated = code_adapt.recipes()
    monkeypatch.setattr(
        code_adapt, "recipes", lambda: {k: v for k, v in curated.items() if k != edge}
    )


def test_ai_draft_is_off_by_default_and_must_be_accepted_when_enabled(monkeypatch):
    # An edge with no curated recipe: falls back to AI only when the flag is on.
    edge = ("bme280_adafruit", "bmp280_gy")
    without_recipe(monkeypatch, edge)
    sketch = (
        "// Synthetic sketch\n#include <Wire.h>\n#include <Adafruit_BME280.h>\n\n"
        "Adafruit_BME280 bme;\n\nvoid setup() {\n  Serial.begin(9600);\n  bme.begin(0x76);\n}\n\n"
        "void loop() {\n  Serial.println(bme.readTemperature());\n  delay(1000);\n}\n"
    )
    files = {RAW + "src/main.ino": sketch}
    client, _, job_id, _ = setup(files=files, offers=[offer(*edge)])
    off = client.post(path(job_id), json={}).json()
    assert off["reason"] == "recipe_not_applicable"

    client, app, job_id, _ = setup(files=files, offers=[offer(*edge)], code_adapt_ai=True)
    new = sketch.replace("Adafruit_BME280.h", "Adafruit_BMP280.h").replace(
        "Adafruit_BME280 bme", "Adafruit_BMP280 bme"
    )
    from bharat_sourcer.code_adapt import unified

    diff = unified("src/main.ino", sketch, new)
    calls = []

    def generate(prompt, schema):
        calls.append(prompt)
        return {
            "files": [{"path": "src/main.ino", "unified_diff": diff}],
            "notes": [],
            "assumptions": ["Humidity readings are removed (synthetic)"],
        }

    app.state.code_patch_service.generate = generate
    draft = client.post(path(job_id), json={}).json()
    assert draft["status"] == "ready" and draft["origin"] == "ai_draft", draft
    assert draft["accepted"] is False and draft["ai_calls"] == 1 and len(calls) == 1
    blocked = client.get(path(job_id) + ".zip")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "PATCH_NOT_ACCEPTED"
    assert client.post(path(job_id) + "/accept").json()["accepted"] is True
    archive = zipfile.ZipFile(io.BytesIO(client.get(path(job_id) + ".zip").content))
    assert "Adafruit_BMP280 bme" in archive.read("src/main.ino").decode()


def test_ai_draft_respects_job_budget_and_records_cost(monkeypatch):
    edge = ("bme280_adafruit", "bmp280_gy")
    without_recipe(monkeypatch, edge)
    sketch = (FIXTURES / "ssd1306.ino").read_text().replace("SSD1306", "BME280")
    files = {RAW + "src/main.ino": sketch}
    client, app, job_id, _ = setup(
        files=files, offers=[offer(*edge)], code_adapt_ai=True, job_gemini_budget_usd=0
    )
    app.state.code_patch_service.generate = lambda prompt, schema: pytest.fail("no call")
    over = client.post(path(job_id), json={}).json()
    assert over["status"] == "unavailable" and over["reason"] == "budget"

    client, app, job_id, _ = setup(files=files, offers=[offer(*edge)], code_adapt_ai=True)
    app.state.code_patch_service.generate = lambda prompt, schema: {"files": []}
    failed = client.post(path(job_id), json={}).json()
    assert failed["reason"] == "ai_failed_validation" and failed["ai_calls"] == 2
    assert app.state.job_service.store.get(job_id).job.cost_estimate is not None
