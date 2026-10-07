"""Unit normalisation and the buyable-spec guardrails. No model calls.

The spec values below are a mocked model response for the 2026-10 "Freeform
Light-Activated LED Circuit" job (dead-bug soldered, 3.6 V DC); they test how the server
guards and labels a model-stated spec, not what a live model would say.
"""

import json

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractedBom, GeminiExtractor, generation_schema
from bharat_sourcer.schemas import (
    BomItem,
    BuyableSpec,
    PartRequirement,
    ProjectContext,
    SpecParam,
)
from bharat_sourcer.sourcing.part_spec import (
    buyable_spec,
    find_measures,
    guard_spec,
    pack_quantity,
    parse_measure,
    seed_spec,
)


@pytest.mark.parametrize(
    "text, resistor, kind, value, unit",
    [
        ("33kΩ", False, "resistance", 33000, "ohm"),
        ("33 kOhm", False, "resistance", 33000, "ohm"),
        ("33K", True, "resistance", 33000, "ohm"),
        ("10K OHM", False, "resistance", 10000, "ohm"),
        ("4R7", False, "resistance", 4.7, "ohm"),
        ("4k7", False, "resistance", 4700, "ohm"),
        ("2M2", False, "resistance", 2.2e6, "ohm"),
        ("330R", True, "resistance", 330, "ohm"),
        ("1-20 Mohm", True, "resistance", 20e6, "ohm"),
        ("22µF", False, "capacitance", 22e-6, "F"),
        ("22μF", False, "capacitance", 22e-6, "F"),
        ("22uF", False, "capacitance", 22e-6, "F"),
        ("22 mfd", False, "capacitance", 22e-6, "F"),
        ("22 micro farad", False, "capacitance", 22e-6, "F"),
        ("100nF", False, "capacitance", 100e-9, "F"),
        ("10pF", False, "capacitance", 10e-12, "F"),
        ("16V", False, "voltage", 16, "V"),
        ("3.6 V DC", False, "voltage", 3.6, "V"),
        ("1/4W", False, "power", 0.25, "W"),
        ("1/4 watt", False, "power", 0.25, "W"),
        ("100 mW", False, "power", 0.1, "W"),
        ("20mA", False, "current", 0.02, "A"),
        ("5mm", False, "length", 0.005, "m"),
        ("5MM", False, "length", 0.005, "m"),
        ("±5%", False, "tolerance", 5, "%"),
        ("22 AWG", False, "gauge", 22, "AWG"),
        ("30AWG", False, "gauge", 30, "AWG"),
        ("SWG 24", False, "gauge", 24, "SWG"),
    ],
)
def test_unit_parsing(text, resistor, kind, value, unit):
    measure = parse_measure(text, resistor)
    assert measure is not None, text
    assert (measure.kind, measure.unit) == (kind, unit)
    assert measure.value == pytest.approx(value, rel=1e-9)


@pytest.mark.parametrize("text", ["GL5528", "0603 package", "5x11", "33K", "pencil 2H", "5 a day"])
def test_no_value_is_invented(text):
    # A bare "33K" is ohms only in a resistor context; part codes are never values.
    assert find_measures(text) == []


def test_several_values_and_the_33k_resistor_without_unit():
    found = find_measures("33K resistor 1/4W ±5%", resistor_context=True)
    assert [(m.kind, m.value) for m in found] == [
        ("power", 0.25),
        ("tolerance", 5.0),
        ("resistance", 33000.0),
    ]


@pytest.mark.parametrize(
    "text, qty",
    [
        ("Light Dependent Resistor LDR 5MM(Pack of 10)", 10),
        ("10 pcs 33k resistor", 10),
        ("Set of 50 resistors", 50),
        ("5mm LED - 100 Pieces", 100),
        ("Package includes: 1 x 22uF capacitor", None),
        ("Pack of 10 (10 pcs)", 10),
        ("Pack of 10, 20 pcs", None),
        ("33k resistor", None),
    ],
)
def test_pack_detection(text, qty):
    assert pack_quantity(text) == qty


PROJECT = ProjectContext(
    summary=(
        "A freeform, dead-bug soldered light-activated LED circuit: an LDR and resistor "
        "divider switch a 5mm LED from a 3.6 V supply."
    ),
    power="3.6 V DC",
    assumptions=["Colour bands on the unmarked resistor suggest 1k–10k."],
)

# Mocked extraction-call output for the six lines (not a live model response).
LINES = {
    "Bare copper wire": {
        "category": "wire",
        "params": [
            {
                "name": "wire_type",
                "value": "bare tinned copper",
                "required": False,
                "origin": "inferred",
                "reason": "Dead-bug builds use stiff uninsulated wire as the frame.",
            }
        ],
        "prefer": ["bare"],
        "synonyms": ["tinned copper wire", "bus wire"],
        "queries": ["tinned copper wire 22 SWG", "bare copper wire for soldering"],
    },
    "33kΩ resistor": {
        "category": "resistor",
        "mount": "tht",
        "mount_reason": "Freeform dead-bug soldering needs leaded through-hole parts.",
        "params": [
            {"name": "resistance", "value": "33kΩ", "origin": "stated"},
            {
                "name": "power_rating",
                "value": "1/4W",
                "operator": "at_least",
                "required": False,
                "origin": "inferred",
                "reason": "Standard hobby size; dissipation at 3.6 V is tiny.",
            },
        ],
        "exclude": ["SMD", "0603", "chip resistor"],
        "queries": ["33k ohm 1/4 watt resistor", "33k resistor through hole"],
    },
    "5mm clear LED": {
        "category": "led",
        "mount": "tht",
        "mount_reason": "A 5 mm LED is a through-hole package.",
        "params": [{"name": "size", "value": "5mm", "origin": "stated"}],
        "prefer": ["clear"],
        "synonyms": ["water clear", "transparent", "white"],
        "queries": ["5mm water clear LED", "5mm white LED"],
    },
    "LDR (Photoresistor)": {
        "category": "ldr",
        "mount": "tht",
        "mount_reason": "Leaded LDR soldered freeform.",
        "params": [
            {
                "name": "size",
                "value": "5mm",
                "required": False,
                "origin": "inferred",
                "reason": "The common hobby LDR size.",
            }
        ],
        "synonyms": ["photoresistor", "light dependent resistor", "GL5528", "GL5537"],
        "queries": ["LDR 5mm GL5528", "photoresistor 5mm"],
    },
    "Through-hole resistor": {
        "category": "resistor",
        "mount": "tht",
        "mount_reason": "The source calls it through-hole.",
        "params": [
            {
                "name": "resistance",
                "value": "1k",
                "operator": "between",
                "value_max": "10k",
                "origin": "inferred",
                "reason": "Project assumption: the colour bands suggest 1k–10k.",
            }
        ],
        "needs_value": True,
        "needs_value_reason": "The source does not state the value.",
        "queries": ["1/4 watt resistor through hole"],
    },
    "22µF 16V electrolytic capacitor": {
        "category": "capacitor_electrolytic",
        "mount": "tht",
        "mount_reason": "Radial electrolytic for a hand-soldered build.",
        "params": [
            {"name": "capacitance", "value": "22µF", "origin": "stated"},
            {"name": "voltage_rating", "value": "16V", "operator": "at_least", "origin": "stated"},
        ],
        "synonyms": ["elko", "radial electrolytic"],
        "queries": ["22uF 16V electrolytic capacitor"],
    },
}


def extracted_lines(lines=LINES):
    bom = {
        "project": {
            "title": "Freeform Light-Activated LED Circuit",
            "summary": PROJECT.summary,
            "power": PROJECT.power,
            "assumptions": PROJECT.assumptions,
        },
        "items": [
            {
                "raw_name": name,
                "qty": 1,
                "evidence": [{"timestamp": "00:10", "observation": f"{name} on the bench"}],
                "buyable": buyable,
            }
            for name, buyable in lines.items()
        ],
    }
    reply = {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(bom)}]}}]
    }
    extractor = GeminiExtractor(
        Settings(_env_file=None, gemini_api_key="test"),
        httpx.MockTransport(lambda _: httpx.Response(200, json=reply)),
    )
    result = extractor.extract("https://www.youtube.com/watch?v=abcdefghijk")
    return {item.raw_name: item for item in result.items}, result.project


def test_extraction_states_buyable_specs_for_all_six_lines():
    items, project = extracted_lines()
    specs = {name: buyable_spec(item, project) for name, item in items.items()}
    assert all(s.origin == "ai_inferred" for s in specs.values())

    resistor = specs["33kΩ resistor"]
    assert (resistor.category, resistor.mount, resistor.mount_origin) == (
        "resistor",
        "tht",
        "inferred",
    )
    assert resistor.mount_reason
    assert {"SMD", "0603", "0805", "chip resistor"} <= set(resistor.exclude)
    value = resistor.params[0]
    assert (value.si_value, value.unit, value.origin) == (33000, "ohm", "stated")
    assert resistor.params[1].si_value == 0.25 and resistor.params[1].origin == "inferred"
    assert resistor.must == ["resistance"]
    assert resistor.queries[0] == "33k ohm 1/4 watt resistor"

    vague = specs["Through-hole resistor"]
    assert vague.needs_value and vague.needs_value_reason
    span = vague.params[0]
    assert (span.si_value, span.si_value_max, span.origin) == (1000, 10000, "inferred")

    cap = specs["22µF 16V electrolytic capacitor"]
    assert cap.params[0].si_value == pytest.approx(22e-6)
    assert cap.params[1].si_value == 16 and cap.params[1].operator == "at_least"
    assert not cap.needs_value

    assert specs["5mm clear LED"].params[0].si_value == pytest.approx(0.005)
    assert "clear" in specs["5mm clear LED"].prefer
    assert "GL5528" in specs["LDR (Photoresistor)"].synonyms
    assert specs["Bare copper wire"].category == "wire"
    assert specs["Bare copper wire"].mount == "any"
    assert all(1 <= len(s.queries) <= 4 for s in specs.values())


def test_buyable_spec_is_in_the_extraction_schema():
    schema = json.dumps(generation_schema(ExtractedBom))
    assert "buyable" in schema and "needs_value" in schema and "$defs" not in schema


def test_invented_values_are_dropped_and_flagged():
    lines = {
        # No basis: the source gives no value and the project states none either.
        "Through-hole resistor": {
            "category": "resistor",
            "mount": "tht",
            "mount_reason": "Named through-hole.",
            "params": [
                {"name": "resistance", "value": "4.7k", "origin": "inferred", "reason": "Typical."}
            ],
        },
        # "stated" but not in the source, and no reason: dropped.
        "Electrolytic capacitor": {
            "category": "capacitor_electrolytic",
            "params": [{"name": "capacitance", "value": "100uF", "origin": "stated"}],
        },
        # An inferred mount needs a reason.
        "Diode": {"category": "diode", "mount": "smd"},
    }
    items, project = extracted_lines(lines)
    resistor = buyable_spec(items["Through-hole resistor"], project)
    assert resistor.params == [] and resistor.needs_value
    assert any("no basis" in r for r in resistor.reasons)
    cap = buyable_spec(items["Electrolytic capacitor"], project)
    assert cap.params == [] and cap.needs_value
    assert buyable_spec(items["Diode"], project).mount == "any"


def test_seed_spec_without_ai_spec_normalises_the_name_only():
    spec = buyable_spec(BomItem(line_id="L01", raw_name="22µF 16V electrolytic capacitor"))
    # The seed classifies the category from the name (v0.21 seeds were always "other").
    assert spec.origin == "seed" and spec.category == "capacitor_electrolytic"
    assert spec.mount == "any" and not spec.needs_value
    assert [(p.name, p.si_value) for p in spec.params] == [
        ("capacitance", pytest.approx(22e-6)),
        ("voltage_rating", 16),
    ]
    assert spec.queries == ["22uF 16V electrolytic capacitor"]
    assert seed_spec(BomItem(line_id="L01", raw_name="Through-hole resistor")).params == []


def test_user_spec_is_kept_and_only_normalised():
    spec = BuyableSpec(
        origin="user",
        category="resistor",
        mount="tht",
        params=[SpecParam(name="resistance", value="4k7", origin="user")],
    )
    item = BomItem(line_id="L01", raw_name="Through-hole resistor", buyable_spec=spec)
    guarded = buyable_spec(item)
    assert guarded.params[0].si_value == 4700 and guarded.mount_origin == "user"
    assert not guarded.needs_value and guarded.queries == ["Through-hole resistor"]


def test_user_requirement_counts_as_stated_source():
    item = BomItem(
        line_id="L01",
        raw_name="Resistor",
        requirements=[PartRequirement(name="resistance", value="33", unit="kΩ")],
    )
    spec = BuyableSpec(
        origin="ai_inferred",
        category="resistor",
        params=[SpecParam(name="resistance", value="33K", origin="stated")],
    )
    guarded = guard_spec(spec, "Resistor resistance 33 kΩ", "")
    assert guarded.params[0].origin == "stated" and not guarded.needs_value
    assert buyable_spec(item.model_copy(update={"buyable_spec": spec})).params[0].si_value == 33000
