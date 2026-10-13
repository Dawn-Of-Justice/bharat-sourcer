"""AI spec fill: missing required spec fields decided from project context, not asked.

Every BOM line, project and Gemini response here is SYNTHETIC test data, not verified
parts or specs. No network call runs: Gemini answers come from httpx.MockTransport and the
job tests use a fake filler.
"""

import json

import httpx

from bharat_sourcer.compat import resolve_part
from bharat_sourcer.config import Settings
from bharat_sourcer.jobs import JobService
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Evidence,
    PartSpecs,
    ProjectContext,
    UpdateLine,
)
from bharat_sourcer.spec_fill import GeminiSpecFiller, accepted, fill_missing_specs

OLED = "1.3 inch I2C OLED display module (SH1106)"
TOUCH = "TTP223 capacitive touch sensor module"
PROJECT = ProjectContext(
    summary="Synthetic desk buddy: an ESP32-C3 drives an I2C OLED and reads a touch pad.",
    power="3.7V LiPo through a TP4056 charger",
    controller="ESP32-C3 Super Mini",
    interfaces=["I2C", "digital input"],
)


def line(line_id, name, **extra):
    evidence = [Evidence(timestamp="00:10", observation="Synthetic video evidence")]
    return BomItem(line_id=line_id, raw_name=name, evidence=evidence, **extra)


def gemini(body):
    text = json.dumps(body)
    return httpx.Response(
        200,
        json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
    )


class DictCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl_s):
        self.values[key] = value


def filler(handler, cache=None):
    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    return GeminiSpecFiller(settings, transport=httpx.MockTransport(handler), cache=cache)


# --- resolve_part with AI values -------------------------------------------------------


def test_ai_values_fill_missing_fields_and_are_labelled():
    item = line(
        "L02",
        TOUCH,
        ai_specs=PartSpecs(
            logic_v=3.3, pinout="GND,I/O,VCC", output_mode="momentary", active_level="high"
        ),
    )
    resolution = resolve_part(item)
    assert resolution.missing_specs == [] and resolution.clarifications == []
    sources = {e.field: (e.source, e.locator) for e in resolution.evidence}
    assert sources["logic_v"] == ("ai_inferred", "ai:L02")
    assert sources["controller"][0] == "part_name"
    assert sources["supply_max_v"][0] == "catalog"


def test_name_catalogue_and_user_values_beat_ai_values():
    item = line(
        "L01",
        OLED,
        specs=PartSpecs(i2c_address="0x3d"),
        ai_specs=PartSpecs(controller="ssd1306", i2c_address="0x3c", resolution="128x32"),
    )
    resolution = resolve_part(item)
    assert resolution.specs.controller == "sh1106"  # the name says SH1106
    assert resolution.specs.i2c_address == "0x3d"  # the user said so
    assert resolution.specs.resolution == "128x64"  # catalogue value
    assert all(e.source != "ai_inferred" for e in resolution.evidence)
    assert resolution.missing_specs == ["pinout"]


def test_only_missing_and_valid_fields_are_accepted():
    specs = accepted(
        {"pinout": "GND,VCC,SCL,SDA", "logic_v": 3.3, "supply_min_v": 9, "supply_max_v": 5},
        ["pinout", "supply_min_v", "supply_max_v"],
    )
    # logic_v was not missing; a minimum above the maximum is dropped, not guessed.
    assert specs.model_dump(exclude_none=True) == {
        "pinout": "GND,VCC,SCL,SDA",
        "supply_min_v": 9.0,
    }


# --- Gemini filler ---------------------------------------------------------------------


def test_one_batched_call_fills_lines_and_caches_them():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return gemini(
            {
                "items": [
                    {"id": 0, "values": {"pinout": "GND,VCC,SCL,SDA", "logic_v": 5.0}},
                    {
                        "id": 1,
                        "values": {
                            "logic_v": 3.3,
                            "pinout": "GND,I/O,VCC",
                            "output_mode": "momentary",
                            "active_level": "high",
                        },
                    },
                    {"id": 7, "values": {"pinout": "ignored"}},
                ]
            }
        )

    cache = DictCache()
    code = Evidence(
        source="code",
        observation="Synthetic include",
        quote="#include <Adafruit_SH110X.h>",
        url="https://github.com/maker/synthetic/blob/HEAD/a.ino#L3",
        file="a.ino",
        line=3,
    )
    items = [
        line("L01", OLED).model_copy(update={"evidence": [code]}),
        line("L02", TOUCH),
        line("L03", "Slide switch"),  # no known family: nothing to fill
    ]
    result = filler(handler, cache).fill(items, PROJECT)
    assert len(requests) == 1
    body = json.loads(requests[0]["contents"][0]["parts"][0]["text"])
    assert body["project"]["controller"] == "ESP32-C3 Super Mini"
    assert [x["missing"] for x in body["lines"]] == [
        ["pinout"],
        ["logic_v", "pinout", "output_mode", "active_level"],
    ]
    assert body["lines"][0]["code"] == ["a.ino:3 #include <Adafruit_SH110X.h>"]
    # The OLED's logic_v was already known (catalogue), so the model's 5.0 is ignored.
    assert result["L01"].model_dump(exclude_none=True) == {"pinout": "GND,VCC,SCL,SDA"}
    assert result["L02"].output_mode == "momentary" and "L03" not in result
    # Same lines, same project: served from the cache with no second call.
    again = filler(handler, cache).fill(items, PROJECT)
    assert len(requests) == 1 and again == result


def test_failures_keep_the_questions():
    items = [line("L02", TOUCH)]
    broken = filler(lambda request: httpx.Response(500, json={}))
    fill_missing_specs(broken, items, PROJECT)
    assert items[0].ai_specs == PartSpecs()
    assert len(resolve_part(items[0]).clarifications) == 4


def test_no_key_means_no_call():
    def handler(request):
        raise AssertionError("no call without a key")

    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key=None)
    no_key = GeminiSpecFiller(settings, transport=httpx.MockTransport(handler))
    assert no_key.fill([line("L02", TOUCH)], PROJECT) == {}


# --- Jobs ------------------------------------------------------------------------------


class FakeFiller:
    def __init__(self):
        self.calls = []

    def fill(self, items, project):
        self.calls.append([item.line_id for item in items])
        return {
            item.line_id: PartSpecs(pinout="GND,VCC,SCL,SDA")
            for item in items
            if item.raw_name == OLED
        }


class Extractor:
    def extract(self, url):
        return [line("L01", OLED), line("L02", TOUCH)]


def test_job_extraction_fills_specs_once_and_draft_edits_reuse_them():
    spec_filler = FakeFiller()
    service = JobService(Extractor(), "synthetic-model", spec_filler=spec_filler)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    job = service.get(job.job_id, token)
    assert spec_filler.calls == [["L01", "L02"]]
    oled, touch = job.items
    assert oled.ai_specs.pinout == "GND,VCC,SCL,SDA" and oled.clarifications == []
    assert [c.field for c in touch.clarifications] == [
        "logic_v",
        "pinout",
        "output_mode",
        "active_level",
    ]
    # A draft edit recomputes questions from the saved values, without a model call.
    edits = [UpdateLine(op="update", line_id="L02", qty=2)]
    service.edit_draft(job, ConfirmJob(edits=edits))
    assert job.items[0].clarifications == [] and spec_filler.calls == [["L01", "L02"]]


def test_renaming_a_line_drops_its_ai_values():
    spec_filler = FakeFiller()
    service = JobService(Extractor(), "synthetic-model", spec_filler=spec_filler)
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    job = service.get(job.job_id, token)
    edits = [UpdateLine(op="update", line_id="L01", raw_name="0.96 inch SSD1306 OLED")]
    service.edit_draft(job, ConfirmJob(edits=edits))
    assert job.items[0].ai_specs == PartSpecs()


def test_demo_jobs_never_fill():
    spec_filler = FakeFiller()
    service = JobService(spec_filler=spec_filler)
    job, _ = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    service.extract(job.job_id)
    assert spec_filler.calls == []


def test_spec_fill_uses_vertex_and_falls_back_to_the_api_key(monkeypatch):
    import httpx

    from bharat_sourcer.config import Settings
    from bharat_sourcer.gemini_api import post_generate

    monkeypatch.setattr("bharat_sourcer.gemini_api.vertex_token", lambda: "t")
    monkeypatch.setattr("bharat_sourcer.resilience.time.sleep", lambda _: None)
    hosts: list[str] = []

    def handle(request):
        hosts.append(request.url.host)
        return httpx.Response(503 if request.url.host == "aiplatform.googleapis.com" else 200)

    settings = Settings(_env_file=None, gemini_api_key="k", gcp_project="demo-project")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        response = post_generate(client, settings, "spec_fill", "m", {})
    assert response.status_code == 200
    assert hosts == ["aiplatform.googleapis.com"] * 2 + ["generativelanguage.googleapis.com"]
