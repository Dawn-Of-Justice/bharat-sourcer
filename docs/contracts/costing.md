# Costing, cart plans and import comparison

Implements M10 (costing), S5 (cart optimiser) and the cost part of S10 (import card).
All arithmetic is Python `Decimal`, rounded half-up to paise for each amount shown.
Nothing here is a final payable or checkout total. `report.total_inr`, `shipping_inr` and
`tax_inr` stay `null`, and every estimate carries its assumptions.

## Status of an amount

Each amount is a `CostAmount`:

| Field | Meaning |
|---|---|
| `amount_inr` | Decimal string, or `null` when `status` is `unknown` |
| `status` | `known`: seller-published or seller-declared. `estimated`: comes from a dated rule or assumption below. `unknown`: no sourced rule, so it is never shown as zero |
| `partial_inr` | Only when `unknown`: the sum of the parts that could be estimated. Show it as "at least ₹X + unknown" and never as a total |
| `assumptions` | Plain-text reasons. Render them in a footnote or tooltip |

When amounts are combined, the result takes the worst status (`unknown` > `estimated` > `known`).

## GST on offers

`offers[].tax_included` is `true`, `false` or `null`. `offers[].tax_evidence` holds the
declaration that was read. Detection is deterministic (`sourcing/tax.py`):

- JSON-LD `valueAddedTaxIncluded` on the Offer or its `priceSpecification`. The value can
  be a boolean or the string `"true"`/`"false"`, and the WooCommerce `{"0": {...}}` shape
  is handled.
- Fixed page phrases: "incl. GST", "inc GST", "inclusive of all taxes", "GST included"
  (included); "excl. GST", "Exclusive GST", "+ GST", "plus GST", "GST extra" (excluded).
- Phrases that follow "MRP" are ignored. The legal MRP line ("MRP … inclusive of all
  taxes") does not describe the selling price.
- If the signals disagree, the value is `null` and the evidence starts with "Conflicting".

Line GST in costing, in order:
1. If the offer declares GST included, the extra GST is 0 (`known`).
2. If the offer declares GST excluded, the extra GST is price × qty × rate (`estimated`).
3. If the offer says nothing, the seller policy table's `prices_include_gst` is used when
   that entry is not unverified (`estimated`).
4. Otherwise the GST is `unknown`.

GST rate: **18% for all categories, assumed, not tax advice.** The rate is in
`backend/src/bharat_sourcer/data/tax_rates.json` (`gst.by_family` can override it by
`specs.family`). The source is a secondary HSN listing
(https://www.credlix.com/hsn-code/8542, 18% for HSN 8542 after the 22 Sep 2025 GST changes,
checked 2026-10-06). It has not been checked against the CBIC rate notification.

## Shipping (per seller)

`backend/src/bharat_sourcer/data/seller_policies.json` is keyed by host without `www.`.
Each entry has `free_above_inr`, `free_when` (`above` or `at_or_above`), `flat_fee_inr`,
`fee_plus_gst`, `source_url`, `checked_on`, a verbatim `quote`, and `unverified`.

| Seller | Free shipping | Fee below | GST on prices | Status |
|---|---|---|---|---|
| robocraze.com | above ₹999 | not stated (location-based) | included ("Incl. GST") | checked 2026-10-06 |
| quartzcomponents.com | more than ₹500 (prepaid) | ₹50 | not stated | checked 2026-10-06 |
| evelta.com | over ₹1000 (sub-total before tax) | ₹45 + GST | excluded | checked 2026-10-06 |
| compoindia.com | on or above ₹2000 | not stated | excluded ("Exclusive GST Tax 18%") | checked 2026-10-06 |
| electronicscomp.com | above ₹499 | not stated | not stated | checked 2026-10-06 |
| flyrobo.in | conflicting (₹499 on homepage, ₹1000 on delivery page) | – | included ("inc GST") | shipping **unverified** |
| rytronics.in | above ₹499 with coupon FREESHIP | – | included ("inc. GST") | shipping **unverified** |
| zbotic.in, silicontechnolabs.in | ₹999 per earlier research notes | – | – | **unverified** |

Rules:
- If the seller has no entry, or its shipping entry is unverified, shipping is `unknown`.
  An unverified entry's note is shown as an assumption. It is never used for an amount.
- The threshold is compared with the seller's listed-price subtotal for the chosen lines.
  At or over the threshold, shipping is `0.00` `estimated`. Below it, shipping is the flat
  fee (plus 18% when `fee_plus_gst`) `estimated`, or `unknown` when no fee is stated.
- `sellers[].free_shipping_gap_inr` is how much more to spend at that seller for free
  shipping (it includes the extra ₹0.01 when the policy says "more than").
- Prepaid orders are assumed. COD fees and PIN-code serviceability are not included.

## `report.costing` (selected offers)

The backend recomputes this on every cost update: selection, refresh, spec change and
import-reference change. It is `null` for demo reports and for reports saved before this
change.

```json
{
  "basis": "selected_offers",
  "complete": false,
  "excluded_line_ids": ["L02"],
  "sellers": [{
    "seller": "evelta.com", "line_ids": ["L01"],
    "parts":    {"amount_inr": "200.00", "status": "known", "partial_inr": null, "assumptions": ["Listed seller prices at checked_at"]},
    "gst":      {"amount_inr": "36.00", "status": "estimated", "assumptions": ["L01: seller policy table (checked 2026-10-06) says the price excludes GST; added 18% (assumed rate, not tax advice)"]},
    "shipping": {"amount_inr": "53.10", "status": "estimated", "assumptions": ["evelta.com: flat shipping ₹45.00 + 18% GST below ₹1000.00 per policy checked 2026-10-06"]},
    "total":    {"amount_inr": "289.10", "status": "estimated"},
    "free_shipping_gap_inr": "800.01",
    "policy": {"seller": "evelta.com", "free_above_inr": "1000.00", "flat_fee_inr": "45.00", "source_url": "https://evelta.com/shipping-returns/", "checked_on": "2026-10-06", "unverified": false}
  }],
  "parts": {...}, "gst": {...}, "shipping": {...}, "total": {...},
  "import_baseline": null,
  "savings_vs_import": null,
  "rates_checked_on": "2026-10-06",
  "disclaimer": "Estimate from seller-published prices and dated policy and tax assumptions; not a final payable total. Check the seller's checkout."
}
```

`complete` is true only when every unowned line has a selection. Lines selected through
research approval (no A/B grade) are included in the costing.

## Import comparison (S10)

`costing.import_baseline` appears only when at least one unowned line has a USD reference
unit price. The price comes from either:
- `lines[].import_reference` set by the user (`source: "user"`), or
- a research fact (`source: "research_fact"`): an `exact` candidate in `ready` research
  with a fact whose name contains "price" and whose value is one USD amount (`$4.95`,
  `USD 12`, or `4.95` with unit `USD`). Pack sizes, ranges and other currencies are rejected.

Formula (shown in `formula`):

```
goods      = Σ price_usd × qty × FX            courier = courier_usd × FX
assessable = goods + courier                   (CIF approximation, no insurance)
BCD = 10% × assessable   SWS = 10% × BCD   IGST = 28% × (assessable + BCD + SWS)
landed = goods + courier + (BCD + SWS + IGST)
```

Assumptions (in `tax_rates.json`, every one dated):

| Item | Value | Source / status |
|---|---|---|
| Heading 9804 personal imports by courier: BCD 10%, SWS 10% of BCD, IGST 28% (42.08% total) | | Chennai Customs FAQ, Oct 2025 (https://chennaicustoms.gov.in/wp-content/uploads/2025/10/Faq.pdf), checked 2026-10-06. **Unverified**: the 22 Sep 2025 GST changes removed the 28% slab for most domestic goods, and whether IGST on 9804 changed has not been confirmed against a CBIC notification (roadmap V13) |
| FX | USD→INR 95.99 | RBI reference rate for 2026-10-01 via MSEI. Customs uses the CBIC-notified rate, so the figure may differ |
| Courier | $30 per order | **Placeholder, unverified**. Calibrate it with real quotes |
| Duty-free threshold | none applied | The FAQ gives none for courier imports |

`import_baseline.complete` is true when every unowned line has a reference price.
`savings_vs_import` (`landed − India total`; positive means India is estimated cheaper)
appears only when the baseline is complete, every line is selected and the India total
is not `unknown`. "Days saved" is not computed, because no sourced delivery-time
assumption exists.

### `POST /v1/jobs/{job_id}/import-references`

Requires `X-Job-Token`. Only completed live reports can be updated; other jobs get 409
`INVALID_STATE`.

```json
{"references": [{"line_id": "L01", "price_usd": "4.95", "source_url": "https://distributor.example/p"}]}
```

`price_usd` must be positive. `null` or an omitted value clears that line's reference.
1–100 distinct unowned lines can be sent. An unknown, repeated or owned line, or a price
of zero, returns 422 `INVALID_REFERENCE`, and the batch is atomic. The response is the
updated Job. A refresh of a line clears its reference, along with its offers and selection.
This is a POST, so it counts toward the job action budget like other actions.

## Cart plans (S5): `GET /v1/jobs/{job_id}/plans`

Requires `X-Job-Token`. Only completed live reports are accepted; others get 409
`INVALID_STATE`. Plans are computed when requested and are not stored. **They never change
selections.** To apply a plan, post its picks to `/selections`. Picks with
`changes_required: true` (grade B) need `accept_changes: true`.

```json
{
  "method": "exhaustive",
  "uncovered_line_ids": [],
  "rules": ["..."],
  "plans": [
    {"kind": "cheapest", "seller_count": 2, "matches_selection": false,
     "picks": [{"line_id": "L01", "offer_url": "...", "seller": "evelta.com", "price_inr": "200.00", "grade": "A", "changes_required": false}],
     "costing": {"basis": "plan", "...": "same shape as report.costing, without import fields"}},
    {"kind": "fewest_sellers", "...": "..."}
  ]
}
```

- Eligible offers are the ones that could be selected now: in stock, checked within 24
  hours, grade A or B, and meeting any declared requirements. Research-only matches need
  explicit user approval and are left out. A line with no eligible offer is listed in
  `uncovered_line_ids`, and the plan's `costing.complete` is false.
- For each line, only the cheapest offer from each seller is considered.
- `cheapest` is ranked by fewest unknown seller totals first, then the lowest estimated
  total. Shipping thresholds are included, so it can move a line to a pricier seller to
  pass a free-shipping threshold.
- `fewest_sellers` is ranked by fewest distinct sellers, then like `cheapest`.
- `method` is `exhaustive` when there are 20,000 seller combinations or fewer. Otherwise it
  is `greedy`: cheapest-per-line or a greedy seller set cover, then at most 10
  single-line improvement passes. `none` means no line had an eligible offer.

## What the frontend should render

- A totals footer with parts, GST, shipping and total, each with a status chip (Known /
  Estimated / Unknown) and the assumptions in a footnote. When the total is unknown, show
  "at least ₹`partial_inr`" and name what is unknown. Always show `disclaimer`. Never say
  "total payable".
- A row per seller with its threshold ("Add ₹`free_shipping_gap_inr` for free shipping"),
  plus a link to `policy.source_url` and its `checked_on` date. Mark unverified policies.
- On offers, show "GST included", "+ GST" or "GST unclear" from `tax_included`, with
  `tax_evidence` in a tooltip.
- A plan toggle (Cheapest / Fewest sellers) that previews the picks and totals, with an
  "Apply" button that posts `/selections`.
- An import card, only when `import_baseline` exists: the landed estimate, the formula,
  the dated assumptions (marked unverified), and savings only when `savings_vs_import` is
  present. Allow entering a USD reference price per line.
