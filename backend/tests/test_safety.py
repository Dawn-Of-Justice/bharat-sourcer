"""Deterministic safety flags. Every BOM and project text here is synthetic test data."""

import json

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import GeminiAssistant
from bharat_sourcer.extraction import ExtractionResult
from bharat_sourcer.jobs import JobService
from bharat_sourcer.safety import evaluate, voltages
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Job,
    PartRequirement,
    PartSpecs,
    ProjectContext,
    UpdateProject,
)


def bom(*parts):
    items = []
    for index, part in enumerate(parts, start=1):
        part = {"raw_name": part} if isinstance(part, str) else dict(part)
        part["requirements"] = [PartRequirement(**r) for r in part.get("requirements", [])]
        if "specs" in part:
            part["specs"] = PartSpecs(**part["specs"])
        items.append(BomItem(line_id=f"L{index:02d}", **part))
    return items


def codes(parts, project=None, user_level="beginner"):
    context = ProjectContext(**project) if project else None
    return {flag.code for flag in evaluate(bom(*parts), context, user_level)}


def volts(value, unit="V", name="operating voltage"):
    return {"name": name, "value": value, "unit": unit}


CASES = [
    # MAINS: mains parts, AC voltages, US 120 V products and relays switching AC loads.
    ("case 2 powerswitch tail", ["Arduino Uno", "PowerSwitch Tail II"], None, {"MAINS"}),
    ("solid state relay", ["SSR-25DA solid state relay"], None, {"MAINS"}),
    ("ac-dc module", ["HLK-PM01 AC-DC module 5V"], None, {"MAINS"}),
    ("power cord", ["IEC power cord"], None, {"MAINS"}),
    ("transformer", ["Step-down transformer 230V to 12V"], None, {"MAINS"}),
    ("appliance load", ["Rice cooker"], None, {"MAINS"}),
    ("uk plug part", ["3-pin plug top with fuse"], None, {"MAINS"}),
    (
        "ac voltage requirement",
        [{"raw_name": "Relay", "requirements": [volts("250", "V AC", "contact rating")]}],
        None,
        {"MAINS"},
    ),
    (
        "relay rating in name is conservative",
        ["5V relay module 10A 250VAC"],
        None,
        {"MAINS"},
    ),
    (
        "relay with lamp in summary",
        ["5V relay module", "Arduino Nano"],
        {"summary": "A relay turns a 230 V lamp on at dusk."},
        {"MAINS"},
    ),
    (
        "relay for home automation",
        ["4 channel relay module", "Arduino Uno"],
        {"summary": "Home automation for the lights and fans in one room."},
        {"MAINS"},
    ),
    ("mains in project power", ["Arduino Uno"], {"power": "Mains powered (230 V AC)"}, {"MAINS"}),
    ("us adapter", ["US 12V 2A wall adapter 120V"], None, {"MAINS"}),
    ("smps also high current", ["12V 5A SMPS"], None, {"MAINS", "HIGH_CURRENT"}),
    # MAINS negatives.
    ("relay 5v coil only", ["5V relay module", "Arduino Uno", "LED"], None, set()),
    (
        "relay switching a dc pump",
        ["5V relay module", "Arduino Uno", "5V mini submersible pump"],
        {"summary": "A soil sensor waters a plant with a 5 V pump."},
        {"HIGH_CURRENT"},
    ),
    ("relay switching a dc fan", ["ESP32", "5V relay", "12V DC fan"], None, set()),
    ("case 12 indian adapter", ["12V 2A adapter 100-240V Type D plug"], None, set()),
    ("usb charger", ["5V 2A USB charger"], None, set()),
    (
        "adapter prose in project",
        ["Arduino Uno"],
        {"power": "5 V from a 100-240 V USB wall adapter"},
        set(),
    ),
    # LIPO: lithium cells unless the BOM shows both protection and a charger.
    ("lipo pack", ["LiPo battery 3.7V 1200mAh"], None, {"LIPO"}),
    ("case 5 nodemcu lipo", ["NodeMCU v3", "LiPo battery 3.7V 500mAh"], None, {"LIPO"}),
    ("protected cell without charger", ["Li-ion 18650 cell with protection"], None, {"LIPO"}),
    ("charger without protection", ["TP4056 Li-ion charger module"], None, {"LIPO"}),
    (
        "protected cell and charger",
        ["Li-ion 18650 cell with protection", "TP4056 charger module with protection"],
        None,
        set(),
    ),
    (
        "lipo with bms and charger",
        ["2S LiPo pack", "2S BMS protection board", "2S balance charger"],
        None,
        set(),
    ),
    ("lithium in project power", ["Arduino Uno"], {"power": "2x 18650 cells (7.4 V)"}, {"LIPO"}),
    ("power bank", ["Power bank 10000mAh"], None, set()),
    ("coin cell", ["CR2032 coin cell"], None, set()),
    ("aa holder", ["4x AA battery holder"], None, set()),
    # HIGH_CURRENT: strips, motors, heavy supplies and stated currents above 3 A.
    ("led strip", ["WS2812B LED strip 60 LED/m 5 m"], None, {"HIGH_CURRENT"}),
    ("plain led strip", ["12V LED strip"], None, {"HIGH_CURRENT"}),
    ("neopixel ring unknown count", ["NeoPixel ring"], None, {"HIGH_CURRENT"}),
    ("few pixels", [{"raw_name": "WS2812B LED", "qty": 4}], None, set()),
    ("stepper", ["NEMA 17 stepper motor"], None, {"HIGH_CURRENT"}),
    ("motor driver", ["L298N motor driver"], None, {"HIGH_CURRENT"}),
    ("vibration motor", ["Coin vibration motor"], None, set()),
    ("watts to amps", ["12V 60W power supply"], None, {"HIGH_CURRENT"}),
    ("3a cable is not above 3a", ["USB-C cable 3A"], None, set()),
    (
        "current requirement",
        [{"raw_name": "Buck converter", "requirements": [volts("5", "A", "output current")]}],
        None,
        {"HIGH_CURRENT"},
    ),
    (
        "mah is not amps",
        ["Li-ion 18650 2600mAh with protection", "TP4056 with protection"],
        None,
        set(),
    ),
    # LEVEL_SHIFT: a controller in one logic domain and a part in the other.
    (
        "case 7 hc-sr04 on esp32",
        ["ESP32 DevKit", "HC-SR04 ultrasonic sensor"],
        None,
        {"LEVEL_SHIFT"},
    ),
    ("hc-sr04p is 3.3 v capable", ["ESP32 DevKit", "HC-SR04P ultrasonic sensor"], None, set()),
    ("hc-sr04 on uno", ["Arduino Uno", "HC-SR04 ultrasonic sensor"], None, set()),
    (
        "neopixels on esp32",
        ["ESP32 DevKit", {"raw_name": "WS2812B LED", "qty": 8}],
        None,
        {"LEVEL_SHIFT"},
    ),
    ("nrf24 on uno", ["Arduino Uno", "nRF24L01 module"], None, {"LEVEL_SHIFT"}),
    (
        "case 1 3.3 v bme280 on uno",
        ["Arduino Uno", {"raw_name": "BME280 module", "requirements": [volts("3.3")]}],
        None,
        {"LEVEL_SHIFT"},
    ),
    (
        "3.3 v bme280 on esp32",
        ["ESP32 DevKit", {"raw_name": "BME280 module", "requirements": [volts("3.3")]}],
        None,
        set(),
    ),
    (
        "3.3 v pro micro by spec",
        [{"raw_name": "Pro Micro", "specs": {"logic_v": 3.3}}, "HC-SR04"],
        None,
        {"LEVEL_SHIFT"},
    ),
    ("5 v pro micro", ["Pro Micro 5V 16MHz", "HC-SR04"], None, set()),
    (
        "lcd with esp32 project",
        ["16x2 LCD with I2C backpack"],
        {"controller": "ESP32"},
        {"LEVEL_SHIFT"},
    ),
    (
        "led forward voltage is not logic",
        [
            "Arduino Uno",
            {"raw_name": "Red LED", "requirements": [volts("2", name="forward voltage")]},
        ],
        None,
        set(),
    ),
    ("demo bom", ["ESP32 development board", "BME280 sensor module", "Jumper wire"], None, set()),
]


@pytest.mark.parametrize(
    ("parts", "project", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_rule_table(parts, project, expected):
    assert codes(parts, project) == expected


def test_case_2_sous_viduino_flags_us_mains_and_lines():
    items = bom("Arduino Uno", "PowerSwitch Tail II", "DS18B20 waterproof sensor", "Rice cooker")
    project = ProjectContext(summary="Sous vide controller switching a rice cooker.")
    [flag] = evaluate(items, project)
    assert (flag.code, flag.severity, flag.method) == ("MAINS", "danger", "deterministic_rules")
    assert flag.line_ids == ["L02", "L04"]
    assert "US 120 V / 60 Hz" in flag.guidance[0]
    text = " ".join(flag.guidance)
    for required in ("230 V / 50 Hz", "Type D", "Type M", "enclosure", "relay module or SSR"):
        assert required in text
    assert "certified smart plug" in text and "low-voltage version" in text
    trigger = next(t for t in flag.triggers if t.line_id == "L02")
    assert (trigger.field, trigger.matched) == ("raw_name", "PowerSwitch Tail")


def test_intermediate_makers_do_not_get_beginner_nudge():
    [flag] = evaluate(bom("SSR-25DA"), None, "intermediate")
    assert not any("low-voltage version" in g for g in flag.guidance)
    assert not any("US 120 V" in g for g in flag.guidance)


def test_case_8_ws2812_estimate_and_level_shift():
    items = bom("NodeMCU", {"raw_name": "WS2812B LED", "qty": 74})
    flags = {flag.code: flag for flag in evaluate(items, None)}
    assert set(flags) == {"HIGH_CURRENT", "LEVEL_SHIFT"}
    assert "about 4.44 A" in flags["HIGH_CURRENT"].message
    assert "Rule estimate, not measured" in flags["HIGH_CURRENT"].message
    assert flags["HIGH_CURRENT"].line_ids == ["L02"]
    assert flags["LEVEL_SHIFT"].line_ids == ["L01", "L02"]
    assert "74AHCT125" in " ".join(flags["LEVEL_SHIFT"].guidance)


def test_listed_level_shifter_still_flags_with_note():
    items = bom("ESP32", "HC-SR04", "Logic level converter 4 channel")
    [flag] = evaluate(items, None)
    assert flag.code == "LEVEL_SHIFT" and "(L03)" in flag.message


def test_lipo_message_names_missing_safeguards():
    [flag] = evaluate(bom("Li-ion 18650 cell with protection"), None)
    assert "a charger" in flag.message and "protection circuit" not in flag.message
    [flag] = evaluate(bom("LiPo 1S 500mAh"), None)
    assert "a protection circuit or a charger" in flag.message
    [flag] = evaluate(bom("Arduino Uno"), ProjectContext(power="LiPo pack"))
    assert flag.line_ids == [] and flag.triggers[0].field == "project.power"


def test_evidence_and_requirement_reason_are_read():
    items = bom(
        {
            "raw_name": "Relay board",
            "requirements": [
                {"name": "coil voltage", "value": "5", "unit": "V", "reason": "Switches mains."}
            ],
        }
    )
    [flag] = evaluate(items, None)
    assert flag.code == "MAINS"
    assert {t.field for t in flag.triggers} >= {"requirements[0].reason", "raw_name"}


def test_rules_are_deterministic_and_ordered():
    items = bom("ESP32", "WS2812B LED strip", "LiPo 2S", "SSR-40DA")
    first, second = evaluate(items, None), evaluate(items, None)
    assert first == second
    assert [flag.code for flag in first] == ["MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT"]


def test_voltage_parser_handles_ranges_and_notation():
    found = [(v.value, v.kind) for v in voltages("AC 100-240V in, 3V3 out, 250VAC, 30 VDC")]
    assert found == [(100, None), (240, None), (3.3, None), (250, "ac"), (30, "dc")]


class Extractor:
    def __init__(self, *names):
        self.names = names

    def extract(self, url):
        return ExtractionResult(
            items=bom(*self.names),
            project=ProjectContext(summary="Synthetic project for safety tests."),
        )


def test_job_flags_follow_extraction_confirmation_and_project_edits():
    jobs = JobService(Extractor("Arduino Uno", "PowerSwitch Tail II", "Relay module"))
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    draft = jobs.get(job.job_id, token)
    assert [flag.code for flag in draft.safety_flags] == ["MAINS"]
    edits = [
        {"op": "remove", "line_id": "L02"},
        {"op": "remove", "line_id": "L03"},
        {"op": "add", "raw_name": "LiPo battery 3.7V"},
    ]
    jobs.confirm(job.job_id, token, ConfirmJob(edits=edits))
    confirmed = jobs.get(job.job_id, token)
    assert [flag.code for flag in confirmed.safety_flags] == ["LIPO"]
    assert confirmed.safety_flags[0].line_ids == ["L04"]
    updated = jobs.update_project(
        job.job_id, token, UpdateProject(description="Plugs into a 230 V wall socket.")
    )
    assert [flag.code for flag in updated.safety_flags] == ["MAINS", "LIPO"]


def test_stored_jobs_without_flags_still_load():
    job = Job(job_id="a" * 32, input=CreateJob(url="https://example.com"))
    data = job.model_dump(mode="json")
    del data["safety_flags"]
    assert Job.model_validate(data).safety_flags == []


def test_chat_context_includes_safety_flags():
    jobs = JobService(Extractor("PowerSwitch Tail II"))
    job, token = jobs.create(CreateJob(url="https://youtu.be/abcdefghijk"))
    jobs.extract(job.job_id)
    seen = {}

    def handler(request):
        payload = json.loads(request.content)
        schema = payload["generationConfig"]["responseJsonSchema"]
        if "allowed" in schema.get("properties", {}):
            text = '{"allowed":true}'
        else:
            seen["context"] = json.loads(payload["contents"][0]["parts"][0]["text"])
            seen["prompt"] = json.dumps(payload)
            text = json.dumps({"text": "See the mains banner.", "cited_line_ids": ["L01"]})
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    adapter = GeminiAssistant(
        Settings(_env_file=None, gemini_api_key="test"), httpx.MockTransport(handler)
    )
    adapter.reply(jobs.get(job.job_id, token))
    [flag] = seen["context"]["safety_flags"]
    assert flag["code"] == "MAINS" and flag["line_ids"] == ["L01"]
    assert "never dismiss or soften a flag" in seen["prompt"]
