"""Project overview: validator, judge application, lifecycle, demo fixture and routes.

Gemini is always mocked: every model reply below is a hand-written fixture, not live
output. The repository files are synthetic and served by a fake fetcher; no network.
"""

import json
import threading
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from bharat_sourcer import overview as ov
from bharat_sourcer.config import Settings
from bharat_sourcer.dispatch import Work, work_once
from bharat_sourcer.export import redact
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Evidence,
    PartSpecs,
    ProjectContext,
    now,
)
from bharat_sourcer.sourcing.cache import MemoryCache
from bharat_sourcer.sourcing.fetch import FetchError, Page

REPO = "https://github.com/maker/synthetic-buddy"
RAW = "https://raw.githubusercontent.com/maker/synthetic-buddy/HEAD/"
SKETCH = """#include <Wire.h>
#include <Adafruit_SH110X.h>
#define SCREEN_WIDTH 128
#define SDA_PIN 8
#define SCL_PIN 9
#define TOUCH_PIN 7
#define MOOD_HAPPY 1
// #define OLD_LED_PIN 4
const int ledPin = 2;
void setup() {
  Wire.begin(SDA_PIN, SCL_PIN);
  pinMode(TOUCH_PIN, INPUT);
}
void loop() {
  if (digitalRead(TOUCH_PIN)) { digitalWrite(ledPin, HIGH); }
}
unsigned long lastPageSwitch = 0;
int touchState = 0;
"""


class FakeFetcher:
    def __init__(self, files: dict[str, str]):
        self.files, self.requests = files, []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.requests.append(url)
        if url not in self.files:
            raise FetchError("not found")
        return Page(url, 200, {"content-type": "text/plain"}, self.files[url].encode())


def code_evidence(line=2, quote="#include <Adafruit_SH110X.h>"):
    return Evidence(
        source="code",
        observation=f"buddy.ino line {line} includes a display library (synthetic)",
        quote=quote,
        url=f"{REPO}/blob/HEAD/buddy.ino#L{line}",
        file="buddy.ino",
        line=line,
    )


def items():
    return [
        BomItem(line_id="L01", raw_name="ESP32-C3 Super Mini", evidence=[code_evidence()]),
        BomItem(line_id="L02", raw_name="1.3 inch SH1106 OLED (I2C)"),
        BomItem(line_id="L03", raw_name="TTP223 touch sensor"),
        BomItem(line_id="L04", raw_name="Jumper wires", qty=10),
    ]


def pin(name, kind="gpio", functions=()):
    return {"name": name, "kind": kind, "functions": list(functions)}


def part(line_id, label, kind, headers, **extra):
    return {
        "line_id": line_id,
        "label": label,
        "kind": kind,
        "width_mm": 22.5,
        "height_mm": 18,
        "color": "blue",
        "shape": "rect",
        "chip": None,
        "features": [],
        "connectors": [],
        "headers": headers,
        "pin_source": "datasheet_knowledge",
        **extra,
    }


def wire(a, b, signal, source="ai_inferred", evidence=None):
    (from_line, from_pin), (to_line, to_pin) = a, b
    return {
        "from_line": from_line,
        "from_pin": from_pin,
        "to_line": to_line,
        "to_pin": to_pin,
        "signal": signal,
        "label": None,
        "source": source,
        "evidence": evidence,
    }


BOARD = part(
    "L01",
    "ESP32-C3 Super Mini",
    "board",
    [
        {
            "side": "left",
            "pins": [pin("5V", "power"), pin("G", "ground"), pin("3.3", "power"), pin("2")],
        },
        {
            "side": "right",
            "pins": [
                pin("7", functions=["GPIO7"]),
                pin("8", "i2c", ["GPIO8", "SDA"]),
                pin("9", "i2c", ["GPIO9", "SCL"]),
                pin("9", "i2c"),  # duplicate on the same header: removed
            ],
        },
    ],
    chip={"label": "ESP32-C3", "x": 0.3, "y": 0.2, "w": 1.4, "h": 0.4},
    connectors=[{"type": "usb_c", "side": "top", "position": 0.5}],
)
OLED = part(
    "L02",
    "SH1106 OLED 1.3in",
    "display",
    [
        {
            "side": "top",
            "pins": [
                pin("GND", "ground"),
                pin("VCC", "power"),
                pin("SCL", "i2c"),
                pin("SDA", "i2c"),
            ],
        }
    ],
    features=[{"type": "screen", "x": 0.05, "y": 0.2, "w": 0.9, "h": 0.7, "text": None}],
)
TOUCH = part(
    "L03",
    "TTP223 touch",
    "sensor",
    [{"side": "bottom", "pins": [pin("GND", "ground"), pin("I/O"), pin("VCC", "power")]}],
)
GENERATED = {
    "parts": [BOARD, OLED, TOUCH, part("L09", "Invented part", "module", [])],
    "wiring": [
        wire(("L01", "3.3"), ("L02", "VCC"), "power"),
        wire(("L01", "G"), ("L02", "GND"), "ground"),
        wire(("L01", "8"), ("L02", "SDA"), "i2c_sda", "code", "buddy.ino:11"),
        wire(("L01", "9"), ("L02", "SCL"), "i2c_scl", "code", "buddy.ino:11"),
        wire(("L01", "7"), ("L03", "I/O"), "digital", "code", "buddy.ino:12"),
        wire(("L01", "3.3"), ("L03", "VCC"), "power"),
        wire(("L01", "G"), ("L03", "GND"), "ground"),
        wire(("L01", "6"), ("L03", "VCC"), "digital"),  # pin 6 is not on the board: removed
    ],
    "notes": ["Assumed the 4-pin I2C version of the OLED."],
}
JUDGED = {
    "summary": "The OLED pin order is contradicted; the rest is consistent with the code.",
    "parts": [
        {
            "line_id": "L01",
            "verdict": "confirmed",
            "reason": "Published Super Mini pinout.",
            "headers": [
                {"header": 0, "verdict": "confirmed", "reason": "Matches the pinout."},
                {"header": 1, "verdict": "confirmed", "reason": "Matches the pinout."},
            ],
        },
        {
            "line_id": "L02",
            "verdict": "confirmed",
            "reason": "SH1106 I2C module.",
            "headers": [{"header": 0, "verdict": "disputed", "reason": "Many print VCC first."}],
        },
        {"line_id": "L03", "verdict": "unverified", "reason": "Generic TTP223 board."},
        {"line_id": "L99", "verdict": "confirmed", "reason": "Not in the drawing."},
    ],
    "wires": [
        {"id": "W01", "verdict": "confirmed", "reason": "3.3 V supply."},
        {"id": "W02", "verdict": "confirmed", "reason": "Ground."},
        {"id": "W03", "verdict": "confirmed", "reason": "buddy.ino:11 sets SDA_PIN 8."},
        {"id": "W04", "verdict": "disputed", "reason": "Contradicted pin (synthetic)."},
        {"id": "W05", "verdict": "confirmed", "reason": "buddy.ino:12 TOUCH_PIN 7."},
        {"id": "W06", "verdict": "unverified", "reason": "Plausible."},
    ],
}


def reply(body, finish="STOP"):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": finish, "content": {"parts": [{"text": json.dumps(body)}]}}
            ],
            "usageMetadata": {"promptTokenCount": 4000, "candidatesTokenCount": 1500},
        },
    )


def kind(body):
    prompt = body["systemInstruction"]["parts"][0]["text"]
    if "skeptical" in prompt:
        return "judge_wires" if "verdict for EVERY wire" in prompt else "judge_parts"
    return "wire" if prompt.startswith("You wire") else "draw"


class Gemini:
    """Answers the part, wiring and judge calls (any order, in parallel); records what was sent."""

    def __init__(self, generated=None, judged=None, generation_status=200, wiring_status=200):
        self.generated = GENERATED if generated is None else generated
        self.judged = JUDGED if judged is None else judged
        self.generation_status = generation_status
        self.wiring_status = wiring_status
        self.grouped_status = False  # True: calls with more than one line fail (overload)
        self.sent: list[dict] = []
        self.urls: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, request):
        body = json.loads(request.content)
        with self.lock:
            self.sent.append(body)
            self.urls.append(str(request.url))
        match kind(body):
            case "judge_parts" | "judge_wires" if self.judged == "fail":
                return httpx.Response(400)
            case "judge_parts":
                return reply({"parts": self.judged.get("parts", [])})
            case "judge_wires":
                return reply({"wires": self.judged.get("wires", [])})
            case "wire":
                if self.wiring_status != 200:
                    return httpx.Response(self.wiring_status)
                return reply(
                    {
                        "wiring": self.generated["wiring"],
                        "notes": self.generated["notes"],
                        "answers": self.generated.get("answers", []),
                    }
                )
        lines = json.loads(body["contents"][0]["parts"][0]["text"])["lines"]
        if self.generation_status != 200 or (self.grouped_status and len(lines) > 1):
            return httpx.Response(self.generation_status if not self.grouped_status else 503)
        # Like the model, a part call may also answer lines it was not given; those are dropped.
        return reply({"parts": self.generated["parts"]})

    def sites(self):
        return sorted(kind(b) for b in self.sent)

    def document(self, which="draw"):
        body = next(b for b in self.sent if kind(b) == which)
        return json.loads(body["contents"][0]["parts"][0]["text"])


def setup(gemini=None, files=None, cache=None, **settings):
    values = {
        "_env_file": None,
        "demo_mode": True,
        "overview_enabled": True,
        "gemini_api_key": "test",
    } | settings
    app = create_app(Settings(**values))
    service = app.state.job_service
    overviews = app.state.overview_service
    overviews.fetcher = FakeFetcher({RAW + "buddy.ino": SKETCH} if files is None else files)
    overviews.transport = httpx.MockTransport(gemini or Gemini())
    overviews.cache = cache
    job, token = service.create(CreateJob(url=REPO))

    def seed(record):
        record.job.demo = False
        record.job.status = "awaiting_confirmation"
        record.job.items = items()
        record.job.project = ProjectContext(summary="A desk companion with an OLED (synthetic).")

    service.store.mutate(job.job_id, seed)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, app, job.job_id


# -- deterministic code reading ------------------------------------------------------------
def test_pin_facts_read_defines_consts_and_uses_but_not_comments_or_non_pins():
    facts = ov.pin_facts({"buddy.ino": SKETCH})
    found = {(f.name, f.pin, f.role) for f in facts}
    assert ("SDA_PIN", 8, "defined") in found
    assert ("SDA_PIN", 8, "i2c_sda") in found and ("SCL_PIN", 9, "i2c_scl") in found
    assert ("TOUCH_PIN", 7, "input") in found and ("ledPin", 2, "output") in found
    ignored = {"MOOD_HAPPY", "SCREEN_WIDTH", "OLD_LED_PIN", "lastPageSwitch", "touchState"}
    assert not {f for f in facts if f.name in ignored}
    sda = next(f for f in facts if f.role == "i2c_sda")
    assert (sda.file, sda.line) == ("buddy.ino", 11)
    python = ov.pin_facts(
        {"main.py": "LED_PIN = 5\ni2c = I2C(0, sda=Pin(4), scl=Pin(6))\nb = Pin(3, Pin.IN)\n"}
    )
    assert {(f.pin, f.role) for f in python} >= {(5, "defined"), (4, "i2c_sda"), (3, "input")}


def test_code_urls_follow_code_evidence_then_github_entry_points():
    _, app, job_id = setup()
    job = app.state.job_service.store.get(job_id).job
    assert ov.code_urls(job) == {"buddy.ino": RAW + "buddy.ino"}
    job.items = [BomItem(line_id="L01", raw_name="Board")]
    urls = ov.code_urls(job)
    assert urls["synthetic-buddy.ino"] == RAW + "synthetic-buddy.ino"
    assert all(url.startswith("https://raw.githubusercontent.com/") for url in urls.values())


# -- validator -------------------------------------------------------------------------
def drawing(generated=None, files=None, line_items=None):
    line_items = line_items or items()
    draft = ov.OverviewDraft.model_validate(generated or GENERATED)
    parts, raw = ov.sanitize(draft, line_items)
    files = {"buddy.ino": SKETCH} if files is None else files
    wires, notes = ov.validate(parts, raw, line_items, files, ov.pin_facts(files))
    return parts, wires, notes


def test_validator_drops_unknown_lines_bad_pins_and_duplicate_header_pins():
    parts, wires, notes = drawing()
    assert [p.line_id for p in parts] == ["L01", "L02", "L03"]  # L09 is not a BOM line
    right = parts[0].headers[1]
    assert [p.name for p in right.pins] == ["7", "8", "9"]
    assert parts[0].chip.w == 1.0  # fractions are clamped
    assert len(wires) == 7 and [w.id for w in wires] == [f"W0{i}" for i in range(1, 8)]
    assert all(w.from_.pin != "6" for w in wires)
    assert any("Removed 1 wire" in note for note in notes)
    # Every code pin except GPIO 2 (ledPin) is wired.
    assert [n for n in notes if n.startswith("Code uses")] == [
        "Code uses GPIO 2 (ledPin, buddy.ino:9) but no wire connects it."
    ]
    assert all(not w.problems for w in wires)


def test_supply_voltages_come_from_power_pin_labels_only():
    def volts(name, kind="power"):
        return ov.pin_voltage(ov.Pin(name=name, kind=kind))

    assert [volts("5V"), volts("3V3"), volts("3.3"), volts("+3.3V"), volts("VBUS")] == [
        5.0,
        3.3,
        3.3,
        3.3,
        5.0,
    ]
    # A switch terminal "2" or an unlabelled VCC has no known voltage; GPIO pins never do.
    assert [volts("2"), volts("VCC"), volts("5V", "gpio")] == [None, None, None]


def test_validator_flags_power_to_ground_supply_mismatch_and_5v_into_3v3_part():
    line_items = [*items()[:3], BomItem(line_id="L05", raw_name="Raw BME280 breakout")]
    sensor = part(
        "L05",
        "BME280",
        "sensor",
        [{"side": "top", "pins": [pin("VDD", "power"), pin("GND", "ground")]}],
    )
    line_items[3].specs = PartSpecs(supply_max_v=3.6)
    generated = {
        "parts": [BOARD, OLED, TOUCH, sensor],
        "wiring": [
            wire(("L01", "5V"), ("L02", "GND"), "power"),
            wire(("L01", "5V"), ("L01", "3.3"), "power"),
            wire(("L01", "5V"), ("L05", "VDD"), "power"),
            wire(("L01", "9"), ("L02", "SDA"), "i2c_sda", "code", "buddy.ino:11"),
        ],
    }
    _, wires, _ = drawing(generated, line_items=line_items)
    short, mixed, overvolt, swapped = wires
    assert short.problems == ["Joins a power pin to ground (a short circuit)."]
    assert mixed.problems == ["Joins a 5 V supply pin to a 3.3 V supply pin."]
    assert overvolt.problems == ["Feeds 5 V into BME280, which takes 3.3 V only."]
    assert swapped.problems == ["The code sets this signal on GPIO 8 (SDA_PIN, buddy.ino:11)."]


def test_code_sources_need_code_and_real_citations():
    generated = {
        "parts": [BOARD | {"pin_source": "code"}, OLED],
        "wiring": [
            wire(("L01", "8"), ("L02", "SDA"), "i2c_sda", "code", "buddy.ino:999"),
            wire(("L01", "2"), ("L02", "SCL"), "i2c_scl", "code", "buddy.ino:9"),
        ],
    }
    _, wires, _ = drawing(generated)
    assert "The cited code line was not found in the project code." in wires[0].problems
    assert wires[1].problems == ["The code sets this signal on GPIO 9 (SCL_PIN, buddy.ino:11)."]
    parts, without_code, notes = drawing(generated, files={})
    assert parts[0].pin_source == "ai_inferred"
    assert {w.source for w in without_code} == {"ai_inferred"}
    assert not [n for n in notes if n.startswith("Code uses")]


# -- judge application -------------------------------------------------------------------
def judged(verdicts=None):
    parts, wires, notes = drawing()
    overview = ov.ProjectOverview(status="ready", parts=parts, wiring=wires, notes=notes)
    ov.apply_verdicts(overview, ov.JudgeDraft.model_validate(verdicts or JUDGED))
    return overview


def test_disputed_wire_stays_visible_and_disputed_header_disputes_the_part():
    overview = judged()
    board, oled, touch = overview.parts
    assert board.verdict == "confirmed"
    assert oled.verdict == "disputed"
    assert oled.verdict_reason.startswith("Pin list (top side) disputed: Many print VCC first.")
    assert touch.verdict == "unverified"
    wires = {w.id: w for w in overview.wiring}
    assert wires["W04"].verdict == "disputed" and wires["W04"] in overview.wiring
    assert wires["W07"].verdict == "unverified" and wires["W07"].reason == ov.NOT_REVIEWED
    assert overview.judge.status == "issues"
    assert (overview.judge.confirmed, overview.judge.unverified, overview.judge.disputed) == (
        5,
        3,
        2,
    )
    assert len(overview.parts) == 3  # the judge's unknown L99 added nothing


def test_rule_problems_keep_a_wire_from_being_confirmed():
    parts, wires, _ = drawing()
    wires[0].problems = ["Joins a power pin to ground (a short circuit)."]
    overview = ov.ProjectOverview(status="ready", parts=parts, wiring=wires)
    ov.apply_verdicts(overview, ov.JudgeDraft.model_validate(JUDGED))
    assert overview.wiring[0].verdict == "unverified"
    assert "rule check found" in overview.wiring[0].reason


# -- generation through the service ----------------------------------------------------------
def test_generation_with_fake_gemini_validates_judges_and_records_cost():
    gemini = Gemini()
    client, app, job_id = setup(gemini)
    response = client.post(f"/v1/jobs/{job_id}/overview")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"  # the drawing runs in the background
    result = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert result["status"] == "ready" and result["demo"] is False
    assert [p["line_id"] for p in result["parts"]] == ["L01", "L02", "L03"]
    assert result["parts"][1]["verdict"] == "disputed"
    assert result["wiring"][3]["verdict"] == "disputed"
    assert result["wiring"][0]["from"] == {"line_id": "L01", "pin": "3.3"}
    assert result["judge"]["status"] == "issues"
    assert result["notes"][0] == ov.AI_NOTICE
    assert "Assumed the 4-pin I2C version of the OLED." in result["notes"]
    # Two parallel part calls (two lines each), a judge per group, the wiring, its judge.
    assert gemini.sites() == ["draw", "draw", "judge_parts", "judge_parts", "judge_wires", "wire"]
    sent = gemini.document("draw")
    assert sent["code"][0]["path"] == "buddy.ino" and "11:   Wire.begin" in sent["code"][0]["text"]
    assert {"name": "TOUCH_PIN", "pin": 7, "role": "input"}.items() <= next(
        p for p in sent["code_pins"] if p["role"] == "input"
    ).items()
    assert len(sent["lines"]) == 2 and sent["other_parts"]
    assert all("untrusted data" in b["systemInstruction"]["parts"][0]["text"] for b in gemini.sent)
    wiring = gemini.document("wire")
    assert [p["line_id"] for p in wiring["parts"]] == ["L01", "L02", "L03"]
    assert "11:   Wire.begin" in wiring["code"][0]["text"]
    assert gemini.document("judge_wires")["drawing"]["wires"][0]["id"] == "W01"
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["overview"]["status"] == "ready" and job["overview"]["stage"] is None
    assert job["cost_estimate"]["calls_by_site"] == {
        "overview": 2,
        "overview_judge": 3,
        "overview_wiring": 1,
    }
    assert job["cost_estimate"]["run_usd"] == 0  # the sourcing run budget is untouched
    stored = app.state.job_service.store.get(job_id)
    assert stored.overview_run_id is None and stored.overview_lease_until is None
    again = client.post(f"/v1/jobs/{job_id}/overview").json()
    assert again["status"] == "ready" and len(gemini.sent) == 6  # a ready one is returned


def test_cached_by_items_and_code_and_judge_failure_leaves_everything_unverified():
    cache = MemoryCache()
    gemini = Gemini(judged="fail")
    client, _, job_id = setup(gemini, cache=cache)
    client.post(f"/v1/jobs/{job_id}/overview")
    skipped = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert skipped["status"] == "ready" and skipped["judge"]["status"] == "skipped"
    assert {p["verdict"] for p in skipped["parts"]} == {"unverified"}
    assert gemini.sites() == ["draw", "draw", "judge_parts", "judge_parts", "judge_wires", "wire"]
    # A judged drawing is cached; an unjudged one is not, so this job draws again.
    good = Gemini()
    second, _, job2 = setup(good, cache=cache)
    second.post(f"/v1/jobs/{job2}/overview")
    assert second.get(f"/v1/jobs/{job2}/overview").json()["judge"]["status"] == "issues"
    third, _, job3 = setup(Gemini(generation_status=400), cache=cache)
    third.post(f"/v1/jobs/{job3}/overview")
    hit = third.get(f"/v1/jobs/{job3}/overview").json()
    assert hit["status"] == "ready" and hit["judge"]["status"] == "issues"
    assert third.get(f"/v1/jobs/{job3}").json()["cost_estimate"]["cache_hits"] == {"overview": 1}


def test_failures_are_stored_with_a_message():
    client, _, job_id = setup(Gemini(generation_status=400))
    client.post(f"/v1/jobs/{job_id}/overview")
    result = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert result["status"] == "failed" and result["message"] == ov.GENERATION_FAILED
    gemini = Gemini()
    keyless, _, other = setup(gemini, gemini_api_key=None)
    keyless.post(f"/v1/jobs/{other}/overview")
    assert keyless.get(f"/v1/jobs/{other}/overview").json()["message"] == ov.NOT_CONFIGURED
    assert gemini.sent == []
    empty, _, third = setup(Gemini(generated={"parts": [], "wiring": [], "notes": []}))
    empty.post(f"/v1/jobs/{third}/overview")
    assert empty.get(f"/v1/jobs/{third}/overview").json()["message"] == ov.NO_PARTS
    # A failed drawing can be retried.
    retry = client.post(f"/v1/jobs/{job_id}/overview").json()
    assert retry["status"] == "pending"


def test_disabled_overview_fails_on_request():
    client, _, job_id = setup(overview_enabled=False)
    result = client.post(f"/v1/jobs/{job_id}/overview").json()
    assert result["status"] == "failed" and result["message"] == ov.DISABLED


# -- lifecycle ----------------------------------------------------------------------------
def test_draft_edits_make_a_drawing_stale_and_redraw_restarts_it():
    gemini = Gemini()
    client, app, job_id = setup(gemini)
    client.post(f"/v1/jobs/{job_id}/overview")
    service = app.state.job_service

    def have(record):
        service.edit_draft(
            record.job, ConfirmJob(edits=[{"op": "have_it", "line_id": "L04", "user_has_it": True}])
        )

    service.store.mutate(job_id, have)
    assert client.get(f"/v1/jobs/{job_id}/overview").json()["status"] == "ready"

    def rename(record):
        service.edit_draft(
            record.job,
            ConfirmJob(edits=[{"op": "update", "line_id": "L03", "raw_name": "Push button"}]),
        )

    service.store.mutate(job_id, rename)
    stale = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert stale["status"] == "stale" and stale["message"] == ov.STALE and stale["parts"]
    client.post(f"/v1/jobs/{job_id}/overview")
    assert len(gemini.sent) == 12  # two full drawings of six calls each
    assert client.get(f"/v1/jobs/{job_id}/overview").json()["status"] == "ready"


def test_result_for_an_edited_list_is_saved_stale_and_expired_leases_fail():
    client, app, job_id = setup()
    service, overviews = app.state.job_service, app.state.overview_service
    original = overviews.build

    def edit_meanwhile(job, ledger, **kwargs):
        result = original(job, ledger, **kwargs)

        def rename(record):
            record.job.items[0].raw_name = "ESP32-S3 board"

        service.store.mutate(job_id, rename)
        return result

    overviews.build = edit_meanwhile
    client.post(f"/v1/jobs/{job_id}/overview")
    assert client.get(f"/v1/jobs/{job_id}/overview").json()["status"] == "stale"

    def interrupted(record):
        record.job.overview = ov.pending(record.job)
        record.overview_run_id = "lost-worker"
        record.overview_lease_until = now() - timedelta(seconds=1)

    service.store.mutate(job_id, interrupted)
    result = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert result["status"] == "failed" and result["message"] == ov.INTERRUPTED


def test_extraction_starts_the_drawing_and_work_once_runs_overview_tasks():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id="L01", raw_name="ESP32-C3 Super Mini")]

    gemini = Gemini(
        generated={"parts": [BOARD], "wiring": [], "notes": []},
        judged={"summary": "ok", "parts": [], "wires": []},
    )
    settings = Settings(
        _env_file=None,
        demo_mode=False,
        sourcing_enabled=False,
        spec_fill_enabled=False,
        overview_enabled=True,
        gemini_api_key="test",
    )
    app = create_app(settings, Extractor())
    app.state.overview_service.transport = httpx.MockTransport(gemini)
    app.state.overview_service.fetcher = FakeFetcher({})
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
        headers = {"X-Job-Token": created["job_token"]}
        job = client.get(created["watch"], headers=headers).json()
        assert job["status"] == "awaiting_confirmation"
        assert job["overview"]["status"] == "ready"
        assert job["overview"]["parts"][0]["verdict"] == "unverified"  # judge reviewed nothing
        assert gemini.sites() == ["draw", "judge_parts", "wire"]
    service, overviews = app.state.job_service, app.state.overview_service
    job_id = created["job_id"]

    def again(record):
        record.job.overview = ov.pending(record.job)
        record.overview_lease_until = now() + timedelta(minutes=5)

    service.store.mutate(job_id, again)
    assert work_once(service, None, Work(job_id=job_id, kind="overview"), overviews)
    saved = service.store.get(job_id).job
    assert saved.overview.status == "ready"
    # Same lines and code: the shared cache answers without another model call.
    assert gemini.sites() == ["draw", "judge_parts", "wire"]
    assert saved.cost_estimate.cache_hits == {"overview": 1}


# -- demo and routes -----------------------------------------------------------------------
def test_demo_jobs_get_a_labelled_fixture_without_any_model_call():
    gemini = Gemini()
    app = create_app(Settings(_env_file=None, demo_mode=True, overview_enabled=True))
    app.state.overview_service.transport = httpx.MockTransport(gemini)
    with TestClient(app) as client:
        created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
        headers = {"X-Job-Token": created["job_token"]}
        result = client.get(created["watch"] + "/overview", headers=headers).json()
    assert result["status"] == "ready" and result["demo"] is True
    assert [p["line_id"] for p in result["parts"]] == ["L01", "L02"]  # jumper wire not drawn
    assert [w["signal"] for w in result["wiring"]] == ["power", "ground", "i2c_sda", "i2c_scl"]
    assert {p["verdict"] for p in result["parts"]} == {"unverified"}
    assert result["judge"]["status"] == "skipped" and "Demo" in result["notes"][0]
    assert all("(demo)" in p["label"] for p in result["parts"])
    assert gemini.sent == []
    job = app.state.job_service.store.get(created["job_id"]).job
    parts = job.overview.parts
    raw = [w.model_dump(mode="json") for w in job.overview.wiring]
    for entry in raw:
        entry["evidence"] = None
    wires, notes = ov.validate(parts, raw, job.items, {}, [])
    assert len(wires) == 4 and all(not w.problems for w in wires) and notes == []
    assert redact(job).overview == job.overview


def test_routes_are_owner_only_and_need_a_parts_list():
    client, app, job_id = setup()
    assert client.get(f"/v1/jobs/{job_id}/overview").json()["error"]["code"] == (
        "OVERVIEW_NOT_FOUND"
    )
    stranger = {"X-Job-Token": "x" * 40}
    assert client.post(f"/v1/jobs/{job_id}/overview", headers=stranger).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/overview", headers=stranger).status_code == 404
    service = app.state.job_service
    queued, token = service.create(CreateJob(url=REPO))
    response = client.post(f"/v1/jobs/{queued.job_id}/overview", headers={"X-Job-Token": token})
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE"
    assert client.post(f"/v1/jobs/{job_id}/overview").status_code == 200


def test_the_drawing_settles_open_spec_questions_it_can_answer():
    answers = [
        {"line_id": "L03", "field": "logic_v", "value": "3.3", "reason": "VCC wired to 3.3."},
        {"line_id": "L03", "field": "output_mode", "value": "sometimes", "reason": "Bad value."},
        {"line_id": "L02", "field": "i2c_address", "value": "0x3c", "reason": "Not asked."},
    ]
    gemini = Gemini(generated=GENERATED | {"answers": answers})
    client, app, job_id = setup(gemini)
    service = app.state.job_service

    def ask(record):
        for item in record.job.items:
            item.clarifications = ov.resolve_part(item).clarifications

    service.store.mutate(job_id, ask)
    client.post(f"/v1/jobs/{job_id}/overview")
    result = client.get(f"/v1/jobs/{job_id}/overview").json()
    settled = {(r["line_id"], r["field"]): r for r in result["resolved"]}
    # The touch pad's pins come off its drawing; the disputed OLED answers nothing.
    assert settled[("L03", "pinout")]["value"] == "GND,I/O,VCC"
    assert settled[("L03", "pinout")]["source"] == "drawing"
    assert settled[("L03", "logic_v")]["value"] == "3.3"
    assert ("L02", "pinout") not in settled and ("L02", "i2c_address") not in settled
    assert ("L03", "output_mode") not in settled  # not an allowed value
    touch = service.store.get(job_id).job.items[2]
    assert touch.ai_specs.pinout == "GND,I/O,VCC" and touch.ai_specs.logic_v == 3.3
    assert [c.field for c in touch.clarifications] == ["output_mode", "active_level"]
    asked = gemini.document("wire")["open_questions"]
    assert {"line_id": "L03", "field": "logic_v", "allowed": [3.3, 5.0]} in asked
    assert not any(q["field"] == "pinout" for q in asked)


def test_a_failed_group_is_redrawn_one_line_per_call(monkeypatch):
    monkeypatch.setattr("bharat_sourcer.resilience.time.sleep", lambda _: None)
    gemini = Gemini()
    gemini.grouped_status = True
    client, _, job_id = setup(gemini)
    client.post(f"/v1/jobs/{job_id}/overview")
    result = client.get(f"/v1/jobs/{job_id}/overview").json()
    assert result["status"] == "ready"
    assert [p["line_id"] for p in result["parts"]] == ["L01", "L02", "L03"]
    assert not any("could not be drawn" in note for note in result["notes"])
    draws = [b for b in gemini.sent if kind(b) == "draw"]
    # Two groups, each tried twice and once on the fallback model, then four single-line calls.
    assert len(draws) == 10
    fallback = [r for r in gemini.urls if "gemini-3.5-flash-lite" in r]
    assert len(fallback) == 2


def test_overview_calls_go_to_vertex_and_fall_back_to_the_api_key(monkeypatch):
    monkeypatch.setattr("bharat_sourcer.gemini_api.vertex_token", lambda: "vertex-token")
    gemini = Gemini()
    client, _, job_id = setup(gemini, gcp_project="demo-project")
    client.post(f"/v1/jobs/{job_id}/overview")
    assert client.get(f"/v1/jobs/{job_id}/overview").json()["status"] == "ready"
    assert gemini.urls and all(
        url.startswith(
            "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/global/"
        )
        for url in gemini.urls
    )

    class Refusing(Gemini):
        def __call__(self, request):
            if "aiplatform" in str(request.url):
                with self.lock:
                    self.urls.append(str(request.url))
                return httpx.Response(403)
            return super().__call__(request)

    refusing = Refusing()
    second, _, other = setup(refusing, gcp_project="demo-project")
    second.post(f"/v1/jobs/{other}/overview")
    assert second.get(f"/v1/jobs/{other}/overview").json()["status"] == "ready"
    assert any("generativelanguage" in url for url in refusing.urls)
