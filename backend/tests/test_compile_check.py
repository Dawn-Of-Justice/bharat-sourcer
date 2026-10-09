"""Compile checks (code-adapt tier 3) with a fake launcher, fake runner identity and a
synthetic repository tarball; nothing reaches GitHub, Cloud Run or a compiler."""

import io
import tarfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer import code_adapt, compile_check
from bharat_sourcer.code_adapt import unified
from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
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
TARBALL = "https://codeload.github.com/maker/synthetic-oled/tar.gz/HEAD"
OFFER = "https://seller.example/sh1106-oled"
RUNNER = {"Authorization": "Bearer runner"}
BME_SKETCH = (
    "// Synthetic sketch\n#include <Wire.h>\n#include <Adafruit_BME280.h>\n\n"
    "Adafruit_BME280 bme;\n\nvoid setup() {\n  Serial.begin(9600);\n  bme.begin(0x76);\n}\n\n"
    "void loop() {\n  Serial.println(bme.readTemperature());\n  delay(1000);\n}\n"
)


def tarball(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"synthetic-oled-abc123/{path}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Fetcher:
    def __init__(self, repo: dict[str, str]):
        self.repo = repo

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        if url == TARBALL:
            return Page(url, 200, {}, tarball(self.repo))
        if url.startswith(RAW) and url[len(RAW) :] in self.repo:
            return Page(url, 200, {}, self.repo[url[len(RAW) :]].encode())
        raise FetchError("not found")


class Launcher:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def launch(self, family, run_id):
        if self.fail:
            raise RuntimeError("quota")
        self.calls.append((family, run_id))


def offer(from_id="ssd1306_096_i2c", to_id="sh1106_13_i2c"):
    return VerifiedOffer(
        url=OFFER,
        seller="seller.example",
        title="Substitute part (synthetic)",
        price_inr="250.00",
        compatibility=Compatibility(
            status="changes_required",
            grade="B",
            method="catalog_rules",
            required_catalog_id=from_id,
            offered_catalog_id=to_id,
        ),
    )


@pytest.fixture(autouse=True)
def runner_identity(monkeypatch):
    monkeypatch.setattr(
        compile_check, "runner_identity", lambda settings, header: header == "Bearer runner"
    )


def setup(repo=None, boards=("Arduino Uno",), edge=None, launcher=None, **settings):
    repo = repo if repo is not None else {"src/main.ino": (FIXTURES / "ssd1306.ino").read_text()}
    app = create_app(Settings(_env_file=None, demo_mode=True, **settings))
    service = app.state.job_service
    fetcher = Fetcher(repo)
    app.state.code_patch_service.fetcher = fetcher
    app.state.compile_service.launcher = launcher if launcher is not None else Launcher()
    job, token = service.create(CreateJob(url="https://github.com/maker/synthetic-oled"))
    path = next(iter(repo))
    evidence = Evidence(
        source="code",
        observation=f"{path} includes the display library (synthetic)",
        quote="#include <Adafruit_SSD1306.h>",
        url=f"https://github.com/maker/synthetic-oled/blob/HEAD/{path}#L4",
        file=path,
        line=4,
    )

    def seed(record):
        item = BomItem(line_id="L01", raw_name="OLED display", evidence=[evidence])
        others = [BomItem(line_id=f"B{i}", raw_name=name) for i, name in enumerate(boards)]
        record.job.demo = False
        record.job.status = "done"
        record.job.items = [item, *others]
        record.job.report = Report(
            demo=False,
            summary="Synthetic report",
            lines=[
                ReportLine(
                    item=item,
                    sourcing_status="offers_found",
                    offers=[offer(*edge) if edge else offer()],
                    selected_offer_url=OFFER,
                )
            ],
        )

    service.store.mutate(job.job_id, seed)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, app, job.job_id, fetcher


def patch_path(job_id):
    return f"/v1/jobs/{job_id}/lines/L01/code-patch"


def run_id(client, job_id):
    return client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]["compile"][
        "run_id"
    ]


def test_boards_listed_and_disabled_by_default():
    app = create_app(Settings(_env_file=None, demo_mode=True))
    client = TestClient(app)
    boards = client.get("/v1/compile/boards").json()
    assert boards["enabled"] is False
    assert {"fqbn": "arduino:avr:uno", "label": "Arduino Uno", "family": "avr"} in boards["boards"]


def test_compile_unavailable_without_runner():
    client, app, job_id, _ = setup()
    app.state.compile_service.launcher = None
    client.post(patch_path(job_id), json={})
    response = client.post(patch_path(job_id) + "/compile", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "COMPILE_UNAVAILABLE"


def test_compile_round_trip_marks_patch_compiled_and_is_idempotent():
    client, app, job_id, _ = setup()
    launcher = app.state.compile_service.launcher
    client.post(patch_path(job_id), json={})
    queued = client.post(patch_path(job_id) + "/compile", json={})
    assert queued.status_code == 202
    check = queued.json()["compile"]
    assert check["status"] == "queued" and check["fqbn"] == "arduino:avr:uno"
    assert check["board"] == "Arduino Uno" and check["attempt"] == 1
    assert launcher.calls == [("avr", check["run_id"])]
    again = client.post(patch_path(job_id) + "/compile", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "COMPILE_IN_PROGRESS"

    internal = f"/internal/compile/{check['run_id']}"
    assert client.get(internal).status_code == 401
    assert client.get(internal, headers={"Authorization": "Bearer other"}).status_code == 401
    bundle = client.get(internal, headers=RUNNER).json()
    assert bundle["sketch"] == "main" and bundle["fqbn"] == "arduino:avr:uno"
    assert list(bundle["files"]) == ["main.ino"]
    assert "Adafruit_SH1106G display" in bundle["files"]["main.ino"]

    result = {
        "status": "compiles",
        "core": "arduino:avr@1.8.8",
        "size": "Sketch uses 9000 bytes (27%) of program storage space.",
    }
    assert client.post(internal + "/result", json=result, headers=RUNNER).json() == {
        "accepted": True
    }
    patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert patch["check"] == "compiles"
    assert patch["compile"]["status"] == "compiles"
    assert patch["compile"]["core"] == "arduino:avr@1.8.8"
    assert patch["compile"]["sketch"] == "src/main.ino" and patch["compile"]["finished_at"]
    late = {"status": "compile_failed", "log": "error: late"}
    assert client.post(internal + "/result", json=late, headers=RUNNER).json() == {
        "accepted": False
    }
    assert client.get(internal, headers=RUNNER).status_code == 410
    archive = zipfile.ZipFile(io.BytesIO(client.get(patch_path(job_id) + ".zip").content))
    readme = archive.read("README-BHARAT-SOURCER.txt").decode()
    assert "compiled for Arduino Uno (arduino:avr:uno)" in readme
    assert "NOT tested on hardware" in readme
    # A finished check can be repeated (for example for another board).
    other = client.post(patch_path(job_id) + "/compile", json={"fqbn": "arduino:avr:mega"})
    assert other.status_code == 202 and other.json()["check"] == "not_checked"
    assert launcher.calls[-1][0] == "avr"


def test_failed_compile_keeps_trimmed_log():
    client, _, job_id, _ = setup()
    client.post(patch_path(job_id), json={})
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    noise = "\n".join(f"note {i}" for i in range(100))
    log = f"{noise}\nmain.ino:7:1: error: 'display' was not declared\n"
    client.post(
        f"/internal/compile/{run}/result",
        json={"status": "compile_failed", "log": log},
        headers=RUNNER,
    )
    patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert patch["check"] == "compile_failed"
    lines = patch["compile"]["log"].splitlines()
    assert lines[0] == "main.ino:7:1: error: 'display' was not declared" and len(lines) == 40
    archive = zipfile.ZipFile(io.BytesIO(client.get(patch_path(job_id) + ".zip").content))
    assert "did NOT compile" in archive.read("README-BHARAT-SOURCER.txt").decode()


@pytest.mark.parametrize(
    ("boards", "body", "status", "code"),
    [
        ((), {}, 422, "FQBN_REQUIRED"),
        (("Arduino Uno", "ESP32 development board"), {}, 422, "FQBN_REQUIRED"),
        ((), {"fqbn": "esp8266:esp8266:d1_mini"}, 202, None),
        (("Arduino Uno",), {"fqbn": "arduino:sam:due"}, 422, "FQBN_UNSUPPORTED"),
    ],
)
def test_board_choice(boards, body, status, code):
    client, app, job_id, _ = setup(boards=boards)
    client.post(patch_path(job_id), json={})
    response = client.post(patch_path(job_id) + "/compile", json=body)
    assert response.status_code == status
    if code:
        assert response.json()["error"]["code"] == code
    else:
        assert app.state.compile_service.launcher.calls[0][0] == "esp8266"


@pytest.mark.parametrize(
    ("name", "fqbn"),
    [
        ("Wemos D1 mini (ESP8266)", "esp8266:esp8266:d1_mini"),
        ("ESP32-S3 development board", "esp32:esp32:esp32s3"),
        ("Raspberry Pi Pico W", "rp2040:rp2040:rpipicow"),
        ("NodeMCU ESP32", "esp32:esp32:esp32"),
        ("NodeMCU ESP8266 board", "esp8266:esp8266:nodemcuv2"),
        ("Arduino Nano", "arduino:avr:nano"),
        ("Arduino Nano Every", None),
        ("Arduino Uno R4 WiFi", None),
    ],
)
def test_board_detection(name, fqbn):
    from bharat_sourcer.schemas import Job

    job = Job.model_construct(items=[BomItem(line_id="B1", raw_name=name)])
    found = [b["fqbn"] for b in compile_check.detect_boards(job)]
    assert found == ([fqbn] if fqbn else [])


def test_unavailable_reasons_are_recorded_on_the_check():
    client, _, job_id, fetcher = setup()
    client.post(patch_path(job_id), json={})
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    fetcher.repo["src/main.ino"] += "\n// changed upstream\n"
    response = client.get(f"/internal/compile/{run}", headers=RUNNER)
    assert response.status_code == 409
    check = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert check["compile"]["status"] == "unavailable"
    assert check["compile"]["reason"] == "source_changed" and check["check"] == "not_checked"


def test_platformio_projects_are_not_compiled():
    sketch = (FIXTURES / "ssd1306.ino").read_text()
    repo = {"src/main.cpp": sketch, "platformio.ini": "[env:uno]\nboard = uno\n"}
    client, _, job_id, _ = setup(repo=repo)
    patch = client.post(patch_path(job_id), json={}).json()
    assert patch["status"] == "ready"
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    assert client.get(f"/internal/compile/{run}", headers=RUNNER).status_code == 409
    check = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert check["compile"]["reason"] == "platformio_not_supported"


def test_sketch_folder_includes_local_files_but_not_other_sketches():
    sketch = (FIXTURES / "ssd1306.ino").read_text()
    repo = {
        "firmware/oled_clock/oled_clock.ino": sketch,
        "firmware/oled_clock/display.h": "#pragma once\n",
        "firmware/oled_clock/src/util/fmt.cpp": "int fmt() { return 0; }\n",
        "firmware/other/other.ino": "void setup() {}\nvoid loop() {}\n",
        "docs/readme.txt": "not code",
    }
    client, _, job_id, _ = setup(repo=repo)
    client.post(patch_path(job_id), json={})
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    bundle = client.get(f"/internal/compile/{run}", headers=RUNNER).json()
    assert bundle["sketch"] == "oled_clock" and bundle["folder"] == "firmware/oled_clock"
    assert sorted(bundle["files"]) == ["display.h", "oled_clock.ino", "src/util/fmt.cpp"]


def test_launch_failure_and_expired_runs():
    client, app, job_id, _ = setup(launcher=Launcher(fail=True))
    client.post(patch_path(job_id), json={})
    failed = client.post(patch_path(job_id) + "/compile", json={}).json()
    assert failed["compile"]["status"] == "unavailable"
    assert failed["compile"]["reason"] == "launch_failed"

    app.state.compile_service.launcher = Launcher()
    first = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]

    def expire(record):
        check = record.job.report.lines[0].code_patch.compile
        check.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    app.state.job_service.store.mutate(job_id, expire)
    second = client.post(patch_path(job_id) + "/compile", json={})
    assert second.status_code == 202 and second.json()["compile"]["run_id"] != first
    stale = client.post(
        f"/internal/compile/{first}/result", json={"status": "compiles"}, headers=RUNNER
    )
    assert stale.json() == {"accepted": False}


def test_runner_errors_and_timeouts():
    client, _, job_id, _ = setup()
    client.post(patch_path(job_id), json={})
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    client.post(
        f"/internal/compile/{run}/result",
        json={"status": "error", "detail": "Bundle rejected: invalid file path"},
        headers=RUNNER,
    )
    patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert patch["compile"]["reason"] == "runner_error" and patch["check"] == "not_checked"
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    client.post(f"/internal/compile/{run}/result", json={"status": "timeout"}, headers=RUNNER)
    patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert patch["compile"]["status"] == "timeout" and patch["check"] == "not_checked"


def test_ai_draft_gets_two_repair_rounds_then_fails(monkeypatch):
    edge = ("bme280_adafruit", "bmp280_gy")
    # Hide the curated recipe so this edge goes to the AI tier.
    curated = code_adapt.recipes()
    monkeypatch.setattr(
        code_adapt, "recipes", lambda: {k: v for k, v in curated.items() if k != edge}
    )
    repo = {"src/main.ino": BME_SKETCH}
    client, app, job_id, _ = setup(repo=repo, edge=edge, code_adapt_ai=True)
    launcher = app.state.compile_service.launcher
    good = BME_SKETCH.replace("Adafruit_BME280.h", "Adafruit_BMP280.h").replace(
        "Adafruit_BME280 bme", "Adafruit_BMP280 bme"
    )
    diff = unified("src/main.ino", BME_SKETCH, good)
    prompts = []

    def generate(prompt, schema):
        prompts.append(prompt)
        return {"files": [{"path": "src/main.ino", "unified_diff": diff}], "notes": ["n"]}

    app.state.code_patch_service.generate = generate
    draft = client.post(patch_path(job_id), json={}).json()
    assert draft["origin"] == "ai_draft" and draft["ai_calls"] == 1
    client.post(patch_path(job_id) + "/accept")
    run = client.post(patch_path(job_id) + "/compile", json={"fqbn": "arduino:avr:uno"}).json()[
        "compile"
    ]["run_id"]
    failure = {"status": "compile_failed", "log": "main.ino:5:1: error: 'bme' has no member"}
    for round_number in (1, 2):
        answer = client.post(f"/internal/compile/{run}/result", json=failure, headers=RUNNER)
        assert answer.json() == {"accepted": True, "repair": True}
        patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
        assert patch["compile"]["status"] == "queued"
        assert patch["compile"]["repairs"] == round_number
        assert patch["compile"]["attempt"] == round_number + 1
        assert patch["accepted"] is False and patch["ai_calls"] == 1 + round_number
        assert "has no member" in prompts[-1] and "<untrusted>" in prompts[-1]
        assert launcher.calls[-1] == ("avr", patch["compile"]["run_id"])
        assert patch["compile"]["run_id"] != run
        run = patch["compile"]["run_id"]
    final = client.post(f"/internal/compile/{run}/result", json=failure, headers=RUNNER)
    assert final.json() == {"accepted": True}
    patch = client.get(f"/v1/jobs/{job_id}").json()["report"]["lines"][0]["code_patch"]
    assert patch["check"] == "compile_failed" and patch["compile"]["repairs"] == 2
    assert len(prompts) == 3 and len(launcher.calls) == 3


def test_curated_patches_are_not_repaired():
    client, app, job_id, _ = setup(code_adapt_ai=True)
    app.state.code_patch_service.generate = lambda prompt, schema: pytest.fail("no repair")
    client.post(patch_path(job_id), json={})
    run = client.post(patch_path(job_id) + "/compile", json={}).json()["compile"]["run_id"]
    answer = client.post(
        f"/internal/compile/{run}/result",
        json={"status": "compile_failed", "log": "error: x"},
        headers=RUNNER,
    )
    assert answer.json() == {"accepted": True}
