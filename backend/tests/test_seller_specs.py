"""Synthetic seller pages; values exercise parsing only and are not real module specs."""

import json

from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import verify_page
from bharat_sourcer.sourcing.specs import label_field, parse_value

URL = "https://seller.example/oled"


def page(title="SSD1306 OLED display", properties=(), body=""):
    product = {
        "@type": "Product",
        "name": title,
        "offers": {"@type": "Offer", "price": "250", "priceCurrency": "INR"},
        "additionalProperty": list(properties),
    }
    html = f'<script type="application/ld+json">{json.dumps(product)}</script>{body}'
    return verify_page(Page(URL, 200, {"content-type": "text/html"}, html.encode()), "OLED")


def sources(offer):
    return {e.field: e.source for e in offer.spec_evidence}


def test_spec_table_rows_and_definition_lists_are_read_with_evidence():
    offer = page(
        body="""
        <table>
          <tr><th>Operating Voltage (V)</th><td>2.0V - 5.5V</td></tr>
          <tr><td>Interface</td><td>IIC</td></tr>
          <tr><td>Display Resolution</td><td>128 x 64 pixels</td></tr>
        </table>
        <dl><dt>I2C Address:</dt><dd>0x3C</dd></dl>
        """
    )
    assert (offer.specs.supply_min_v, offer.specs.supply_max_v) == (2.0, 5.5)
    assert offer.specs.interface == "i2c"
    assert offer.specs.resolution == "128x64"
    assert offer.specs.i2c_address == "0x3c"
    assert offer.specs.controller == "ssd1306"
    assert sources(offer)["interface"] == "seller_table"
    assert sources(offer)["controller"] == "seller_title"
    assert all(e.locator == URL for e in offer.spec_evidence)
    assert offer.spec_conflicts == []


def test_ambiguous_or_generic_values_stay_unknown():
    offer = page(
        title="OLED display",
        body="""
        <table>
          <tr><td>Interface</td><td>I2C / SPI</td></tr>
          <tr><td>Voltage</td><td>3.3V</td></tr>
          <tr><td>Operating Voltage</td><td>5V</td></tr>
          <tr><td>Logic Level</td><td>3.3V or 5V</td></tr>
        </table>
        <script>document.write("<table><tr><td>Interface</td><td>SPI</td></tr></table>")</script>
        """,
    )
    # Only the title's product family is established; every ambiguous row is ignored.
    assert offer.specs.model_dump(exclude_none=True) == {"family": "oled"}
    assert [e.field for e in offer.spec_evidence] == ["family"]


def test_title_and_table_disagreement_is_reported_not_picked():
    offer = page(
        title="SSD1306 OLED 128x64",
        body="<table><tr><td>Resolution</td><td>128x32</td></tr></table>",
    )
    assert offer.specs.resolution is None
    assert offer.specs.controller == "ssd1306"
    [conflict] = offer.spec_conflicts
    assert conflict.field == "resolution"
    assert {(c.value, c.source) for c in conflict.candidates} == {
        ("128x64", "seller_title"),
        ("128x32", "seller_table"),
    }


def test_json_ld_property_labels_use_aliases_and_invalid_values_conflict():
    offer = page(
        properties=[
            {"@type": "PropertyValue", "name": "Communication Interface", "value": "I2C"},
            {"@type": "PropertyValue", "name": "logic_v", "value": "12"},
        ]
    )
    assert offer.specs.interface == "i2c"
    assert sources(offer)["interface"] == "seller_property"
    assert offer.specs.logic_v is None
    assert offer.specs.controller == "ssd1306"
    assert [c.field for c in offer.spec_conflicts] == ["logic_v"]


def test_label_and_value_helpers():
    assert label_field("Operating Voltage (DC):") == "supply"
    assert label_field("Frequency") is None
    assert parse_value("supply", "3.3 to 5V") == {"supply_min_v": 3.3, "supply_max_v": 5.0}
    assert parse_value("supply", "5V - 3.3V") == {}
    assert parse_value("clock_mhz", "16 MHz crystal") == {"clock_mhz": 16}
    assert parse_value("controller", "ATmega32U4") == {"controller": "atmega32u4"}
    assert parse_value("interface", "x" * 300) == {}
