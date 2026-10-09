# Recommendations, order plan and line images

Status: released in v0.21.0; included in v0.27.0.
Code: `backend/src/bharat_sourcer/recommend.py`, `plans.py`, `images.py` (`line_image`),
and the completion hook in `jobs.py`. All new fields are optional, so older snapshots still
load.

The goal is that the backend **picks the part for the maker** and groups the order by
seller, so after sourcing the user sees a ready plan. They only step in to change a pick,
acknowledge changes, or answer a missing value.

## When recommendations run

| Event | What happens |
| --- | --- |
| Sourcing completes (first run or refresh), in the same transaction that sets `done` | Automatic selections are released, offers are re-graded with project context, then recommendations are recomputed and applied |
| `POST /specs` changes a line | That line's offers are re-graded and its selection is cleared (existing rule); recommendations are recomputed for every line without a user choice |
| `POST /selections` | Marks the line `selection_source: "user"`; nothing else is recomputed, but `order_plan` and `line_image` are rebuilt |
| Any cost update (checkpoint, selection, import prices) | `order_plan` and every `line_image` are rebuilt from the stored state; nothing is re-selected |

Recommendations are deterministic: there is no model call and no network access.

## Offer scoring

`score_offer(line, offer, context)` gives each offer a score from 0 to 1. The score is the
weighted sum of one value per factor, and each factor adds a reason string. The weights
are kept in one table, `recommend.WEIGHTS`:

| Factor | Weight | Values |
| --- | --- | --- |
| Match (`offer.match.status`, matching stream) | 0.30 | exact 1.0 · compatible 0.8 · partial 0.4 · no match info 0.55 (neutral) · **mismatch excluded**. If `match.score` is present, the value is scaled by 0.7 + 0.3 × score |
| Compatibility grade | 0.25 | A 1.0 · B 0.85 · unknown 0.6 (neutral) · C 0.45 · D 0.3 · **X excluded** |
| Stock | 0.15 | in stock 1.0 · not reported 0.6 · preorder 0.3 · **out of stock excluded** while any other listing is not out of stock (otherwise 0.05) |
| Seller trust (`offer.trust.label`) | 0.10 | established 1.0 · verified basics 0.75 · not checked 0.5 · unverified 0.4; a price anomaly halves the value |
| Price | 0.15 | cheapest cost to cover the needed quantity on the line ÷ this offer's cost |
| Freshness (`checked_at`) | 0.05 | ≤ 24 h 1.0 · ≤ 72 h 0.6 · older 0.3 |

There are three more rules:

- **Requirements.** Evidence showing that a declared requirement is not met excludes the offer. If the evidence is missing, the offer is not excluded, but it gets a reason and cannot be auto-selected.
- **Packs.** When `offer.pack_qty` is known (from the matching stream), the cost is `ceil(qty / pack_qty) × price`. The reason states the packs, the unit cost and any spare units. Without `pack_qty`, the listing price is treated as a unit price.
- **Unknown value.** When the line's spec has `needs_value` (the spec it was sourced with, a user edit, or the seed spec from the name), a single fixed-value listing is **excluded** ("a single-value listing would guess it"); only kits and assortments (title says kit, assortment, "30 values"…; a "pack of 10" of one value is not a kit) can be recommended.
- **Acceptable offers** score at least `MIN_ACCEPTABLE` (0.5) and are not excluded. Only acceptable offers are ever recommended.

## Basket rules (order consolidation)

1. Lines the user chose (`selection_source: "user"` with a selection, or a selection saved before this feature) are **fixed**. They still count toward their seller's subtotal and shipping.
2. For every other line, the candidates are the acceptable offers within `SCORE_BAND` (0.1) of the line's best score. Only the best listing per seller is kept.
3. Each combination is ranked by:
   `Σ seller (parts + GST + shipping) + penalty × (sellers − 1)`, with ties going to the higher total score. GST and shipping follow the costing rules (`costing.md`): GST status from the seller page or policy table, shipping from the dated policy table and its free-shipping thresholds. Only for **ranking**, unknown GST is assumed to be the default rate and unknown shipping is assumed to be ₹60, so missing information never looks free. These assumed values are never shown as costs.
4. The penalty (`BS_RECOMMEND_SELLER_PENALTY_INR`, default ₹60) approximates one more shipping fee plus the hassle of another order. An order is split only when splitting saves more than that.
5. The search is exhaustive up to 20,000 combinations. Above that, it uses greedy set cover and the cheapest start, each followed by single-swap improvement passes, and keeps the better result. The `improve` and `fewest_start` helpers are shared with `GET /plans`.

## Selection rule decision

A recommendation is **applied as the selection** only when `/selections` would accept it
without a research approval:

- the offer is in stock;
- it was checked within 24 hours;
- every declared requirement is met by evidence, and none is contradicted;
- its grade is **A or B**, or it has no rule grade and is **judge-confirmed**;
- the line's value is known (`needs_value` is false). A kit recommended for a line without
  a known value is never applied: `blocked_reason` says the value is not known and
  `next_steps` starts with "Choose the value for …". `GET /plans` leaves such lines out.

**Judge-confirmed** means the spec judge ([part matching](part-matching.md)) rated the
listing `exact` or `compatible`, backed by quotes the server found verbatim in the listing
(or by the deterministic shortcut, where structured data states every spec param). Such an
offer counts as meeting requirements that research did not cover, and is selected with
`grade: null`. A rule finding (grade C, D or X) or a requirement the evidence contradicts
always blocks automatic selection, whatever the judge said. `/selections` accepts the same
offers manually.

Unknown specs never get a positive grade, so an offer whose compatibility is unknown and
not judge-confirmed (or graded C or D) is **recommended but not selected**. In that case:

- `recommended_offer_url` and `recommendation` (with its reasons and `blocked_reason`) are set;
- the line still appears in `order_plan` with `selected: false`;
- `report.costing` (selection-based) leaves the line out.

This gives the user a ready plan without presenting an unchecked part as verified.

Grade B offers are applied with `changes_accepted: false` and `changes_required: true` in
the plan. The reasons include "acknowledge the listed changes before ordering". The UI must
show the changes, and an explicit acknowledgement goes through `/selections` with
`accept_changes: true`, which makes the line a user choice.

## `selection_source` and user choices

Each line has these fields:

- `selection_source`: one of
  - `"recommended"`: applied automatically;
  - `"user"`: chosen or cleared through `/selections`;
  - `null`: nothing selected yet.
- `user_offer_url`: the offer the user chose. It is kept across refreshes and spec updates. When `selection_source` is `"user"` and `user_offer_url` is `null`, the user **cleared** the line.

Recomputation never overwrites a user choice:

- **Refresh.** The user's choice is carried onto the refreshed line. When sourcing completes, the user's offer is re-selected if it is still listed and still passes the selection rules (grade B needs re-acknowledging). If it no longer passes, the line stays unselected and the new best offer is only *recommended*.
- **Spec update on the user's own line.** The selection is cleared because the grade it was chosen under no longer holds. The user's offer is restored by the same rule as for a refresh.
- **Cleared line.** It stays cleared and appears in the unsourced group with `cleared_by_user`.

## `report.lines[].recommendation`

| Field | Meaning |
| --- | --- |
| `status` | `recommended` or `unsourced` |
| `offer_url`, `seller` | the recommended listing |
| `score` | 0–1 from the table above |
| `reasons` | one string per factor, plus basket reasons ("grouped with L02, L03 from robocraze.com"; "₹X more than Y, but avoids a separate order …") |
| `blocked_reason` | why it was not applied as the selection (null if it was applied) |
| `unsourced_reason` | `pending` · `needs_value` · `no_offers` · `no_acceptable_offer` · `needs_quantity` |
| `next_steps` | for example "Which resistor value do you need?", or "Research candidate: … (url)" |
| `qty`, `pack_qty`, `packs` | needed quantity and pack rounding |

When the user has chosen a line, the last recommendation stays on it, so the UI can show
"Recommended: X" next to the user's pick.

## `report.order_plan`

The plan is built from each line's selection, or from its recommendation when nothing is
selected. It is `null` for demo reports.

```jsonc
{
  "sellers": [
    {
      "seller": "robocraze.com",
      "lines": [
        {
          "line_id": "L01", "name": "LED", "offer_url": "https://…", "title": "…",
          "qty": 12, "pack_qty": 10, "packs": 2, "units": 20,
          "unit_price_inr": "50.00",      // listing price (per pack when pack_qty is set)
          "line_price_inr": "100.00",
          "selection_source": "recommended", "selected": true,
          "grade": "A", "changes_required": false, "blocked_reason": null
        }
      ],
      "subtotal_inr": "100.00",
      "gst": { "status": "estimated", … }, "shipping": { … }, "total": { … },
      "free_shipping_gap_inr": "899.01",
      "policy": { … },                       // dated policy (costing.md)
      "product_links": ["https://…"]          // one per line; there are no seller cart APIs
    }
  ],
  "unsourced": [
    { "line_id": "L03", "name": "Resistor", "reason": "needs_value",
      "message": "Needs a value: choose resistance for Resistor",
      "next_steps": ["Which resistor value do you need?"], "research_urls": [] }
  ],
  "seller_count": 1,
  "costing": { "basis": "plan", … },     // the same CostBreakdown as report.costing
  "ready": false,                        // true when every needed line is in a seller group
  "disclaimer": "…"
}
```

Unsourced `reason` values:

- `pending`: sourcing or recommendations have not run yet;
- `needs_value`: a missing spec blocks matching, or the part's value is not known and no kit
  was found (next step: "Choose the value for …");
- `no_offers`: no verified listing was found (the research candidates are listed);
- `no_acceptable_offer`: every listing was excluded or scored too low;
- `needs_quantity`: the quantity is unknown;
- `cleared_by_user`: the user cleared the line.

## `GET /v1/jobs/{id}/plans`

This endpoint is unchanged except for two additions:

- `plans[]` now ends with `kind: "recommended"`, the same basket as `order_plan`, with user picks fixed;
- `seller_penalty_inr` reports the penalty used.

`cheapest` and `fewest_sellers` still use only offers that could be selected now (A or B).
`PlanPick.grade` can be `null`, `C` or `D` in the recommended plan, and picks gain `qty` and
`packs`. Plans are still computed on request and never applied.

## `report.lines[].line_image`

Every line gets exactly one image, chosen in this order:

1. **Selected offer photo**: `kind: "selected_offer"`. If there is no selection, or it has no photo, the recommended offer's photo is used (`kind: "recommended_offer"`).
2. **Any other verified offer photo** on the line: `kind: "offer"`, labelled "may differ from the chosen offer".
3. **A page reference image** from `image_candidates` (for example a project-page product photo): `kind: "reference"`, labelled "not necessarily the exact product".
4. **The labelled category illustration** (`kind: "category"`) or a generic illustration (`kind: "placeholder"`). These are inline SVG `data:` URLs.

Research candidates do not carry images in the current schema, so step 3 uses only
`image_candidates`. `GET /images` (see [part images](part-images.md)) still works and now lists
the selected or recommended offer's photo first. If a `line_image` URL fails to load, the
frontend should fall back to `GET /images` with `failed_urls`.

Images are visual references only. They never establish identity, specs or compatibility.

## What the frontend should show

- An **Order plan** view (the default after sourcing) grouped by `order_plan.sellers`. Each seller card shows:
  - the lines with their image, quantity and pack rounding, unit and line price;
  - the subtotal, GST and shipping (with their known, estimated or unknown status);
  - "Add ₹X for free shipping" from `free_shipping_gap_inr`;
  - the product links, opened in new tabs (there is no seller cart API, so "cart links" are product pages).
- A **Recommended** badge on `selection_source: "recommended"` lines, with a **why** popover listing `recommendation.reasons`. A recommendation that is not selected (`selected: false`) shows `blocked_reason` and is not counted as chosen.
- A **Change** action that opens the line's offers. Choosing one calls `/selections` and turns the line into a user pick, labelled "Your choice". Grade B needs the changes acknowledged (`accept_changes: true`).
- An **Unsourced** group showing each line's `message` and `next_steps` (answer the value, open research candidates, refresh).
- Every line uses `line_image` and shows its `label`. Illustrations and reference images must stay visibly labelled.

All prices are seller-published at `checked_at`. Totals are estimates, not a payable
amount. Demo reports have no plan, and their fixture data is never presented as
recommended.
