# Code patches for substituted parts (v0.28.0)

When a part is replaced by a catalogue substitute and the project's code is available
(GitHub projects whose code files were read as code evidence), the backend can produce
the code change for the substitute: a unified diff per file, a ZIP of patched files, and
the non-code changes (wiring, power, verification) as notes. Implements tiers 1–2 of
[docs/plans/code-adapt/PLAN.md](../plans/code-adapt/PLAN.md). Nothing is compiled or run.

## Labels (show them every time)

| Field | Values | Meaning |
| --- | --- | --- |
| `origin` | `curated` | A maintained recipe for this exact substitute and library. |
| | `ai_draft` | Model-written, then checked by rules; the owner must accept it. |
| `check` | `not_checked` | Always today: no compile runner exists. Show "Not compiled". |
| `status` | `ready` / `unavailable` | `unavailable` always has a `reason` and usually `detail`. |

Wiring, power and verification changes are never patched; they are listed in `notes`
(prefixed `Wiring:`, `Power:`, `Verify:`, or `Code (not patched):`). Always show notes,
even when `status` is `unavailable`.

## Create

`POST /v1/jobs/{job_id}/lines/{line_id}/code-patch` with `{"offer_url": "…"}` (optional;
defaults to the line's selected offer). Owner/job-token access as other job routes; counts
as one action. Returns `CodePatch` and stores it on `report.lines[].code_patch`
(replacing any earlier patch for the line).

`reason` values when `status: unavailable`:

| reason | Meaning / suggested UI |
| --- | --- |
| `no_substitute` | The offer is the same part, or not a catalogue substitute. |
| `recipe_not_applicable` | No recipe for this edge, or the code is not in the form the recipe expects (`detail` says which step). |
| `no_code_change_needed` | The substitute needs no code change (e.g. A4988 → TMC2209 STEP/DIR); notes still apply. |
| `no_code` / `file_not_read` | No code evidence, or the files could not be read now. |
| `out_of_scope_mcu` | A different microcontroller; porting is out of scope. |
| `ai_failed_validation` | AI draft failed the safety and scope checks (after one repair). |
| `budget` | The project's AI budget or the daily AI-draft cap is used up. |

Errors: 422 `OFFER_REQUIRED` (no saved offer chosen), 404 `LINE_NOT_FOUND`,
409 `INVALID_STATE` (no report), 409 `PROPOSAL_STALE` (offer changed meanwhile).

## Accept (AI drafts)

`POST /v1/jobs/{job_id}/lines/{line_id}/code-patch/accept` sets `accepted: true`.
Curated patches are created accepted. Does not count as an action. Show the diff and the
labels before offering Accept.

## Download

`GET /v1/jobs/{job_id}/lines/{line_id}/code-patch.zip` returns `application/zip` with:

- the patched copies of each changed file at their repository paths;
- the repository `LICENSE` (or `LICENSE.md`, `LICENSE.txt`, `COPYING`) when found;
- `README-BHARAT-SOURCER.txt` with origin, "NOT COMPILED", applied steps and notes.

The server re-reads each original file and refuses with 409 `SOURCE_CHANGED` if it changed
since the patch was made (request a new patch). AI drafts must be accepted first
(409 `PATCH_NOT_ACCEPTED`). 404 `PATCH_NOT_FOUND` when there is no ready patch.

## Sharing

Code patches are owner-only: `code_patch` is removed from `/v1/shared/*` views and shared
exports.

## Curated recipes (v0.28.0)

| Edge | Library | What changes |
| --- | --- | --- |
| DHT22 → DHT11 | Adafruit DHT / DHTesp | `DHT22` identifiers (define, constructor) → `DHT11` |
| SSD1306 0.96″ → SH1106 1.3″ (I²C) | Adafruit SSD1306 → SH110X | include, `Adafruit_SH1106G` object, `begin(addr, true)`, colour constants, PlatformIO `lib_deps` |
| A4988 → DRV8825 | AccelStepper | `setMinPulseWidth(2)` after each `setMaxSpeed()`; microstep note |
| A4988 → TMC2209 | any | No code change (`no_code_change_needed`); wiring/power notes |

Recipes edit code only outside comments and strings, and refuse instead of guessing when
an expected call is missing or ambiguous.

## Tier 2 (AI drafts)

Off unless `BS_CODE_ADAPT_AI=true`. Only used when no curated recipe exists for the
edge. Input is at most 3 code files (60 KB) that reference the original part's library.
Drafts must apply cleanly, touch only those files, add only the substitute's includes,
contain no network, filesystem, process or credential code, change ≤ 40 % of a file and
stay near lines that use the original library; one repair attempt, then
`ai_failed_validation`. Calls count against the project's AI budget and a daily cap
(`BS_CODE_ADAPT_DAILY_LIMIT`, default 50).

## Frontend status

Not built. Suggested: on a line whose selected offer is a substitute, a "Code changes"
button → diff viewer with labels and notes → Accept (AI drafts) → Download ZIP.
