# Project overview (v0.33.0)

After extraction finishes (`awaiting_confirmation`), the backend reconstructs the project
for the review step: a drawable description of every part and the wiring between them.
Seller search still starts only when the owner confirms (`POST /v1/jobs/{id}/confirm`).

Everything here is **AI-inferred and checked**, never verified against the physical board.
The UI must say so ("drawn from the project code and AI knowledge; check your board's
labels"); the backend also puts that sentence first in `notes`. Demo jobs return a
labelled fixture overview (`demo: true`).

This shipped as v0.32.0 (the draft said v0.31.0, which was already used by the robu.in
release); the shape below is unchanged from the draft.

## Pipeline

v0.33.0 splits generation into parallel calls and saves progress (see **Progressive
drawing** below); the inputs, validation and judging rules here are unchanged.

1. **Generate** (Gemini; v0.33.0: parts by site `overview`, wiring by site `overview_wiring`): input is the project
   context (the model's own summary, power, controller, interfaces and assumptions; an
   owner-edited title or description is not sent), the draft BOM lines (id, name, count,
   specs, requirements, up to four evidence quotes each) and the code text of the
   project's GitHub files. Files are the ones code evidence cites; when nothing is cited and
   a source is a GitHub repository, the usual entry points (`<repo>.ino`,
   `<repo>/<repo>.ino`, `src/main.cpp`, `main.py`, `code.py`, `platformio.ini`) are tried.
   At most 10 fetches and 6 files of 200 KB each, from `raw.githubusercontent.com` through
   the guarded fetcher (the same bounds as `code_evidence.py`); the model gets them with line
   numbers, files with pin facts first, 60,000 characters in total. A deterministic parser
   also extracts **code pin facts** with `file:line`: pin-named `#define`s and `const`
   integers (`#define TOUCH_PIN 7`, `const int ledPin = 2`; a non-const variable counts only
   when its name contains `pin`), `Wire.begin(sda, scl)` / `Wire.setPins`,
   `SPI.begin(...)`, `pinMode`, `digitalRead`/`digitalWrite`, `analogRead`, `touchRead`,
   `analogWrite`/`ledcAttach(Pin)`, `attachInterrupt(digitalPinToInterrupt(...))`, and
   MicroPython/CircuitPython `Pin(...)`, `sda=Pin(...)`, `ADC(Pin(...))`, `board.GP15`.
   Output: one `PartVisual` per line that is a physical part (boards, modules, sensors,
   displays, batteries, switches, passives; not wire, solder, filament or tools) and the
   `WireConnection` list.
2. **Validate** (deterministic, `overview.py`): parts for unknown lines and second parts
   for the same line are dropped; duplicate pin names on a header are removed; every wire
   endpoint must name an existing `line_id` and an existing pin of that part (matched
   case-insensitively and rewritten to the pin's exact name), otherwise the wire is removed
   and a `notes` entry says how many were removed; duplicate wires are removed and wires are
   renumbered `W01`, `W02`, ... `problems` entries are added for:
   - a power pin wired to a ground pin;
   - two supply pins with different voltages. Voltages come from power-pin labels only:
     `5V`, `VBUS`, `3V3`, `3.3V`, a bare `3.3`; `VCC`, `VIN` or `2` have no known voltage;
   - a 5 V supply pin into a power pin of a part declared 3.3 V-only (BOM
     `specs.supply_max_v` below 4.5 V, or every power pin of the part labelled 3.3 V);
   - an I2C wire on a different board pin than the code sets (`Wire.begin(8, 9)`);
   - `source: "code"` whose `evidence` is not an existing `file:line`, or whose board pin
     the code never uses.

   A board pin matches a code pin by its GPIO function (`GPIO8`) or its label (`8`,
   `GPIO8`, `IO8`; `D3`/`A0` tokens). A code pin with no wire adds a `notes` entry such as
   "Code uses GPIO 2 (ledPin, buddy.ino:9) but no wire connects it." When no code could be
   read, `source: "code"` becomes `ai_inferred` (wires and `pin_source`).
3. **Judge** (Gemini, site `overview_judge`, separate call, different prompt): receives the
   generated JSON plus the same evidence and returns a verdict per part, per pin header and
   per wire: `confirmed` (supported by code, a quote or well-known datasheet facts for that
   exact module), `unverified` (plausible but unsupported) or `disputed` (contradicted).
   The server applies verdicts:
   - disputed wires stay visible but flagged;
   - a part takes the worst of its own verdict and its pin headers' verdicts, so a disputed
     pin list makes the part `disputed` (`verdict_reason` starts "Pin list (left side)
     disputed: ...");
   - anything the judge did not review is `unverified` with reason "Not reviewed by the
     checker.";
   - a wire with validator `problems` is never `confirmed` (it becomes `unverified`);
   - the judge never adds parts or wires (verdicts for unknown ids are ignored).

   `judge.status` is `issues` when anything is disputed, else `passed`; counts are over the
   final part and wire verdicts. When the judge call fails or the drawing used up its
   budget, the overview is still `ready` with `judge.status: "skipped"` and everything
   `unverified`.
4. Any other failure leaves `status: "failed"` with a message; review and confirm still
   work. Messages: "AI drawing is not configured on this server." (no Gemini key), "The
   project overview is turned off on this server.", "Skipped to stay within this project's
   AI budget; try Redraw later.", "The AI could not draw this project right now; try
   Redraw.", "No drawable parts were found in the parts list.", "Drawing was interrupted;
   try Redraw." and "Drawing failed unexpectedly; try Redraw."

Budget: both calls are attributed to the job ledger (`cost_estimate.calls_by_site.overview`
and `.overview_judge`, added to `total_usd`; like extraction they do not use the sourcing
run budget `run_usd`). Each drawing has its own `BS_JOB_GEMINI_BUDGET_USD` cap (the judge is
skipped if drawing alone reached it), and no drawing starts once a sourcing run reached the
job budget. Judged results are cached for 7 days in the shared cache (namespace `overview`)
by (prompt version, model, items hash, code hash); a cache hit makes no model call. The
live Desk Buddy check (6 parts, 12 wires) cost about $0.054 for both calls and took 48 s.

## Progressive drawing (v0.33.0)

- **Parts**: the lines are split into groups of two and drawn by parallel calls (site
  `overview`, up to 8 at once, low thinking, 40 s timeout). Each call gets the project
  context, its own lines, the names of the other parts, the pin facts and the first 16,000
  characters of numbered code, and may only draw its own lines. As each group lands the
  stored overview is updated: `status: "pending"`, `stage: "parts"`, `parts` = everything
  drawn so far in parts-list order, all `unverified`, `judge.status: "pending"`.
  Each group is judged at once by its own judge call (parts and pin headers only).
- A grouped call that fails or times out after one retry is redrawn one line per call. A
  call whose model stays overloaded (429/5xx or timeouts after its retries) gets one try on
  `BS_OVERVIEW_FALLBACK_MODEL` (default `gemini-3.5-flash-lite`; empty turns it off).
  Lines that still fail are left out with the note "Some parts could not be drawn; try
  Redraw." If no part could be drawn at all, the drawing fails (`GENERATION_FAILED`).
- **Wiring**: when every part call is back, `stage: "wiring"`, and one call (site
  `overview_wiring`, low thinking) gets the full numbered code (60,000 characters), the pin
  facts, the drawn parts with their pin headers and `open_questions` (below), and returns
  the wires, notes and answers. If it fails the overview is still `ready` with the parts,
  no wires and the note "The wiring could not be drawn; try Redraw."
- **Checking**: the validator runs, then `stage: "checking"` is stored with the wires, and
  one judge call reviews the wires (given the parts' pins, which it does not re-judge).
- **Done**: verdicts from all judge calls are applied together (the rules above), `stage`
  becomes null and `status` `ready`. If every judge call failed, `judge.status: "skipped"`;
  if only some failed, the unreviewed items are `unverified` ("Not reviewed by the
  checker."). Only a complete drawing (no failed part, wiring or judge call) is cached.
- Clients poll `GET /v1/jobs/{id}/overview` (the web app every 1.5 s) or read
  `job.overview` from the job stream while `pending`, and show verdict pills only once it
  is no longer `pending`.

The live Desk Buddy check (7 lines) showed all parts at 13 s, wires at 27 s and finished in
41 s for about $0.034 (was one 48 s call with nothing shown until the end).

Overview calls are served by Vertex AI (location `global`) when the server has a GCP
project, falling back to the Gemini API key when Vertex refuses; the request and response
shapes are the same. On Vertex the Desk Buddy drawing showed all parts at 10 s and finished
in 25 s.

### Settled questions (`resolved`)

Lines often carry clarifications ("Confirm pinout for this part") for spec fields the parts
list could not fill. The drawing answers what it can:

- `pinout`: read off the part's drawn pin headers (names in header order, comma-separated,
  at most 200 characters), `source: "drawing"`.
- other `PartSpecs` fields asked by a line (`logic_v`, `i2c_address`, `supply_min_v`,
  `output_mode`, `active_level`, ...): sent to the wiring call as
  `open_questions: [{line_id, field, allowed}]`; it answers only when the code, the wires it
  drew, the drawn pins, the project context or well-known datasheet facts for that exact
  module decide it, with a reason; `source: "wiring"`. Answers for questions that were not
  asked, with values outside the field's allowed values, or for a part the judge disputed
  are dropped.

When the drawing is saved `ready` while the job is `awaiting_confirmation`, each settled
value is filled in as the line's `ai_specs` (gaps only, like spec fill; values that
conflict with known specs are dropped) and the line's `clarifications` are recomputed, so
answered questions disappear. Owner-declared specs always win. `ai_specs` and
`clarifications` are not part of `items_hash`, so this never makes the drawing stale.

## API

- `GET /v1/jobs/{job_id}/overview` → `ProjectOverview` (owner, or the job token when
  accounts are off). 404 `OVERVIEW_NOT_FOUND` when no overview exists (older jobs, a job
  still extracting, or `BS_OVERVIEW_ENABLED=false`). A `pending` overview whose 15-minute
  lease ran out (a lost task or a crashed worker) is answered and stored as `failed`
  ("Drawing was interrupted; try Redraw.").
- `POST /v1/jobs/{job_id}/overview` (no body) → 200 `ProjectOverview`; owner only. Starts
  generation when the status is `failed`, `stale` or missing (or an interrupted `pending`)
  and returns `status: "pending"`; otherwise returns the current one unchanged. 409
  `INVALID_STATE` unless the job is `awaiting_confirmation` or later (`resolving`,
  `sourcing`, `paused`, `done`, or `failed` with a parts list). With accounts on, the POST
  counts as a project action like other project POSTs, so read with GET and POST only for
  Redraw/Retry. Demo jobs get the fixture at once; with the overview turned off the POST
  stores `failed`.
- `job.overview` carries the same object in job snapshots and the event stream, and
  `GET /v1/shared/{share_token}` carries it as `overview` for share-link readers. "Copy to
  my projects" copies a `ready` or `stale` overview.
- Generation is started automatically when extraction completes: inline after extraction
  locally, as its own Cloud Task (`kind: "overview"`) in cloud mode, so the review page is
  never blocked. Pending overviews are not redispatched by the sweep; the lease above lets
  the owner restart them. When the owner edits the draft parts list (`edit_draft`, also
  chat-approved edits and confirmation), an existing `ready` or `pending` overview becomes
  `stale` ("The parts list changed after this was drawn; redraw to update it.") when the
  edit changed a line's id, name, count, specs or requirements, or added or removed a line;
  marking a part "I have it" does not. A stale overview keeps its parts and wiring and is
  not regenerated automatically; the UI offers "Redraw". A drawing that finishes after
  such an edit is saved as `stale`.

Configuration: `BS_OVERVIEW_ENABLED` (default `true`). Models follow
`BS_GEMINI_SITE_MODELS` (sites `overview`, `overview_judge`; default `BS_GEMINI_MODEL`) and
thinking `BS_GEMINI_SITE_THINKING` (`overview_judge` is `low` by default; `overview` uses the
model default).

## Schemas

```text
ProjectOverview {
  status: "pending" | "ready" | "failed" | "stale"
  stage: "parts" | "wiring" | "checking" | null   // v0.33.0: progress while pending
  message: string | null              // human-readable reason for failed/stale
  generated_at: datetime | null
  items_hash: string | null           // SHA-256 of the lines the drawing was made from
  demo: bool
  parts: PartVisual[]                 // ≤ 40, ≤ 360 pins in total
  wiring: WireConnection[]            // ≤ 120
  judge: OverviewJudge
  notes: string[]                     // ≤ 10, each ≤ 300, e.g. "Code uses GPIO 3 but no wire connects it"
  resolved: ResolvedSpec[]            // v0.33.0, ≤ 120: open spec questions the drawing settled
}

ResolvedSpec {
  line_id: string
  field: string                       // a PartSpecs field, e.g. "pinout", "logic_v"
  value: string                       // ≤ 200, e.g. "GND,VCC,SCL,SDA", "3.3"
  reason: string | null               // ≤ 300
  source: "drawing" | "wiring"
}

OverviewJudge {
  status: "passed" | "issues" | "skipped" | "pending"
  summary: string | null              // one sentence, ≤ 300
  confirmed: int; unverified: int; disputed: int   // over parts and wires
}

PartVisual {
  line_id: string                     // BOM line it draws
  label: string                       // ≤ 40 chars, short display name ("ESP32-C3 Super Mini")
  kind: "board" | "module" | "sensor" | "display" | "battery" | "switch" | "passive"
        | "connector" | "other"
  body: { width_mm: number (1–300), height_mm: number (1–300),
          color: "blue" | "black" | "green" | "red" | "purple" | "yellow" | "white"
                 | "silver" | "orange",
          shape: "rect" | "rounded" | "round" | "pouch" }
  chip: { label: string ≤ 24, x: 0–1, y: 0–1, w: 0–1, h: 0–1 } | null   // fractions of body
  features: [{ type: "screen" | "led" | "button" | "antenna" | "touch_pad" | "lens"
                     | "label",
               x, y, w, h: 0–1, text: string ≤ 24 | null }]               // ≤ 8
  connectors: [{ type: "usb_c" | "micro_usb" | "jst" | "barrel" | "screw_terminal"
                       | "pin_socket",
                 side: "top" | "bottom" | "left" | "right", position: 0–1 }]  // ≤ 4
  headers: [{ side: "top" | "bottom" | "left" | "right", pins: Pin[] }]     // ≤ 4, 1–40 pins each
  pin_source: "code" | "datasheet_knowledge" | "ai_inferred"
  verdict: "confirmed" | "unverified" | "disputed"
  verdict_reason: string | null       // ≤ 300
}

Pin {
  name: string ≤ 16                   // silkscreen label: "GPIO8", "SDA", "VCC", "5V"; unique per header
  kind: "power" | "ground" | "gpio" | "analog" | "i2c" | "spi" | "uart" | "control" | "other"
  functions: string[] ≤ 4             // "SDA", "ADC1_CH3", "TX"; each ≤ 24
}

WireConnection {
  id: string                          // "W01"
  from: { line_id, pin }              // pin = Pin.name on that part
  to:   { line_id, pin }
  signal: "power" | "ground" | "i2c_sda" | "i2c_scl" | "spi" | "uart" | "digital"
          | "analog" | "pwm" | "other"
  label: string | null                // "Touch input", "Battery +"; ≤ 40
  source: "code" | "description" | "ai_inferred"
  evidence: string | null             // "DeskBuddy.ino:14" or a short quote; ≤ 200
  verdict: "confirmed" | "unverified" | "disputed"
  reason: string | null               // ≤ 300
  problems: string[]                  // deterministic validator findings, ≤ 6
}
```

Fractions are clamped to 0–1 and sizes to 1–300 mm by the server. Every string field is
plain text; render it as text, never as HTML.
