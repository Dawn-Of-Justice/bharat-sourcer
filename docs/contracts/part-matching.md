# Buyable specs and spec matching (unreleased, branch `mvp/matching`)

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
| `origin` | `ai_inferred` (written by the extraction call), `user` (edited), `seed` (fallback built from the part name only; nothing inferred) |
| `category` | `resistor`, `capacitor_electrolytic`, `capacitor_ceramic`, `led`, `ldr`, `wire`, `diode`, `transistor`, `ic`, `module`, `board`, `sensor`, `connector`, `switch`, `battery`, `other` |
| `mount`, `mount_origin`, `mount_reason` | `tht` / `smd` / `any`; `stated`, `inferred` (with a reason, e.g. "freeform dead-bug soldering needs through-hole parts"), `user` or `default` |
| `params[]` | `name`, `value` as sellers write it, `operator` (`equals`, `at_least`, `at_most`, `between` with `value_max`), server-filled `unit` + `si_value`/`si_value_max` (33kΩ → 33000 `ohm`; 22µF → 2.2e-5 `F`), `required`, `origin` (`stated`/`inferred`/`user`), `reason` |
| `must` | names of required params |
| `prefer` | descriptive words ("clear", "bare") that never block a match |
| `exclude` | listing terms that rule a listing out (SMD codes are added for through-hole resistors, LEDs, diodes and ceramic capacitors) |
| `synonyms` | other seller names (LDR = photoresistor = GL5528; elko = electrolytic) |
| `queries` | 2–4 seller-style searches, used by seller search |
| `needs_value`, `needs_value_reason` | a resistor/capacitor with no value in the source; a `between` range appears only when the project assumptions state one |
| `reasons` | notes, including values the server dropped |

How it is produced: the extraction call (one call per job, no extra call) returns a
`buyable` block per part. The server then normalises units and drops values without a
basis: a `stated` value must appear in the part name, evidence or user requirements; an
inferred resistor/capacitor value must appear in the project context; an inferred mount
or param needs a reason. Unit parsing handles µ/u/micro, Ω/ohm/R, RKM codes (4R7, 4k7, 2M2),
bare `33K` for resistors, k/M, F/uF/nF/pF/mfd, mm, V, W, fractions (1/4W), %, AWG/SWG.

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

Server checks can downgrade but never upgrade: `exact`/`compatible` with no verified quote,
a title stating a different value (e.g. 10k for a 33k spec) or an excluded term in the title
(e.g. "SMD") becomes `partial` (score ≤ 0.6). Offers are sorted exact → compatible → partial.

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
