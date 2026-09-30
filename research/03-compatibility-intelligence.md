# Bharat Sourcer: Compatibility Intelligence Research Report

*How to make BOM extraction and substitution reasoning accurate, verifiable and good enough to demo*
*Prepared 2026-09-30 for the Google Cloud AI Builder Cup 2026 entry (Gemini + Cloud Run/Firebase)*

---

## 0. Executive summary (what to build, in one page)

1. **Treat extraction as evidence fusion, not "ask Gemini what's in the video."** Pull from 4 to 6 sources: video description, transcript/audio, linked pages (Adafruit `.md` guides, Instructables "Supplies", Hackster "Components and supplies"), GitHub code (`#include`, `platformio.ini`, `library.properties`), and video frames. Every BOM line carries `evidence[]` with a source type and a timestamp or URL. Items seen in only one weak source get flagged, not silently included.
2. **Resolve each item to a canonical *chip + module + ecosystem* triple** (for example `BME280` chip, `Adafruit 2652 breakout` module, `STEMMA QT` ecosystem). Maker substitutions nearly always swap the *module* while keeping the *chip*, or swap the chip within a *family*. Your knowledge graph should model exactly that.
3. **Grade compatibility the way component-intelligence vendors do, adapted for makers.** Z2Data grades cross-references as Drop-In A/B/C on "package and pinout first", then parametrics ([Z2Data Advanced Cross Search](https://www.z2data.com/products/part-risk-manager/features/advanced-cross-search)). Bharat Sourcer can use a maker version: **A = drop-in, B = config/code tweak, C = rewire/adapter part needed, D = functional alternative requiring redesign, X = unsafe or incompatible.**
4. **Hard constraints in code, explanation by the LLM.** Voltage domains, logic levels, mains voltage, I2C address clashes, pin-function mismatches and library existence are deterministic checks. Gemini writes the explanation and the code diff, and an LLM-as-judge verifies the explanation against a checklist. Recent literature strongly supports this split. LLMs are good at code and logic but weak on physical pin connections ([PCEval, arXiv:2601.02404](https://arxiv.org/abs/2601.02404v1)). Expert-curated hardware knowledge beats LLM-generated knowledge ([Skilled AI Agents for Embedded/IoT, arXiv:2603.19583](https://arxiv.org/pdf/2603.19583)).
5. **Never recommend a SKU you haven't fetched.** Each product recommendation must pass link-alive, in-stock, title-matches-chip, and price-parsed checks before it reaches the UI. Anything that fails is shown as "search suggestion", not "product".
6. **Ship a 15-project eval set** (below) with gold BOMs and gold substitution verdicts, and run it through ADK's `adk eval` with `rubric_based_final_response_quality_v1`, `hallucinations_v1` and a custom link-validity metric ([ADK criteria](https://adk.dev/evaluate/criteria/index.md)).

---

## 1. BOM extraction from videos, text and code

### 1.1 Source hierarchy (most to least reliable)

| Rank | Source | How to get it | Typical quality |
|---|---|---|---|
| 1 | Project code repo (GitHub) | `#include` lines, `platformio.ini` `lib_deps`, Arduino `library.properties` `depends=` | Very high for *which chip/library*; says nothing about modules |
| 2 | Structured project pages | Adafruit Learn (append `.md?view=all`, e.g. [magtag-weather.md](https://learn.adafruit.com/magtag-weather.md?view=all)), Hackster "Components and supplies", Instructables "Supplies" step, Random Nerd Tutorials "Parts Required" | High. Often has vendor SKUs |
| 3 | YouTube description + pinned comment | YouTube Data API `videos.list` (snippet.description) | Medium to high. Often affiliate links (Amazon/AliExpress/eBay) that can be resolved to product titles |
| 4 | Transcript / narration | Gemini video input with audio. Caption download via the official API is owner-restricted, so rely on Gemini processing the YouTube URL directly | Medium. Mentions quantities and "I used X instead of Y" |
| 5 | Video frames | Gemini video understanding, default 1 FPS sampling, custom `fps`, clip `start_offset`/`end_offset`, MM:SS timestamps ([Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding?authuser=9)) | Medium. Great for module identification (board colour, silkscreen), poor for tiny SMD markings |
| 6 | Schematic / PCB files | KiCad `kicad-cli sch export bom` / `sch export netlist` ([KiCad CLI docs](https://docs.kicad.org/9.0/en/cli/cli.html)). Fritzing `.fzz` is a zip containing `.fz` XML with part `moduleIdRef`s | Very high when present, rare in YouTube projects |

Gemini accepts **public YouTube URLs directly** (free tier capped at 8 hours/day). An "agentic mode" on newer Flash models navigates the timeline and loads only what it needs, using "up to 88% fewer tokens" on long content ([Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding?authuser=9)). For a 20-minute build video: run a cheap full pass at 1 FPS for chapter segmentation, then do targeted re-reads of "parts overview" and "wiring" segments at higher FPS with `start_offset`/`end_offset`.

Real pages show why ranking matters:
- DroneBot Workshop's HC-SR04 article has a parts-list section marked "COMING SOON!", yet the body references HC-SR04, Arduino Uno, DHT22/DHT11, resistors, and the NewPing and Adafruit DHT libraries ([DroneBot HC-SR04](https://dronebotworkshop.com/hc-sr04-ultrasonic-distance-sensor-arduino/)). Extraction must read prose, not just lists.
- The Hackster infinity-mirror clock lists hardware (NodeMCU v3, WS2812B 74 LED/m, 470 µF capacitor, phone charger 5 V) *and* software (Adafruit_NeoPixel, Timezone by JChristensen, TimeLib) ([Hackster project](https://www.hackster.io/rundhall/infinity-mirror-wall-clock-in-ikea-picture-frame-700125)). This is ideal cross-check material.

### 1.2 Multi-pass extraction pipeline

```
INPUT: url
1. classify(url) -> {youtube, instructables, hackster, adafruit_learn, github, blog}
2. harvest():
     youtube  -> description, pinned comment, chapters, linked URLs (unshorten amzn.to / s.click.aliexpress)
     page     -> readable markdown (Adafruit .md; Jina/readability for others)
     github   -> tree; fetch README, *.ino/*.cpp/*.h, platformio.ini, library.properties, *.kicad_sch, *.fzz
     follow links 1 hop deep (limit 10) if they are project pages or product pages
3. extract_per_source(source) -> [RawMention{text, qty?, source, locator, confidence}]
     - Gemini structured output (JSON schema below), temperature 0
     - code: deterministic regex for #include / lib_deps -> LibraryEvidence
4. video_pass():
     a) coarse pass: "list segments where components are shown or wired" -> [(t0,t1,label)]
     b) fine pass on each segment (fps=2..5): "identify every module/board visible; read silkscreen text;
        output bounding description + timestamp; say UNKNOWN rather than guess"
5. canonicalize(mentions) -> resolve each to Part{chip, module, ecosystem} via KG + fuzzy match
6. fuse():  group mentions by canonical id; confidence = 1 - Π(1 - w_source * c_mention)
     library evidence can CONFIRM chip identity (Adafruit_BME280.h => BME280) but never quantity
7. conflict_check(): e.g. description says BMP280 but code includes Adafruit_BME280.h -> flag
8. OUTPUT: BOM[] with evidence[], unresolved[], conflicts[]
```

Suggested source weights (tune on eval set): code 0.9, structured page 0.85, description 0.75, transcript 0.6, frames 0.5, comments 0.3.

### 1.3 Recognizing modules and chip markings from frames

- **Object detection datasets exist but are the wrong granularity.** ElectroCom61 has 2,121 images, 61 classes and 12,937 annotations, including Arduino boards, GSM modules and sensors. YOLOv9s reached 95.9% mAP@50 and EfficientDetV2 95.6% ([ElectroCom61, Data in Brief 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11847280)). Roboflow Universe also hosts community models (e.g. [electronic components recognition](https://universe.roboflow.com/elec-3yngs/electronic-components-recognition-dfh01)). These detect *class* ("ultrasonic sensor"), which is useful as a cross-check, but Bharat Sourcer needs *identity* ("HC-SR04 vs RCWL-1601 vs JSN-SR04T"). **Use Gemini multimodal for identity and skip training a detector in a hackathon.**
- **Geometric reading by LMMs is weak.** A 2025 paper found current large multimodal models "severely suffer from inaccurate geometric perception" on IC footprint drawings and built ICGeo8K (8,608 samples) to fix it ([LLM4-IC8K, arXiv:2508.03725](https://arxiv.org/abs/2508.03725)). Practical takeaway: do not rely on the model to count pins or read pin spacing from video. Rely on silkscreen text, board shape/colour and the narration.
- **Prompting tactics that work for identity:**
  1. Ask for *visible text verbatim* first (silkscreen: "GY-BME280", "HW-201", "DOIT ESP32 DEVKIT V1"), then identity as a separate field.
  2. Force `identity_confidence` and `alternatives[]` ("could also be BMP280, which looks the same").
  3. Provide a "look-alike list" from the KG in the prompt (BME280/BMP280, SSD1306/SH1106, DHT22/AM2302, NodeMCU v2/v3, Nano FTDI/CH340).
  4. Grab the best frame (`timestamp`) so the UI can show it next to the BOM line. This is great for demos and trust.
- **Known look-alike traps** (encode as KG `OFTEN_MISLABELED_AS` edges): a "$1.30 BME280" is almost certainly a BMP280. Chip-ID register 0xD0 reads 0x60 for BME280 and 0x58 for BMP280, and the BME280 metal can is nearly square while the BMP280's is rectangular ([atomic14 fake sensors](https://www.atomic14.com/esp32/sensors/fake-sensors/)). The same source flags DS18B20 clones, black-PCB MH-Z19, 10 Hz HX711 clones, NEO-6M fakes, and eCO2 sensors (SGP30/CCS811/ENS160) that measure VOCs, not true CO2.

### 1.4 Extraction output schema (Gemini structured output)

```json
{
  "$id": "BomItem",
  "type": "object",
  "required": ["line_id", "raw_name", "category", "qty", "evidence", "confidence"],
  "properties": {
    "line_id": {"type": "string"},
    "raw_name": {"type": "string", "description": "verbatim as creator wrote/said it"},
    "canonical": {
      "type": "object",
      "properties": {
        "chip": {"type": "string", "examples": ["BME280", "ESP8266EX", "A4988", "WS2812B"]},
        "module": {"type": "string", "examples": ["Adafruit 2652", "GY-BME280-3.3", "NodeMCU v3 LoLin"]},
        "ecosystem": {"enum": ["none","STEMMA","STEMMA_QT","Qwiic","Grove","Feather","FeatherWing","Pololu_stepper","Arduino_shield","Pi_HAT","Pi_pHAT","Wemos_D1_mini_shield"]},
        "kg_id": {"type": "string"}
      }
    },
    "category": {"enum": ["mcu_board","sensor","actuator","motor_driver","display","power","passive","connector","mechanical","mains_switching","led","rf_module","tool","consumable"]},
    "qty": {"type": ["number","null"]},
    "qty_unit": {"enum": ["pcs","m","g","set", null]},
    "role_in_project": {"type": "string", "description": "e.g. 'switches rice cooker heater'"},
    "interfaces_used": {"type": "array", "items": {"enum": ["I2C","SPI","UART","1-Wire","PWM","ANALOG","DIGITAL","STEP_DIR","USB","MAINS_AC"]}},
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["source_type","locator","quote"],
        "properties": {
          "source_type": {"enum": ["code","structured_page","description","transcript","frame","schematic","comment"]},
          "locator": {"type": "string", "description": "URL#anchor, file:line, or mm:ss"},
          "quote": {"type": "string"}
        }
      }
    },
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "lookalike_risk": {"type": "array", "items": {"type": "string"}},
    "optional": {"type": "boolean"}
  }
}
```

---

## 2. Parametric matching and cross-reference: how the pros do it

### 2.1 What commercial tools do

| Tool | Mechanism (from docs) | Takeaway for Bharat Sourcer |
|---|---|---|
| **Nexar / Octopart `similarParts`** | GraphQL field returning "parts identified by Nexar to be similar in specification and functionality" ([Nexar support](https://support.nexar.com/support/solutions/articles/101000434631-supply-similar-parts)). Octopart's key specs are "hand picked by our team of electrical engineers", results always stay "within the same category… algorithmically generated, not cross-referenced", and the algorithm is meant to "think like an applications engineer" ([Altium/Octopart Similar Parts](https://resources.altium.com/p/similar-parts-automated-part-discovery)). Seller inventory can be filtered by country ([Nexar query examples](https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples)) | **Per-category hand-picked key specs** is the pattern to copy. The free Evaluation plan covers up to 100 matched parts and includes Tech Specs, Datasheets and Similar Parts ([Nexar plans](https://nexar.com/compare-plans)), which is enough for chip-level lookups in a demo. Octopart has no data on Indian maker modules, so use it for *chips*, not modules |
| **Z2Data** | Drop-In A (identical package/pinout, zero parametric difference), B (minor differences), C (major differences), then "Other Packages". Tiers "build on package and pinout first" ([Z2Data](https://www.z2data.com/products/part-risk-manager/features/advanced-cross-search)). Form-Fit-Function framing, with the note that "Function is where most cross-reference failures originate" ([Z2Data guide](https://www.z2data.com/guides/the-ultimate-guide-to-cross-references/)) | Copy the **tiering**, redefined for modules (section 2.3) |
| SiliconExpert / Ultra Librarian / SnapEDA / Findchips | Parametric databases plus CAD models; Findchips aggregates distributor stock | For the hackathon, cite as "industry pattern". You don't need them |

### 2.2 Per-category key attributes (the "hand-picked specs")

Split every attribute into **HARD** (mismatch means grade ≥ C or X), **SOFT** (affects score and explanation) and **INFO**.

**MCU dev board**
- HARD: MCU family/core (ESP32, ESP32-S2/S3/C3, ESP8266, ATmega328P, RP2040/RP2350), logic voltage (3.3/5 V), required peripherals used by the project (Wi-Fi, BLE, native USB-HID, DAC, touch pins, ADC channel count), flash ≥ project need, and pins used by the project that exist on the candidate with the same function.
- SOFT: form factor (Uno, Nano, Feather, D1 mini, DevKitC 30/38-pin, Pico), USB-serial chip (CH340/CP2102/FTDI/native), onboard LiPo charger, onboard regulator current, connector (micro-USB/USB-C), antenna type.
- INFO: price, board-package name for Arduino/PlatformIO (`board = nodemcuv2`, `esp32dev`).

**Sensor module**
- HARD: measured quantity set (a BMP280 has **no humidity**), bus (I2C/SPI/analog/1-Wire), supply range of the *module* (onboard LDO or not), I/O voltage tolerance, I2C address options.
- SOFT: accuracy/range, sample rate, connector ecosystem (STEMMA QT/Qwiic JST-SH 1 mm vs Grove 2 mm), breakout size and mounting holes.
- INFO: library support set.

**Motor driver**
- HARD: motor type (bipolar stepper, unipolar, brushed DC, BLDC), max motor voltage, current per phase (RMS), control interface (STEP/DIR, PWM+DIR, UART, SPI), footprint family (Pololu 16-pin).
- SOFT: microstep resolution, current-set method (Vref formula), noise (StealthChop), protection pins (FAULT), minimum STEP pulse width.

**Display**
- HARD: controller IC (SSD1306, SH1106, ST7735, ST7789, ILI9341, HD44780+PCF8574), interface, resolution, logic voltage.
- SOFT: size, colour, touch controller, backlight current.

**Power**
- HARD: input (mains 230 V/50 Hz in India vs 120 V/60 Hz US), output voltage(s), current, connector/polarity (5.5×2.1 vs 5.5×2.5 mm barrel), plug type.
- SOFT: efficiency, ripple, certification (BIS for many categories).

**Addressable LEDs**
- HARD: protocol/chip (WS2812B, SK6812 RGBW, APA102/SK9822 with clock line), supply voltage (5 V vs 12 V strips such as WS2815), colour order (RGB vs RGBW changes code).
- SOFT: density (30/60/74/144 per m), IP rating, data-line logic threshold.

**Mains switching**
- HARD: rated AC voltage/current, isolation, control-input voltage and polarity (many Indian relay modules are active-LOW), enclosure/finger-safety.
- SOFT: SSR vs electromechanical, zero-cross.

### 2.3 Maker compatibility grades (adapted from Z2Data A/B/C)

| Grade | Name | Definition | UI colour |
|---|---|---|---|
| **A** | Drop-in | Same chip or pin/protocol-compatible part, same voltage domain, same library, no code change | green |
| **B** | Drop-in + config | Same wiring. Needs a one-line code/config change (I2C address, board definition, driver install, bootloader option, Vref re-tune) | green-yellow |
| **C** | Rewire / add part | Needs wiring changes or an extra part (level shifter, voltage divider, adapter cable, different PSU) and possibly a library swap | amber |
| **D** | Functional alternative | Different chip/approach that achieves the project goal but changes behaviour/spec (DHT22→DHT11, BME280→BMP280+separate humidity), with code rewrite | orange |
| **X** | Not recommended | Unsafe (mains, Li-ion without protection) or cannot meet a HARD requirement | red |

### 2.4 Form-factor and ecosystem facts the KG must encode

- **Pololu stepper footprint**: the DRV8825 is "a higher-performance drop-in replacement" for the A4988 in many applications, **but** the pin that is the logic supply on the A4988 is a FAULT output on the DRV8825. It supports 1/32 microstepping, current limit = VREF × 2, STEP high/low each ≥ 1.9 µs (vs 1 µs on the A4988), 45 V max vs 35 V, and a SLEEP pin that is not pulled up by default ([Pololu DRV8825](https://www.pololu.com/product/2133)). The TMC2209 in the same footprint uses different meanings for the MS pins, adds PDN/UART, and "while marketed as a drop-in replacement… requires different pin configuration" ([Arduino forum A4988→TMC2209](https://forum.arduino.cc/t/exchanging-a4988-for-tmc2209/870682)).
- **I2C cable ecosystems**: STEMMA QT and Qwiic are both JST-SH 1.0 mm 4-pin with identical pin order, so they interchange fully. Classic STEMMA is JST-PH 2.0 mm. Grove is a proprietary 2.0 mm 4-pin that works with STEMMA/Qwiic I2C devices only via adapter cables ([Tom's Hardware comparison](https://www.tomshardware.com/features/stemma-vs-qwiic-vs-grove-connectors)). Adafruit sells JST-PH↔JST-SH adapters ([Adafruit 4424](https://www.adafruit.com/product/4424)). Qwiic is specified at 3.3 V, so a 5 V Grove host is a HARD check.
- **Logic levels**: "ESP32 GPIOs are not 5 V tolerant. Use a voltage divider or level shifter between the HC-SR04 ECHO pin and the ESP32" ([Espressif component registry, hc_sr04](https://components.espressif.com/components/phlangone/hc_sr04/versions/2.0.0/readme)). Random Nerd Tutorials' ESP32 + HC-SR04 guide wires ECHO directly, and its comments disagree about whether that's safe ([RNT ESP32 HC-SR04](https://randomnerdtutorials.com/esp32-hc-sr04-ultrasonic-arduino/)). **Policy: when sources conflict on an electrical safety margin, the conservative rule wins, and the UI says so.**
- **NeoPixels at 3.3 V**: a 3.3 V MCU driving 5 V NeoPixels can cause "incorrect colors, flickering, dimness, and seemingly 'dead' pixels". Fixes: 74AHCT125, LXB0108 or the Adafruit Pixel Shifter ([Adafruit NeoPixel level shifting](https://learn.adafruit.com/neopixel-levelshifter.md)).
- **Mains**: India is 230 V / 50 Hz with Type D (6 A) and Type M (16 A) plugs, and the government has prohibited importing appliances without proper D/M plugs ([WorldStandards India](https://www.worldstandards.eu/electricity/plug-voltage-by-country/india/)). The US is 120 V / 60 Hz. Any US project that switches mains or uses a US wall appliance is automatically grade ≥ C, and grade X if it uses a US-only switching product.

---

## 3. Firmware and code impact

### 3.1 Dependency detection

- **Arduino**: parse `#include <...>` from `.ino/.cpp/.h`. Map headers to libraries using the Arduino library index (`library_index.json` lists every Library Manager release with `providesIncludes`, `architectures`, `dependencies`; downloadable from `downloads.arduino.cc/libraries/library_index.json(.gz)`). In a library's own `library.properties`, `depends=` is "a comma-separated list of dependencies… version constraints can be specified in parentheses" and `architectures=` is "a comma separated list of architectures supported… use `*`" ([Arduino library spec](https://arduino.github.io/arduino-cli/1.0/library-specification/)). Example: Adafruit BME280 Library v2.3.0 has `architectures=*` and `depends=Adafruit Unified Sensor, Adafruit BusIO` ([library.properties](https://github.com/adafruit/Adafruit_BME280_Library/blob/master/library.properties)).
- **PlatformIO**: the Library Dependency Finder resolves dependencies by parsing `#include` directives. Modes are `chain` (default), `deep`, and `chain+`/`deep+` (which evaluate `#ifdef`s). Compatibility modes are soft/strict/off ([PlatformIO LDF](https://docs.platformio.org/en/latest/librarymanager/ldf.html)). The registry supports the qualifier `header:FILENAME` to "locate libraries containing specific header files", plus `framework:` and `platform:` filters ([pio pkg search](https://docs.platformio.org/en/latest/core/userguide/pkg/cmd_search.html)). **This is the cleanest header→library resolver available: `pio pkg search "header:Adafruit_BME280.h"`.**
- **CircuitPython/MicroPython**: parse `import adafruit_xxx`. The Adafruit CircuitPython bundle names map almost 1:1 to chips (`adafruit_bme280`, `adafruit_ssd1306`).
- **Raspberry Pi Python**: `requirements.txt`, `import board, busio` (Blinka).

### 3.2 Header → chip → library KG edges (seed examples)

| Header / import | Chip(s) | Library | Default I2C addr | Notes |
|---|---|---|---|---|
| `Adafruit_BME280.h` | BME280 | Adafruit BME280 Library | 0x77 (`BME280_ADDRESS`), alt 0x76 | `readHumidity()` exists ([header](https://github.com/adafruit/Adafruit_BME280_Library/blob/master/Adafruit_BME280.h)) |
| `Adafruit_BMP280.h` | BMP280 | Adafruit BMP280 Library | 0x77, alt 0x76 | `begin(addr, chipid=0x58)`, no humidity ([header](https://github.com/adafruit/Adafruit_BMP280_Library/blob/master/Adafruit_BMP280.h)) |
| `Adafruit_SSD1306.h` | SSD1306 | Adafruit SSD1306 | 0x3C/0x3D | 0.96" modules |
| `Adafruit_SH110X.h` | SH1106G, SH1107 | Adafruit SH110X | 0x3C | classes `Adafruit_SH1106G`, `Adafruit_SH1107`, built on Adafruit GFX ([repo](https://github.com/adafruit/Adafruit_SH110x)) |
| `NewPing.h` | HC-SR04 family | NewPing | n/a | used by DroneBot tutorial |
| `Adafruit_NeoPixel.h` | WS2812B/SK6812 | Adafruit NeoPixel | n/a | `NEO_GRB` vs `NEO_GRBW` |
| `TMCStepper.h` | TMC2208/2209/2130/5160 | TMCStepper | n/a | UART/SPI config |
| `AccelStepper.h` | any STEP/DIR | AccelStepper | n/a | `setMinPulseWidth()` matters for DRV8825 |
| `DHT.h` | DHT11/DHT22/AM2302 | DHT sensor library | n/a | `#define DHTTYPE` |
| `OneWire.h` + `DallasTemperature.h` | DS18B20 | same | n/a | 4.7 kΩ pull-up |

### 3.3 Generating code diffs

Algorithm (runs after the substitution verdict):

```
def code_impact(project_code, original, substitute, kg):
    impacts = []
    lib_o, lib_s = kg.library_for(original.chip), kg.library_for(substitute.chip)
    if lib_o != lib_s:
        impacts.append(LibrarySwap(lib_o, lib_s, api_map=kg.api_map(lib_o, lib_s)))
    if substitute.i2c_default != original.i2c_default and project_code.calls_begin_without_addr():
        impacts.append(AddressChange(original.i2c_default, substitute.i2c_default))
    if substitute.board_id != original.board_id:
        impacts += pin_remap(project_code.pins_used(), original.pinmap, substitute.pinmap)
        impacts.append(BoardTarget(original.board_id, substitute.board_id))   # FQBN / platformio env
    # LLM step: produce unified diff constrained to the listed impacts
    diff = gemini.generate(prompt=DIFF_PROMPT, context={code, impacts, api_map}, schema=UnifiedDiff)
    # verification: compile with arduino-cli / pio in Cloud Run job
    ok, log = compile(diff.apply(project_code), target=substitute.board_id)
    for _ in range(2):
        if ok: break
        diff = gemini.repair(diff, log); ok, log = compile(...)
    return impacts, diff, ok
```

**Why compile in the loop:** EmbedAgent/EmbedBench (ICSE 2026) found that migrating Arduino code to ESP-IDF reached only 29.4% pass@1 (Arduino→Pico MicroPython: 73.8%), with syntax errors behind about 41.9% of failures. Retrieval augmentation plus compiler feedback raised DeepSeek-R1 from 55.6% to 65.1% ([EmbedAgent, arXiv:2506.11003](https://arxiv.org/abs/2506.11003)). **Keep ports inside the Arduino framework (arduino-esp32 core) rather than rewriting to ESP-IDF.** A headless `arduino-cli compile --fqbn esp32:esp32:esp32` in a Cloud Run job is feasible. Pre-bake the cores into the container image, because the ESP32 core is large.

---

## 4. Worked substitution cases (12)

Each case is written the way the agent should output it: original → India-available alternative → grade → what changes (wiring / power / code / risk).

### Case 1: Adafruit BME280 (STEMMA QT, #2652) → generic "GY-BME280" purple module
- **Project**: Adafruit IO Environmental Monitor (Feather HUZZAH ESP8266 + BME280 + SGP30) ([guide](https://learn.adafruit.com/adafruit-io-air-quality-monitor)).
- **Grade**: B (C if the module is 5 V only, D if it turns out to be a BMP280).
- **Wiring**: no STEMMA QT connector, so solder headers and use 4 jumpers (VIN, GND, SCL, SDA). The Adafruit board has an onboard regulator and level shifting. The "GY-BME280-3.3" variant sold by Indian stores ([Robu listing](https://stg.robu.in/product/gy-bme280-3-3-precision-altimeter-atmospheric-pressure-sensor-module)) must be powered from **3.3 V only**. Fine with a Feather, but don't feed it 5 V from an Uno.
- **Code**: generic modules usually strap SDO low, giving address **0x76**, while the Adafruit library defaults to 0x77. Diff: `bme.begin()` → `bme.begin(0x76)`.
- **Risk**: look-alike BMP280. Add a self-test snippet that reads register 0xD0 (0x60 = BME280, 0x58 = BMP280) ([atomic14](https://www.atomic14.com/esp32/sensors/fake-sensors/)). If the chip is a BMP280 the humidity feed is lost, so it becomes grade D: switch to `Adafruit_BMP280`, drop the humidity feed, or add an AHT20/SHT31 for humidity.

### Case 2: PowerSwitch Tail II (US 120 V) → 230 V relay/SSR module in an enclosed box
- **Project**: Adafruit "Sous-viduino" (Metro 328, RGB LCD shield, DS18B20, PowerSwitch Tail 2, rice cooker) ([guide](https://learn.adafruit.com/sous-vide-powered-by-arduino-the-sous-viduino)).
- **Grade**: C for skilled builders. **X** if the user shows no mains experience. The UI should default to recommending a certified enclosed smart plug or a pre-built SSR controller box.
- **Power**: US mains is 120 V/60 Hz and India is 230 V/50 Hz with Type D/M plugs ([WorldStandards](https://www.worldstandards.eu/electricity/plug-voltage-by-country/india/)). The PowerSwitch Tail is a US-plug product, so it is unusable. The rice cooker itself must be an Indian 230 V model. Check its wattage against the relay's rating with ≥2× margin for resistive loads.
- **Wiring**: common Indian 5 V relay modules are often **active-LOW**. If the code does `digitalWrite(RelayPin, HIGH)` for ON, invert it. An SSR (DC-controlled, 3–32 V input) keeps the original active-HIGH logic.
- **Code**: invert output polarity if needed. The PID window (`WindowSize`) is fine, since mains frequency doesn't matter for time-proportioning.
- **Safety checklist** (hard-coded, not LLM): enclosure, earth continuity, fuse, strain relief, no exposed 230 V on the Arduino side.

### Case 3: A4988 → TMC2209 (e.g. MKS TMC2209 V2.0, ₹849 incl. GST at Probots, out of stock when checked) ([Probots](https://probots.co.in/mks-tmc2209-v2-stepper-motor-driver-uart-module.html))
- **Project**: DroneBot Workshop stepper tutorial with A4988 + NEMA 17 ([DroneBot](https://dronebotworkshop.com/stepper-motors-with-arduino/)).
- **Grade**: C.
- **Wiring**: same Pololu footprint, but the MS1/MS2 pins select different microstep tables. MS3 becomes SPREAD (tie to GND for StealthChop), and PDN/UART need handling ([Arduino forum](https://forum.arduino.cc/t/exchanging-a4988-for-tmc2209/870682)). Some TMC modules invert DIR relative to the A4988, so tell the user to swap one coil pair or invert in code.
- **Power**: MKS TMC2209 motor supply is 5.5–28 V (vs A4988 8–35 V). A 12 V NEMA 17 setup is fine. A 36 V project is **not**.
- **Current**: re-tune Vref using the module's own formula. Never reuse the A4988 value.
- **Code**: STEP/DIR mode needs no library change. Optional: add `TMCStepper` for UART current control and StallGuard.
- **Benefit to explain**: near-silent StealthChop, up to 1/256 microstep interpolation.

### Case 4: A4988 → DRV8825 (the cheaper common alternative)
- **Grade**: B.
- **Changes**: current limit = VREF × 2 ([Pololu](https://www.pololu.com/product/2133)), so re-tune Vref. The A4988 VDD pin position is FAULT on the DRV8825. It's harmless if the board ties it to logic VCC via the carrier's resistor, but warn anyway. Minimum STEP pulse is 1.9 µs, so add `stepper.setMinPulseWidth(2)` for AccelStepper and check hand-written `delayMicroseconds(1)` loops. Microstepping now goes to 1/32, and MS pin tables differ, so revise the steps-per-mm constant if MS pins are all high.

### Case 5: Adafruit Feather HUZZAH ESP8266 → NodeMCU v3 (LoLin) ESP8266
- **Grade**: B for code, C for power (battery).
- **Wiring**: GPIO numbers are the same chip, but silkscreen labels differ (D1=GPIO5, D2=GPIO4 on NodeMCU). The agent must rewrite wiring instructions from `GPIO n` to `Dx` labels. Adafruit FeatherWings won't stack, so the Proto FeatherWing becomes a perfboard.
- **Power**: NodeMCU has **no LiPo charger/JST**. The 1200 mAh LiPo from the original BOM needs a TP4056 module *with protection* (DW01) plus a boost or LDO feed, or drop the battery and power over USB. Note that NodeMCU v3 (LoLin) is wider than v2 (Amica) and covers both breadboard rows. Recommend v2 or two breadboards.
- **Code**: board target `Adafruit Feather HUZZAH ESP8266` → `NodeMCU 1.0 (ESP-12E Module)` (PlatformIO `board = nodemcuv2`). `LED_BUILTIN` polarity/pin may differ (GPIO0 red LED on the Feather vs GPIO2 on NodeMCU). USB-serial is CH340 on most Indian NodeMCUs, so a driver install may be needed on Windows.

### Case 6: 0.96" SSD1306 OLED → 1.3" "OLED" module (very often SH1106)
- **Grade**: B (library swap). The KG should flag that "1.3 inch I2C OLED" listings in India are mostly SH1106.
- **Wiring**: same 4 pins, but **check VCC/GND order** on the header: some 1.3" boards swap them. The agent must tell the user to read the silkscreen, because a reversed supply kills the module.
- **Code diff**:
```diff
-#include <Adafruit_SSD1306.h>
-Adafruit_SSD1306 display(128, 64, &Wire, -1);
+#include <Adafruit_SH110X.h>
+Adafruit_SH1106G display(128, 64, &Wire, -1);
 ...
-display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
+display.begin(0x3C, true);
-display.setTextColor(SSD1306_WHITE);
+display.setTextColor(SH110X_WHITE);
```
Library reference: [Adafruit_SH110x](https://github.com/adafruit/Adafruit_SH110x). Both libraries sit on Adafruit GFX, so drawing calls are unchanged. The alternative is U8g2 with an `SH1106` constructor, but that means a bigger rewrite.

### Case 7: Arduino Uno project with HC-SR04 → ESP32 DevKit V1 (user already owns one)
- **Grade**: C.
- **Wiring**: HC-SR04 needs 5 V to range reliably, so power it from VIN/5V. ECHO outputs 5 V and **ESP32 GPIOs are not 5 V tolerant**, so add a divider (e.g. 1 kΩ/2 kΩ, or the 1 kΩ + 2.2 kΩ some commenters use) or a level shifter ([Espressif registry](https://components.espressif.com/components/phlangone/hc_sr04/versions/2.0.0/readme)). Mention that some tutorials skip this ([RNT](https://randomnerdtutorials.com/esp32-hc-sr04-ultrasonic-arduino/)), and that Bharat Sourcer takes the conservative path. Better alternative: a 3.3 V-capable sensor such as the RCWL-1601 / "HC-SR04P" variant, which becomes grade B.
- **Code**: pin numbers change (avoid strapping pins GPIO0/2/12/15 and input-only pins 34–39 for TRIG). NewPing's ESP32 support varies by version, so fall back to `pulseIn()`. Board target changes to `esp32:esp32:esp32`.

### Case 8: 3.3 V MCU (NodeMCU/ESP32) driving a WS2812B strip
- **Project**: Hackster infinity mirror clock (NodeMCU v3 + WS2812B + 470 µF + phone charger) ([Hackster](https://www.hackster.io/rundhall/infinity-mirror-wall-clock-in-ikea-picture-frame-700125)).
- **Grade**: A for strips/Indian equivalents (WS2812B is sold widely). Flag an optional C upgrade for reliability.
- **Wiring**: 3.3 V data into a 5 V-powered strip can flicker. Recommend a 74AHCT125 (or 74HCT245) level shifter ([Adafruit](https://learn.adafruit.com/neopixel-levelshifter.md)) plus a 300–500 Ω series resistor and the 470 µF cap already in the BOM.
- **Power**: size the supply as LEDs × 60 mA worst case (74 LEDs ≈ 4.4 A at full white). A "phone charger" is inadequate at full white, so either cap brightness in code (`strip.setBrightness(64)`) or buy a 5 V 5 A SMPS (230 V input, Indian plug). The agent should state the math.
- **Code**: if the substitute strip is SK6812 RGBW, change `NEO_GRB` to `NEO_GRBW`. Otherwise no change.

### Case 9: Genuine Arduino Nano → Indian Nano clone (CH340, old bootloader)
- **Grade**: B.
- **Changes**: install the CH340 driver, then select Processor "ATmega328P (Old Bootloader)" if uploads fail. This is "one of the most common Nano clone upload problems" ([Universal-Solder troubleshooting](https://www.universal-solder.ca/troubleshooting-arduino-failed-upload/)). No wiring or code changes. The KG models this as `(module: Nano clone) -[REQUIRES_CONFIG]-> "old bootloader", "CH340 driver"`.

### Case 10: Adafruit PiOLED (Pi add-on, #3527) → generic 0.91" SSD1306 128×32 I2C module
- **Project**: Adafruit Pi-Hole with Pi Zero W ([guide](https://learn.adafruit.com/pi-hole-ad-blocker-with-pi-zero-w)).
- **Grade**: C (rewire, same software).
- **Wiring**: not a plug-on HAT. Four jumpers: 3V3 (pin 1), SDA (pin 3), SCL (pin 5), GND (pin 6). Enable I2C with `raspi-config`.
- **Code**: none. Same SSD1306 controller, same `adafruit-circuitpython-ssd1306` library, address 0x3C.
- **Mechanical**: the Adafruit Pi Zero case won't hold it the same way, so suggest a 3D-printable alternative.

### Case 11: DHT22 → DHT11 (cheaper and more common)
- **Grade**: D (functional downgrade).
- **Code**: `#define DHTTYPE DHT22` → `DHT11`. Wiring is the same, including the pull-up on 3-pin modules.
- **Impact**: DHT11 has a lower range and resolution (roughly 0–50 °C at 1 °C steps vs −40–80 °C at 0.1 °C for DHT22). The agent should **refuse to recommend it if the project measures sub-zero or needs decimals** (e.g. a freezer monitor) and suggest an AHT20/SHT31 (I2C) instead, with the accompanying library change.

### Case 12: US "12 V 2 A wall wart" → Indian 12 V 2 A SMPS adapter
- **Grade**: A to B.
- **Checks**: 230 V AC input with a Type D plug. Barrel size 5.5×2.1 mm vs 5.5×2.5 mm (a mismatch gives an intermittent connection). Centre-positive polarity. For motor projects, peak current headroom. Prefer BIS-marked adapters, since many adapter categories fall under India's compulsory registration scheme.

### Case 13: Adafruit MagTag (ESP32-S2 e-ink all-in-one) → no local equivalent
- **Projects**: [MagTag Weather](https://learn.adafruit.com/magtag-weather.md?view=all), [Cheerlights wreath](https://learn.adafruit.com/cheerlights-led-animations.md?view=all).
- **Decision**: first try to *import the genuine board* via an Indian reseller of Adafruit (grade A). Otherwise use a **LilyGO/Waveshare ESP32 + 2.9" e-paper** (grade D: SSD1680 driver, different pin map, CircuitPython support may not exist, so the agent might port to Arduino + GxEPD2). Showing this "import vs redesign" choice with cost and effort is a strong demo moment.

---

## 5. Knowledge representation

### 5.1 Graph model (Firestore collections or a small Neo4j/Spanner Graph)

Nodes:
- `Chip {id, family, vendor, vdd_min, vdd_max, io_5v_tolerant, interfaces[], i2c_addrs[], chip_id_reg?, datasheet_url}`
- `Module {id, name_aliases[], chip_id, vin_min, vin_max, has_regulator, has_level_shift, logic_v, connector, ecosystem, pinout[{label, function, gpio?}], dims_mm, holes}`
- `Library {id, framework, headers[], depends[], architectures[], api_symbols[]}`
- `Ecosystem {id, connector, pitch_mm, voltage, pin_order}` (STEMMA QT, Qwiic, Grove, Pololu stepper, Feather, D1 mini)
- `Board {id, mcu_chip, fqbn, pio_board, pinmap, usb_serial, charger, logic_v}`
- `Listing {vendor(robu|robocraze|probots|evelta|electronicscomp|quartzcomponents|amazon.in|mouser.in|...), url, title, module_id, price_inr, stock, fetched_at, http_status}`

Edges:
- `Module -USES_CHIP-> Chip`
- `Chip -SUPPORTED_BY-> Library`
- `Chip -FAMILY_UPGRADE_OF / DOWNGRADE_OF-> Chip` (DHT22↔DHT11, BMP280→BME280)
- `Module -FOOTPRINT_COMPATIBLE {grade, notes[]}-> Module` (A4988↔DRV8825↔TMC2209)
- `Module -OFTEN_MISLABELED_AS-> Module` (BMP280 sold as BME280)
- `Ecosystem -ADAPTS_TO {cable}-> Ecosystem`
- `Library -API_MAP {symbol_map}-> Library` (SSD1306 → SH110X)

Seed about 150 modules that cover about 80% of maker BOMs: Uno/Nano/Mega/ESP32/ESP8266/Pico boards, HC-SR04, DHT, BME/BMP, DS18B20, MPU6050, SSD1306/SH1106, 16×2 LCD+PCF8574, WS2812B, SG90/MG996R, 28BYJ-48+ULN2003, L298N, A4988/DRV8825/TMC2209, relay modules, TP4056, MT3608, LM2596, INA219, HX711, RC522, NEO-6M, MAX7219, DFPlayer. Hand-curation matters. The Duke study found human-expert skills achieved 42/42 on Arduino, while LLM-generated skills were "inconsistent or sometimes detrimental" ([arXiv:2603.19583](https://arxiv.org/pdf/2603.19583)). **Pitch line: "curated compatibility graph + LLM reasoning", not "LLM guesses".**

### 5.2 Datasheet parsing to fill the KG

- A pipeline like Docling plus hybrid chunking to JSON, with vision models describing figures and results stored in a DB for reuse ([Altium, local-LLM datasheet extractor](https://resources.altium.com/p/building-local-llm-datasheet-extractor-ic-driver-development)). With Gemini you can instead pass the PDF directly and use a JSON schema.
- Research baselines: D2S-FLOW reached EM 0.86 / F1 0.92 on datasheet parameter extraction using attention-guided document focusing, hierarchical retrieval and name normalization ([arXiv:2502.16540](https://arxiv.org/abs/2502.16540v2)). DocEDA combines layout analysis and CoT parameter extraction into a component DB ([arXiv:2412.05301](https://arxiv.org/abs/2412.05301)).
- **Normalization is the hard part**: "VDD", "VCC", "Supply voltage", "V_IN" all map to `vdd_range`. Keep a synonym table per category, and store `{value, unit, min, typ, max, conditions, page, quote}` so every number is traceable.

### 5.3 Matching algorithm (hybrid: rules + embeddings + LLM judge)

```
def find_substitutes(item, project_ctx, kg, market):
    # 1. candidate generation
    cands  = kg.same_chip_modules(item.chip)                          # best: same chip, different module
    cands += kg.footprint_compatible(item.module)                     # Pololu, Feather, etc
    cands += kg.family_alternatives(item.chip)                        # up/downgrades
    cands += vector_search(embed(item.spec_text), index="modules", k=20, filter={"category": item.category})
    cands  = [c for c in dedupe(cands) if market.has_live_listing(c, country="IN")]

    # 2. hard constraints (deterministic)
    results = []
    for c in cands:
        violations, fixes = [], []
        for rule in RULES[item.category] + RULES["global"]:
            r = rule(item, c, project_ctx)        # returns PASS | FIXABLE(fix) | FAIL(reason)
            if r.fail:   violations.append(r)
            if r.fixable: fixes.append(r.fix)
        if violations: continue                    # or keep as grade X with reason, for explanation
        grade = grade_from(fixes)                  # none->A, config->B, wiring/part->C, spec-change->D

        # 3. soft score
        s = (0.35*param_similarity(item, c) + 0.2*library_overlap(item, c)
             + 0.15*ecosystem_match(item, c) + 0.15*availability_score(c)
             + 0.15*price_score(c))
        results.append(Candidate(c, grade, fixes, s))

    # 4. rank: grade first, then score
    top = sorted(results, key=lambda r: (GRADE_ORDER[r.grade], -r.score))[:3]

    # 5. LLM explanation + code impact, then judge
    for t in top:
        t.explanation = gemini.explain(item, t, project_ctx, fixes=t.fixes, schema=ImpactReport)
        t.code_diff   = code_impact(project_ctx.code, item, t.module, kg)
        t.judge       = llm_judge(t, CHECKLIST[item.category])        # section 5.5
        t.confidence  = calibrate(t)
    return top
```

Example global rules (Python predicates, not prompts):
- `logic_level`: if MCU.logic_v == 3.3 and any signal from a 5 V-output module goes to an MCU input and not MCU.io_5v_tolerant → FIXABLE(level_shifter | divider).
- `i2c_address_collision`: for all I2C modules on one bus, addresses must be unique after the substitution. Otherwise FIXABLE(set ADDR pin) or FAIL.
- `supply_range`: module.vin range must contain the rail it is connected to.
- `mains`: category == mains_switching or any item role mentions AC mains → requires `rated_voltage >= 250 VAC`, plug type in {D, M}. The project flag `mains=True` forces a safety banner.
- `measured_quantities_superset`: substitute.measures ⊇ project.used_quantities. Otherwise the grade is at least D.
- `library_exists_for_framework`: KG or registry must have a library for (chip, framework). Otherwise the grade is at least D.
- `pin_function`: each project pin's function (ADC, PWM, touch, DAC, input-only) must exist on the substitute board.

### 5.4 Output schema for the compatibility report

```json
{
  "$id": "ImpactReport",
  "type": "object",
  "required": ["original","substitute","grade","changes","confidence","citations"],
  "properties": {
    "original":   {"$ref": "#/defs/PartRef"},
    "substitute": {"$ref": "#/defs/PartRef"},
    "grade": {"enum": ["A","B","C","D","X"]},
    "summary": {"type": "string", "maxLength": 280},
    "changes": {
      "type": "object",
      "properties": {
        "wiring":   {"type": "array", "items": {"type":"object","properties":{"from":{"type":"string"},"to":{"type":"string"},"why":{"type":"string"}}}},
        "power":    {"type": "array", "items": {"type": "string"}},
        "extra_parts": {"type": "array", "items": {"$ref": "#/defs/PartRef"}},
        "code":     {"type": "object", "properties": {
                      "library_swap": {"type":"array","items":{"type":"string"}},
                      "board_target": {"type":"string"},
                      "diff": {"type":"string", "description":"unified diff"},
                      "compiled": {"type":"boolean"}}},
        "mechanical": {"type": "array", "items": {"type": "string"}},
        "behaviour":  {"type": "array", "items": {"type": "string"}, "description":"spec/perf differences the user will notice"}
      }
    },
    "safety_flags": {"type": "array", "items": {"enum": ["MAINS","LIPO","HIGH_CURRENT","LEVEL_SHIFT_REQUIRED","HEAT"]}},
    "verify_on_arrival": {"type": "array", "items": {"type": "string"}, "examples": [["Read reg 0xD0: expect 0x60"]]},
    "confidence": {"type": "number"},
    "citations": {"type": "array", "items": {"type":"object","properties":{"claim":{"type":"string"},"url":{"type":"string"},"quote":{"type":"string"}}}}
  }
}
```

### 5.5 LLM-as-judge checklist (per category, run with a separate Gemini call)

Generic checklist items (each is yes/no/NA, with the evidence span):
1. Does the explanation state the supply voltage of the substitute, and does it match the rail used?
2. Are all signal-level mismatches (3.3 V vs 5 V) addressed?
3. If an I2C device changed, is the address stated and consistent with the code diff?
4. If the chip changed, is the library change reflected in the diff, and does every API call in the diff exist in the new library (checked against the KG `api_symbols`)?
5. Are measured quantities or capabilities lost (humidity, microstep, colour channel)?
6. Is any claim unsupported by a citation or KG fact? (List them.)
7. For mains or LiPo, is the safety banner present?
8. Is the product link one we fetched in the last 24 hours, and does its title contain the chip or module name?

Run the judge **three times** (with temperature > 0) and take the majority. This mirrors DRCY's "multi-run consensus", where an AllSpice production system runs several parallel reviews per component group and reconciles them, including agentic datasheet retrieval with self-evaluation scoring ([DRCY, arXiv:2603.15672](https://arxiv.org/html/2603.15672)).

### 5.6 Confidence scoring

`confidence = σ( w1·extraction_conf + w2·kg_coverage + w3·rule_pass_ratio + w4·judge_agreement + w5·listing_freshness − w6·lookalike_risk )`

Calibrate on the eval set so that "0.8" means right about 80% of the time (a reliability plot on a demo slide looks rigorous). Show three buckets in the UI: **Verified** (KG + rules + live listing), **Likely** (LLM + rules, no KG entry), **Check manually**.

### 5.7 Hallucination prevention for SKUs and links

1. **Recommendations only from fetched listings.** The recommender cannot emit a URL. It emits a `listing_id` from the `Listing` table, and the UI renders the URL from the DB.
2. **Listing verification job** (Cloud Run job, cached 24 h): HTTP 200, not redirected to a search or home page, title fuzzy-contains the chip/module token, price parsed in INR, stock status parsed. Mark stale beyond 72 h.
3. **Grounding with Google Search** for discovery only. Gemini's `google_search` tool returns queries and citation annotations with start/end indices ([Gemini grounding docs](https://ai.google.dev/gemini-api/docs/google-search)). Candidates found this way still go through step 2 before display.
4. **Title ≠ truth**: Indian listings copy titles. For look-alike-risk parts, add a "verify on arrival" test (chip-ID read, I2C scan).
5. **Numeric claims must cite** the KG (with datasheet page) or a fetched page quote. The judge (5.5 item 6) strips uncited numbers.

---

## 6. Evaluation

### 6.1 Eval set: 15 projects with published parts lists

All URLs below were opened during this research unless marked (*). Gold BOMs should be built by hand from the page (and code, where available).

| # | Project | Creator (country) | URL | Why it's in the set |
|---|---|---|---|---|
| 1 | Pi Hole Ad Blocker with Pi Zero W | Adafruit (US) | https://learn.adafruit.com/pi-hole-ad-blocker-with-pi-zero-w | Pi HAT → generic module rewiring (Case 10) |
| 2 | MagTag Daily Weather Forecast | Adafruit (US) | https://learn.adafruit.com/magtag-weather.md?view=all | Unavailable all-in-one board, import vs redesign (Case 13) |
| 3 | Adafruit IO Environmental Monitor | Adafruit (US) | https://learn.adafruit.com/adafruit-io-air-quality-monitor | BME280, SGP30, discontinued VEML6070, LiPo (Cases 1, 5) |
| 4 | PyPortal Weather Station | Adafruit (US) | https://learn.adafruit.com/pyportal-weather-station | Proprietary display board, 5 V 2 A supply |
| 5 | Sous-viduino | Adafruit (US) | https://learn.adafruit.com/sous-vide-powered-by-arduino-the-sous-viduino | **Mains 120→230 V** (Case 2) |
| 6 | Cheerlights Holiday Wreath | Adafruit (US) | https://learn.adafruit.com/cheerlights-led-animations.md?view=all | NeoPixel + MagTag |
| 7 | NeoPixel level shifting guide | Adafruit (US) | https://learn.adafruit.com/neopixel-levelshifter.md | Tests level-shift rule |
| 8 | HC-SR04 Ultrasonic with Arduino | DroneBot Workshop (Canada) | https://dronebotworkshop.com/hc-sr04-ultrasonic-distance-sensor-arduino/ | **Parts list "coming soon"**: extraction must use prose + video |
| 9 | Stepper Motors with Arduino | DroneBot Workshop | https://dronebotworkshop.com/stepper-motors-with-arduino/ | A4988/L298N/ULN2003 (Cases 3, 4) |
| 10 | 8-bit breadboard computer | Ben Eater (US) | https://eater.net/8bit/parts | ~30 74LS ICs, stress test for qty extraction; 74LS vs 74HC substitution |
| 11 | Infinity mirror wall clock | Hackster community | https://www.hackster.io/rundhall/infinity-mirror-wall-clock-in-ikea-picture-frame-700125 | WS2812B + NodeMCU + IKEA frame (Case 8, non-electronic parts) |
| 12 | ESP32 BME280 web server | Random Nerd Tutorials (Portugal) | https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/ | DOIT DevKit V1 + BME280 (address 0x76 issue) |
| 13 | ESP32 + HC-SR04 | Random Nerd Tutorials | https://randomnerdtutorials.com/esp32-hc-sr04-ultrasonic-arduino/ | Conflicting safety advice (Case 7) |
| 14 | Plant Watering System | Instructables | https://www.instructables.com/Plant-Watering-System/ | Pump, moisture sensor, relay (page opened; supplies list not rendered in fetch, so verify manually) |
| 15 | (*) A GreatScott! Instructables build, e.g. from https://www.instructables.com/member/GreatScottLab/ | GreatScott! (Germany, English-language) | pick one with a video and parts list | Video-first extraction (component shots + narration) |

Note: US/UK purity is loose (DroneBot is Canadian, RNT Portuguese, GreatScott German). They are all English-language channels that Indian makers follow. For a UK flavour, add a Pimoroni/The Pi Hut guide or a James Bruton build (not verified here).

For each project, store:
```json
{"project_id":"adafruit-sousviduino",
 "inputs":{"url":"..."},
 "gold_bom":[{"canonical_chip":"DS18B20","module":"waterproof probe","qty":1,"category":"sensor"}, "..."],
 "gold_substitutions":[{"original":"PowerSwitch Tail 2","acceptable":["SSR-25DA in enclosure","230V relay module (enclosed)"],
                        "required_changes":["230V rated","Type D/M plug","enclosure","relay polarity check"],
                        "grade_range":["C","X"]}],
 "must_flag":["MAINS"]}
```

### 6.2 Metrics

| Stage | Metric | Definition |
|---|---|---|
| Extraction | **Item recall / precision / F1** | Match on canonical chip (or module for non-IC items) against gold. Qty accuracy is reported separately (±0 for ICs, ±10% for lengths) |
| Extraction | **Evidence validity** | % of BOM lines whose `evidence.locator` actually contains the quote (automated string check for text; spot-check for timestamps) |
| Resolution | **Canonicalization accuracy** | raw_name → correct KG id |
| Substitution | **Grade accuracy** | exact grade match, plus "within one grade" |
| Substitution | **Required-change recall** | fraction of gold `required_changes` mentioned (LLM judge with rubric) |
| Substitution | **Safety flag recall** | must be 100% for MAINS/LIPO. Treat as a gate, not an average |
| Code | **Compile pass@1** | the diff compiles for the substitute target (`arduino-cli compile`) |
| Links | **Link validity** | HTTP 200 + title match + INR price parsed at eval time |
| Links | **Hallucinated URL rate** | URLs in the output not present in the `Listing` table. Target 0 |
| Overall | **Judge agreement with human** | on 30 samples, Cohen's κ (pcbGPT reported κ = 0.941 for its automated comparator, a good bar to quote) ([pcbGPT, arXiv:2606.01188](https://arxiv.org/pdf/2606.01188)) |

### 6.3 Using ADK eval

ADK provides `tool_trajectory_avg_score` (exact tool-call trajectory), `response_match_score` (ROUGE-1), `final_response_match_v2` (LLM-judged), `rubric_based_final_response_quality_v1`, `rubric_based_tool_use_quality_v1`, `hallucinations_v1` (groundedness vs context), `safety_v1` and multi-turn metrics ([ADK criteria](https://adk.dev/evaluate/criteria/index.md); [ADK eval codelab](https://codelabs.developers.google.com/adk-eval/instructions)). Suggested `test_config.json`:

```json
{
  "criteria": {
    "tool_trajectory_avg_score": {"threshold": 0.8, "match_type": "IN_ORDER"},
    "rubric_based_final_response_quality_v1": {
      "threshold": 0.8,
      "judge_model_options": {"judge_model": "gemini-flash-latest", "num_samples": 3},
      "rubrics": [
        {"rubric_id": "voltage_addressed", "rubric_content": {"text_property": "For every substitute, the response states supply voltage and logic level and flags any 3.3V/5V mismatch with a concrete fix."}},
        {"rubric_id": "code_impact", "rubric_content": {"text_property": "If the chip or board changed, the response names the library/board-target change and shows a code diff."}},
        {"rubric_id": "mains_safety", "rubric_content": {"text_property": "If any part switches AC mains, the response flags 230V/50Hz, Indian plug types and enclosure/safety requirements."}},
        {"rubric_id": "grade_justified", "rubric_content": {"text_property": "Each A/B/C/D/X grade is justified by at least one specific wiring, power, code, or spec difference."}}
      ]
    },
    "hallucinations_v1": {"threshold": 0.85, "judge_model_options": {"judge_model": "gemini-flash-latest"}},
    "safety_v1": 0.9
  }
}
```
The expected trajectory for `IN_ORDER` matching is `fetch_sources → extract_bom → resolve_parts → search_listings → check_compatibility → generate_code_diff → verify_links`. Add a **custom Python metric** for link validity and hallucinated-URL rate. It's simpler to run it as a pytest over the agent's JSON output next to `adk eval`.

---

## 7. Research to cite in the deck (2023–2026, all opened)

| Paper | Year / venue | One-line result to cite |
|---|---|---|
| **EmbedAgent / EmbedBench**, Xu et al. [arXiv:2506.11003](https://arxiv.org/abs/2506.11003) | ICSE 2026 | 126 cases, 9 components, 3 platforms. Arduino→ESP-IDF migration only 29.4% pass@1, and RAG + compiler feedback lifts results. **Justifies compile-in-the-loop and staying in the Arduino framework.** |
| **PCEval** [arXiv:2601.02404](https://arxiv.org/abs/2601.02404v1) | 2026 | 13 LLMs are strong at code and logical circuits but "struggle significantly with physical breadboard layout… proper pin connections". **Justifies deterministic pin/voltage rules.** |
| **Skilled AI Agents for Embedded & IoT**, Li et al. (Duke) [arXiv:2603.19583](https://arxiv.org/pdf/2603.19583) | 2026 | IoT-SkillsBench, 42 tasks on real hardware. Human-expert skills give 42/42 (Arduino), while LLM-generated skills are inconsistent. **Justifies a curated compatibility KG.** |
| **DRCY: Agentic Hardware Design Reviews**, Dumont et al. (AllSpice) [arXiv:2603.15672](https://arxiv.org/html/2603.15672) | 2026 | Production multi-agent pin-by-pin datasheet checks with multi-run consensus. **Industry precedent for our checker + judge design.** |
| **pcbGPT**, King et al. (KIT) [arXiv:2606.01188](https://arxiv.org/pdf/2606.01188) | 2026 | NL→KiCad schematics with embedding + lexical component search and vision datasheet summaries. pass@1 0.90. Failures are missing support components (59.1%) and wrong interface connections (40.0%). |
| **SchGen**, Luo et al. [alphaxiv 2605.30345](https://alphaxiv.org/abs/2605.30345) | 2026 | Semantic code representation for schematics. A 20B model beats bigger generalists (60.5% functional correctness). **Representation matters.** |
| **LLM workflows for SMPS design**, Nau et al. [arXiv:2507.10639](https://arxiv.org/abs/2507.10639) | 2025 | Simulation feedback plus reasoning lifts solve rate from 15% to 91% on 269 tasks. **Tool feedback loops work.** |
| **D2S-FLOW** [arXiv:2502.16540](https://arxiv.org/abs/2502.16540v2) | 2025 | Datasheet parameter extraction EM 0.86 / F1 0.92 with name normalization. |
| **DocEDA**, Chen et al. [arXiv:2412.05301](https://arxiv.org/abs/2412.05301) | 2024 | Datasheet layout analysis + CoT extraction into a component DB; 90.5% image-to-circuit accuracy. |
| **LLM4-IC8K / ICGeo8K**, Wang et al. [arXiv:2508.03725](https://arxiv.org/abs/2508.03725) | 2025 | LMMs have poor geometric perception on IC footprints. **Don't trust vision for pin geometry.** |
| **Exploring LLMs for Embedded System Development**, Englhardt et al. [arXiv:2307.03817](https://arxiv.org/abs/2307.03817v2) | 2023 | GPT-4 gives functional I2C interfaces 66% of the time. A human-AI workflow raised sensor-build success from 25% to 100%. |
| **Language Models for Electronic Circuit Design from Textual Descriptions** (Pins100 / Micro25) [arXiv:2305.14874](https://arxiv.org/abs/2305.14874) | 2023 (EMNLP Findings, "From Words to Wires") | 60–96% pass@1 on microcontroller circuit + Arduino tasks. Early evidence that LLMs know component pinouts. |
| **ElectroCom61** dataset, Sayeedi et al. [Data in Brief 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11847280) | 2025 | 61-class electronic component detection, YOLOv9s 95.9% mAP@50. Good for class-level cross-checks. |

**Deck narrative**: "Benchmarks show LLMs write embedded code well but fail on physical pin/voltage reasoning (PCEval, EmbedBench). Production systems solve this with datasheet-grounded, multi-run checks (DRCY) and curated expert knowledge (IoT-SkillsBench). Bharat Sourcer applies the same recipe to the India sourcing problem."

---

## 8. Hackathon-scoped build plan for this layer

1. **Day 1–2**: KG seed (150 modules, 40 chips, 30 libraries) as Firestore JSON; rules engine (8 global rules + per-category rules) as pure Python with unit tests from the 13 cases above.
2. **Day 3**: extraction agents (page, code, description, video) with the `BomItem` schema; fusion and conflict detection.
3. **Day 4**: listing scraper/verifier for 3 to 4 Indian stores (respect robots.txt and ToS; cache aggressively); `Listing` table.
4. **Day 5**: compatibility agent + ImpactReport + code-diff generation + Cloud Run compile job (arduino-cli with esp32/esp8266/avr cores pre-installed).
5. **Day 6**: judge + confidence calibration; eval set run with `adk eval`; reliability chart for the deck.
6. **Demo**: paste the Sous-viduino link. The BOM appears with frame thumbnails and evidence chips. PowerSwitch Tail gets a red **MAINS** banner and a 230 V alternative. The Feather HUZZAH → NodeMCU swap shows a compiled diff. The BME280 shows the "verify on arrival: read 0xD0 = 0x60" card.

---

## 9. Sources opened for this report

- Nexar similarParts: https://support.nexar.com/support/solutions/articles/101000434631-supply-similar-parts
- Nexar query examples: https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples
- Nexar plans: https://nexar.com/compare-plans
- Octopart Similar Parts: https://resources.altium.com/p/similar-parts-automated-part-discovery
- Z2Data Advanced Cross Search: https://www.z2data.com/products/part-risk-manager/features/advanced-cross-search
- Z2Data cross-reference guide: https://www.z2data.com/guides/the-ultimate-guide-to-cross-references/
- Pololu DRV8825: https://www.pololu.com/product/2133
- A4988→TMC2209 forum: https://forum.arduino.cc/t/exchanging-a4988-for-tmc2209/870682
- Probots MKS TMC2209: https://probots.co.in/mks-tmc2209-v2-stepper-motor-driver-uart-module.html
- Espressif hc_sr04 component: https://components.espressif.com/components/phlangone/hc_sr04/versions/2.0.0/readme
- Adafruit NeoPixel level shifting: https://learn.adafruit.com/neopixel-levelshifter.md
- STEMMA/Qwiic/Grove comparison: https://www.tomshardware.com/features/stemma-vs-qwiic-vs-grove-connectors
- Fake sensors: https://www.atomic14.com/esp32/sensors/fake-sensors/ ; https://www.atomic14.com/esp32/sensors/bme280/
- Adafruit BME280/BMP280/SH110x headers & properties: https://github.com/adafruit/Adafruit_BME280_Library/blob/master/Adafruit_BME280.h , https://github.com/adafruit/Adafruit_BME280_Library/blob/master/library.properties , https://github.com/adafruit/Adafruit_BMP280_Library/blob/master/Adafruit_BMP280.h , https://github.com/adafruit/Adafruit_SH110x
- Arduino library spec: https://arduino.github.io/arduino-cli/1.0/library-specification/
- PlatformIO LDF: https://docs.platformio.org/en/latest/librarymanager/ldf.html ; pkg search: https://docs.platformio.org/en/latest/core/userguide/pkg/cmd_search.html
- KiCad CLI: https://docs.kicad.org/9.0/en/cli/cli.html
- Nano clone upload issues: https://www.universal-solder.ca/troubleshooting-arduino-failed-upload/
- India mains: https://www.worldstandards.eu/electricity/plug-voltage-by-country/india/
- Gemini video understanding: https://ai.google.dev/gemini-api/docs/video-understanding?authuser=9
- Gemini grounding: https://ai.google.dev/gemini-api/docs/google-search
- ADK eval criteria: https://adk.dev/evaluate/criteria/index.md
- Altium datasheet extractor: https://resources.altium.com/p/building-local-llm-datasheet-extractor-ic-driver-development
- Papers: listed in section 7; ElectroCom61: https://pmc.ncbi.nlm.nih.gov/articles/PMC11847280
- Eval projects: listed in section 6.1
