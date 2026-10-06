# Safety flags (M13)

`job.safety_flags` lists hazards found by **hard-coded deterministic rules**
(`backend/src/bharat_sourcer/safety.py`). No model writes, removes or rephrases a flag.
The text is templated. Flags are advice derived from the saved BOM and project text.
They are not verified seller facts and not a statement that a build is safe.

## When they are computed

| Moment | Function |
| --- | --- |
| Extraction finishes (`awaiting_confirmation`) | `JobService.extract` |
| Draft edits: confirmation and accepted chat proposals | `JobService.edit_draft` |
| Spec/requirement updates on a completed report | `JobService.apply_spec_updates` (when something changed) |
| Project title/description edits | `JobService.update_project` |

The BOM review stage already sees them. Jobs saved before this field existed load with
`safety_flags: []` until one of those events runs again. Demo jobs run the same rules on
their fixed demo BOM, which raises no flag.

## Shape

```json
{
  "code": "MAINS",
  "severity": "danger",
  "title": "230 V mains: read before building",
  "message": "This project may connect to or switch mains power. ...",
  "guidance": ["A part here is a US 120 V / 60 Hz product. ...", "India's mains is 230 V / 50 Hz. ..."],
  "line_ids": ["L02", "L04"],
  "triggers": [{"line_id": "L02", "field": "raw_name", "matched": "PowerSwitch Tail"}],
  "method": "deterministic_rules",
  "rule_version": "safety-rules-1"
}
```

- `code`: `MAINS | LIPO | HIGH_CURRENT | LEVEL_SHIFT`. There is at most one flag per code,
  always in that order.
- `severity` is fixed per code: MAINS `danger`, LIPO `warning`, HIGH_CURRENT `warning`,
  LEVEL_SHIFT `caution`.
- `line_ids`: the BOM lines involved, in BOM order. This can be empty when only the project
  understanding triggered the flag, for example `project.power: "2x 18650 cells"`.
- `triggers` (max 20): the saved text that matched. `field` is one of `raw_name`,
  `specs.family`, `specs.logic_v`, `specs.supply_min_v`, `specs.supply_max_v`,
  `requirements[i]`, `requirements[i].reason`, `evidence[i].observation`, `evidence[i].quote`,
  or `project.<title|description|summary|power|controller|interfaces[i]|assumptions[i]>`.
- Owned lines (`user_has_it`) are still checked, because a hazard applies whether or not
  you buy the part.

## Rules

Matching is case-insensitive keyword/regex matching plus voltages and currents parsed from
names, requirements (`name value unit`, plus `reason`) and specs.

**MAINS**
- Mains parts and loads: "mains", PowerSwitch Tail, IoT Relay, SSR / solid-state relay,
  triac/MOC30xx/zero-cross, contactor, MCB/RCCB, HLK-PM / Hi-Link, AC-DC modules, bare SMPS,
  switching power supplies, power cords, extension boards, wall sockets, appliances (rice
  cooker, kettle, geyser, heaters), bulbs/E27/B22, ceiling and table fans, mains/step-down
  transformers, 50/60 Hz, plug tops (Type A/B/D/G/M, 3-pin).
- Any voltage of 100–400 V that is not labelled DC (for example `230V`, `250VAC`, a
  requirement `250 V AC`).
- **US 120 V parts** (worked Case 2): PowerSwitch Tail, IoT Relay, NEMA 1-15/5-15, Type A/B
  plugs, "US plug/version", 60 Hz, or 100–130 V with no 200+ V option. These add a first
  guidance line: do not use in India; replace with a 230 V-rated part or a certified smart plug.
- A **relay with a 5 V coil is not mains by itself**. Relay lines are added to MAINS only
  when MAINS already fired, or the project or another line mentions an AC-type load (lights,
  lamps, bulbs, fans, appliances, home automation, smart switch/plug, sockets, heaters,
  cookers, TV/AC). Hint text stating DC or a voltage ≤ 60 V ("12V DC fan") does not count.
- Sealed plug-in adapters/chargers/power banks only flag when US-only. A
  "12V 2A adapter 100-240V Type D plug" (worked Case 12) raises nothing. Project prose
  that mentions an adapter does not flag on its voltage range.
- Guidance: 230 V / 50 Hz, ≥ 250 V AC rating; Type D (6 A) / Type M (16 A) plugs; enclosure,
  strain relief, fuse, earth, no exposed 230 V; 230 V-rated relay module or SSR with 2× current
  margin; a certified smart plug where possible; electrician review. `user_level: beginner`
  also gets a "consider a low-voltage version" line.

**LIPO**
- Lithium cells: LiPo, Li-ion, lithium polymer/ion, LiFePO4, 18650/21700/26650/14500/16340/
  18350, LIR coin cells, "1S–6S" packs, 3.7 V cells. Power banks are ignored.
- The flag is dropped only when the **BOM** shows both protection and a charger. Protection
  means a battery, charger or BMS line saying protected/protection/BMS/PCM/DW01/8205. A charger
  means TP40xx, MCP738xx, IP5306, BQ2xxx, CN3065 or "charger/charging". So "Li-ion 18650 with
  protection" plus "TP4056 with protection" raises nothing. The cell alone still flags (no
  charger), and a plain TP4056 flags (no protection). AI project prose is never accepted as
  protection evidence. The message names the missing safeguard.

**HIGH_CURRENT**
- LED strips/tape/matrices always. Addressable LEDs (WS2812/WS2811/SK6812/APA102/NeoPixel)
  flag when the LED count is unknown (ring, stick, matrix) or the rule estimate is ≥ 1 A, at
  60 mA per LED at full white. The count comes from "N LEDs", density × length
  ("60 LED/m 5 m"), or qty for single pixels. The estimate goes in `message` as
  "Rule estimate, not measured" (Case 8: 74 LEDs ≈ 4.44 A).
- Motors, steppers/NEMA, servos, BLDC/ESC, solenoids, pumps, Peltier, electromagnets,
  heaters, high-power LEDs, motor drivers (L298N, TB6612, DRV88xx, A4988, TMC2xxx, BTS7960,
  ULN2003), lead-acid/car batteries. Coin/vibration/haptic motors are excluded.
- Any stated current above 3 A, or watts ÷ a stated DC voltage above 3 A ("12V 60W"). Relay
  and SSR lines are skipped here because "10A" is a contact rating. A "3A" cable does not flag.

**LEVEL_SHIFT**
- 3.3 V controllers: ESP32*, ESP8266/NodeMCU/Wemos/ESP-01, RP2040/RP2350/Pico, Raspberry Pi,
  STM32, Nano 33, Due/MKR/Zero/GIGA, Teensy 3.2+/4, nRF52, XIAO, Feather, micro:bit, or
  `specs.logic_v: 3.3` / "3.3V"/"8MHz" on Pro Micro/Pro Mini. 5 V controllers: Uno, Mega,
  Nano, Leonardo, Micro, ATmega328/2560/32u4, Pro Mini/Micro, Digispark/ATtiny85.
- 5 V parts: addressable LEDs, HC-SR04 (not HC-SR04P), LCD1602/2004/16x2/20x4, PCF8574,
  MAX7219, MQ-x gas sensors, "5V logic/only". 3.3 V-only parts: nRF24L01, RC522, SX127x/
  RA-01/LoRa, HC-05/06, "3.3V only", BME/BMP280-3.3. For other logic parts, specs (`logic_v`,
  `supply_max_v ≤ 3.6`, `supply_min_v ≥ 4.5`) and voltage requirements are also read.
  Power, passive, motor and battery lines are not classified this way (an LED's forward
  voltage is not logic).
- Fires when a controller in one domain meets any part or controller in the other.
  Controllers and parts named in project text count too. A listed level shifter does not
  clear the flag; the message names it and asks to route every mixed signal through it.

## Deliberately conservative (known false positives)

- Relay listings with an AC contact rating ("10A 250VAC") raise MAINS even if the project
  switches DC.
- Unlabelled 100–400 V values raise MAINS, including high-voltage DC such as nixie boost
  converters. No separate HIGH_VOLTAGE_DC code exists yet.
- A relay plus "lights"/"fans"/"sockets" text without a DC label raises MAINS.
- Evidence and requirement-reason text is scanned too, so a passing mention can flag a line.
- Any servo or pump raises HIGH_CURRENT.

## Not covered

HEAT, LASER and 60 Hz-specific parts (doc 10 §1.2), compatibility grades (X for US mains
parts) and fix suggestions with resistor values. Spoken or translated banners are not
implemented either.

## Chat

The assistant context includes `safety_flags`. The prompt tells the model to repeat their
guidance when relevant and never to dismiss or soften a flag.

## Frontend

- Render one banner per flag **above the BOM** on the review page and on the report.
  Order is MAINS, LIPO, HIGH_CURRENT, LEVEL_SHIFT. Colours: `danger` red, `warning` amber,
  `caution` yellow/blue.
- Show `title` and `message` and expand `guidance` as a checklist. Render the text verbatim.
  Do not hide a MAINS banner behind a collapsed state.
- Highlight `line_ids` rows with a small badge for the code. Optionally show `triggers` as
  "why this flag" (field + matched text).
- Label the banners as automatic rule checks: "Automatic safety check, not a guarantee".
- Flags update after confirmation, chat-accepted edits, spec updates and project edits, so
  re-read them from each job snapshot.
