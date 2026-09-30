# Prompts and schemas

> **In one minute.** Every LLM call returns **structured JSON** validated by Pydantic. The schemas below are the contract between agents, the database and the UI. Prompts are versioned files in `backend/agents/prompts/` and share one rule: *evidence or UNKNOWN, never a guess*. No `temperature` is set (deprecated); determinism comes from schemas, `thinking_level` and rules.

---

## 1. Core schemas (Pydantic → JSON Schema)

```python
# backend/schemas/core.py
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl

SourceType = Literal["code", "structured_page", "description", "transcript", "frame", "schematic", "comment", "user"]
Category = Literal["mcu_board", "sensor", "actuator", "motor_driver", "display", "power", "passive", "connector",
                   "mechanical", "mains_switching", "led", "rf_module", "battery", "tool", "consumable", "other"]
Ecosystem = Literal["none", "STEMMA", "STEMMA_QT", "Qwiic", "Grove", "Feather", "FeatherWing", "Pololu_stepper",
                    "Arduino_shield", "Pi_HAT", "Pi_pHAT", "Wemos_D1_mini_shield", "Other"]
Grade = Literal["A", "B", "C", "D", "X"]
SafetyFlag = Literal["MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT_REQUIRED", "HEAT", "LASER", "SHARP"]

class Evidence(BaseModel):
    source_type: SourceType
    locator: str = Field(description="URL#anchor, file:line, or MM:SS")
    quote: str = Field(description="verbatim text or a short description of what is visible")

class RawMention(BaseModel):
    raw_name: str
    visible_text: Optional[str] = Field(None, description="silkscreen/label text read verbatim")
    identity: Optional[str] = None
    identity_confidence: float = Field(ge=0, le=1)
    lookalikes: list[str] = []
    qty: Optional[float] = None
    qty_unit: Optional[Literal["pcs", "m", "g", "set"]] = None
    role_in_project: Optional[str] = None
    evidence: list[Evidence]

class Canonical(BaseModel):
    chip: Optional[str] = None           # "BME280"
    module: Optional[str] = None         # "GY-BME280-3.3"
    ecosystem: Ecosystem = "none"
    kg_id: Optional[str] = None

class BomItem(BaseModel):
    line_id: str                         # "L01"
    raw_name: str
    canonical: Canonical
    category: Category
    qty: Optional[float]
    qty_unit: Optional[str] = "pcs"
    role_in_project: Optional[str]
    interfaces_used: list[Literal["I2C","SPI","UART","1-Wire","PWM","ANALOG","DIGITAL","STEP_DIR","USB","MAINS_AC"]] = []
    evidence: list[Evidence]
    confidence: float = Field(ge=0, le=1)
    lookalike_risk: list[str] = []
    optional: bool = False
    user_has_it: bool = False
    safety_flags: list[SafetyFlag] = []

class Conflict(BaseModel):
    line_ids: list[str]
    kind: Literal["chip_mismatch", "qty_mismatch", "lookalike", "mains_detected", "other"]
    message: str

class BomDraft(BaseModel):
    items: list[BomItem]
    conflicts: list[Conflict] = []
    unresolved: list[RawMention] = []
    segments: list[dict] = []            # [{"label":"wiring","start":"05:00","end":"07:40"}]
```

### 1.1 Part specs

```python
class SpecValue(BaseModel):
    value: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    unit: Optional[str] = None
    text: Optional[str] = None
    source: Literal["kg", "datasheet", "listing", "llm"] = "llm"
    citation: Optional[str] = None       # URL#page=N or kg id

class PartSpec(BaseModel):
    category: Category
    chip: Optional[str]
    module: Optional[str]
    supply_v: Optional[SpecValue] = None         # module input range
    logic_v: Optional[SpecValue] = None          # I/O level
    io_5v_tolerant: Optional[bool] = None
    interfaces: list[str] = []
    i2c_addresses: list[str] = []                # ["0x76","0x77"]
    measures: list[str] = []                     # ["temperature","pressure","humidity"]
    current_a: Optional[SpecValue] = None
    footprint: Optional[str] = None              # "Pololu_16pin", "Feather", "DevKitC_38"
    connector: Optional[str] = None              # "JST-SH-4", "Dupont"
    board_fqbn: Optional[str] = None             # for MCU boards
    libraries: list[str] = []
    mains_rating_vac: Optional[float] = None
    attributes: dict[str, SpecValue] = {}        # category-specific extras
    spec_source: Literal["kg", "datasheet", "llm"] = "llm"

class ResolvedPart(BaseModel):
    line_id: str
    item: BomItem
    spec: PartSpec
    voltage_domain: Literal["logic_3v3", "logic_5v", "motor", "mains", "battery", "none"]
```

### 1.2 Offers and listings

```python
class Offer(BaseModel):                  # what a sourcing adapter or grounded search returns
    seller: str                          # "robocraze"
    url: HttpUrl
    title: str
    price_value: Optional[float]
    price_currency: Literal["INR", "USD", "EUR", "GBP"] = "INR"
    price_includes_gst: Optional[bool]
    in_stock: Optional[bool]
    module_guess: Optional[str]
    source_tier: Literal["A_ucp", "A_store_api", "B_distributor", "C_grounded", "cache"]
    evidence_snippet: Optional[str]

class Listing(BaseModel):                # only verified offers become listings
    listing_id: str                      # sha1(url)
    seller: str
    url: HttpUrl
    title: str
    module_id: Optional[str]
    price_inr_incl_gst: float
    gst_added_by_us: bool
    stock: Literal["in_stock", "out_of_stock", "unknown"]
    fetched_at: str
    http_status: int
    source_tier: str
    title_match_score: float
```

### 1.3 Compatibility report

```python
class WiringChange(BaseModel):
    from_: str = Field(alias="from")
    to: str
    why: str

class CodeChange(BaseModel):
    library_swap: list[str] = []         # ["Adafruit_SSD1306 -> Adafruit_SH110X"]
    board_target: Optional[str] = None   # "esp32:esp32:esp32"
    diff: Optional[str] = None           # unified diff
    compiled: Optional[bool] = None
    compile_log_url: Optional[str] = None

class Citation(BaseModel):
    claim: str
    url: str
    quote: Optional[str] = None

class ImpactReport(BaseModel):
    line_id: str
    original: Canonical
    substitute_listing_id: str
    grade: Grade
    grade_reasons: list[str]             # from rules engine, verbatim
    summary: str = Field(max_length=280)
    wiring: list[WiringChange] = []
    power: list[str] = []
    extra_parts: list[str] = []          # e.g. "74AHCT125 level shifter"
    code: CodeChange = CodeChange()
    mechanical: list[str] = []
    behaviour: list[str] = []            # "no humidity reading"
    safety_flags: list[SafetyFlag] = []
    verify_on_arrival: list[str] = []    # "Read register 0xD0: expect 0x60"
    confidence: float
    confidence_bucket: Literal["verified", "likely", "check"]
    citations: list[Citation]
```

### 1.4 Costing and final report

```python
class LineChoice(BaseModel):
    line_id: str
    listing_id: Optional[str]            # None if user_has_it or unsourced
    qty: float
    unit_inr: Optional[float]
    line_inr: Optional[float]
    grade: Optional[Grade]
    status: Literal["sourced", "have_it", "import_only", "unsourced"]

class SellerSplit(BaseModel):
    seller: str
    subtotal_inr: float
    shipping_inr: float
    free_shipping_threshold_inr: Optional[float]

class ImportBaseline(BaseModel):
    original_total: float
    currency: str
    fx_rate: float
    fx_date: str
    intl_shipping_inr: float
    bcd_rate: float = 0.10
    sws_rate_on_bcd: float = 0.10
    igst_rate: float                     # configurable; see cost doc
    landed_inr: float
    assumptions: list[str]

class Costing(BaseModel):
    plan: Literal["cheapest", "fewest_sellers"]
    lines: list[LineChoice]
    sellers: list[SellerSplit]
    parts_total_inr: float
    shipping_total_inr: float
    grand_total_inr: float
    import_baseline: Optional[ImportBaseline]
    savings_inr: Optional[float]
    savings_pct: Optional[float]
    local_share_pct: float

class DesiBom(BaseModel):
    job_id: str
    project_title: str
    source_url: str
    summary: str
    safety_banners: list[str]
    lines: list[dict]                    # BomItem + chosen Listing + ImpactReport (denormalised for UI)
    costing: dict[str, Costing]          # {"cheapest":…, "fewest_sellers":…}
    sources_footer_html: Optional[str]   # Google search_suggestions (ToS)
    generated_at: str
    model_versions: dict[str, str]
```

## 2. Prompts

Every prompt starts with the shared preamble:

```text
You are part of Bharat Sourcer, a system that helps makers in India rebuild electronics projects with parts available in India.
Rules:
1. Evidence or UNKNOWN. Every claim must point to evidence you were given (timestamp MM:SS, URL, quote, file:line, datasheet page). If you cannot support a claim, say UNKNOWN.
2. Never invent part numbers, prices, URLs or stock status.
3. Prefer the conservative engineering answer when sources disagree about electrical safety.
4. Output ONLY JSON matching the provided schema.
```

### P1 Page extractor

```text
Task: Extract every physical item needed to build the project described in the provided pages.
Read parts/supplies sections AND the prose (authors often mention parts only in text).
For each item give raw_name (verbatim), qty (only if stated), role_in_project, and evidence with locator (URL#section) and a short verbatim quote.
Include tools and consumables but mark category "tool"/"consumable".
Do not merge different variants (e.g. "BME280" vs "BMP280").
```

### P2 Video extractor

```text
Task: Watch this build video and list every electronic or mechanical component that is SHOWN, NAMED, or WIRED.
Context you can use: video title, description (below), and this look-alike list: {lookalikes}.
For each component:
- visible_text: any text printed on the board/chip exactly as seen (e.g. "GY-BME280", "DOIT ESP32 DEVKIT V1"). Empty if none legible.
- identity and identity_confidence (0–1). If two parts look alike, list the other in lookalikes.
- evidence: at least one timestamp MM:SS where it is visible or named; say whether from frame or narration.
- qty only if you can count it or the narrator states it.
- role_in_project in ≤ 8 words.
Also return segments: time ranges for "parts overview", "wiring", "code", "demo".
If you cannot identify an item, set identity to UNKNOWN and describe it (colour, size, pins, connector).
```

### P3 Part resolver (KG miss)

```text
Task: Produce the technical spec of this part as used in this project.
Inputs: BomItem, evidence URLs, optional datasheet.
Fill PartSpec. For every numeric field, set source ("datasheet"/"listing"/"llm") and citation (URL#page=N).
Module-level values (e.g. breakout board with a regulator accepts 3–5 V) take priority over chip-level values.
If the module variant is ambiguous (3.3 V-only vs 5 V-tolerant breakouts exist), set the field to null and add attributes.variant_ambiguity.
```

### P4 Grounded seller search (Tier C)

```text
Task: Find where this part can be bought in India today.
Part: {canonical} | key specs: {hard_specs} | acceptable substitutes: {candidate_modules}
Search Indian sellers, prioritising: {allowlisted_domains}.
Return Offer objects only for product pages (not category or search pages), with price as shown on the page and whether it includes GST if stated.
Do not return marketplaces outside India. Do not guess prices. If a page shows "out of stock", set in_stock=false.
```

### P5 Compatibility explainer

```text
Task: Explain what changes if the maker uses SUBSTITUTE instead of ORIGINAL in THIS project.
You are given: original spec, substitute spec, project context (MCU logic voltage, rails, pins used, libraries, code excerpt), and RULE_FINDINGS from a deterministic checker.
RULE_FINDINGS are authoritative: you may NOT upgrade the grade; you may downgrade with a reason.
Write for a {user_level} maker. Fill ImpactReport:
- wiring: concrete from→to changes with why
- power: supply/rail changes and current math if relevant
- extra_parts: exact part names (e.g. "74AHCT125", "1kΩ + 2kΩ divider")
- behaviour: what the user will notice (lost features, accuracy)
- verify_on_arrival: quick tests (I2C scan, chip-ID register)
- citations: datasheet pages (from File Search) or KG ids for every number you state.
```

### P6 Judge (checklist; run ×3)

```text
Evaluate this ImpactReport against the checklist. Answer yes/no/na with the exact span of evidence.
1 States substitute supply voltage and it matches the rail.
2 All 3.3V/5V signal mismatches addressed.
3 If I2C device changed: address stated and consistent with the code diff.
4 If chip changed: library change in diff; every API call exists in the new library (api_symbols provided).
5 Lost quantities/capabilities stated.
6 Every number has a citation (list uncited numbers).
7 MAINS/LIPO banner present when applicable.
8 Listing fetched < 24h and title contains chip/module token.
Return {"pass": bool, "failures": [...], "uncited_numbers": [...]}.
```

### P7 Code impact

```text
Task: Produce a unified diff for the project code that implements EXACTLY these impacts: {impacts}.
Library API map: {api_map}. Target board FQBN: {fqbn}.
Change nothing else. Keep the Arduino framework (do not port to ESP-IDF).
If an impact cannot be implemented, return it in "unimplemented" with a reason.
```

### P8 Report composer

```text
Write the Desi BOM summary for a {user_level} maker in {lang_ui}.
3–5 sentences: what the project is, total cost and savings, the 1–2 most important changes, any safety warning (use the provided banner text verbatim).
Then ≤ 2 sentences per line for "what changes". Plain words; no jargon without a short explanation.
```

### P9 Narrator text (before TTS)

```text
Rewrite the summary and the changes as a spoken explanation in {language} for a student. Keep part numbers, pin names and units in English (e.g. "GPIO 5", "3.3 volt"). ≤ 120 seconds when read aloud.
```

## 3. Prompt engineering rules

- One prompt file per agent, with a version header (`# v3 2026-10-09`). The prompt version is stored in every job's `model_versions`.
- Put stable context first (preamble, schema, KG excerpt) so implicit caching can kick in.
- Use look-alike lists and few-shot examples from [../04-reference/01-worked-substitution-cases.md](../04-reference/01-worked-substitution-cases.md).
- Prompt changes are regression-tested with the eval set before deploy.
