# Evaluation plan

> **In one minute.** We build 15 real projects with hand-made **gold BOMs** and gold substitution verdicts. On that set we measure:
> - extraction recall and precision
> - grade accuracy
> - safety-flag recall (must be 100%)
> - compile pass rate
> - link validity
> - hallucinated-URL rate (target 0)
>
> Everything runs through `adk eval` plus a pytest metrics script in CI. The numbers go into the deck and the video ("91% part recall on 15 projects" — only if true).

Research: [research/03 §6](../../research/03-compatibility-intelligence.md).

---

## 1. Eval set (15 projects)

All URLs were opened on 30 Sep 2026, except where noted.

| # | Project | Creator | URL | What it tests |
|---|---|---|---|---|
| 1 | Pi Hole Ad Blocker with Pi Zero W | Adafruit (US) | https://learn.adafruit.com/pi-hole-ad-blocker-with-pi-zero-w | Pi HAT → generic module rewire (Case 10) |
| 2 | MagTag Daily Weather | Adafruit (US) | https://learn.adafruit.com/magtag-weather.md?view=all | Unavailable all-in-one → import vs redesign (Case 13) |
| 3 | Adafruit IO Environmental Monitor | Adafruit (US) | https://learn.adafruit.com/adafruit-io-air-quality-monitor | BME280, SGP30, LiPo, Feather (Cases 1, 5) |
| 4 | PyPortal Weather Station | Adafruit (US) | https://learn.adafruit.com/pyportal-weather-station | Proprietary display board, 5 V 2 A PSU |
| 5 | Sous-viduino | Adafruit (US) | https://learn.adafruit.com/sous-vide-powered-by-arduino-the-sous-viduino | **Mains 120 → 230 V** (Case 2), safety gate |
| 6 | Cheerlights Holiday Wreath | Adafruit (US) | https://learn.adafruit.com/cheerlights-led-animations.md?view=all | NeoPixel + MagTag |
| 7 | NeoPixel level shifting | Adafruit (US) | https://learn.adafruit.com/neopixel-levelshifter.md | Level-shift rule |
| 8 | HC-SR04 with Arduino | DroneBot Workshop (CA) | https://dronebotworkshop.com/hc-sr04-ultrasonic-distance-sensor-arduino/ | Parts list "coming soon", so parts must come from prose and video |
| 9 | Stepper motors with Arduino | DroneBot Workshop | https://dronebotworkshop.com/stepper-motors-with-arduino/ | A4988 / L298N / ULN2003 (Cases 3, 4) |
| 10 | 8-bit breadboard computer | Ben Eater (US) | https://eater.net/8bit/parts | ~30 74LS ICs: quantities, 74LS vs 74HC |
| 11 | Infinity mirror wall clock | Hackster | https://www.hackster.io/rundhall/infinity-mirror-wall-clock-in-ikea-picture-frame-700125 | WS2812B + NodeMCU, PSU current math (Case 8) |
| 12 | ESP32 BME280 web server | Random Nerd Tutorials (PT) | https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/ | Address 0x76 issue |
| 13 | ESP32 + HC-SR04 | Random Nerd Tutorials | https://randomnerdtutorials.com/esp32-hc-sr04-ultrasonic-arduino/ | Conflicting safety advice (Case 7) |
| 14 | Plant Watering System | Instructables | https://www.instructables.com/Plant-Watering-System/ | Pump, relay, moisture sensor. ⚠️ Supplies list didn't render; verify manually |
| 15 | *(pick)* a GreatScott! build with a video | GreatScott! (DE, English) | https://www.instructables.com/member/GreatScottLab/ | Video-first extraction. ⚠️ Choose on day 2 |

**Add video-heavy cases.** At least 5 of the 15 must be YouTube-first (the video is the primary source), e.g. DroneBot, GreatScott!, Andreas Spiess, a UK creator such as James Bruton or a Pimoroni/The Pi Hut guide. Record each channel's video URL in `eval/projects.yaml`.

## 2. Gold file format

```json
{
  "project_id": "adafruit-sousviduino",
  "inputs": {"url": "https://learn.adafruit.com/sous-vide-powered-by-arduino-the-sous-viduino"},
  "gold_bom": [
    {"canonical_chip": "ATmega328P", "module": "Adafruit Metro 328", "qty": 1, "category": "mcu_board"},
    {"canonical_chip": "DS18B20", "module": "waterproof probe", "qty": 1, "category": "sensor"},
    {"module": "PowerSwitch Tail II", "qty": 1, "category": "mains_switching"}
  ],
  "gold_substitutions": [
    {"original": "PowerSwitch Tail II",
     "acceptable": ["SSR-25DA in enclosure", "230V relay module (enclosed)", "certified smart plug"],
     "required_changes": ["230V rated", "Type D/M plug", "enclosure", "relay polarity check"],
     "grade_range": ["C", "X"]}
  ],
  "must_flag": ["MAINS"],
  "notes": "Rice cooker must be a 230 V Indian model."
}
```

The gold files are written by two team members independently. Differences are resolved by discussion, and agreement is reported (Cohen's κ on grades).

## 3. Metrics

| Stage | Metric | Definition | Target (MVP) |
|---|---|---|---|
| Extraction | Part recall | gold parts found (canonical chip/module match) / gold parts | ≥ 0.85 |
| Extraction | Part precision | correct parts / parts returned | ≥ 0.85 |
| Extraction | Qty accuracy | exact for ICs, ±10% for lengths | ≥ 0.8 |
| Extraction | Evidence validity | locator actually contains the quote (automatic for text, spot-check for timestamps) | ≥ 0.9 |
| Resolution | Canonicalisation accuracy | raw → correct KG id | ≥ 0.9 |
| Sourcing | India coverage | lines with ≥ 1 verified Indian listing / lines | report |
| Sourcing | **Link validity** | HTTP 200 + title match + INR price at eval time | ≥ 0.95 |
| Sourcing | **Hallucinated URL rate** | URLs shown that aren't in `listings` | **0** |
| Compatibility | Grade accuracy | exact / within one grade | ≥ 0.7 / ≥ 0.9 |
| Compatibility | Required-change recall | gold `required_changes` mentioned (LLM judge + rubric) | ≥ 0.8 |
| Compatibility | **Safety-flag recall** | MAINS/LIPO flagged when gold says so | **1.0 (gate)** |
| Code | Compile pass@1 / pass@3 | diff compiles for target | report |
| Cost | Median savings vs import | across projects | report |
| System | p50 / p95 job time | wall clock | < 3 min / < 6 min |
| System | Cost per job | tokens + grounding | < $1 |
| Judge | Agreement with human | Cohen's κ on 30 sampled grades | report |
| Confidence | Calibration | reliability plot (bucketed) | deck chart |

## 4. `adk eval` configuration

`eval/test_config.json`:

```json
{
  "criteria": {
    "tool_trajectory_avg_score": {"threshold": 0.8, "match_type": "IN_ORDER"},
    "rubric_based_final_response_quality_v1": {
      "threshold": 0.8,
      "judge_model_options": {"judge_model": "gemini-3.8-flash", "num_samples": 3},
      "rubrics": [
        {"rubric_id": "voltage_addressed", "rubric_content": {"text_property": "For every substitute, the response states supply voltage and logic level and flags any 3.3V/5V mismatch with a concrete fix."}},
        {"rubric_id": "code_impact", "rubric_content": {"text_property": "If the chip or board changed, the response names the library/board-target change and shows a code diff."}},
        {"rubric_id": "mains_safety", "rubric_content": {"text_property": "If any part switches AC mains, the response flags 230V/50Hz, Indian plug types and enclosure/safety requirements."}},
        {"rubric_id": "grade_justified", "rubric_content": {"text_property": "Each A/B/C/D/X grade is justified by at least one specific wiring, power, code, or spec difference."}}
      ]
    },
    "hallucinations_v1": {"threshold": 0.85, "judge_model_options": {"judge_model": "gemini-3.8-flash"}},
    "safety_v1": 0.9
  }
}
```

The expected tool trajectory (`IN_ORDER`) is: `fetch_sources → extract_bom → resolve_parts → search_listings → verify_listings → check_compatibility → generate_code_diff → cost`.

Run it with:

```bash
adk eval backend/agents eval/evalsets/core.evalset.json --config_file_path eval/test_config.json
pytest eval/test_metrics.py --report eval/out/metrics.json   # recall/precision/grade/link/hallucinated-url/compile
```

## 5. Unit tests for the rules engine

Each of the 13 worked cases ([../04-reference/01-worked-substitution-cases.md](../04-reference/01-worked-substitution-cases.md)) becomes a pytest with fixed input specs and the expected grade plus findings. These tests don't call any LLM, so they run in under 1 s in CI.

## 6. Cadence

| When | What |
|---|---|
| Day 3 | Gold BOMs for 8 projects ready |
| Day 5 | First extraction-only eval → fix prompts |
| Day 9 | Full pipeline eval on 8 projects |
| Day 12 | Full 15-project eval; freeze prompts except bug fixes |
| Day 14 | Final numbers + reliability chart for the deck |
| Every PR | Smoke eval on 3 fixtures (offline recorded responses) |

## 7. Reporting in the deck

A single slide shows:

- a small table: recall, precision, grade accuracy, safety recall, link validity, hallucinated URLs, median savings
- the reliability plot
- one sentence on methodology ("15 real US/UK projects, gold BOMs made by two people independently")

**Never** round up or cherry-pick. Judges value auditability.
