# Compatibility rules: part catalogue, resolver and A–X grades

Status: released in v0.20.0; included in v0.27.0. Everything here is
deterministic Python. No model is called, and nothing here is a verified seller fact.

## 1. Curated part catalogue (M5 knowledge graph, static)

`backend/src/bharat_sourcer/data/parts_catalog.json` holds about 150 common maker parts:
dev boards, sensors, displays, motor drivers, actuators, addressable LEDs, relays and mains
switches, power modules, comms modules, cables and a few passives. It ships as package
data and is loaded and validated once per process (`catalog.load_catalog()`).

Each entry has `id`, `name`, `category`, `chip`, `aliases`, optional shared `generic`
terms, and only the facts that apply, for example `supply_v`, `logic_v` or
`logic_follows_supply`, `io_5v_tolerant`, `input_3v3_ok`, `output_signals`, `interfaces`,
`i2c_addresses` (the default first), `pins`, `connector`, `measures`, `ranges`, `steps`,
`display_controller`, `display_resolution`, `current_a`, `motor_supply_v`,
`control_interface`, `output_v`, `input_vac`, `plug`, `barrel`, `polarity`, `mains`,
`mains_rating_vac`, `enclosed`, `active_level`, `control_v`, `protocol`, `ma_per_led`,
`features`, `board_target`, `usb_serial`, `bootloader`, `pin_labels`, `strapping_pins`,
`input_only_pins`, `rails_v`, `libraries`, `lookalikes`, `verify`, curated `substitutes`
(edges with a grade and change list), `notes`, `source` and `verified`.

Rules for the data:

- **Every entry has `verified: false`.** Values were curated from datasheets and vendor
  guides but have not been checked one by one against the cited `source`. A maintainer
  must check them before setting `verified: true`; the loader rejects `verified` without
  `source`.
- Values describe a *typical* module. Clones differ, so header pin order is only listed
  where it is standard (for example HC-SR04). OLED pin order is deliberately left out.
- `mains: true` marks parts that switch or take mains power (relay modules, SSRs,
  PowerSwitch Tail, Sonoff, HLK-PM01). The safety banners are a separate stream and can
  read this flag.
- The loader rejects duplicate ids, aliases shared by two entries, dangling `lookalikes`
  and `substitutes` references, unordered ranges, bad I2C addresses, sensors without
  `measures` and mains flags outside the relay/power categories (`tests/test_catalog.py`).

## 2. Resolver (raw BOM name → catalogue entry)

`catalog.resolve_name(name)` normalises the name: lower case, `×` becomes `x`, and
`0.96"` or `0.96 inch` become `0.96in`. Hyphen and space variants match the same way, so
`HC-SR04`, `HC SR04` and `HCSR04` are all one part, while `HC-SR04P` stays distinct.
An alias matches when its spelling equals adjacent name tokens, or when its tokens appear
in order with at most two unrelated tokens between them.

Outcomes:

| `status` | Meaning |
|---|---|
| `matched` | One entry explains the name. `confidence` (0–1) falls as the name gains unexplained words |
| `ambiguous` | Only shared terms matched (`BME280`, `OLED`, `Pro Micro`), or the name mentions two parts (`SSD1306 SH1106 OLED`). `candidates[]` lists up to six; nothing is guessed |
| `unmatched` | No alias matched; the original behaviour applies |

`resolve_part` (used for every BOM line) now adds `resolution.catalog`
(`CatalogMatch`):

```json
{"status": "matched", "id": "ds18b20", "name": "DS18B20 temperature sensor",
 "category": "sensor", "chip": "ds18b20", "confidence": 1.0, "candidates": [],
 "facts": {"supply_v": "3–5.5", "interfaces": "one_wire", "measures": "temperature"},
 "requirements": [{"name": "supply voltage", "value": "3–5.5", "unit": "V",
   "origin": "inferred", "reason": "Curated catalogue reference for … not verified …"}],
 "lookalikes": [], "verify": null, "notes": null,
 "source_url": "https://…", "verified": false, "origin": "curated_catalog"}
```

- For the original typed families (`pro_micro`, `oled`, `ttp223`, `usb_cable`) a matched
  entry pre-fills `resolution.specs`. Each such value has a `SpecEvidence` with the new
  source `"catalog"` and locator `catalog:<id>`. Values from the user and from the part
  name always win. If they contradict the catalogue, the catalogue values are dropped.
- `catalog.requirements` are reference values only. They are **not** copied into
  `items[].requirements`, so they never gate selection.
- A matched part no longer gets the generic "What must this part do…?" clarification.
- An ambiguous match pre-fills nothing, so the existing clarifications still ask.

## 3. Rules engine (M8)

`compat_rules.evaluate(required, offered, context)` compares facts about the BOM's
original part (catalogue entry plus the user's and the name's specs) with facts about an
offer. Each fact carries its source.

**Offered-side rule:** catalogue values that the resolver attached to an offer, from its
listing title, are labelled `catalog`. They can raise findings, which can lower a grade,
but they never count as known. Only seller-declared (`seller`, `seller_title`) or user
values can support an A or B. Unknown specifications block positive grades.

Context (`compat.project_context`) comes from `job.project` (AI-inferred, labelled):

- the controller is resolved through the catalogue for logic level, 5 V tolerance,
  rails, strapping and input-only pins;
- voltages in the power text become extra rails, and battery words set `uses_battery`;
- other BOM lines give the I2C addresses already in use;
- the line's requirements can give motor voltage or current, load current, temperature
  range or resolution, and LED count.

Rules (the finding's `rule`, with its grade floor):

| Rule | Fires when | Floor |
|---|---|---|
| `identity` | Category differs | X |
| `curated_substitute` | A catalogue edge exists (A4988→DRV8825 B, A4988→TMC2209 C, SSD1306→SH1106 B, DHT22→DHT11 D) | edge grade |
| `board_chip` / `chip` | Different MCU / different chip with no category rule | D |
| `interface` | Primary bus missing but another is shared / no common bus | C / X |
| `supply_range` | Rail outside the supply range but another project rail fits / none fits | C / X |
| `supply_rail` | A supply-following module can run from the controller rail (advice) | A |
| `logic_level` | 5 V output into a non-tolerant 3.3 V input; 3.3 V module on 5 V; 3.3 V data into 5 V input (A if the original design had the same limit) | C |
| `i2c_address` | Default address differs (jumper or code change) | B |
| `i2c_collision` | New default address is used by another BOM part | C |
| `connector` | STEMMA QT/Qwiic/Grove → header (B); HAT → jumpers (C); Feather form factor (A, advice); other (C) | B / C |
| `header_order` | Same pins, different order (VCC/GND warning) or different pins | C |
| `measured_superset` | Offer loses a measured quantity / the project uses it | D / X |
| `measured_range`, `measured_resolution` | Narrower or coarser than the original / than a stated need | D / X |
| `library_change` | Different sensor chip with no shared library | B |
| `display_controller` | Controller differs without a curated edge | B |
| `display_resolution` | Resolution differs | D |
| `control_interface` | STEP/DIR vs PWM/DIR etc. | D |
| `driver_chip` | Different driver chip without an edge | C |
| `driver_current` | Below the original (confirm) / below the stated motor current | C / X |
| `motor_supply` | Narrower range (confirm) / stated motor voltage out of range | C / X |
| `mains_rating` | Rated below max(250, 230 + 20) VAC | X |
| `mains_enclosure` | Bare module replaces an enclosed product | C |
| `polarity` | Active-LOW vs active-HIGH control or output | B |
| `control_voltage` | Controller logic outside the SSR control range | C |
| `output_voltage`, `output_current` | Wrong output voltage / lower or insufficient current | X / C / X |
| `mains_input` | Adapter input range excludes 230 VAC | X |
| `plug`, `barrel`, `polarity` (barrel) | US plug / barrel size mismatch / reversed polarity | C / C / X |
| `battery_protection`, `battery_charger` | Lost DW01 protection / no LiPo charger and the project uses a battery | C |
| `board_logic`, `board_clock`, `board_target`, `usb_driver`, `bootloader`, `pin_labels` | Board-level config changes | C / B |
| `board_feature` | Board loses a feature the project uses | X |
| `pin_function` | The project's controller differs from the source project's | B |
| `led_protocol`, `current_headroom` | RGB↔RGBW (B), APA102 clock line (C); PSU too small (A if pre-existing, else C) | B / C |
| `output_mode`, `connector_a/b`, `usb_data` | Original typed-family mismatches | X |
| `lookalike_risk` | Look-alikes exist; adds a verify-on-arrival test | A |

**Overall grade.** The overall grade is the worst finding grade. If any needed fact is
missing and that worst grade is A or B, the grade is `null` (status `unknown`). A C, D or
X grade is kept even when facts are missing, because a known problem stays visible. In
that case `reasons` adds "Other specifications are unknown, so the grade may be worse".
Grade A findings are advice only.

| Grade | `grade_label` | Meaning | `status` |
|---|---|---|---|
| A | Works as is | Drop-in for the declared facts | `compatible` |
| B | Works with a small setting change | Address, library, board target, polarity, driver | `changes_required` |
| C | Works with wiring or power changes | Rewire, level shifter, another rail, enclosure, adapter | `changes_required` |
| D | Different part, similar result | Functional alternative; code or behaviour changes | `changes_required` |
| X | Don't use | Unsafe or misses a hard requirement | `incompatible` |

All 13 worked cases in `docs/04-reference/01-worked-substitution-cases.md` are pytest
cases with fixed, labelled input facts (`tests/test_compat_rules.py`), including their
variants (5 V Uno and BMP280 for case 1, 36 V for case 3, battery use for case 5, swapped
header for case 6, HC-SR04P for case 7, freezer/decimal needs for case 11). One result
differs from that table on purpose: case 12 with a mismatched barrel is graded C (an
adapter or plug change), not B.

## 4. API changes (additive; stored jobs still load)

`report.lines[].offers[].compatibility` gains:

| Field | Type | Notes |
|---|---|---|
| `method` | `"declared_specs"` \| `"catalog_rules"` | `catalog_rules` when the BOM part matched the catalogue |
| `grade_label` | string \| null | Plain-language text for the grade |
| `findings[]` | `{rule, grade, area, message, change, basis[]}` | `area`: `wiring`, `code`, `power`, `safety`, `verify`; `basis` lists `side.field:source` (e.g. `offered.supply_v:catalog`) |
| `what_changes` | `{wiring[], code[], power[], safety[], verify[]}` \| null | Change texts grouped for the drawer, advice included |
| `required_catalog_id`, `offered_catalog_id` | string \| null | Catalogue ids used |

The existing fields keep their meaning. `grade` can now also be C or D. `changes` lists
the change texts from B–X findings, `missing_fields` uses the `required.`, `offered.` and
`context.` prefixes, and `references` lists catalogue sources plus the offer URL. Parts
the catalogue does not know keep the original comparison (`method: "declared_specs"`,
empty `findings`). The `SpecEvidence.source` enum gains `"catalog"`, and
`items`/`report.lines[].resolution` gains `catalog` (`CatalogMatch`, see §2).

Where grading runs: during sourcing (without project context), after `POST /specs`, and
once more when sourcing completes with `job.project` context. That last pass skips lines
that already have a selected offer, so an existing selection never changes grade.

Selection is unchanged. Only A and B are selectable through the compatibility path, and
B still needs `accept_changes`. C and D offers stay unselectable unless the existing
research-review path applies. That path requires status `unknown`, so C/D/X offers cannot
use it.

## 5. What the frontend should render

- **Grade chip** on each offer: icon plus text, never colour alone. Suggested pairs:
  A ✓ "Works as is" (green); B ⇄ "Small setting change" (teal); C ⚠ "Wiring or power
  changes" (amber); D ◐ "Different part, similar result" (orange); X ⛔ "Don't use" (red).
  With no grade (`null`), show "Not enough information" and list `missing_fields` in
  plain words.
- **"What changes" drawer** opened from the chip. Show `what_changes` grouped under Wiring,
  Code, Power, Safety and Verify on arrival. List the `findings` messages with their own
  small grade badge. Show `safety` items first and in bold.
- **Labelling.** When `method` is `catalog_rules`, show "Checked by rules against a
  curated catalogue (unverified reference data) and the seller's declared specs". Never
  call the grade verified. A `basis` item that ends in `:catalog` should read "typical
  module value, not stated by this seller".
- **Catalogue match on the BOM line** (`resolution.catalog`). When matched, show
  "Recognised as <name>", with the facts table on expand and the `verify` text as a
  check-on-arrival note. When ambiguous, show "Which one is it?" with the candidate names;
  the user picks one by editing the part name. `requirements` can be offered as
  "Suggested requirements (catalogue reference)" for the user to adopt.

## 6. Limits

- Catalogue facts are unverified. Positive grades still need seller- or user-declared
  facts, which sellers rarely give beyond the typed `PartSpecs` fields. In practice most
  live offers stay `null` or get a C/D/X warning with "what changes".
- Offered-side facts come only from `PartSpecs` (seller title, JSON-LD and spec tables)
  and the title match; richer seller facts (ranges, features) are not extracted yet.
- Project context is the AI's reading of the source and is not verified. The
  `source_controller` (case 7: original project's board vs the user's) is not
  populated by the pipeline yet; only tests exercise `pin_function`.
- No code-impact diff, compile check or LLM explanation (M9) is produced, and no I2C
  collision check runs across project parts beyond default addresses.
