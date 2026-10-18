"""Tolerant model-output validation and deep GitHub reads (code and KiCad schematics).

The bad model outputs below are SYNTHETIC reconstructions of failure shapes recorded live on
2026-10-16 (a suggested_qty of 1475712128, a project title of tens of KB of repeated words,
one malformed part beside a good one). Every README, sketch, schematic and part here is
SYNTHETIC test data, not verified parts, quantities or evidence. No network or Gemini call
runs: files come from a fake fetcher and Gemini responses from httpx.MockTransport.
"""

import json
import logging

import httpx
import pytest

from bharat_sourcer.code_evidence import part_kind, placed_symbols, read_code, schematic_name
from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import (
    ExtractedPageBom,
    ExtractionError,
    GeminiExtractor,
    cut_loop,
    lenient_bom,
    looping,
    truncate,
)
from bharat_sourcer.sourcing.fetch import Page

REPO = "https://github.com/maker/synthetic-remote"
RAW = "https://raw.githubusercontent.com/maker/synthetic-remote/HEAD/"
TREE = "https://api.github.com/repos/maker/synthetic-remote/git/trees/HEAD?recursive=1"
README = (
    "# Synthetic remote\n\nA voice-controlled TV remote. Firmware is in firmware/ and the "
    "board is in pcb/. It has an ESP32 board and an IR LED.\n"
)
SKETCH = "// Synthetic sketch\n#include <Wire.h>\n#include <Adafruit_SH110X.h>\n"
# Synthetic KiCad 7 schematic: a library definition, then placed symbols, including a power
# flag, a test point and a do-not-fit resistor that must be skipped.
SCHEMATIC = """(kicad_sch
\t(version 20231120)
\t(lib_symbols
\t\t(symbol "Device:R"
\t\t\t(in_bom yes)
\t\t\t(property "Reference" "R"
\t\t\t)
\t\t\t(property "Value" "R"
\t\t\t)
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:R")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "R1"
\t\t)
\t\t(property "Value" "100R 0.25W"
\t\t)
\t\t(property "Footprint" "Resistor_THT:R_Axial_DIN0207"
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:R")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "R2"
\t\t)
\t\t(property "Value" "100R 0.25W"
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:R")
\t\t(in_bom yes)
\t\t(dnp yes)
\t\t(property "Reference" "R3"
\t\t)
\t\t(property "Value" "100k DNF"
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:LED")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "D1"
\t\t)
\t\t(property "Value" "IR333C"
\t\t)
\t)
\t(symbol
\t\t(lib_id "Device:C_Polarized")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "C1"
\t\t)
\t\t(property "Value" "220uF/16V"
\t\t)
\t)
\t(symbol
\t\t(lib_id "Connector:TestPoint_Probe")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "TP1"
\t\t)
\t\t(property "Value" "TP_VBAT"
\t\t)
\t)
\t(symbol
\t\t(lib_id "power:PWR_FLAG")
\t\t(in_bom yes)
\t\t(dnp no)
\t\t(property "Reference" "#FLG01"
\t\t)
\t\t(property "Value" "PWR_FLAG"
\t\t)
\t)
)
"""
GOOD = {
    "raw_name": "ESP32 board",
    "qty": 1,
    "evidence": [{"quote": "It has an ESP32 board", "observation": "README names it"}],
}


def page(url, body, status=200, content_type="text/plain; charset=utf-8"):
    return Page(url, status, {"content-type": content_type}, body.encode())


class FakeFetcher:
    """Synthetic stand-in for SafeFetcher: serves canned documents and records calls."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.calls.append((url, max_bytes))
        value = self.responses.get(url, page(url, "", 404))
        if isinstance(value, Exception):
            raise value
        return value


def gemini(body):
    text = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(
        200,
        json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
    )


def extractor(fetcher, handler):
    return GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(handler),
        fetcher=fetcher,
    )


def tree(*paths):
    body = {"tree": [{"path": path, "type": "blob", "size": 1000} for path in paths]}
    return page(TREE, json.dumps(body), content_type="application/json")


def repository(**extra):
    return FakeFetcher(
        {
            RAW + "README.md": page(RAW + "README.md", README),
            TREE: tree("firmware/remote/remote.ino", "pcb/remote/remote.kicad_sch", "logo.png"),
            RAW + "firmware/remote/remote.ino": page(RAW + "firmware/remote/remote.ino", SKETCH),
            RAW + "pcb/remote/remote.kicad_sch": page(
                RAW + "pcb/remote/remote.kicad_sch", SCHEMATIC
            ),
            **extra,
        }
    )


def project(**fields):
    return {"summary": "A synthetic voice remote.", **fields}


def test_huge_suggested_qty_is_dropped_not_fatal():
    part = {**GOOD, "qty": None, "suggested_qty": 1475712128, "qty_reason": "one per button"}
    result = extractor(repository(), lambda r: gemini({"items": [part]})).extract(REPO)
    line = result.items[0]
    assert (line.qty, line.qty_source) == (1, "inferred")
    assert line.qty_reason == "Count not stated; assumed one for this build."


def test_runaway_title_becomes_null_and_long_text_is_truncated():
    runaway = "Voice Remote " * 3000  # about 39 KB, the recorded failure shape
    body = {
        "project": project(title=runaway, description="word " * 10 + "x" * 700),
        "items": [GOOD],
    }
    result = extractor(repository(), lambda r: gemini(body)).extract(REPO)
    assert result.project is not None
    assert result.project.title is None
    assert result.project.summary == "A synthetic voice remote."
    assert result.project.description is not None and len(result.project.description) <= 600


def test_looping_required_text_is_cut_where_the_loop_starts():
    observation = "Shown on the board. " + "again and again " * 400
    part = {**GOOD, "evidence": [{"quote": "It has an ESP32 board", "observation": observation}]}
    result = extractor(repository(), lambda r: gemini({"items": [part]})).extract(REPO)
    kept = result.items[0].evidence[0].observation
    assert kept.startswith("Shown on the board.") and len(kept) < 100


def test_invalid_item_beside_a_valid_one_is_dropped_and_logged(caplog):
    bad = {"raw_name": "", "qty": "two", "evidence": []}
    with caplog.at_level(logging.WARNING):
        result = extractor(repository(), lambda r: gemini({"items": [bad, GOOD]})).extract(REPO)
    assert [x.raw_name for x in result.items] == ["ESP32 board"]
    assert "EXTRACTION_ITEMS_DROPPED dropped=1 kept=1" in caplog.text


def test_a_bad_buying_spec_costs_the_spec_not_the_part():
    part = {**GOOD, "buyable": {"category": "not-a-category", "mount": "tht"}}
    bom = lenient_bom(ExtractedPageBom, {"items": [part]})
    assert bom.items[0].raw_name == "ESP32 board" and bom.items[0].buyable is None


def test_evidence_quotes_still_have_to_be_on_the_page():
    invented = {**GOOD, "evidence": [{"quote": "a free laptop", "observation": "Invented"}]}
    result = extractor(repository(), lambda r: gemini({"items": [invented, GOOD]})).extract(REPO)
    assert [x.raw_name for x in result.items] == ["ESP32 board"]


@pytest.mark.parametrize(
    "output",
    [
        {"items": [{"raw_name": "", "qty": 1, "evidence": []}]},  # every part malformed
        {"project": project()},  # no items list
        '{"items": [',  # cut off
    ],
)
def test_unusable_output_is_still_invalid_extraction(output):
    fetcher = FakeFetcher(
        {
            "https://www.hackster.io/maker/x": page(
                "https://www.hackster.io/maker/x", "<p>An ESP32 board</p>", content_type="text/html"
            )
        }
    )
    with pytest.raises(ExtractionError) as captured:
        extractor(fetcher, lambda r: gemini(output)).extract("https://www.hackster.io/maker/x")
    assert captured.value.code == "INVALID_EXTRACTION"


def test_text_helpers():
    assert looping("remote " * 20) and not looping("A voice-controlled TV remote with an ESP32.")
    assert cut_loop("Voice Remote " * 10) == "Voice Remote Voice Remote Voice"
    assert truncate("one two three", 9) == "one two"
    assert truncate("abcdefghij", 4) == "abcd"


def test_readme_without_parts_reads_code_and_kicad_schematics():
    fetcher = repository()
    result = extractor(fetcher, lambda r: gemini({"items": []})).extract(REPO)
    assert result.items == []
    names = {x.raw_name: x for x in result.code_items}
    assert "SH1106 OLED display" in names  # from the sketch's #include
    assert set(names) >= {
        "100R 0.25W resistor (R1, R2)",
        "IR333C LED (D1)",
        "220uF/16V electrolytic capacitor (C1)",
    }
    # Test points, power flags and do-not-fit parts are not parts to buy.
    assert not any("TP_VBAT" in n or "PWR_FLAG" in n or "100k" in n for n in names)
    resistor = names["100R 0.25W resistor (R1, R2)"]
    assert (resistor.qty, resistor.qty_source) == (2, "stated")
    evidence = resistor.evidence[0]
    assert evidence.source == "code" and evidence.file == "pcb/remote/remote.kicad_sch"
    # The quote is the cited line of the schematic, verbatim apart from whitespace.
    cited = SCHEMATIC.splitlines()[evidence.line - 1]
    assert evidence.quote == " ".join(cited.split()) == '(property "Value" "100R 0.25W"'
    assert str(evidence.url).endswith(f"pcb/remote/remote.kicad_sch#L{evidence.line}")
    assert any(url == TREE for url, _ in fetcher.calls)


def test_readme_with_parts_still_reads_schematics():
    fetcher = repository()
    result = extractor(fetcher, lambda r: gemini({"items": [GOOD]})).extract(REPO)
    assert [x.raw_name for x in result.items] == ["ESP32 board"]
    assert any(url.endswith(".kicad_sch") for url, _ in fetcher.calls)
    assert any(x.raw_name.startswith("IR333C LED") for x in result.code_items)


def test_github_readme_read_failure_falls_back_to_code_and_schematics():
    result = extractor(repository(), lambda r: gemini('{"items": [')).extract(REPO)
    assert result.items == []
    assert any(x.raw_name.startswith("IR333C LED") for x in result.code_items)


def test_github_readme_read_failure_without_code_still_fails():
    fetcher = FakeFetcher({RAW + "README.md": page(RAW + "README.md", README)})
    with pytest.raises(ExtractionError) as captured:
        extractor(fetcher, lambda r: gemini('{"items": [')).extract(REPO)
    assert captured.value.code == "INVALID_EXTRACTION"


def test_placed_symbols_ignores_library_definitions_and_repeated_units():
    repeated = SCHEMATIC.replace(
        '\t(symbol\n\t\t(lib_id "Device:LED")',
        '\t(symbol\n\t\t(lib_id "Device:LED")\n\t\t(in_bom yes)\n\t\t(property "Reference" "D1"\n'
        '\t\t)\n\t\t(property "Value" "IR333C"\n\t\t)\n\t)\n\t(symbol\n\t\t(lib_id "Device:LED")',
    )
    references = [symbol["reference"] for symbol in placed_symbols(repeated)]
    assert references == ["R1", "R2", "D1", "C1"]


def test_schematic_names_keep_part_numbers_and_name_unset_values_by_kind():
    assert schematic_name("AO3400A", "Transistor_FET:AO3400A", "transistor") == (
        "AO3400A transistor"
    )
    assert schematic_name("R", "Device:R", "resistor") == "resistor"
    assert schematic_name("INMP441", "Connector_Generic:Conn_01x06", None) == "INMP441"
    assert schematic_name("10k", "Device:R", "resistor") == "10k resistor"
    assert part_kind("C3", "Device:C_Polarized") == "electrolytic capacitor"
    assert part_kind("D1", "Device:LED") == "LED"
    assert part_kind("U2", "Connector_Generic:Conn_01x06") is None


def test_schematics_are_skipped_when_not_kicad_or_missing():
    fetcher = repository(
        **{RAW + "pcb/remote/remote.kicad_sch": page(RAW + "pcb/remote/remote.kicad_sch", "EAGLE")}
    )
    items = read_code(fetcher, REPO, README, deep=True)
    assert [x.raw_name for x in items] == ["SH1106 OLED display"]
