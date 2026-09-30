# Compatibility engine

> **In one minute.** This is the core of the product. It has four parts:
> 1. A **curated knowledge graph** (KG) of about 150 maker modules, 40 chips and 30 libraries.
> 2. A **deterministic rules engine** that checks the hard constraints: voltage, logic level, I2C, mains, pin functions, measured quantities and library availability.
> 3. **Gemini**, which explains the result and writes code changes, grounded in datasheets.
> 4. An **LLM judge** plus a compile check that verify Gemini's output.
>
> Every substitute gets a grade: **A** drop-in, **B** config/code tweak, **C** rewire or add a part, **D** functional alternative, **X** not recommended.
>
> We follow the recipe the research supports. LLMs are good at code but weak at physical pin and voltage reasoning, so rules decide and the LLM explains.

Deep research: [research/03-compatibility-intelligence.md](../../research/03-compatibility-intelligence.md).

---

## 1. Why hybrid (rules + LLM)

| Evidence | Implication |
|---|---|
| **PCEval** (arXiv:2601.02404, 2026): 13 LLMs are strong at code and logic but "struggle significantly with physical breadboard layout… proper pin connections" | Pin and voltage decisions are deterministic |
| **EmbedBench** (ICSE 2026): Arduino→ESP-IDF migration only 29.4% pass@1; RAG + compiler feedback helps | Stay in the Arduino framework; compile in the loop |
| **IoT-SkillsBench** (Duke, arXiv:2603.19583): human-expert skills 42/42, LLM-generated skills inconsistent | A curated KG beats LLM-generated knowledge |
| **DRCY** (AllSpice, arXiv:2603.15672): production pin-by-pin datasheet checks with multi-run consensus | Datasheet-grounded explanation + judge ×3 |
| **Z2Data** cross-reference tiers (package/pinout first, then parametrics) and **PartGenie** tiers (exact / pin-compatible / functional / partial) | Our A–X grades are a maker version of these |

**Pitch line:** "a curated compatibility graph plus LLM reasoning, not LLM guesses."

## 2. Per-category attributes

Each attribute is **HARD** (a mismatch caps the grade at C, D or X), **SOFT** (affects score and explanation) or **INFO**.

| Category | HARD | SOFT | INFO |
|---|---|---|---|
| **MCU dev board** | MCU family (ESP32 / S2 / S3 / C3, ESP8266, ATmega328P, RP2040/2350), logic V, peripherals the project uses (Wi-Fi, BLE, native USB-HID, DAC, touch, ADC count), flash ≥ need, every used pin's *function* exists | form factor (Uno, Nano, Feather, D1 mini, DevKitC 30/38, Pico), USB-serial chip (CH340 / CP2102 / native), LiPo charger, regulator current, connector, antenna | FQBN / PlatformIO board id, price |
| **Sensor module** | measured quantities ⊇ used (BMP280 has **no humidity**), bus, module supply range (regulator?), I/O tolerance, I2C address options | accuracy, range, sample rate, connector ecosystem (STEMMA QT/Qwiic JST-SH 1 mm vs Grove 2 mm), size, holes | library set |
| **Motor driver** | motor type, max motor V, current per phase (RMS), control interface (STEP/DIR, PWM+DIR, UART, SPI), footprint (Pololu 16-pin) | microstep, current-set method (Vref formula), noise (StealthChop), FAULT pin, min STEP pulse | |
| **Display** | controller IC (SSD1306, SH1106, ST7735, ST7789, ILI9341, HD44780+PCF8574), interface, resolution, logic V | size, colour, touch controller, backlight current, **header pin order** | |
| **Power** | input (India 230 V/50 Hz), output V, current, polarity + barrel size (5.5×2.1 vs 5.5×2.5), plug type (D/M) | efficiency, ripple, BIS mark | |
| **Addressable LED** | protocol (WS2812B, SK6812 RGBW, APA102/SK9822), supply V (5 V vs 12 V WS2815), colour order | density, IP rating, data threshold | |
| **Mains switching** | rated VAC/A (≥ 250 VAC), isolation, control-input V and polarity (active-LOW modules), enclosure | SSR vs relay, zero-cross | |
| **Battery** | chemistry, protection (BMS/DW01), connector (JST-PH polarity!), C-rating | capacity | |

## 3. Grades

| Grade | Name | Definition | UI |
|---|---|---|---|
| **A** | Drop-in | Same chip or pin- and protocol-compatible part, same voltage domain, same library, no code change | ✅ green + check |
| **B** | Drop-in + config | Same wiring; one-line code or config change (I2C address, board definition, driver install, old bootloader, Vref re-tune) | 🔁 teal + swap |
| **C** | Rewire / add a part | Wiring change or an extra part (level shifter, divider, adapter cable, different PSU); possibly a library swap | ⚠️ amber + warning, "What changes" required |
| **D** | Functional alternative | Different chip or approach that meets the goal but changes behaviour or spec (DHT22→DHT11, BME280→BMP280 + AHT20); code rewrite | 🟠 orange |
| **X** | Not recommended | Unsafe (mains without an enclosure/rating, unprotected Li-ion) or can't meet a HARD requirement | ⛔ red, never pre-selected |

The UI copy uses plain words: "Works as is", "Works with a small setting change", "Works with wiring changes", "Different part, similar result", "Don't use".

## 4. Knowledge graph

### 4.1 Nodes (Firestore collections `kg_*`)

| Node | Key fields |
|---|---|
| `Chip` | id, family, vendor, vdd_min/max, io_5v_tolerant, interfaces[], i2c_addrs[], chip_id_reg (e.g. BME280 0xD0=0x60), datasheet_url, pages{} |
| `Module` | id, aliases[], chip_id, vin_min/max, has_regulator, has_level_shift, logic_v, connector, ecosystem, pinout[{label, function, gpio}], header_order, dims_mm, holes, common_in_india (bool) |
| `Library` | id, framework (arduino / circuitpython / micropython / pio), headers[], depends[], architectures[], api_symbols[] |
| `Ecosystem` | id, connector, pitch_mm, voltage, pin_order |
| `Board` | id, mcu_chip, fqbn, pio_board, pinmap, strapping_pins, input_only_pins, usb_serial, charger, logic_v, led_builtin |

### 4.2 Edges

| Edge | Example |
|---|---|
| `Module -USES_CHIP-> Chip` | GY-BME280-3.3 → BME280 |
| `Chip -SUPPORTED_BY-> Library` | BME280 → Adafruit_BME280 |
| `Chip -FAMILY_UP/DOWN-> Chip` | DHT22 → DHT11 (down), BMP280 → BME280 (up) |
| `Module -FOOTPRINT_COMPATIBLE{grade, notes}-> Module` | A4988 ↔ DRV8825 (B: Vref×2, FAULT pin, 1.9 µs pulse) ↔ TMC2209 (C: MS pins differ, PDN/UART) |
| `Module -OFTEN_MISLABELED_AS-> Module` | "BME280" listings ↔ BMP280; "1.3 inch OLED" ↔ SH1106 |
| `Ecosystem -ADAPTS_TO{cable}-> Ecosystem` | STEMMA QT ≡ Qwiic; STEMMA (JST-PH) → Qwiic via adapter; Grove → Qwiic via adapter cable |
| `Library -API_MAP{symbol_map}-> Library` | Adafruit_SSD1306 → Adafruit_SH110X (`SSD1306_WHITE→SH110X_WHITE`, `begin(SSD1306_SWITCHCAPVCC,0x3C)→begin(0x3C,true)`) |

### 4.3 Seed list (~150 modules, ~80% of maker BOMs)

- **Boards:** Uno, Nano (genuine + CH340 clone), Mega, Pro Mini, ESP32 DevKit V1 (30/38), ESP32-S3 DevKitC, ESP32-C3 SuperMini, NodeMCU v2/v3, Wemos D1 mini, Pico / Pico W, Feather HUZZAH (ESP8266/ESP32), Teensy 4.x, STM32 Black Pill.
- **Sensors:** HC-SR04 / HC-SR04P / RCWL-1601 / JSN-SR04T, DHT11/22, BME280 / BMP280 / AHT20 / SHT31, DS18B20, MPU6050, VL53L0X, HC-SR501, soil moisture (resistive / capacitive), LDR, INA219, HX711, MQ-x, BH1750.
- **Displays:** SSD1306 0.96/0.91, SH1106 1.3, 16×2 LCD + PCF8574, ST7735, ST7789, ILI9341, MAX7219, TM1637, e-paper 2.9".
- **Actuators and drivers:** SG90, MG996R, 28BYJ-48 + ULN2003, L298N, L9110S, TB6612FNG, A4988, DRV8825, TMC2208/2209, N20 gearmotors, NEMA 17.
- **Power:** TP4056 (with/without protection), MT3608, LM2596, AMS1117, HLK-PM01, 12 V/5 V SMPS adapters, 18650 holders.
- **RF and comms:** HC-05, NRF24L01, RC522, NEO-6M, SIM800L, LoRa SX1278.
- **LEDs:** WS2812B strips/rings, SK6812 RGBW, APA102.
- **Mains:** 1/2/4-ch relay modules (active-LOW), SSR-25DA, Sonoff-type.
- **Misc:** DFPlayer Mini, level shifters (BSS138, 74AHCT125), breadboards, jumpers.

Curation: the data/KG owner fills 10–15 modules/day from datasheets and Pololu/Adafruit product pages, with a page citation on every number. The loader validates the schema.

## 5. Rules engine

Pure Python, `backend/compat/rules.py`, unit-tested with the 13 worked cases. Each rule returns `PASS | FIXABLE(fix, grade_floor) | FAIL(reason)`.

| Rule | Logic | Fix / outcome |
|---|---|---|
| `logic_level` | MCU logic 3.3 V and a 5 V-output signal goes to an MCU input that isn't 5 V tolerant | FIXABLE(divider 1 kΩ/2 kΩ or level shifter) → ≥ C |
| `supply_range` | Module vin range doesn't contain the rail it's wired to | FIXABLE(move to 3V3/5V rail or add regulator) → ≥ C; FAIL if no rail fits |
| `i2c_collision` | After substitution, two devices on one bus share an address | FIXABLE(set ADDR pin / TCA9548A) → ≥ B/C; else FAIL |
| `i2c_address_change` | Substitute default address ≠ original and the code calls `begin()` with no address | FIXABLE(code) → ≥ B |
| `measured_superset` | substitute.measures ⊉ quantities the project uses | → D (or FAIL if the core function is lost) |
| `library_exists` | No library for (chip, framework) in the KG or registry | → ≥ D |
| `pin_function` | A used pin's function (ADC, PWM, touch, DAC, input-only, strapping) doesn't exist on the substitute board | FIXABLE(remap) → ≥ B/C; FAIL if not enough capable pins |
| `mains` | category = mains_switching, or any line switches AC | require rating ≥ 250 VAC, plug D/M, enclosure; US-only plug products → X; always MAINS banner |
| `frequency_sensitive` | 60 Hz synchronous motor / transformer on 50 Hz | → D or X with explanation (≈17% slower / ≈20% more flux) |
| `battery_protection` | Li-ion/LiPo without protection or charger | FIXABLE(TP4056 with DW01) → ≥ C; LIPO banner |
| `current_headroom` | PSU current < sum of loads (e.g. WS2812B 60 mA × N at full white) | FIXABLE(bigger PSU or `setBrightness`) → ≥ C |
| `footprint` | Footprint differs but KG `FOOTPRINT_COMPATIBLE` edge exists | use the edge grade + notes |
| `header_order` | Display VCC/GND order differs (common on 1.3" OLEDs) | FIXABLE(wiring note, **bold warning**) → ≥ C |
| `polarity` | Relay module active-LOW vs original active-HIGH | FIXABLE(code invert) → ≥ B |
| `connector_ecosystem` | STEMMA QT/Qwiic ↔ Dupont / Grove | FIXABLE(adapter cable or solder headers) → ≥ B/C |
| `lookalike_risk` | KG `OFTEN_MISLABELED_AS` edge exists | Add verify-on-arrival test; lower confidence |

**Conflict policy:** when sources disagree about an electrical safety margin (e.g. HC-SR04 ECHO straight into an ESP32), the conservative rule wins and the UI says so.

## 6. Matching algorithm

```python
def find_substitutes(item, ctx, kg, market):
    # 1 candidates
    c  = kg.same_chip_modules(item.chip)                 # best: same chip, different module
    c += kg.footprint_compatible(item.module)
    c += kg.family_alternatives(item.chip)
    c += distributor.substitutions(item.mpn)             # DigiKey v4 Substitutions (chip-level)
    c += vector_search(embed(item.spec_text + image), "kg_modules", k=20, filter={"category": item.category})
    c  = [m for m in dedupe(c) if market.has_verified_listing(m, country="IN")]

    # 2 hard rules
    results = []
    for m in c:
        findings = [r(item, m, ctx) for r in RULES[item.category] + RULES["global"]]
        if any(f.fail for f in findings):
            results.append(Candidate(m, "X", findings)); continue
        grade = max_grade_floor(findings)                # A if no fixes
        score = (0.35*param_similarity(item, m) + 0.20*library_overlap(item, m) +
                 0.15*ecosystem_match(item, m) + 0.15*availability(m) + 0.15*price_score(m))
        results.append(Candidate(m, grade, findings, score))

    # 3 rank: grade then score
    top = sorted([r for r in results if r.grade != "X"], key=lambda r: (GRADE_ORDER[r.grade], -r.score))[:3]
    top += [r for r in results if r.grade == "X"][:1]   # show one "don't use" with reason when instructive

    # 4 explain + code + judge
    for t in top:
        t.report = llm_explain(item, t, ctx, file_search=DATASHEETS)   # cannot upgrade grade
        t.report.code = code_impact(ctx.code, item, t.module, kg)       # diff + compile
        verdicts = [llm_judge(t.report, CHECKLIST[item.category]) for _ in range(3)]
        t.report.confidence = calibrate(item, t, verdicts)
    return top
```

The "exact match" path is also taken when a verified Indian listing exists for the *same module* (e.g. the genuine Adafruit board at Thingbits). Then the grade is A and the UI offers **Exact (genuine)** vs **Cheaper alternative** side by side.

## 7. Confidence

```
confidence = σ( w1·extraction_conf + w2·kg_coverage + w3·rule_pass_ratio
              + w4·judge_agreement + w5·listing_freshness − w6·lookalike_risk )
```

- Weights are calibrated on the eval set so that 0.8 ≈ correct 80% of the time. The reliability plot goes in the deck.
- Buckets (PAIR guidance: show categories, not percentages):

| Bucket | Meaning |
|---|---|
| **Verified** | KG + rules + fresh listing |
| **Likely** | LLM spec + rules |
| **Check manually** | Low confidence; show N-best alternatives |

## 8. Code impact

1. **Detect dependencies:**
   - `#include` → library → chip (KG + PlatformIO `header:` search + Arduino `library_index.json` `providesIncludes`)
   - `platformio.ini` `lib_deps`
   - `library.properties` `depends=`
2. **Build the impact list** (deterministic): library swap with API map, address change, pin remap (avoid strapping and input-only pins), board target (FQBN), polarity.
3. **Gemini** produces a unified diff **limited to that list** (prompt P7).
4. **Compile** in the `bs-compile` job with `arduino-cli compile --fqbn …`, with up to 2 repair rounds.
5. **UI:** diff viewer + "✅ Compiles for ESP32 Dev Module", or "⚠️ Didn't compile — here's why".

Example (SSD1306 → SH1106):

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

## 9. Hallucination controls specific to compatibility

- The LLM can't set a grade better than the rules engine allows.
- Every number in an ImpactReport needs a citation (KG id or datasheet page). The judge strips uncited numbers.
- "Verify on arrival" tests are attached for look-alike-risk parts: I2C scan, chip-ID register read, voltage check with a multimeter.
- Safety banners are templated text, not generated.
