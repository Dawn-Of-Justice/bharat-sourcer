"""Curated catalogue integrity and deterministic name resolution (no network, no model)."""

import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from bharat_sourcer.catalog import CatalogEntry, load_catalog, normalize, parse_catalog
from bharat_sourcer.compat import resolve_part
from bharat_sourcer.schemas import BomItem, PartRequirement


def raw():
    path = files("bharat_sourcer").joinpath("data", "parts_catalog.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_catalogue_loads_and_has_broad_coverage():
    catalog = load_catalog()
    assert 80 <= len(catalog.entries) <= 160
    categories = {entry.category for entry in catalog.entries.values()}
    assert {"dev_board", "sensor", "display", "motor_driver", "led", "relay", "power"} <= categories


def test_every_entry_is_unverified_or_cites_a_source():
    for entry in load_catalog().entries.values():
        assert not entry.verified or entry.source
        assert entry.source is None or entry.source.startswith("https://")


def test_references_aliases_and_ranges_are_consistent():
    catalog = load_catalog()
    for entry in catalog.entries.values():
        for ref in entry.lookalikes + [s.id for s in entry.substitutes]:
            assert ref in catalog.entries and ref != entry.id
        for bounds in [entry.supply_v, entry.motor_supply_v, *entry.ranges.values()]:
            assert bounds is None or bounds[0] <= bounds[1]
        assert all(normalize(alias) for alias in entry.aliases)
        if entry.mains:
            assert entry.category in {"relay", "power"}


@pytest.mark.parametrize(
    "change",
    [
        {"supply_v": [5, 3.3]},
        {"i2c_addresses": ["0x3C"]},
        {"category": "sensor", "measures": []},
        {"verified": True, "source": None},
        {"family": "oled", "chip": "atmega32u4"},
        {"unknown_field": 1},
    ],
)
def test_entry_validation_rejects_bad_data(change):
    entry = next(e for e in raw()["entries"] if e["id"] == "ssd1306_096_i2c")
    with pytest.raises(ValidationError):
        CatalogEntry.model_validate(entry | change)


def test_duplicate_ids_aliases_and_dangling_references_are_rejected():
    entries = raw()["entries"]
    first = entries[0]
    with pytest.raises(ValueError, match="Duplicate"):
        parse_catalog({"entries": [first, first]})
    clash = first | {"id": "other_board"}
    with pytest.raises(ValueError, match="Alias"):
        parse_catalog({"entries": [first, clash]})
    with pytest.raises(ValueError, match="unknown reference"):
        parse_catalog({"entries": [first | {"lookalikes": ["missing_part"]}]})
    with pytest.raises(ValueError):
        parse_catalog({"items": []})


@pytest.mark.parametrize(
    "name, expected",
    [
        ("HC-SR04 Ultrasonic Sensor", "hc_sr04"),
        ("HCSR04", "hc_sr04"),
        ("HC-SR04P", "hc_sr04p"),
        ("GY-BME280 purple module 3.3V", "bme280_gy_3v3"),
        ('1.3" OLED SH1106', "sh1106_13_i2c"),
        ("ESP32-S3 DevKitC", "esp32_s3_devkitc"),
        ("A4988 stepper motor driver", "a4988"),
        ("16x2 LCD with I2C backpack", "lcd1602_i2c"),
        ("Arduino Pro Micro compatible 5V 16M Mini Leonardo", "pro_micro_5v"),
        ("TTP223 Capacitive Touch Sensor Module", "ttp223"),
    ],
)
def test_resolver_matches_specific_names(name, expected):
    result = load_catalog().resolve(name)
    assert result.status == "matched"
    assert result.entry.id == expected
    assert 0.5 <= result.confidence <= 1


@pytest.mark.parametrize(
    "name, candidates",
    [
        ("BME280 sensor", {"bme280_adafruit", "bme280_gy_3v3", "bme280_gy_5v"}),
        ("I2C OLED display", {"ssd1306_096_i2c", "sh1106_13_i2c"}),
        ("Pro Micro board", {"pro_micro_5v", "pro_micro_3v3"}),
        ("SSD1306 SH1106 OLED", {"sh1106_13_i2c", "ssd1306_096_i2c"}),
        ("ESP32 DevKit V1 with OLED", {"esp32_devkit_v1"}),
    ],
)
def test_ambiguous_names_return_candidates_instead_of_guessing(name, candidates):
    result = load_catalog().resolve(name)
    assert result.status == "ambiguous"
    assert result.entry is None
    assert candidates <= {entry.id for entry, _ in result.candidates}


@pytest.mark.parametrize("name", ["bearing", "motor", "LED", "resistors", "Synthetic part"])
def test_unknown_names_stay_unmatched(name):
    assert load_catalog().resolve(name).status == "unmatched"


def test_hyphen_spacing_and_inch_spellings_normalise():
    assert normalize('0.96" OLED') == normalize("0.96 inch OLED") == normalize("0.96in oled")
    assert load_catalog().resolve("HC SR04").entry.id == "hc_sr04"
    assert load_catalog().resolve("hc-sr04").entry.id == "hc_sr04"


def test_resolution_prefills_labelled_catalogue_specs_for_known_families():
    resolution = resolve_part(BomItem(line_id="L01", raw_name="Pro Micro 5V 16MHz"))
    assert resolution.specs.logic_v == 5.0
    assert resolution.specs.clock_mhz == 16
    sources = {e.field: (e.source, e.locator) for e in resolution.evidence}
    assert sources["logic_v"] == ("catalog", "catalog:pro_micro_5v")
    assert sources["clock_mhz"][0] == "part_name"
    assert resolution.catalog.status == "matched"
    assert resolution.catalog.verified is False
    assert resolution.catalog.origin == "curated_catalog"
    # Pin order varies between clones, so the catalogue never answers it.
    assert "pinout" in resolution.missing_specs


def test_catalogue_requirements_are_reference_only():
    item = BomItem(line_id="L01", raw_name="DS18B20 waterproof probe")
    resolution = resolve_part(item)
    assert resolution.catalog.id == "ds18b20"
    assert resolution.catalog.facts["supply_v"] == "3–5.5"
    assert all(isinstance(r, PartRequirement) for r in resolution.catalog.requirements)
    assert all(r.origin == "inferred" for r in resolution.catalog.requirements)
    assert all("not verified" in r.reason for r in resolution.catalog.requirements)
    # Known parts skip the generic "what must it do" question; the BOM line is unchanged.
    assert resolution.clarifications == []
    assert item.requirements == []


def test_ambiguous_names_do_not_prefill_and_user_answers_win():
    resolution = resolve_part(BomItem(line_id="L01", raw_name="I2C OLED display"))
    assert resolution.catalog.status == "ambiguous"
    assert "controller" in resolution.missing_specs
    item = BomItem(
        line_id="L02", raw_name="0.91 inch OLED", specs={"family": "oled", "controller": "sh1106"}
    )
    resolution = resolve_part(item)
    assert resolution.specs.controller == "sh1106"
    assert next(e for e in resolution.evidence if e.field == "controller").source == "user"


def test_user_conflict_with_catalogue_falls_back_without_catalogue_values():
    # The catalogue's 3.3 V variant runs at 8 MHz; a 5 V answer drops the catalogue values.
    item = BomItem(line_id="L01", raw_name="Pro Micro 3.3V", specs={"logic_v": 5.0})
    resolution = resolve_part(item)
    assert resolution.specs.logic_v == 5.0
    assert resolution.specs.clock_mhz is None
    assert all(e.source != "catalog" for e in resolution.evidence)
