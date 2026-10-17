# Worked substitution cases

> **In one minute.** These are 13 realistic substitutions, written the way the agent should output them: original → Indian alternative → grade → what changes (wiring / power / code / risk). They serve three purposes: few-shot examples for prompt P5, unit tests for the rules engine, and demo material.

Grades: A drop-in · B config · C rewire/add part · D functional alternative · X don't use.

---

## Summary table

| # | Original (US/UK) | Indian alternative | Grade | Key change | Rules that fire |
|---|---|---|---|---|---|
| 1 | Adafruit BME280 (STEMMA QT #2652) | GY-BME280 purple module (3.3 V variant) | **B** (C if 5 V-only module; D if actually BMP280) | `bme.begin(0x76)`; 3.3 V only; jumpers not STEMMA | i2c_address_change, supply_range, connector_ecosystem, lookalike_risk |
| 2 | PowerSwitch Tail II (US 120 V) | 230 V-rated SSR/relay in an enclosure (or a certified smart plug) | **C / X** | Mains voltage, plug D/M, enclosure, relay polarity | mains, polarity |
| 3 | A4988 | MKS TMC2209 V2.0 | **C** | MS pin tables differ, MS3→SPREAD, PDN/UART, 5.5–28 V motor supply, re-tune Vref | footprint (edge C) |
| 4 | A4988 | DRV8825 clone | **B** | Current limit = VREF × 2; FAULT pin; min STEP pulse 1.9 µs; 1/32 microstep | footprint (edge B) |
| 5 | Adafruit Feather HUZZAH ESP8266 | NodeMCU v3 (LoLin) | **B** (code) / **C** (battery) | D-labels vs GPIO; no LiPo charger → TP4056 with protection; board target; CH340 driver | pin_function, battery_protection |
| 6 | 0.96" SSD1306 OLED | 1.3" OLED (usually SH1106) | **B** (+ C warning) | Library swap to Adafruit_SH110X; **check VCC/GND order** | library swap, header_order |
| 7 | Uno + HC-SR04 → user's ESP32 DevKit | ESP32 + divider (or HC-SR04P / RCWL-1601) | **C** (B with a 3.3 V sensor) | ECHO 5 V → divider 1 kΩ/2 kΩ; avoid strapping/input-only pins; `pulseIn()` fallback | logic_level, pin_function |
| 8 | NodeMCU driving WS2812B (Hackster clock) | Same + 74AHCT125 + 5 V 5 A SMPS | **A** (optional C upgrade) | 3.3 V data → level shifter; PSU sizing 60 mA × LEDs; `setBrightness` | logic_level, current_headroom |
| 9 | Genuine Arduino Nano | Nano clone (CH340, old bootloader) | **B** | CH340 driver; "ATmega328P (Old Bootloader)" | config |
| 10 | Adafruit PiOLED HAT (#3527) | Generic 0.91" SSD1306 128×32 I2C | **C** | 4 jumpers (pins 1/3/5/6), enable I2C; same library; case differs | connector_ecosystem |
| 11 | DHT22 | DHT11 | **D** | Lower range/resolution. **Refuse** for sub-zero/decimal needs → AHT20/SHT31 | measured_superset (range) |
| 12 | US 12 V 2 A wall wart | Indian 12 V 2 A SMPS adapter | **A–B** | 230 V input, Type D plug, barrel 5.5×2.1 vs 2.5, polarity, BIS mark | supply_range, connector |
| 13 | Adafruit MagTag (ESP32-S2 e-ink) | Genuine via an Adafruit reseller (A) **or** LilyGO/Waveshare ESP32 + 2.9" e-paper (D) | **A / D** | Import-vs-redesign choice; SSD1680 driver, pin map, Arduino + GxEPD2 port | library_exists, pin_function |

---

## Case details

### Case 1: Adafruit BME280 → GY-BME280 (purple)

- **Project:** Adafruit IO Environmental Monitor ([guide](https://learn.adafruit.com/adafruit-io-air-quality-monitor)).
- **Wiring:** no STEMMA QT, so solder headers and use 4 jumpers (VIN, GND, SCL, SDA). The Adafruit board has a regulator and level shifting. The "GY-BME280-3.3" variant sold in India (e.g. [Robu listing](https://stg.robu.in/product/gy-bme280-3-3-precision-altimeter-atmospheric-pressure-sensor-module)) must be powered from **3.3 V only**. That's fine with a Feather; don't feed it 5 V from an Uno.
- **Code:** generic modules usually strap SDO low, giving address **0x76**, while the Adafruit library defaults to 0x77. Change `bme.begin()` → `bme.begin(0x76)`.
- **Verify on arrival:** read register 0xD0. It should be 0x60 for a BME280 and 0x58 for a BMP280 ([atomic14](https://www.atomic14.com/esp32/sensors/fake-sensors/)). If it's a BMP280, humidity is gone and the grade becomes D: switch to `Adafruit_BMP280`, or add an AHT20/SHT31.

### Case 2: PowerSwitch Tail II → 230 V SSR/relay

- **Project:** Sous-viduino ([guide](https://learn.adafruit.com/sous-vide-powered-by-arduino-the-sous-viduino)).
- **Why:** the US mains product is unusable in India (120 V/60 Hz, NEMA plug). The rice cooker must be a 230 V Indian model. The relay needs ≥ 2× margin for a resistive load.
- **Wiring:** Indian 5 V relay modules are often **active-LOW**, so invert `digitalWrite`. An SSR (3–32 V DC input) keeps the logic active-HIGH.
- **Code:** polarity only. The PID time-proportioning window doesn't depend on mains frequency.
- **Safety (templated):** enclosure, earth, fuse, strain relief, no exposed 230 V; beginners get pointed to a certified smart plug.

### Case 3: A4988 → TMC2209 (MKS V2.0)

- **Listing:** Probots, ₹849 incl. GST, out of stock when checked ([Probots](https://probots.co.in/mks-tmc2209-v2-stepper-motor-driver-uart-module.html)).
- **Changes:**
  - Same Pololu footprint, but MS1/MS2 select different microstep tables.
  - MS3 becomes SPREAD (tie to GND for StealthChop). PDN/UART must be handled.
  - Some modules invert DIR ([Arduino forum](https://forum.arduino.cc/t/exchanging-a4988-for-tmc2209/870682)).
- **Power:** motor supply 5.5–28 V (vs 8–35 V on the A4988). A 36 V build is not OK.
- **Current:** re-tune Vref with the module's own formula.
- **Code:** STEP/DIR needs no change. Adding `TMCStepper` is optional (UART current, StallGuard).
- **Benefit:** near-silent operation, 1/256 interpolation.

### Case 4: A4988 → DRV8825

From [Pololu 2133](https://www.pololu.com/product/2133):

- Current limit = **VREF × 2**.
- The pin that is VDD on the A4988 is **FAULT** on the DRV8825.
- STEP high/low must each be **≥ 1.9 µs**, so add `stepper.setMinPulseWidth(2)` (AccelStepper) and check `delayMicroseconds(1)` loops.
- 45 V max. SLEEP is not pulled up by default.
- Microstepping goes to 1/32, and the MS tables differ, so update steps/mm.
- **Price context:** Pololu $15.95 vs clone ₹100.30 incl. GST (Zbotic).

### Case 5: Feather HUZZAH ESP8266 → NodeMCU v3

- **Pins:** same GPIOs, different silkscreen (D1 = GPIO5, D2 = GPIO4). Rewrite the wiring instructions using D-labels. FeatherWings won't stack.
- **Power:** there's **no LiPo charger or JST**. Add a TP4056 *with* protection (DW01) plus a regulator, or drop the battery. v3 is wider than v2 and covers both breadboard rows.
- **Code:** board target `NodeMCU 1.0 (ESP-12E Module)` / `board = nodemcuv2`. `LED_BUILTIN` differs (GPIO0 vs GPIO2). The CH340 driver may be needed.

### Case 6: SSD1306 0.96" → 1.3" (SH1106)

```diff
-#include <Adafruit_SSD1306.h>
-Adafruit_SSD1306 display(128, 64, &Wire, -1);
+#include <Adafruit_SH110X.h>
+Adafruit_SH1106G display(128, 64, &Wire, -1);
-display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
+display.begin(0x3C, true);
-display.setTextColor(SSD1306_WHITE);
+display.setTextColor(SH110X_WHITE);
```

- Some 1.3" boards swap VCC/GND on the header. **Read the silkscreen**, because a reversed supply kills the module.
- Both libraries use Adafruit GFX, so drawing calls are unchanged ([Adafruit_SH110x](https://github.com/adafruit/Adafruit_SH110x)).

### Case 7: HC-SR04 on an ESP32

- HC-SR04 needs 5 V to range reliably, and ECHO outputs 5 V. **ESP32 GPIOs are not 5 V tolerant** ([Espressif registry](https://components.espressif.com/components/phlangone/hc_sr04/versions/2.0.0/readme)).
- **Fix:** a divider (1 kΩ / 2 kΩ) or a level shifter.
- Random Nerd Tutorials wires ECHO directly and its commenters disagree. We take the conservative path and say so.
- **Better:** HC-SR04P or RCWL-1601 (3.3 V capable), which brings the grade to B.
- **Pins:** avoid strapping pins (0, 2, 12, 15) and input-only pins (34–39) for TRIG.
- **Code:** NewPing ESP32 support varies, so fall back to `pulseIn()`.

### Case 8: WS2812B from a 3.3 V MCU

- **Project:** [Hackster infinity mirror clock](https://www.hackster.io/rundhall/infinity-mirror-wall-clock-in-ikea-picture-frame-700125).
- **Wiring:** 3.3 V data into a 5 V strip may flicker. Add a 74AHCT125 ([Adafruit](https://learn.adafruit.com/neopixel-levelshifter.md)) plus a 300–500 Ω series resistor and the 470 µF cap.
- **Power:** 74 LEDs × 60 mA ≈ **4.4 A** at full white, so a phone charger is inadequate. Use `setBrightness(64)` or a 5 V 5 A SMPS (230 V input, Indian plug).
- **Code:** if the strip is SK6812 RGBW, use `NEO_GRB` → `NEO_GRBW`.

### Case 9: Nano → Nano clone

- Install the CH340 driver.
- If uploads fail, select **"ATmega328P (Old Bootloader)"** ([Universal-Solder](https://www.universal-solder.ca/troubleshooting-arduino-failed-upload/)).
- No code or wiring changes.

### Case 10: PiOLED → generic 0.91" SSD1306

- **Project:** [Pi-Hole with Pi Zero W](https://learn.adafruit.com/pi-hole-ad-blocker-with-pi-zero-w).
- **Wiring:** it isn't a HAT. Use jumpers to 3V3 (pin 1), SDA (3), SCL (5), GND (6), then run `raspi-config` → enable I2C.
- **Code:** unchanged (`adafruit-circuitpython-ssd1306`, 0x3C). The case differs; suggest a 3D-printable enclosure.

### Case 11: DHT22 → DHT11

- **Code:** change `#define DHTTYPE DHT22` → `DHT11`.
- **Trade-off:** DHT11 covers roughly 0–50 °C in 1 °C steps, vs −40–80 °C at 0.1 °C for DHT22.
- **Refuse** for freezer or decimal use cases; suggest an AHT20/SHT31 (I2C, library change) instead.

### Case 12: 12 V 2 A adapter

Check:

- 230 V AC input and a Type D plug
- barrel 5.5×2.1 vs 5.5×2.5 (a mismatch gives an intermittent contact)
- centre-positive polarity
- headroom for motor peaks
- prefer BIS-marked adapters

### Case 13: MagTag (no local equivalent)

- **Option A:** buy the genuine board through an Indian Adafruit reseller (Thingbits, Robu, Evelta…) at a higher cost.
- **Option D:** LilyGO/Waveshare ESP32 + 2.9" e-paper, with an SSD1680 driver, a different pin map, and a port from CircuitPython to Arduino + GxEPD2.
- Showing the cost and effort side by side makes a strong demo moment.
