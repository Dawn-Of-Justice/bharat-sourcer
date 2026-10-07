# Evaluation gold set

> **Status (7 October 2026): agent draft, not human gold.** `backend/evaluation/gold/`
> holds 14 text projects transcribed by an AI agent from their public pages on
> 6 October 2026 (`agent_draft_needs_human_review`), plus 5 candidate YouTube videos with
> empty BOMs (`needs_human_labelling`). No file has been reviewed by a person. **No accuracy
> figure may be quoted from this set**; the harness prints an "UNREVIEWED LABELS" warning
> and won't produce an accuracy headline until every scored file is `human_reviewed`.

The set follows the [evaluation plan](../03-delivery/02-evaluation-plan.md) (15 projects,
section 2 gold format, section 3 metrics). The scoring rules are described in the harness
section of [`backend/README.md`](../../backend/README.md#extraction-quality-evaluation).

## Files

| File | Contents |
| --- | --- |
| `index.json` | Manifest: `description`, set-level `label_status`, `drafted_by`, `drafted_on`, and one entry per project (`project_id`, `file`, `plan_row`, `kind`, `label_status`). Entries must agree with their files. |
| `<project_id>.json` | One project in the gold format below. |

Each project file:

| Field | Meaning |
| --- | --- |
| `project_id`, `plan_row`, `title`, `creator` | Identity; `plan_row` is the row in the plan's table (null for extra video candidates). |
| `kind` | `text` (project page is the primary source) or `video` (YouTube-first). |
| `label_status` | `needs_human_labelling` (no labels yet; skipped by the harness), `agent_draft_needs_human_review` or `human_reviewed` (needs two names in `reviewed_by`). |
| `inputs.url`, `inputs.video_url` | The URL scored (YouTube for `video`); an optional companion video. |
| `source` | Provenance of the draft: fetched URL, `fetched_on`, HTTP status, robots.txt finding, method. |
| `gold_bom` | Parts: `name`, `aliases`, `qty` (`null` if unknown), `qty_unit` (`pcs`, or `mm`/`cm`/`m` for lengths scored within 10%), `canonical_chip`, `module`, `category`, `notes`. |
| `gold_substitutions` | `original`, `aliases`, `acceptable`, `required_changes`, inclusive `grade_range` (A < B < C < D < X), `case_ref` to [worked substitution cases](../04-reference/01-worked-substitution-cases.md), `notes`. |
| `must_flag` | Safety codes a correct run must raise: `MAINS`, `LIPO`, `HIGH_CURRENT`, `LEVEL_SHIFT`. |
| `notes`, `ambiguities` | What the drafter was unsure about. Reviewers resolve each one. |
| `drafted_by`, `reviewed_by` | Who drafted it; the independent reviewers. |

Draft conventions to keep or change during review:

- Only parts the build needs are listed: tools (soldering iron, 3D printer) are excluded;
  optional parts the guide builds are included with a note.
- Packs count as one line (e.g. "magnet feet, pack of 4" is qty 1).
- `HIGH_CURRENT` was used for motor drivers needing current tuning or LED loads of several
  amps; `LEVEL_SHIFT` for 5 V signals into 3.3 V parts or 3.3 V data into 5 V LEDs.
- A US wall adapter got a Case 12 substitution by analogy; those notes say so.

## Current status

| Row | Project | Status | Flags | Main open points |
| --- | --- | --- | --- | --- |
| 1 | `adafruit-pi-hole-zero-w` | draft | none | Optional OLED and headers; which PSU |
| 2 | `adafruit-magtag-weather` | draft | LIPO | Case 13 A/D expressed as range A-D |
| 3 | `adafruit-io-environmental-monitor` | draft | LIPO | VEML6070 wired but not on Parts page |
| 4 | `adafruit-pyportal-weather-station` | draft | none | Optional case parts |
| 5 | `adafruit-sousviduino` | draft | MAINS | Rice cooker as a line |
| 6 | `adafruit-cheerlights-wreath` | draft | none | Whether HIGH_CURRENT/LEVEL_SHIFT apply |
| 7 | `adafruit-neopixel-levelshifter` | draft | LEVEL_SHIFT, HIGH_CURRENT | No parts list; BOM inferred from prose |
| 8 | `dronebot-hc-sr04-arduino` | draft | none | Parts list "coming soon"; from prose only |
| 9 | `dronebot-stepper-motors-arduino` | draft | HIGH_CURRENT | Parts list "coming soon"; supply ratings |
| 10 | `ben-eater-8bit-computer` | draft | none | Table transcribed; no grade for 74LS vs 74HC |
| 11 | `hackster-infinity-mirror-clock` | draft | LEVEL_SHIFT, HIGH_CURRENT | 470 vs 450 uF; 60 of 74 LEDs used |
| 12 | `rnt-esp32-bme280-web-server` | draft | none | Grade range for GY-BME280 |
| 13 | `rnt-esp32-hc-sr04` | draft | LEVEL_SHIFT | OLED only in the second example |
| 14 | `instructables-plant-watering-system` | draft | none | Page is "Table-Top Electric Plant": no relay or sensor module, unlike the plan's summary |
| 15 | `video-greatscott-cocktail-machine` | needs labelling | | Candidate video |
| | `video-greatscott-diy-tachometer` | needs labelling | | Candidate video |
| | `video-spiess-cat-feeder` | needs labelling | | Two embedded videos; pick the primary |
| | `video-spiess-volt-ampere-meter` | needs labelling | | Candidate video |
| | `video-dronebot-hc-sr04` | needs labelling | | Video for row 8 |

The plan asks for at least 5 YouTube-first projects; the 5 candidates were taken from the
creators' Instructables pages (GreatScott!, Andreas Spiess) and DroneBot's article embeds.
The companion videos of rows 8, 9, 11 and 12 are recorded as `inputs.video_url`.

## Review workflow (human labellers)

1. **Two people label independently.** Each reviewer opens the source (page or video) and
   writes their own BOM, quantities, `must_flag` and substitution grades without looking at
   the other's work. The agent draft may serve as a checklist of candidate parts, but each
   reviewer must confirm every line against the source. For videos, record
   `evidence_windows` (`MM:SS`) where each part is shown or named.
2. **Measure agreement.** Before discussing, compute Cohen's κ on the substitution grades
   (and, if useful, on per-part presence and `must_flag` codes) across all reviewed
   projects. Record κ and the number of items in `notes` of `index.json`.
3. **Reconcile.** Resolve each difference and each listed `ambiguity` by discussion. Delete
   ambiguities that are settled; keep a short note for any judgement call.
4. **Promote.** Set the file's `label_status` and its index entry to `human_reviewed`, put
   both names in `reviewed_by`, and set `index.json`'s `label_status` to `human_reviewed`
   only when every scored file is reviewed. The loader enforces two reviewers and uses the
   weakest status in the set.
5. **Run the harness** on saved predictions:
   `python scripts/evaluate_extraction.py --cases evaluation/gold/index.json --predictions <dir>`.
   Only then may the deck quote the numbers, with the methodology sentence from the plan.

Don't edit a reviewed file without re-running steps 1–4 for that project.
