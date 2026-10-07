"""The 13 worked substitution cases (docs/04-reference/01-worked-substitution-cases.md).

Inputs are fixed, labelled test facts: catalogue values re-labelled as declared for the
offer, plus explicit overrides. They are not verified seller data. No model is called.
"""

import pytest

from bharat_sourcer.catalog import load_catalog
from bharat_sourcer.compat import assess_offer, project_context, reassess_report, resolve_part
from bharat_sourcer.compat_rules import Context, Side, evaluate, side_from_entry
from bharat_sourcer.schemas import (
    BomItem,
    PartRequirement,
    PartSpecs,
    ProjectContext,
    Report,
    ReportLine,
    VerifiedOffer,
)


def part(entry_id, source="test", **overrides) -> Side:
    side = side_from_entry(load_catalog().get(entry_id), source)
    for name, value in overrides.items():
        side.set(name, value, source)
    return side


def board(entry_id, **changes) -> Context:
    entry = load_catalog().get(entry_id)
    values = dict(
        controller=entry.name,
        controller_logic_v=entry.logic_v,
        controller_5v_tolerant=entry.io_5v_tolerant,
        rails=tuple(entry.rails_v),
        strapping_pins=tuple(entry.strapping_pins),
        input_only_pins=tuple(entry.input_only_pins),
    )
    return Context(**(values | changes))


def rules(outcome, grade=None):
    return {f.rule for f in outcome.findings if grade is None or f.grade == grade}


FEATHER = board("feather_huzzah_esp8266")
UNO = board("arduino_uno_r3")


# Case 1: Adafruit BME280 → GY-BME280-3.3
def test_case_01_bme280_on_3v3_board_is_address_and_connector_change():
    outcome = evaluate(part("bme280_adafruit"), part("bme280_gy_3v3"), FEATHER)
    assert outcome.grade == "B"
    assert {"i2c_address", "connector"} <= rules(outcome, "B")
    assert "lookalike_risk" in rules(outcome, "A")
    change = next(f.change for f in outcome.findings if f.rule == "i2c_address")
    assert "0x76" in change
    assert not outcome.missing


def test_case_01_bme280_3v3_module_on_5v_uno_needs_rail_and_level_change():
    outcome = evaluate(part("bme280_adafruit"), part("bme280_gy_3v3"), UNO)
    assert outcome.grade == "C"
    assert {"supply_range", "logic_level"} <= rules(outcome, "C")
    supply = next(f for f in outcome.findings if f.rule == "supply_range")
    assert "3.3 V rail" in supply.change


def test_case_01_bmp280_lookalike_loses_humidity():
    outcome = evaluate(part("bme280_adafruit"), part("bmp280_gy"), FEATHER)
    assert outcome.grade == "D"
    assert "measured_superset" in rules(outcome, "D")
    needs_humidity = Context(**(vars(FEATHER) | {"needs": frozenset({"humidity"})}))
    assert evaluate(part("bme280_adafruit"), part("bmp280_gy"), needs_humidity).grade == "X"


# Case 2: PowerSwitch Tail II (US 120 V) → 230 V SSR / relay
def test_case_02_ssr_needs_enclosure_on_indian_mains():
    outcome = evaluate(part("powerswitch_tail_2"), part("ssr_25da"), UNO)
    assert outcome.grade == "C"
    finding = next(f for f in outcome.findings if f.rule == "mains_enclosure")
    assert finding.area == "safety" and "enclosure" in finding.change


def test_case_02_active_low_relay_adds_polarity_change():
    outcome = evaluate(part("powerswitch_tail_2"), part("relay_1ch_5v"), UNO)
    assert outcome.grade == "C"
    assert "polarity" in rules(outcome, "B")
    assert "digitalWrite" in next(f.change for f in outcome.findings if f.rule == "polarity")


def test_case_02_us_120v_product_is_not_usable():
    outcome = evaluate(part("powerswitch_tail_2"), part("powerswitch_tail_2"), UNO)
    assert outcome.grade == "X"
    assert "mains_rating" in rules(outcome, "X")


# Case 3: A4988 → TMC2209 (MKS V2.0)
def test_case_03_tmc2209_is_rewire_grade_and_fails_at_36v():
    at_12v = evaluate(part("a4988"), part("tmc2209_mks"), Context(motor_supply_v=12))
    assert at_12v.grade == "C"
    texts = " ".join(f.change for f in at_12v.findings if f.change)
    assert "SPREAD" in texts and "PDN/UART" in texts and "VREF" in texts
    at_36v = evaluate(part("a4988"), part("tmc2209_mks"), Context(motor_supply_v=36))
    assert at_36v.grade == "X"
    assert "motor_supply" in rules(at_36v, "X")


# Case 4: A4988 → DRV8825
def test_case_04_drv8825_is_config_change():
    outcome = evaluate(part("a4988"), part("drv8825"), Context(motor_supply_v=12))
    assert outcome.grade == "B"
    texts = " ".join(f.change for f in outcome.findings if f.change)
    assert "VREF × 2" in texts and "FAULT" in texts and "1.9 µs" in texts
    assert not outcome.missing


def test_driver_current_below_motor_need_is_unsafe():
    ctx = Context(motor_supply_v=12, motor_current_a=1.5)
    outcome = evaluate(part("a4988"), part("a4988", current_a=1.0), ctx)
    assert outcome.grade == "X"
    assert "driver_current" in rules(outcome, "X")


# Case 5: Feather HUZZAH ESP8266 → NodeMCU v3
def test_case_05_nodemcu_without_battery_is_board_config_change():
    outcome = evaluate(
        part("feather_huzzah_esp8266"), part("nodemcu_v3_lolin"), Context(uses_battery=False)
    )
    assert outcome.grade == "B"
    assert {"board_target", "usb_driver", "pin_labels"} <= rules(outcome, "B")


def test_case_05_nodemcu_with_battery_needs_protected_charger():
    outcome = evaluate(
        part("feather_huzzah_esp8266"), part("nodemcu_v3_lolin"), Context(uses_battery=True)
    )
    assert outcome.grade == "C"
    assert "DW01" in next(f.change for f in outcome.findings if f.rule == "battery_charger")


def test_case_05_unknown_battery_use_blocks_positive_grade():
    outcome = evaluate(part("feather_huzzah_esp8266"), part("nodemcu_v3_lolin"), Context())
    assert outcome.grade is None
    assert "context.uses_battery" in outcome.missing


# Case 6: SSD1306 0.96" → SH1106 1.3"
OLED_PINS = ["GND", "VCC", "SCL", "SDA"]


def test_case_06_sh1106_is_library_swap():
    outcome = evaluate(
        part("ssd1306_096_i2c", pins=OLED_PINS), part("sh1106_13_i2c", pins=OLED_PINS)
    )
    assert outcome.grade == "B"
    change = next(f.change for f in outcome.findings if f.rule == "curated_substitute")
    assert "Adafruit_SH110X" in change and "begin(0x3C, true)" in change


def test_case_06_swapped_vcc_gnd_header_needs_rewire_warning():
    outcome = evaluate(
        part("ssd1306_096_i2c", pins=OLED_PINS),
        part("sh1106_13_i2c", pins=["VCC", "GND", "SCL", "SDA"]),
    )
    assert outcome.grade == "C"
    finding = next(f for f in outcome.findings if f.rule == "header_order")
    assert "VCC/GND" in finding.change


def test_display_without_known_header_order_cannot_grade_positive():
    outcome = evaluate(part("ssd1306_096_i2c"), part("sh1106_13_i2c"))
    assert outcome.grade is None
    assert "required.pins" in outcome.missing


# Case 7: HC-SR04 from an Uno project on the user's ESP32
ESP32_FROM_UNO = board("esp32_devkit_v1", source_controller="Arduino Uno")


def test_case_07_hc_sr04_on_esp32_needs_echo_divider():
    outcome = evaluate(part("hc_sr04"), part("hc_sr04"), ESP32_FROM_UNO)
    assert outcome.grade == "C"
    logic = next(f for f in outcome.findings if f.rule == "logic_level")
    assert "ECHO" in logic.message and "1 kΩ/2 kΩ" in logic.change
    remap = next(f for f in outcome.findings if f.rule == "pin_function")
    assert remap.grade == "B" and "12" in remap.change and "34" in remap.change


def test_case_07_hc_sr04p_on_3v3_is_pin_remap_only():
    outcome = evaluate(part("hc_sr04"), part("hc_sr04p"), ESP32_FROM_UNO)
    assert outcome.grade == "B"
    assert "logic_level" not in rules(outcome)
    assert "supply_rail" in rules(outcome, "A")


# Case 8: NodeMCU driving WS2812B
def test_case_08_ws2812b_keeps_grade_a_with_optional_upgrades():
    ctx = board("nodemcu_v2_cp2102", led_count=74, psu_current_a=2.0)
    outcome = evaluate(part("ws2812b"), part("ws2812b"), ctx)
    assert outcome.grade == "A"
    advisories = {f.rule: f for f in outcome.findings if f.grade == "A"}
    assert "74AHCT125" in advisories["logic_level"].change
    assert "4.4 A" in advisories["current_headroom"].message
    assert "setBrightness" in advisories["current_headroom"].change


def test_rgbw_strip_needs_constructor_change():
    outcome = evaluate(part("ws2812b"), part("sk6812_rgbw"), board("nodemcu_v2_cp2102"))
    assert outcome.grade == "B"
    assert "NEO_GRBW" in next(f.change for f in outcome.findings if f.rule == "led_protocol")


# Case 9: Genuine Nano → CH340 clone
def test_case_09_nano_clone_needs_driver_and_old_bootloader():
    outcome = evaluate(part("arduino_nano"), part("arduino_nano_ch340"))
    assert outcome.grade == "B"
    assert {"usb_driver", "bootloader"} <= rules(outcome, "B")


# Case 10: PiOLED HAT → generic 0.91" SSD1306
def test_case_10_pioled_to_generic_oled_needs_jumpers():
    outcome = evaluate(
        part("adafruit_pioled"), part("ssd1306_091_i2c"), board("raspberry_pi_zero_w")
    )
    assert outcome.grade == "C"
    finding = next(f for f in outcome.findings if f.rule == "connector")
    assert "pin 1" in finding.change and "raspi-config" in finding.change
    assert "display_controller" not in rules(outcome)


# Case 11: DHT22 → DHT11
def test_case_11_dht11_is_functional_alternative():
    outcome = evaluate(part("dht22"), part("dht11"), UNO)
    assert outcome.grade == "D"
    assert {"curated_substitute", "measured_range", "measured_resolution"} <= rules(outcome, "D")
    assert "DHTTYPE" in " ".join(f.change for f in outcome.findings if f.change)


@pytest.mark.parametrize(
    "need",
    [
        {"ranges": {"temperature_c": (-10, None)}},
        {"steps": {"temperature_c": 0.1}},
    ],
)
def test_case_11_dht11_refused_for_freezer_or_decimal_needs(need):
    outcome = evaluate(part("dht22"), part("dht11"), Context(**(vars(UNO) | need)))
    assert outcome.grade == "X"


# Case 12: US 12 V 2 A wall wart → Indian 12 V 2 A SMPS
def test_case_12_indian_smps_is_drop_in():
    outcome = evaluate(part("adapter_12v_2a_us"), part("smps_12v_2a"))
    assert outcome.grade == "A"
    assert not outcome.missing


@pytest.mark.parametrize(
    "change, grade, rule",
    [
        ({"barrel": "5.5x2.5"}, "C", "barrel"),
        ({"polarity": "center_negative"}, "X", "polarity"),
        ({"current_a": 1.0}, "C", "output_current"),
        ({"output_v": 9.0}, "X", "output_voltage"),
        ({"input_vac": (100, 120)}, "X", "mains_input"),
    ],
)
def test_case_12_adapter_variants(change, grade, rule):
    outcome = evaluate(part("adapter_12v_2a_us"), part("smps_12v_2a", **change))
    assert outcome.grade == grade
    assert rule in rules(outcome, grade)


# Case 13: Adafruit MagTag
def test_case_13_genuine_magtag_is_drop_in():
    outcome = evaluate(part("adafruit_magtag"), part("adafruit_magtag"))
    assert outcome.grade == "A"


def test_case_13_esp32_epaper_board_is_redesign():
    outcome = evaluate(part("adafruit_magtag"), part("lilygo_t5_epaper"))
    assert outcome.grade == "D"
    assert "board_chip" in rules(outcome, "D")


# General rules
def test_catalogue_only_offer_facts_never_give_a_positive_grade():
    offered = part("bme280_gy_3v3", source="catalog")
    for name in ("id", "category", "chip"):
        offered.sources[name] = "seller_title"
    outcome = evaluate(part("bme280_adafruit"), offered, FEATHER)
    assert outcome.grade is None
    assert "offered.supply_v" in outcome.missing
    # The address change is still shown as "what changes".
    assert "i2c_address" in rules(outcome, "B")


def test_catalogue_facts_can_still_raise_problems():
    offered = part("bme280_gy_3v3", source="catalog")
    offered.sources["category"] = "seller_title"
    outcome = evaluate(part("bme280_adafruit"), offered, UNO)
    assert outcome.grade == "C"
    assert outcome.missing
    supply = next(f for f in outcome.findings if f.rule == "supply_range")
    assert "offered.supply_v:catalog" in supply.basis


def test_category_mismatch_is_incompatible():
    outcome = evaluate(part("hc_sr04"), part("ssd1306_096_i2c"))
    assert outcome.grade == "X"
    assert "identity" in rules(outcome, "X")


def test_i2c_collision_with_another_project_device():
    ctx = Context(**(vars(FEATHER) | {"i2c_in_use": frozenset({"0x76"})}))
    outcome = evaluate(part("bme280_adafruit"), part("bme280_gy_3v3"), ctx)
    assert "i2c_collision" in rules(outcome, "C")


# Pipeline integration: report lines carry findings, grade label and what changes.
def offer(title, **specs):
    return VerifiedOffer(
        url="https://seller.example/item",
        seller="seller.example",
        title=title,
        price_inr="100.00",
        stock="in_stock",
        specs=PartSpecs(**specs),
    )


def test_offer_assessment_uses_catalogue_rules_and_labels_everything():
    resolution = resolve_part(BomItem(line_id="L01", raw_name="Adafruit BME280"))
    result = assess_offer(resolution, offer("GY-BME280-3.3 Module"))
    assert result.method == "catalog_rules"
    assert result.required_catalog_id == "bme280_adafruit"
    assert result.offered_catalog_id == "bme280_gy_3v3"
    # Catalogue facts alone flag the narrower supply but cannot clear the offer.
    assert result.grade == "C" and result.missing_fields
    assert any("may be worse" in reason for reason in result.reasons)
    assert result.what_changes.wiring and result.what_changes.code
    assert any("unverified" in reason for reason in result.reasons)
    assert "https://seller.example/item" in result.references


def test_project_controller_adds_level_shifting_findings():
    project = ProjectContext(controller="Arduino Uno", power="5 V USB")
    item = BomItem(line_id="L01", raw_name="Adafruit BME280")
    result = assess_offer(resolve_part(item), offer("GY-BME280-3.3 Module"), project, [item], item)
    assert result.grade == "C"
    assert any(f.rule == "logic_level" for f in result.findings)
    assert result.grade_label == "Works with wiring or power changes"
    assert result.status == "changes_required"
    assert result.what_changes.power


def test_unknown_parts_keep_the_original_comparison():
    resolution = resolve_part(BomItem(line_id="L01", raw_name="Synthetic bearing"))
    result = assess_offer(resolution, offer("Bearing 608ZZ"))
    assert result.method == "declared_specs"
    assert result.grade is None
    assert result.findings == [] and result.what_changes is None


def test_project_context_reads_controller_power_and_requirements():
    item = BomItem(
        line_id="L02",
        raw_name="A4988",
        requirements=[
            PartRequirement(name="motor voltage", value="24", unit="V"),
            PartRequirement(name="motor current", value="1.2", unit="A"),
        ],
    )
    other = BomItem(line_id="L03", raw_name="SSD1306 I2C OLED")
    ctx = project_context(
        ProjectContext(controller="ESP32 DevKit V1", power="18650 Li-ion battery, 5 V boost"),
        [item, other],
        item,
    )
    assert ctx.controller_logic_v == 3.3 and ctx.controller_5v_tolerant is False
    assert 5.0 in ctx.rails and ctx.uses_battery is True
    assert ctx.motor_supply_v == 24 and ctx.motor_current_a == 1.2
    assert ctx.i2c_in_use == {"0x3c"}
    assert 12 in ctx.strapping_pins


def test_reassess_report_skips_selected_lines():
    item = BomItem(line_id="L01", raw_name="Adafruit BME280")
    selected = BomItem(line_id="L02", raw_name="Adafruit BME280")
    lines = [
        ReportLine(item=i, sourcing_status="offers_found", offers=[offer("GY-BME280-3.3")])
        for i in (item, selected)
    ]
    lines[1].selected_offer_url = lines[1].offers[0].url
    report = Report(summary="test", lines=lines)
    reassess_report(report, ProjectContext(controller="Arduino Uno"))
    assert report.lines[0].offers[0].compatibility.grade == "C"
    assert report.lines[1].offers[0].compatibility is None
