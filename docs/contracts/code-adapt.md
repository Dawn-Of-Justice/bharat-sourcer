# Code patches for substituted parts (v0.28.0; compile checks v0.29.0)

When a part is replaced by a catalogue substitute and the project's code is available
(GitHub projects whose code files were read as code evidence), the backend can produce
the code change for the substitute: a unified diff per file, a ZIP of patched files, and
the non-code changes (wiring, power, verification) as notes. Implements tiers 1–3 of
[docs/plans/code-adapt/PLAN.md](../plans/code-adapt/PLAN.md). Since v0.29.0 the owner can
ask for a compile-only check ([below](#compile-check-v0290)). Nothing is ever uploaded, run
or tested on hardware.

## Labels (show them every time)

| Field | Values | Meaning |
| --- | --- | --- |
| `origin` | `curated` | A maintained recipe for this exact substitute and library. |
| | `ai_draft` | Model-written, then checked by rules; the owner must accept it. |
| `check` | `not_checked` | No finished compile check. Show "Not compiled". |
| | `compiles` | Compiled for `compile.board`. Show "Compiles for <board>, not tested on hardware". |
| | `compile_failed` | The compiler rejected it; show `compile.log`. |
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

## Compile check (v0.29.0)

`GET /v1/compile/boards` returns `{enabled, boards: [{fqbn, label, family}]}`. Show the
compile button only when `enabled` is true.

`POST /v1/jobs/{job_id}/lines/{line_id}/code-patch/compile` with `{"fqbn": "…"}` (optional)
returns `202` and the `CodePatch` with `compile.status: "queued"`. Owner/job-token access;
counts as one action. Without `fqbn` the board comes from the parts list; if it names no
supported board, or several, the answer is 422 `FQBN_REQUIRED`: let the user pick one from
`/v1/compile/boards`. Poll the job (or use the stream) until the status changes; a check
takes about 1–3 minutes, longer on the first run of the day (image start).

`code_patch.compile` (`CompileCheck`):

| Field | Meaning |
| --- | --- |
| `status` | `queued`, `compiles`, `compile_failed`, `unavailable` (with `reason`), `timeout` |
| `fqbn`, `board` | Board compiled for, e.g. `esp32:esp32:esp32` / "ESP32 Dev Module" |
| `core` | Pinned core used, e.g. `esp32:esp32@3.3.12` |
| `log` | Up to 40 compiler lines, errors first, when it failed; paths are sketch-relative |
| `size` | The compiler's flash/RAM usage line when it compiled |
| `sketch` | Repository path of the compiled sketch |
| `attempt`, `repairs` | AI drafts that fail get up to 2 repair rounds (below) |
| `expires_at` | A `queued` check past this time has timed out and can be requested again |

`reason` when `status: unavailable`: `source_changed` (request a new patch),
`source_unavailable`, `sketch_not_found`, `platformio_not_supported` (PlatformIO projects
are not compiled because their build scripts run project code), `too_large`,
`launch_failed`, `runner_error`.

When a check finishes, the top-level `check` becomes `compiles` or `compile_failed`;
`timeout` and `unavailable` leave it `not_checked`. The ZIP README states the result. A new
patch (`POST …/code-patch`) starts again at `not_checked`.

**AI drafts:** if an `ai_draft` fails to compile and `BS_CODE_ADAPT_AI` is on, the backend
asks the model for a revision with the compiler errors, validates it with the same rules as
the first draft, replaces `files`, sets `accepted: false` and compiles again, at most twice
(`repairs`), each call counted against the AI budget. Show the new diff and ask for Accept
again. Curated patches are never rewritten.

Errors: 503 `COMPILE_UNAVAILABLE` (not enabled), 404 `PATCH_NOT_FOUND`, 409
`COMPILE_IN_PROGRESS`, 409 `PROPOSAL_STALE` (patch replaced meanwhile), 409
`INVALID_STATE` (demo project), 422 `FQBN_REQUIRED` / `FQBN_UNSUPPORTED`, 429
`COMPILE_DAILY_LIMIT` (`BS_COMPILE_DAILY_LIMIT`, default 100 per day).

Boards (v0.29.0): Arduino Uno, Nano (ATmega328P), Mega 2560, Leonardo, Micro; ESP32 and
ESP32-S3/-C3/-S2 Dev Modules, Adafruit Feather ESP32; NodeMCU 1.0, Wemos D1 mini; Raspberry
Pi Pico / Pico W. Libraries are the pinned set in `backend/compile/pins.json` (the libraries
in the code-evidence map, with their dependencies); a sketch that needs another library
fails with "No such file or directory" in `log`.

How it runs: one isolated Cloud Run job per core family, with no permissions, no secrets
and no internet route, compiles the sketch the API assembles from the repository snapshot.
See [the runbook](../../backend/infra/README.md#compile-runner-code-adapt-tier-3).

## Frontend status

The results view shows a "Code changes" panel for a selected catalogue substitute.
It displays file diffs, origin and "Not compiled" labels, plus wiring, power and
verification notes. AI drafts require Accept before Download ZIP. Shared reports do
not show code patches.

Compile check (v0.29.0) UI is not built. Suggested: a "Check it compiles" button when
`/v1/compile/boards` reports `enabled`, a board picker on `FQBN_REQUIRED`, then the result
badge (`check`), `size` or `log`, and the re-Accept prompt after an AI repair round.
