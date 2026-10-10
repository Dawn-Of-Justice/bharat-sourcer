import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bharat_sourcer.compat import assess, parse_name, resolve_part
from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import BomItem, PartSpecs
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import verify_page


def oled(**changes):
    values = {
        "family": "oled",
        "controller": "ssd1306",
        "interface": "i2c",
        "resolution": "128x64",
        "logic_v": 3.3,
        "supply_min_v": 3.3,
        "supply_max_v": 5.0,
        "pinout": "GND,VCC,SCL,SDA",
        "i2c_address": "0x3c",
    }
    return PartSpecs(**(values | changes))


def test_matching_complete_specs_grade_a_with_limited_scope():
    result = assess(oled(), oled())
    assert result.grade == "A"
    assert result.scope == "declared_specs_only"
    assert result.references


def test_address_only_change_grade_b():
    result = assess(oled(), oled(i2c_address="0x3d"))
    assert result.grade == "B"
    assert result.changes == ["Change the configured I2C address from 0x3c to 0x3d"]


@pytest.mark.parametrize(
    "changed",
    [
        {"controller": "sh1106"},
        {"logic_v": 5.0},
        {"interface": "spi"},
        {"resolution": "128x32"},
        {"pinout": "VCC,GND,SCL,SDA"},
        {"supply_min_v": 4.0},
        {"supply_max_v": 3.3},
    ],
)
def test_hard_mismatch_blocks(changed):
    assert assess(oled(), oled(**changed)).grade == "X"


def test_unknown_cannot_get_positive_grade_even_with_known_address_change():
    result = assess(oled(), oled(pinout=None, i2c_address="0x3d"))
    assert result.status == "unknown"
    assert result.grade is None
    assert "offered.pinout" in result.missing_fields


def test_known_mismatch_is_not_hidden_by_missing_fields():
    assert assess(oled(), oled(controller="sh1106", pinout=None)).grade == "X"


def test_pro_micro_voltage_variant_mismatch():
    required = PartSpecs(
        family="pro_micro",
        controller="atmega32u4",
        logic_v=5.0,
        clock_mhz=16,
        pinout="pro_micro_v13",
    )
    candidate = PartSpecs(
        family="pro_micro",
        controller="atmega32u4",
        logic_v=3.3,
        clock_mhz=8,
        pinout="pro_micro_v13",
    )
    assert assess(required, candidate).grade == "X"


def test_sensor_output_mode_and_polarity_must_match():
    values = {
        "family": "ttp223",
        "controller": "ttp223",
        "logic_v": 3.3,
        "interface": "digital",
        "supply_min_v": 2.0,
        "supply_max_v": 5.5,
        "pinout": "GND,IO,VCC",
        "output_mode": "momentary",
        "active_level": "high",
    }
    required = PartSpecs(**values)
    assert assess(required, PartSpecs(**values)).grade == "A"
    assert assess(required, PartSpecs(**(values | {"output_mode": "toggle"}))).grade == "X"
    assert assess(required, PartSpecs(**(values | {"active_level": "low"}))).grade == "X"


def test_charge_only_cable_cannot_replace_data_cable():
    values = {
        "family": "usb_cable",
        "connector_a": "usb_a",
        "connector_b": "micro_b",
        "data_support": True,
    }
    assert assess(PartSpecs(**values), PartSpecs(**(values | {"data_support": False}))).grade == "X"
    assert assess(PartSpecs(**values), PartSpecs(**(values | {"data_support": None}))).grade is None


def test_name_does_not_inherit_chip_specs_or_confuse_supply_with_logic():
    specs = parse_name("TTP223 module 2.0-5.5V")
    assert specs.supply_max_v is None
    assert specs.logic_v is None
    assert parse_name("Pro Micro 5V 16MHz").logic_v is None
    assert parse_name("SSD1306 SH1106 OLED").controller is None


def test_unsupported_family_stays_unknown():
    assert assess(PartSpecs(), PartSpecs()).grade is None


@pytest.mark.parametrize(
    "values",
    [
        {"supply_min_v": 5, "supply_max_v": 3.3},
        {"family": "pro_micro", "controller": "ssd1306"},
        {"family": "pro_micro", "logic_v": 3.3, "clock_mhz": 16},
        {"data_support": "yes"},
    ],
)
def test_invalid_specs_rejected(values):
    with pytest.raises(ValidationError):
        PartSpecs(**values)


def test_seller_properties_have_evidence_and_conflicts_become_unknown():
    product = {
        "@type": "Product",
        "name": "SSD1306 I2C OLED 128x64",
        "offers": {"@type": "Offer", "price": "100", "priceCurrency": "INR"},
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "controller", "value": "sh1106"},
            {"@type": "PropertyValue", "name": "logic_v", "value": 3.3},
        ],
    }
    html = '<script type="application/ld+json">' + json.dumps(product) + "</script>"
    page = Page("https://seller.example/oled", 200, {"content-type": "text/html"}, html.encode())
    offer = verify_page(page, "OLED")
    assert offer.specs.controller is None
    assert offer.specs.logic_v == 3.3
    assert any(e.field == "logic_v" and e.source == "seller_property" for e in offer.spec_evidence)


def test_clarification_answer_persists_through_confirmation():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id="L01", raw_name="Pro Micro board")]

    settings = Settings(_env_file=None, demo_mode=False, sourcing_enabled=False)
    with TestClient(create_app(settings, Extractor())) as client:
        created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
        headers = {"X-Job-Token": created["job_token"]}
        job = client.get(created["watch"], headers=headers).json()
        assert "logic_v" in [q["field"] for q in job["items"][0]["clarifications"]]
        response = client.post(
            created["watch"] + "/confirm",
            headers=headers,
            json={
                "edits": [
                    {
                        "op": "update",
                        "line_id": "L01",
                        "specs": {
                            "family": "pro_micro",
                            "controller": "atmega32u4",
                            "logic_v": 5.0,
                            "clock_mhz": 16,
                            "pinout": "pro_micro_v13",
                        },
                    }
                ]
            },
        )
        assert response.status_code == 202
        item = client.get(created["watch"], headers=headers).json()["items"][0]
        assert item["specs"]["logic_v"] == 5.0
        assert item["clarifications"] == []
        resolution = resolve_part(BomItem.model_validate(item))
        assert next(e for e in resolution.evidence if e.field == "logic_v").source == "user"


def test_conflicting_confirmation_rolls_back_every_edit():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id="L01", raw_name="SSD1306 OLED 128x64")]

    with TestClient(
        create_app(Settings(_env_file=None, demo_mode=False, sourcing_enabled=False), Extractor())
    ) as client:
        created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
        headers = {"X-Job-Token": created["job_token"]}
        before = client.get(created["watch"], headers=headers).json()
        response = client.post(
            created["watch"] + "/confirm",
            headers=headers,
            json={
                "edits": [
                    {"op": "update", "line_id": "L01", "qty": 2},
                    {"op": "update", "line_id": "L01", "specs": {"family": "pro_micro"}},
                ]
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_SPECS"
        assert client.get(created["watch"], headers=headers).json() == before
