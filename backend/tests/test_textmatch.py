import pytest

from bharat_sourcer.sourcing.textmatch import pack_size, title_gate, values


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
    ],
)
def test_conflicts(query, title):
    assert not title_gate(query, title)


def test_values_and_packs():
    assert values("4K7 resistor")["resistance"] == values("4.7k resistor")["resistance"]
    assert pack_size("Pack of 10") == 10
    assert pack_size("10pcs") == 10
    assert pack_size("x10") == 10
