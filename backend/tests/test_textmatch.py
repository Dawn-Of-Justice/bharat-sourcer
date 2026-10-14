import pytest

from bharat_sourcer.sourcing.textmatch import model_numbers, title_gate, values


@pytest.mark.parametrize(
    "query,title",
    [
        ("HC-SR04", "HCSR04 Ultrasonic Sensor"),
        ("NEMA 17 stepper motor", "NEMA17 Stepper Motor"),
        ("IRFZ44N", "IRFZ44 N-Channel MOSFET"),
        ("10k resistor 1/4W", "10K Ohm 0.25W Carbon Film Resistor"),
        ("4.7µF capacitor", "4.7 uF Capacitor"),
        ("100uF capacitor", "100 MFD capacitor"),
        ("5mm LED (red) x5", "5mm Red LED (Pack of 10)"),
        ("Breadboard 830 points", "830 Point Solderless Breadboard"),
        ("20cm jumper wires", "200mm Jumper Wire"),
        ("18650 holder 2 cell", "Dual 18650 Battery Holder"),
        ('0.96" OLED', "OLED 0.96 inch module"),
        ("Wire 22 AWG solid core", "22 AWG Solid Core Wire"),
        ("Arduino Uno R3", "Arduino UNO R3 Compatible Board"),
        ("ESP32 DevKit V1", "ESP32 DevKit V1 Development Board"),
        ("BME280 sensor module", "BME280 Environmental Sensor"),
        ("SG90 servo", "TowerPro SG90 Servo Motor"),
        ("LM2596 buck converter", "LM2596 Buck Converter Module"),
        ("TP4056 charging module", "TP4056 Charging Module"),
        ("jumper wires male to female", "Male to Female Jumper Wire"),
        ("WS2812B LED strip", "WS2812B Addressable LED Strip"),
        ("A4988 driver", "A4988 Stepper Motor Driver"),
        ("100uF 25V capacitor", "100 MFD 25 V Electrolytic Capacitor"),
        ("IRFZ44N mosfet", "IRFZ44 N-Channel MOSFET"),
        ("Raspberry Pi Pico", "Raspberry Pi Pico Board"),
    ],
)
def test_equivalent_titles(query, title):
    assert title_gate(query, title)


@pytest.mark.parametrize(
    "query,title",
    [
        ("LM2596S", "LM2596 Buck Converter"),
        ("10k resistor", "100K Resistor"),
        ("Arduino Uno R3", "Case for Arduino UNO R3"),
        ("NEMA 17", "Bracket for NEMA17"),
        ("ESP32 30 pin", "ESP32 38 pin"),
        ("0.96 inch OLED", "0.96 OLED module"),
        ("5 inch display", "5 in 1 display kit"),
        ("10k resistor", "Carbon Film Resistor"),
        ("100uF 25V capacitor", "100uF capacitor"),
        ("ESP32 30 pin", "ESP32 Development Board"),
    ],
)
def test_conflicts(query, title):
    assert not title_gate(query, title)


def test_values_normalise_resistance():
    assert values("4K7 resistor")["resistance"] == values("4.7k resistor")["resistance"]


@pytest.mark.parametrize(
    "name,models",
    [
        ("1.3-inch I2C OLED display (SH1106)", ["SH1106"]),
        ("0.96-inch OLED SSD1306", ["SSD1306"]),
        ("1.44-inch TFT ST7735", ["ST7735"]),
    ],
)
def test_hyphenated_inch_sizes_are_not_model_numbers(name, models):
    assert model_numbers(name) == models


def test_hyphenated_inch_size_still_matches_the_listing():
    assert title_gate("1.3-inch I2C OLED display (SH1106)", "1.3 inch I2C OLED SH1106 Module")
