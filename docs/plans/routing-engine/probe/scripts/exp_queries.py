from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.seller_search import query_variants, normalise, short_query, tokens, overlap
from bharat_sourcer.sourcing.service import seller_queries
from bharat_sourcer.sourcing.part_spec import buyable_spec, find_measures
from bharat_sourcer.sourcing.listings import title_matches
from bharat_sourcer.sourcing.cache import normalise_part

names = [
    "10k resistor 1/4W",
    "10kΩ Resistor (1/4 W, 5%)",
    "ESP32 DevKit V1 30 pin",
    "Jumper wires male-female 20cm",
    "HC-SR04",
    "HC-SR04 Ultrasonic Sensor",
    "10 x 220Ω resistors",
    "2x 18650 Li-ion cell 3.7V",
    "4.7µF 50V electrolytic capacitor",
    "0.1uF ceramic capacitor (104)",
    "Arduino Uno R3 (compatible)",
    "SG90 micro servo motor",
    "पुश बटन स्विच",
    "Push button 6x6mm tactile",
    "LM7805 voltage regulator",
    "16x2 LCD with I2C",
    "1N4007",
    "Breadboard 830 points",
    "M3 x 10mm screws",
    "TP4056 Type-C charging module",
    "0.96\" OLED display I2C SSD1306",
    "Resistor kit",
    "5mm LED (red) x5",
    "IRFZ44N MOSFET",
    "Wire, 22 AWG, solid core",
]
for n in names:
    item = BomItem(line_id="l1", raw_name=n)
    spec = buyable_spec(item)
    qs = seller_queries(spec.queries, n, n)
    print(repr(n))
    print("   spec.cat=", spec.category, "queries=", spec.queries, "needs_value=", spec.needs_value)
    print("   seller_queries=", qs)
    print("   shorts=", [short_query(q) for q in qs])
    print("   normalise_part=", normalise_part(n))

print("--- title_matches (legacy gate, used w/o judge or when judge fails) ---")
pairs = [
    ("10k resistor 1/4W", "10K Ohm 0.25W Carbon Film Resistor (Pack of 10)"),
    ("10k resistor 1/4W", "10k Ohm 1/4 Watt Resistor"),
    ("ESP32 DevKit V1 30 pin", "ESP32 Development Board 30 Pin DOIT DevKit V1 WiFi + Bluetooth"),
    ("Jumper wires male-female 20cm", "Male to Female Jumper Wire 20cm 40 pcs"),
    ("HC-SR04", "HC-SR04 Ultrasonic Distance Sensor Module"),
    ("HC-SR04", "HCSR04 Ultrasonic Sensor"),
    ("4.7µF 50V electrolytic capacitor", "4.7uF 50V Electrolytic Capacitor"),
    ("4.7µF 50V electrolytic capacitor", "4.7 uF 50 V Electrolytic Capacitor"),
    ("Arduino Uno R3 (compatible)", "Arduino UNO R3 Board with USB Cable"),
    ("5mm LED (red) x5", "5mm Red LED (Pack of 10)"),
    ("Push button 6x6mm tactile", "6x6x5mm Tactile Push Button Switch"),
    ("Breadboard 830 points", "830 Point Solderless Breadboard"),
]
for q, t in pairs:
    print(title_matches(q, t), "|", q, "|", t)

print("--- overlap (seller ranking tie-break) ---")
print(overlap("10k resistor 1/4w", "10K Ohm 0.25W Carbon Film Resistor"))
print(tokens("10k resistor 1/4w"), tokens("10K Ohm 0.25W Carbon Film Resistor"))
print(tokens("jumper wires male-female 20cm"))
print("measures:", find_measures("10k resistor 1/4W", True))
print("measures:", find_measures("Jumper wires male-female 20cm"))
print("measures:", find_measures("ESP32 DevKit V1 30 pin"))
print("measures:", find_measures("2x 18650 Li-ion cell 3.7V"))
print("measures:", find_measures("M3 x 10mm screws"))
