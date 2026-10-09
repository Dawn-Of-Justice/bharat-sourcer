# Buyable specs and spec matching (unreleased, branch `mvp/matching`)

## Routing and fallback changes (v0.27.0)

Seller queries use a bounded ladder with model numbers and spelling variants, buying-spec
queries, cleaned names, value/category searches and synonyms. Every candidate is scored
against the original part, including stated values, rather than the relaxed query that
found it. Accessory titles are demoted. This is search relevance, not a compatibility grade.

When a judge call fails or the paid budget is exhausted, deterministic shortcut and cached
verdicts survive. Remaining candidates pass a conservative title gate that normalises
model spellings, passive values, units and plurals while rejecting known conflicts.
Offers admitted by that fallback keep `match: null`; they are not labelled AI-confirmed.
The gate does not establish complete electrical or mechanical compatibility.

Why: on the 2026-10 "Freeform Light-Activated LED Circuit" job a token title match missed an
exact Sharvi 22µF page ("22µF" vs "22uF"), rejected "5mm clear LED" and "LDR (Photoresistor)"
listings for wording, and accepted 0603 SMD chip resistors for a dead-bug soldered build.
Matching is now decided by an LLM **spec judge** that reads each listing like a buyer.
Deterministic code is limited to guardrails: unit normalisation, quote checks, INR/price
sanity and "no inferred prices".

All fields below are additive and optional; older snapshots have them as `null`.

## Buyable spec

`items[].buyable_spec` and `report.lines[].buyable_spec` (`BuyableSpec`):

| Field | Meaning |
| --- | --- |
| `origin` | `ai_inferred` (written by the extraction call, or by the batched spec writer for lines without one), `user` (edited), `seed` (fallback built from the part name only; nothing inferred) |
| `category` | `resistor`, `capacitor_electrolytic`, `capacitor_ceramic`, `led`, `ldr`, `wire`, `diode`, `transistor`, `ic`, `module`, `board`, `sensor`, `connector`, `switch`, `battery`, `other` |
| `mount`, `mount_origin`, `mount_reason` | `tht` / `smd` / `any`; `stated`, `inferred` (with a reason, e.g. "freeform dead-bug soldering needs through-hole parts"), `user` or `default` |
| `params[]` | `name`, `value` as sellers write it, `operator` (`equals`, `at_least`, `at_most`, `between` with `value_max`), server-filled `unit` + `si_value`/`si_value_max` (33kΩ → 33000 `ohm`; 22µF → 2.2e-5 `F`), `required`, `origin` (`stated`/`inferred`/`user`), `reason` |
| `must` | names of required params |
| `prefer` | descriptive words ("clear", "bare") that never block a match |
| `exclude` | listing terms that rule a listing out (SMD codes are added for through-hole resistors, LEDs, diodes and ceramic capacitors) |
| `synonyms` | other seller names (LDR = photoresistor = GL5528; elko = electrolytic) |
| `queries` | 2–4 seller-style searches, used by seller search |
| `needs_value`, `needs_value_reason` | a resistor/capacitor (seed: also inductor) with no value in the source; a `between` range appears only when the project assumptions state one. While it is true no single-value listing is auto-selected (see below) |
| `reasons` | notes, including values the server dropped |

How it is produced: the extraction call (one call per job, no extra call) returns a
`buyable` block per part. The server then normalises units and drops values without a
basis: a `stated` value must appear in the part name, evidence or user requirements; an
inferred resistor/capacitor value must appear in the project context; an inferred mount
or param needs a reason. Unit parsing handles µ/u/micro, Ω/ohm/R, RKM codes (4R7, 4k7, 2M2),
bare `33K` for resistors, k/M, F/uF/nF/pF/mfd, mm, V, W, fractions (1/4W), %, AWG/SWG.

**Spec writer for lines without an AI spec** (added 2026-10-07). Jobs extracted before
buyable specs existed, and lines added or renamed by the user, have `buyable_spec: null`.
When sourcing starts or a refresh runs, the lines this run will source that still have no
spec get **one batched Gemini call for the whole job** (`site: "spec"`, `BS_GEMINI_MODEL`
or `BS_GEMINI_SITE_MODELS.spec`, `thinkingLevel: low`; `BS_SPEC_WRITER_ENABLED`, default
true). It sees the line names, quantities and requirements plus the project summary,
description, power and assumptions, and returns the extraction schema's `buyable` block per
line. The prompt asks it to infer physical suitability from the build (wire for a small
freeform or breadboard circuit: `wire_gauge` 18–24 AWG or 0.5–1 mm diameter, tinned bus
wire; `tht` for hand-soldered builds). The result goes through the same guardrails as
extraction, is saved on `items[].buyable_spec` with `origin: ai_inferred` (so it is paid
once per job; later refreshes reuse it), and is cached per (item text, project hash) in the
shared cache (`spec` namespace, 7 days). A user-saved or renamed-meanwhile line is never
overwritten. The call respects the job budget; on any failure (HTTP error, malformed JSON,
`MAX_TOKENS`, budget) the lines keep seed specs and sourcing continues; a failed batch is
not retried by the same process for 10 minutes.

**Seed specs** (no AI spec): values from the name and the user's own requirements, plus a
deterministic `category` from name keywords (resistor, capacitor by kind or value, LED,
LDR, wire, diode, transistor, IC, module, board, sensor, switch, battery, connector), a
stated `mount` when the name says through-hole/SMD, and `needs_value: true` with a reason
for a resistor, capacitor or inductor whose name gives no value. Seed specs never take the
deterministic shortcut.

Editing: `POST /v1/jobs/{id}/confirm` with `{"op": "update", "line_id": "L02",
"buyable_spec": {...}}` saves it with `origin: "user"` (only normalised, never dropped).
Renaming a line drops an AI spec (it described the old name); sourcing then uses a seed spec.

## Spec judge

One batched Gemini call per BOM line (`site: "judge"`, `BS_JUDGE_MODEL`, default
`gemini-3.1-flash-lite`, `thinkingLevel: low`), only when there are candidates. It sees the
spec, a short project context and up to 8 candidates, each limited to the title, up to 12
spec rows, a 300-char description, an 800-char visible-text snippet, variant names and the
declared price/stock (context only). No call is made when:

- there are no candidates;
- a candidate is a **deterministic shortcut**: the AI/user spec's category, every param
  (after unit normalisation) and the mount are stated in the listing, nothing conflicts and
  no excluded term appears (`method: "deterministic_shortcut"`, status `exact`);
- the verdict is cached for (spec hash, candidate URL, listing content hash), TTL
  `BS_JUDGE_CACHE_TTL_S` (7 days). The cache keeps statuses and listing quotes, not the
  model's reasons;
- the paid-call budget is exhausted.

If the judge is disabled (`BS_JUDGE_ENABLED=false`) or fails (HTTP error, malformed JSON,
`MAX_TOKENS`, budget), the line falls back to the legacy title check and offers have
`match: null`.

### `offers[].match` (`OfferMatch`)

| Field | Meaning |
| --- | --- |
| `status` | `exact` (right part, required params stated and matching, right package), `compatible` (right part; a non-critical param missing or a harmless superset), `partial` (plausible but a key fact is missing or ambiguous; kits), `mismatch` (never returned in offers: those listings are dropped) |
| `score` | 0–1 |
| `matched`, `missing`, `conflicts` | param names |
| `reasons` | short buyer-style reasons (AI-written) |
| `claims[]` | `claim` + `quote`; only quotes found verbatim in the listing are kept |
| `dropped_claims` | claims removed because their quote was not in the listing |
| `variant` | the chosen variant name for multi-variant pages |
| `pack_qty` | pieces in the listing ("pack of 10") |
| `method`, `model` | `llm_judge` or `deterministic_shortcut` |

Server checks can downgrade but never upgrade. `exact`/`compatible` becomes `partial`
(score ≤ 0.6) when:

- no claim has a verified quote;
- the title states a different value (e.g. 10k for a 33k spec);
- the title contains an excluded term (e.g. "SMD");
- a number in the title or a spec row contradicts any spec param after unit normalisation
  (e.g. "4mm Dia Copper Wire" against a 0.5–1 mm diameter, or against 18–24 AWG, which is
  converted to 0.51–1.02 mm). Spool lengths of 10 cm or more are ignored for diameter-sized
  params, and a kit's values count as a range;
- the spec has `needs_value` and the listing is a single fixed value (not a kit or
  assortment): buying it would guess the value.

With `needs_value`, a kit or assortment that passes these checks is capped at `compatible`
(never `exact`). The prompt states the same rules; the server enforces them. Verdicts cached
before these checks are not reused (the cache key has a version). Offers are sorted exact →
compatible → partial.

`offers[].pack_qty` mirrors `match.pack_qty`. The price is always the page's declared price
for the listing (the pack), never a per-piece figure computed by the model.

### Variants and price sources

- Several offers / `AggregateOffer`: the offer whose URL is the page URL is used; otherwise
  the judge picks `variant_id` (its declared price, stock and same-host URL are used) or says
  every variant matches (lowest-price in-stock variant). With neither, the page is skipped.
  An `AggregateOffer` price range without listed offers is never priced.
- Pages whose Product JSON-LD has no offers: OpenGraph `product:price:amount` /
  `og:price:amount` + `product:price:currency=INR`, or microdata `itemprop=price`; exactly
  one distinct price, INR only, not on Shopify (the storefront JSON path handles it).
  `verification: "seller_meta_tags"`.

## What the frontend should show

- A match chip per offer: **Exact** / **Compatible** / **Partial** (label it "AI match" for
  `llm_judge`, "Spec match" for `deterministic_shortcut`), with `reasons` and the quoted
  `claims` in a tooltip or expander. No chip when `match` is `null`.
- `pack_qty` next to the price ("₹28.91 · pack of 10").
- `variant` under the title when present.
- The line's `buyable_spec`: category, mount with its reason, params with an "inferred"
  label and reason, and a **Needs value** warning when `needs_value` is true (show the
  `between` range as "assumed from the project" when present). Offer an edit control that
  sends `buyable_spec` in a confirm `update`.
- `report.lines[].stages` may contain `research_skipped` (the research review did not run
  because a sufficient offer existed or the budget was reached; it is not counted in
  `gemini_calls`).
