# Frontend handoff — backend v0.21.0 (sourcing engine)

For the frontend agent or teammate. Read it after
[the v0.20 handoff](frontend-handoff-v0.20.md), whose items still apply. All new fields are
optional, so the current frontend keeps working; until this is built, users see the new
automatic selections without the order plan around them.

**What changed for users.** Sourcing now recommends and **selects parts automatically**,
groups them by seller to save shipping, and gives every line an image. The main screen
after sourcing should be the **order plan**, not a list of offers to pick from.

General rules from v0.20 apply: label estimates, AI judgements and demo data; text plus an
icon, never colour alone; re-read fields from every job snapshot.

**Needed now:** evidence can also have `source: "youtube_description"` with a `quote`
(no timestamp). Extend the v0.20 item 1 fix in `evidenceText()`: render it as
"Video description “quote” — observation". Until then such evidence shows as `null — …`.
Description quotes disappear from responses 30 days after `job.video_meta.fetched_at`
(YouTube API policy); `video_meta.links` lists the description's store and other links.

## Priority order

| # | Item | Size | Contract |
|---|---|---|---|
| 1 | Order plan view (default after sourcing) | M | [recommendations.md](recommendations.md) |
| 2 | Recommended badge, "why" popover, Change, "Your choice" | S | [recommendations.md](recommendations.md) |
| 3 | `line_image` on every line | XS | [recommendations.md](recommendations.md) |
| 4 | Match chips, pack size, variant | S | [part-matching.md](part-matching.md) |
| 5 | Buyable spec panel and "Needs value" prompt | S | [part-matching.md](part-matching.md) |
| 6 | Unsourced group with next steps | S | [recommendations.md](recommendations.md) |
| 7 | Nearby markets card | S | [nearby-markets.md](nearby-markets.md) |
| 8 | Sourcing diagnostics and estimated AI cost | XS | [seller-search.md](seller-search.md), [cost-controls.md](cost-controls.md) |

## 1. Order plan view — `report.order_plan`

The default view once the report is ready. One card per entry in `order_plan.sellers`:

- the lines with `line_image`, quantity and pack rounding, unit price and line price;
- the subtotal, GST and shipping, each with its Known / Estimated / Unknown status;
- "Add ₹`free_shipping_gap_inr` for free shipping" when present;
- product links opening in new tabs (sellers have no cart API, so these are product pages).

Show `order_plan.disclaimer` and the plan total from `order_plan.costing`, never as
"total payable". Lines in a seller card with `selected: false` are recommendations that
could not be applied automatically: show `blocked_reason`.

## 2. Recommendations and overrides

- A **Recommended** badge on lines with `selection_source: "recommended"`, with a **why**
  popover listing `recommendation.reasons`.
- **Change** opens the line's offers. Choosing one calls the existing `/selections`, and
  the line becomes `selection_source: "user"`, labelled **Your choice**. User choices are
  never overwritten by refreshes or spec updates. Grade B offers need the changes
  acknowledged (`accept_changes: true`).
- An offer the spec judge confirmed may be selected with `grade: null`; show its match chip
  (item 4) rather than a grade chip.

## 3. Line images — `lines[].line_image`

Use `line_image` (`url`, `kind`, `label`, `source_url`) for every line, and show `label`.
Reference photos and category illustrations must stay visibly labelled as such.

## 4. Match chips — `offers[].match`, `offers[].pack_qty`

- **Exact** / **Compatible** / **Partial**, labelled "AI match" for `method: "llm_judge"` and
  "Spec match" for `deterministic_shortcut`. Put `reasons` and the quoted `claims` in a
  tooltip or expander. No chip when `match` is null.
- `pack_qty` beside the price: "₹28.91 · pack of 10".
- `match.variant` under the title when present.

## 5. Buyable spec — `items[].buyable_spec`, `lines[].buyable_spec`

Show category, mount with its reason, and params with an "inferred" label and reason.
When `needs_value` is true, show a **Needs value** prompt (with the assumed range from the
project when present) and an edit control that sends `buyable_spec` in a confirm
`update`. A line without a value is never searched blind.

## 6. Unsourced group — `order_plan.unsourced`

Each entry has `name`, `reason`, `message` and `next_steps` (answer the value, open
research candidates, refresh). Show them below the seller cards.

## 7. Nearby markets — `GET /v1/jobs/{id}/markets?pin=560002`

A "Pick it up today" card: ask for the PIN (or use location with permission and send
`lat`/`lng`), then show `summary` with `summary_label`, the `places` with their Maps links,
and `location.label` (PIN results are approximate city centres). **Google Maps
attribution rules are mandatory:**

1. Render `attribution.sources` immediately after the summary and places, in order, as
   links. Nothing in between.
2. They must be viewable within one interaction.
3. Never modify the text "Google Maps".

Handle 422 (`INVALID_PIN`, `PIN_NOT_SUPPORTED` with its hint), 429 `FEATURE_QUOTA` and
503. Demo responses are fictional "(demo)" shops with no sources: label them as a sample.

## 8. Diagnostics and cost

- When a line has no offers, its `sourcing_error.message` now names blocked sellers and
  how many sellers were searched; show it as is. `lines[].seller_search.candidate_urls`
  are unverified leads, never offers.
- Optional: `job.cost_estimate.total_usd` as "Estimated AI cost", never as a charge.

## Not in this release

Seller checkout or carts, compile checks (M9) and the headless renderer proposal
(`roadmap.md` §15).
