# Code adaptation for substituted parts — plan (draft, 2026-10-09)

Status: **design only, not approved.** Do not implement until the owner answers §8.
Depends on: the routing engine work (`docs/plans/routing-engine/PLAN.md`) landing first.

## 1. Goal

When a build's part is replaced by a substitute (cheaper, in stock, or the only one sold
in India) and the project's code is available, give the user the code change that makes
the build work with the substitute: a reviewable diff, patched files to download, and the
non-code changes (wiring, power, verification) next to it. Never silently change code,
never present an unchecked patch as working.

Out of scope: porting to a different microcontroller family (Uno → ESP32), safety-critical
changes (mains, battery charging, motor current limits), hosting modified code publicly,
running user code.

## 2. What already exists (build on it)

- `code_evidence.py` reads up to 8 code/build files from a public GitHub repo via
  `raw.githubusercontent.com`, and maps `#include`, Python imports, `lib_deps` and
  `board =` to parts with `file:line` evidence (`data/library_parts.json`).
- `data/parts_catalog.json` curated substitutes carry `changes[]` with `area` ∈
  `code | wiring | power | verify`. Today there are **4 edges, all with code changes**:
  DHT22→DHT11 (D), SSD1306→SH1106 (B), A4988→DRV8825 (B), A4988→TMC2209 (C).
- `compat_rules.py` grades substitutes (A compatible … X incompatible) and emits
  findings per area; `board_chip` already says "Port the code…" for a different MCU (D).
- `ReportLine.changes_accepted` records that the user accepted a grade-B change set.
- Gemini is the project's model provider (judge, discovery, research); keys and budgets
  live in `config.py` / the usage ledger.

## 3. Design principles

1. **Decide by confidence × risk (routing matrix).**

   | Source of the change | Risk area | Outcome |
   |---|---|---|
   | Curated recipe (tier 1) | code only | Patch shown with diff, labelled "curated change" |
   | AI-drafted (tier 2) | code only | Diff shown, labelled "AI draft — not compiled"; user must accept |
   | Any | wiring / power / verify | Notes only (text), never a patch |
   | Any | MCU change, mains, LiPo, high current | Notes only + existing safety flags |
2. **Deterministic first, model second.** Recipes are data + pure functions; the model is
   only used when no recipe exists, and its output passes the same validators.
3. **Server-side gates only.** The client can request a patch or accept one; it can never
   mark a patch as compiled or reviewed.
4. **Bounded loops.** At most 1 model draft + 1 repair per line; compile fix loop (tier 3)
   at most 2 rounds; per-job and per-day caps in the usage ledger.
5. **Fail loud.** Every "no patch" carries a reason: `no_code`, `file_not_read`,
   `recipe_not_applicable`, `ai_failed_validation`, `out_of_scope_mcu`, `safety`,
   `budget`.
6. **Labels are part of the data.** `origin: curated | ai_draft`, `check: not_checked |
   compiles | compile_failed`. Exports and share links carry the label.

## 4. Tier 1 — curated recipes

- New `data/code_recipes.json`, keyed by substitute edge `{from_id, to_id}`, each step one
  of: `replace_include`, `replace_identifier` (word-boundary), `replace_constructor`
  (regex with named groups, e.g. `Adafruit_SSD1306 (\w+)\((.*)\)`), `replace_define`
  (`#define DHTTYPE DHT22` → `DHT11`), `replace_lib_dep` (platformio `lib_deps`,
  `library.properties` `depends`), `insert_after` (e.g. `setMinPulseWidth(2)` after the
  AccelStepper constructor, only if AccelStepper is used). Each recipe names the source
  `changes[]` text it implements and the notes it cannot implement.
- New `code_adapt.py`: `apply_recipe(files, recipe) -> PatchResult` (pure; returns
  unified diff per file, applied steps, skipped steps with reasons). Refuses when an
  anchor matches 0 or > N times (ambiguous), so it never guesses.
- Recipes for the 4 existing edges first; then add catalog edges for common swaps found
  in jobs (e.g. BME280→BMP280 with humidity reads removed and a note that humidity is
  lost; MPU6050 variants) — each new edge gets a fixture sketch and expected diff.
- Fixtures: `tests/fixtures/code_adapt/<edge>/{before,after}/…` — small synthetic
  sketches written for the tests (labelled synthetic), not copied from real repos.

## 5. Tier 2 — AI-drafted patch

- Input: only the files `code_evidence` linked to the original part (≤ 3 files, ≤ 60 KB
  total), the original and substitute catalog entries, their `changes[]` notes, and the
  substitute's library from `library_parts.json`. No other repo content.
- Output (structured JSON): `files[{path, unified_diff}]`, `notes[]`, `assumptions[]`.
- Validators (same code as the eval): diff applies cleanly; touches only input files;
  only adds includes that map to the substitute in `library_parts.json`; no new network,
  filesystem, `system()`/`exec` or credential-looking strings; size of change ≤ 40 % of
  the touched file; no change outside lines that reference the original library unless
  the step names them. Fail → one repair attempt with the validator errors → else
  `ai_failed_validation`.
- Cost: one Gemini call per line (+1 repair), counted in the usage ledger; skipped when
  the job budget is spent.

## 6. Tier 3 — compile check (separate approval)

- A Cloud Run **Job** (not the API service) with `arduino-cli` and pinned cores
  (`arduino:avr`, `esp32:esp32`, `esp8266:esp8266`, `rp2040`). One image per core family,
  rebuilt only when the pinned versions change, so runs start warm.
- Input: repo at the commit `code_evidence` read (pin the SHA, not HEAD), the patch, the
  FQBN from `platformio.ini board=` / the BOM's dev board / the user. Libraries resolved
  from the Arduino library index at pinned versions.
- Compile only, never upload or run. Runs as a service account with no permissions, no
  secrets, egress limited to GitHub + the Arduino index. **PlatformIO projects are not
  compiled** in v1 (their `extra_scripts` execute repo Python) — they get tiers 1–2 only.
- Result written to an inbox doc keyed by `(job_id, line_id, attempt)` and processed by
  the API (idempotent; a duplicate result is ignored). Compiler errors (first 40 lines)
  feed at most 2 repair rounds back through tier 2's validators.
- Timeouts: 300 s per compile, job-level cap; stuck runs are marked `compile_timeout`.

## 7. API and data (additive; regenerate OpenAPI)

- `ReportLine.code_patch: CodePatch | None` with `origin`, `check`, `files[{path,
  diff}]`, `notes[]`, `reason` (when absent), `source_commit`, `created_at`.
- `POST /v1/jobs/{id}/lines/{line_id}/code-patch` (owner only, budgeted) creates it;
  `GET …/code-patch.zip` returns patched files + the repo's LICENSE + a README stating
  origin/check labels. Not included in `/v1/shared/*` by default (owner decision).
- Frontend is the teammate's: backend ships the fields; UI is a follow-up.

## 8. Owner decisions

1. Build tiers 1–2 now (after routing)? Tier 3 compile runner later or never?
2. Share links: include patches (labelled) or owner-only?
3. Before building: measure the input mix (share of jobs with GitHub/code sources) from
   the job store with `scripts/usage_report.py`-style counting — if code is rare, ship
   cart links first.
4. Accept PlatformIO-only repos without compile (tiers 1–2), or skip them?

## 9. Phases and tests

1. Recipes engine + 4 edges + fixtures (`tests/test_code_adapt.py`): exact diffs,
   ambiguity refusal, no-op when library absent, labels, reasons.
2. Tier 2 behind `BS_CODE_ADAPT_AI` flag: validator tests with hostile drafts (extra
   files, `system()`, unrelated rewrites, unknown includes), budget accounting.
3. Eval: gold set of (sketch, edge) → expected diff; deterministic scorer imports the
   production validators; synthetic set flagged `synthetic` (harness check only).
4. Tier 3 (if approved): runner image, job, inbox processing, fake-runner tests.
5. Docs: `docs/contracts/code-adapt.md`, contracts README changelog, backend README,
   version bump.
