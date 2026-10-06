# Frontend handoff — backend v0.20.0

For the frontend agent or teammate. Backend v0.20.0 adds the features below. All new
response fields are optional or default to empty, so the current frontend keeps working.
Item 1 is a small display fix the current UI needs; everything else is new UI.

Each section links the contract doc that owns the details (fields, errors, limits). Read
that doc before building the section. Regenerated types are in [`openapi.json`](openapi.json).

General rules that apply to every item:

- Label everything that is an estimate, a rule check, an AI suggestion or demo data as
  such. Never present prices as payable totals, trust labels as guarantees, or safety
  banners as a full safety review.
- Chips and badges use text plus an icon, never colour alone.
- Re-read new fields from every job snapshot (SSE or `GET /v1/jobs/{id}`); several are
  recomputed after confirmation, chat-accepted edits and spec updates.

## Priority order

| # | Item | Size | Contract |
|---|---|---|---|
| 1 | Render code evidence | XS — needed now | [multi-source-intake.md](multi-source-intake.md) |
| 2 | Safety banners | S | [safety-flags.md](safety-flags.md) |
| 3 | Costing footer, plans, GST chips, import card | M | [costing.md](costing.md) |
| 4 | Confidence chips, conflicts, look-alikes, sources, extra source inputs | M | [multi-source-intake.md](multi-source-intake.md) |
| 5 | Seller trust badges | S | [seller-trust.md](seller-trust.md) |
| 6 | Export buttons, share control, public share page | M | [export-and-share.md](export-and-share.md) |
| 7 | Explain aloud, zoom, parts-bin scan (only when enabled) | M | [gemini-extras.md](gemini-extras.md) |
| 8 | Landing page: Adafruit Learn and maker-blog links | XS | [multi-source-intake.md](multi-source-intake.md) |

## 1. Render code evidence (needed now)

GitHub jobs now return evidence with `source: "code"`, `file`, `line`, `quote` (the line's
text) and `url` (a link to that line). `evidenceText()` in `frontend/src/api.ts` treats
every non-`project_page` entry as video and prints `null — …` for these.

- Add `'code'` to `Evidence.source` and the optional `file?: string | null` and
  `line?: number | null` fields.
- Render code evidence as "Code `file:line` “quote” — observation", linking to `url`,
  labelled "Code".

## 2. Safety banners — `job.safety_flags`

- One banner per flag **above the BOM** on the review page and on the report, in the
  order MAINS, LIPO, HIGH_CURRENT, LEVEL_SHIFT. `severity`: `danger` red, `warning` amber,
  `caution` yellow or blue.
- Show `title` and `message` verbatim, and `guidance` as a checklist. Never collapse a
  MAINS banner.
- Badge the rows in `line_ids` with the flag code; optionally show `triggers` as "why this
  flag" (field + matched text).
- Label: "Automatic safety check, not a guarantee".

## 3. Costing — `report.costing`, `GET /plans`, `POST /import-references`

- **Totals footer:** parts, GST, shipping and total, each with a Known / Estimated /
  Unknown chip and its `assumptions` in a footnote. When the total is unknown, show "at
  least ₹`partial_inr`" and say what is unknown. Always show `disclaimer`. Never say
  "total payable".
- **Per seller:** a row with its threshold ("Add ₹`free_shipping_gap_inr` for free
  shipping"), a link to `policy.source_url` with its `checked_on` date, and a marker on
  unverified policies.
- **Offers:** "GST included", "+ GST" or "GST unclear" from `tax_included`, with
  `tax_evidence` in a tooltip.
- **Plans:** a toggle (Cheapest / Fewest sellers) from `GET /v1/jobs/{id}/plans` that
  previews picks and totals, with an "Apply" button that posts the picks to the existing
  `/selections` endpoint. Plans never change the selection on their own. The endpoint
  returns 409 for jobs without a completed live report.
- **Import card:** only when `import_baseline` exists. Show the landed estimate, the
  formula and the dated assumptions (marked unverified), and savings only when
  `savings_vs_import` is present. Add a per-line "US reference price" input that posts to
  `POST /v1/jobs/{id}/import-references` (`{references: [{line_id, price_usd, source_url}]}`).
  This call counts toward the action budget.
- `costing` is null for demo reports.

## 4. Multi-source intake — confidence, conflicts, look-alikes, sources

- **Confidence chip** on each BOM line from `confidence`: "✓ Verified", "◐ Likely",
  "⚠ Check", with `confidence_reason` in a tooltip. No chip when null.
- **Conflict banner** at confirmation when any line has `conflicts`: "N lines have
  conflicting sources", linking to the lines. On the line, show each `values[]` entry
  with its source and locator (a timestamp, `file:line` or quote linking to `url`) and
  the `message`. The backend never auto-picks a side; the user resolves it by editing.
- **Look-alike warning** on lines with `lookalikes`: "Often confused with SH1106" plus
  `note`. Mark `origin: "ai"` entries as AI-suggested.
- **Sources list** from `job.source_reports` (kind, role, parts found). Show failed extra
  sources with their `error.message`.
- **Create form:** optional "Add another source" inputs, at most 3, sent as
  `sources: [url, …]` on `POST /v1/jobs`. Only one video is allowed per job
  (400 `UNSUPPORTED_SOURCES`).

## 5. Seller trust — `offers[].trust`

- A label badge next to the seller name:
  - `established`: the plain name, optionally a subtle "Established" tag.
  - `verified_basics`: "Verified basics"; when `new_seller`, "New seller · GSTIN
    verified" if `signals.gstin` is set, otherwise "New seller · policies found".
  - `unverified`: "Unverified seller — check before paying", with a "prefer COD" hint.
- A separate "New seller" badge whenever `new_seller` is true.
- "Unusually cheap — check seller" when `signals.price_anomaly` is true. Keep the offer
  visible and selectable.
- An expandable "Why?" list of `reasons`, plus `checked_at`. Show "Trust not checked"
  when `trust` is absent. The GSTIN is checksum-valid only, so never call a seller
  "verified" without qualification.

## 6. Export and share

- **Report page:** "Download CSV" (`GET /v1/jobs/{id}/export.csv`) and "Print / PDF"
  (open `GET /v1/jobs/{id}/export.html` in a new tab). Fetch through the proxy so
  credentials are attached, then save the blob.
- **Share control:** show the state from `GET /v1/jobs/{id}/share`. "Create link" calls
  `POST` and shows a copy box with a frontend URL that embeds the returned `share_token`.
  The token is shown only once, and creating again replaces the old link, so warn about
  both. "Revoke" calls `DELETE`. The CORS allow-list now includes `DELETE`.
- **Public share page:** a route reachable without sign-in that calls
  `GET /v1/shared/{share_token}` through the proxy (the integration key is still
  required) and renders a read-only report: no chat, edit, select, refresh or
  image-generation controls. Show `notice` prominently and the demo label when `demo` is
  true. Handle 404 `SHARE_NOT_FOUND` (revoked or replaced) and 429.

## 7. Gemini extras (hidden unless enabled)

All three are off in production until the owner enables them. Call
`GET /v1/jobs/{id}/extras` once per job view and hide anything disabled.

- **Explain aloud:** a 🔊 button with a language picker (`languages`) and a spinner
  (calls can take tens of seconds), then `<audio controls>` with
  `src = "data:audio/wav;base64," + audio_base64` and the `transcript` with its `label`.
  Show "Demo sample" when `demo` is true. Show `remaining`; handle 429 `FEATURE_QUOTA`.
- **Zoom in:** a button on rows listed in `zoom_line_ids`, only while the job is
  `awaiting_confirmation`. Show "We zoomed into 03:07–03:22: …". When `message_id` is set,
  the existing chat proposal card handles the rename.
- **Scan my parts bin:** a camera or file input (JPEG, PNG, WebP; check
  `scan_max_bytes` and downscale in the browser if larger), posted as base64 JSON
  (`{image_base64}`). Overlay `box_2d` on the local preview for `likely_present` rows,
  and point the user to the proposal card to mark parts "✔ You have this". Say that the
  photo is not stored.

## 8. Landing page sources

The backend now accepts Adafruit Learn guides and a fixed list of maker tutorial blogs
(see the contract for the hosts), besides YouTube, Instructables and GitHub. The landing
page's Article tab currently accepts only Instructables hostnames; widen it to the
supported list. Hackster still returns `SOURCE_UNAVAILABLE`.

## Not in this release

The compatibility rules engine (catalogue-backed grades A, B, C, D and X with "what
changes" findings) is still being built and will ship in a later release with its own
contract. Items that need owner approval are in [`roadmap.md`](../../roadmap.md).
