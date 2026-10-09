"""Curated code recipes on synthetic sketches (tests/fixtures/code_adapt, not real projects)."""

from pathlib import Path

import pytest

from bharat_sourcer.catalog import load_catalog
from bharat_sourcer.code_adapt import apply_recipe, code_mask, recipes

FIXTURES = Path(__file__).parent / "fixtures" / "code_adapt"


def read(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


def test_every_recipe_matches_a_curated_catalogue_edge_and_its_text():
    catalog = load_catalog()
    for (from_id, to_id), recipe in recipes().items():
        entry = catalog.get(from_id)
        edge = next(s for s in entry.substitutes if s.id == to_id)
        code_texts = {c.text for c in edge.changes if c.area == "code"}
        claimed = set(recipe.get("implements", [])) | set(recipe.get("not_implemented", []))
        assert claimed <= code_texts, (from_id, to_id)


def test_dht22_to_dht11_changes_code_only_not_comments_or_strings():
    result = apply_recipe({"logger.ino": read("dht22.ino")}, "dht22", "dht11")
    assert result.ok
    [patch] = result.files
    assert "#define DHTTYPE DHT11   // DHT22 sensor on pin 2" in patch.patched
    assert 'Serial.println("DHT22 logger starting");' in patch.patched
    changed = [
        line
        for line in patch.diff.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert changed == [
        "-#define DHTTYPE DHT22   // DHT22 sensor on pin 2",
        "+#define DHTTYPE DHT11   // DHT22 sensor on pin 2",
    ]
    assert any("Verify:" in note and "DHT11" in note for note in result.notes)


def test_ssd1306_to_sh1106_patches_sketch_and_platformio():
    files = {"src/main.ino": read("ssd1306.ino"), "platformio.ini": read("platformio.ini")}
    result = apply_recipe(files, "ssd1306_096_i2c", "sh1106_13_i2c")
    assert result.ok
    patched = {p.path: p.patched for p in result.files}
    sketch = patched["src/main.ino"]
    assert "#include <Adafruit_SH110X.h>" in sketch
    assert "Adafruit_SH1106G display(128, 64, &Wire, -1);" in sketch
    assert "display.begin(0x3C, true)" in sketch
    assert "setTextColor(SH110X_WHITE)" in sketch and "SH110X_BLACK" in sketch
    # The string literal mentioning the old constant is untouched.
    assert '"Using SSD1306_WHITE text"' in sketch
    assert "adafruit/Adafruit SH110X@^2.5.7" in patched["platformio.ini"]
    assert not result.skipped or all("not used" in s for s in result.skipped)


def test_ssd1306_recipe_refuses_unexpected_begin_form():
    sketch = read("ssd1306.ino").replace(
        "display.begin(SSD1306_SWITCHCAPVCC, 0x3C)", "display.begin(SSD1306_SWITCHCAPVCC)"
    )
    result = apply_recipe({"a.ino": sketch}, "ssd1306_096_i2c", "sh1106_13_i2c")
    assert not result.ok and result.reason == "recipe_not_applicable"
    assert "begin" in result.detail
    assert result.files == []


def test_recipe_refuses_other_library_and_ambiguous_matches():
    thingpulse = '#include "SSD1306Wire.h"\nSSD1306Wire display(0x3c, SDA, SCL);\n'
    other = apply_recipe({"a.ino": thingpulse}, "ssd1306_096_i2c", "sh1106_13_i2c")
    assert other.reason == "recipe_not_applicable" and "library" in other.detail
    many = read("dht22.ino") + "".join(f"\nint x{i} = DHT22;" for i in range(8))
    ambiguous = apply_recipe({"a.ino": many}, "dht22", "dht11")
    assert ambiguous.reason == "recipe_not_applicable" and "Ambiguous" in ambiguous.detail


def test_drv8825_inserts_min_pulse_width_once_and_is_idempotent():
    result = apply_recipe({"s.ino": read("a4988.ino")}, "a4988", "drv8825")
    assert result.ok
    patched = result.files[0].patched
    assert "  stepper.setMaxSpeed(1000);\n  stepper.setMinPulseWidth(2);" in patched
    assert any("Microstep" in note and "not patched" in note for note in result.notes)
    assert any(note.startswith("Power:") for note in result.notes)
    again = apply_recipe({"s.ino": patched}, "a4988", "drv8825")
    assert not again.ok and again.reason == "recipe_not_applicable"


def test_no_code_change_and_unknown_edges_have_reasons():
    tmc = apply_recipe({"s.ino": read("a4988.ino")}, "a4988", "tmc2209_mks")
    assert not tmc.ok and tmc.reason == "no_code_change_needed"
    assert any(note.startswith("Wiring:") for note in tmc.notes)
    unknown = apply_recipe({"s.ino": "x"}, "arduino_uno_r3", "esp32_devkit")
    assert unknown.reason == "recipe_not_applicable"
    empty = apply_recipe({}, "dht22", "dht11")
    assert empty.reason == "no_code"


@pytest.mark.parametrize(
    ("text", "python", "code"),
    [
        ('a = "x // y"; // c\nb', False, "a = ; \nb"),
        ("x /* c */ y", False, "x  y"),
        ("a = 'b' # c\nd", True, "a =  \nd"),
        ('a = """doc\nDHT22"""\nb', True, "a = \nb"),
    ],
)
def test_code_mask_skips_comments_and_strings(text, python, code):
    mask = code_mask(text, python)
    assert "".join(c for c, keep in zip(text, mask, strict=True) if keep) == code
