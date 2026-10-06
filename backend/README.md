# Backend

The integration deployment was observed on 5 October 2026 with Firebase account and
guest authentication enabled. The frontend origin is included in CORS. The
`BS_AUTH_ENABLED=false` setting shown below remains the default for a fresh local setup.

v0.20.0 closes most of the planned MVP gaps. Deterministic [safety flags](../docs/contracts/safety-flags.md)
(MAINS, LIPO, HIGH_CURRENT, LEVEL_SHIFT) appear on every job. [Costing](../docs/contracts/costing.md) adds
GST detection, dated seller shipping policies, a per-seller breakdown with known/estimated/unknown
status, cart plans (`GET /plans`) and an optional import comparison. [Multi-source intake](../docs/contracts/multi-source-intake.md)
reads Adafruit Learn guides, a fixed list of maker blogs and GitHub code files, merges up to three
extra `sources` per job, and flags conflicts, look-alikes and per-line confidence.
[Seller trust](../docs/contracts/seller-trust.md) labels offers from free signals (RDAP domain age,
GSTIN checksum, HTTPS, policies, price anomalies) and adds a Shopify/WooCommerce JSON fast path.
[Export and share](../docs/contracts/export-and-share.md) adds CSV, printable HTML and revocable
read-only share links. [Gemini extras](../docs/contracts/gemini-extras.md) (explain aloud, clip zoom,
parts-bin scan) ship disabled. A curated [parts catalogue and rules engine](../docs/contracts/compatibility-rules.md)
resolves BOM names and grades offers A, B, C, D or X with "what changes" findings. The [evaluation gold set](../docs/contracts/evaluation-gold-set.md) is an
unreviewed agent draft; no accuracy figure is claimed. Items needing owner approval are in
[`roadmap.md`](../roadmap.md).

Cost controls (unreleased, branch `mvp/cost`): a cross-job shared cache
(`sourcing/cache.py`), research skipped when a verified in-stock compatible offer exists,
capped research text, refresh that re-fetches known offer pages before any paid search, a
per-run Gemini budget (`BS_JOB_GEMINI_BUDGET_USD`, default $0.25), low thinking for
classifier-like call sites and an estimated `job.cost_estimate`. See
[cost controls](../docs/contracts/cost-controls.md).

v0.19.3 counts grounding search queries in usage logs (Gemini 3 bills per query), logs the
Gemini cost research, and defaults image generation to `gemini-3.1-flash-lite-image`.

v0.19.2 logs Gemini token usage per call site (`GEMINI_USAGE` lines) and adds
`scripts/usage_report.py`; see the [Gemini cost log](infra/gemini-cost.md).

v0.19.1 tightens inferred requirements after a live check: they must be measurable specs
with units (resistance, voltage, connector…), not restated part types, and reasoned values
go into the part's requirements. Possibly missing parts are listed as assumptions only.

v0.19.0 makes extraction understand the project before listing parts: `job.project` holds
an AI-written, owner-editable title and description, a non-editable summary of how the
build works, and its power, controller, interfaces and assumptions. Missing quantities are
decided from project context (`qty_source: inferred` with `qty_reason`) instead of
blocking confirmation, and each part gets inferred requirements (`origin: inferred`, with
a reason) that feed research. `POST /v1/jobs/{id}/project` edits the title/description;
`GET /v1/projects` returns them. See [project understanding](../docs/contracts/project-understanding.md).

v0.18.1 makes Instructables extraction work (their pages are client-rendered; the backend
reads the project JSON the page itself loads, allowed by robots.txt), strips page
boilerplate, and replaces Python's robots parser, which silently ignored some sites' rules
and wildcards. Hackster blocks automated access (Cloudflare 403) and now returns a clear
`SOURCE_UNAVAILABLE` message. Seller parsing was evaluated on 17 trimmed real Indian seller pages
([findings](infra/seller-page-evaluation.md)); fixes cover inch notation in titles,
label-unit supply ranges and percent-escape URL comparison.

v0.18.0 accepts public Instructables, Hackster and GitHub repository URLs in live mode and
extracts a BOM from the page text (README for GitHub). Page evidence carries a quote the
server found verbatim in the fetched page, plus its URL. It also adds an offline extraction
evaluation harness (`scripts/evaluate_extraction.py`); no real labelled set exists yet,
so no accuracy figure is claimed. A live check on 5 October 2026 extracted 21 quoted parts
from the `scottbez1/smartknob` README in 10 seconds; the landing page now enables GitHub
links. A second live check extracted 13 quoted parts from an Instructables project in 7 seconds;
the Article tab now accepts Instructables links. Hackster remains unsupported (Cloudflare 403).

v0.17.11 posts a deterministic chat summary when a chat-approved refresh finishes and keeps
a bounded `job.actions` history of proposal decisions. See [chat actions](../docs/contracts/chat-actions.md).

v0.17.10 ranks grounded discovery sources before the per-part fetch limit: known Indian
retailers and `.in` domains first, datasheet hosts and global distributors that block reads
last. Production data showed most "no verified offers" parts had spent their five fetches
on TTI, Mouser, DigiKey, LCSC and datasheet PDFs. Ranking only reorders grounded URLs.

v0.17.9 lets chat propose spec/requirement changes for completed reports; they apply only
after approval. See [chat actions](../docs/contracts/chat-actions.md).

v0.17.8 fixes missing seller images: storefront placeholder images (such as Shopify's
`no-image` asset, returned for every Robocraze product) are rejected, and a verified
single-product page falls back to its `og:image`/`twitter:image` metadata (same-host
`http` is upgraded to `https`). Offers saved before v0.15 have no `image_url`; refresh
those parts to collect images.

v0.17.7 reads seller specification tables and common JSON-LD property labels, and reports
seller-source disagreements as `spec_conflicts` instead of silently dropping them.

v0.17.6 bounds the scheduled queue sweep, isolates per-job enqueue failures and logs
`QUEUE_AGE_EXCEEDED` for stuck work. See [durable dispatch](../docs/contracts/queued-dispatch.md).

v0.17.5 matches plural part names ("Resistors", "Jumper wires") to category
illustrations. Merges to `main` now deploy to Cloud Run automatically.

v0.17.4 adds part image fallbacks: matching page product photos, labelled SVG category
illustrations and opt-in AI illustrations with separate daily quotas. Image requests do not
consume the project action quota. See the [image handoff](../docs/contracts/frontend-image-handoff.md).

v0.17.3 preserves grounded discovery URLs when Gemini ends with MAX_TOKENS,
while keeping downstream evidence verification and blocked-response rejection.
See [the sourcing investigation](../docs/contracts/sourcing-incident-2026-10-05.md).

v0.17.2 checks Firebase account status for disabled/deleted users and revoked
sessions on each authenticated request. Provider outages fail closed with 503.
The runtime identity needs `firebaseauth.users.get`; see the auth rollout guide.

v0.17.1 adds `GET /v1/session/usage` for remaining personal quotas and reset times,
and returns the applicable quota reset delay in `Retry-After` on usage rejection.

v0.17.0 adds optional Firebase Google authentication, signed guest sessions,
owner-scoped saved projects, guest-to-account claims and shared usage limits.
Authentication defaults to disabled until the frontend proxy and Firebase setup
are ready. See [authentication and rollout](../docs/contracts/authentication.md).

v0.16.1 adds one bounded alternative-source search when no verified offer or research
evidence is available. Unreadable pages no longer consume the document-review budget.
See the [research limits and cost controls](../docs/contracts/part-research.md).

v0.16 adds [general part research](../docs/contracts/part-research.md): arbitrary
categories, source-linked facts, AI suitability assessments, flexible user requirements,
and deterministic comparisons. Research candidates survive missing structured offers.
Chat can answer from these results. The frontend needs the documented research cards
and requirement controls; research candidates are separate from verified price offers.

v0.15 adds optional seller product image URLs to verified offers. The frontend can
display these directly; image metadata is optional and never affects offer verification.

v0.14 adds a project-scope chat gate, three concurrent sourcing lines per batch,
explicit seller variant verification and useful no-offer diagnostics.
See [behavior and limits](../docs/contracts/project-chat-and-sourcing.md).

GitHub Actions checks backend changes and deploys successful `main` builds to
Cloud Run. See [CI/CD setup and first run](infra/github-actions.md).

v0.13 supports [Cloud Tasks dispatch and scale to zero](../docs/contracts/queued-dispatch.md).
Local development retains background tasks; cloud execution uses authenticated HTTP workers.

v0.12 adds [user-approved chat refresh proposals](../docs/contracts/chat-actions.md).
Approval atomically queues a scoped refresh with existing limits and stale-report checks.

v0.11 adds persisted sourcing pause/resume at part checkpoints. Chat remains available;
see [frontend controls and limitations](../docs/contracts/pause-resume.md).

Python + FastAPI, with an isolated package, virtual environment, tests and configuration.

## Run locally (PowerShell)

From the repository root, using Python 3.12 or newer:

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.venv/Scripts/python -m uvicorn bharat_sourcer.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux use `.venv/bin/python` in place of `.venv/Scripts/python`.

Open `http://127.0.0.1:8000/docs` for interactive requests, or `/healthz` for health.
Demo mode needs no credentials or cloud services. Environment variables use the `BS_` prefix;
`.env` is loaded from the working directory (`backend/`).

`requirements-dev.lock` pins the tested runtime and development dependencies. Update it
deliberately when upgrading dependencies, then rerun checks and regenerate OpenAPI.

## Implemented workflow

1. `POST /v1/jobs` accepts an HTTP(S) project URL and returns a job ID and secret job token.
2. A background task loads a fixed BOM in demo mode, or in live mode extracts a public YouTube
   video or a supported project page (Instructables, Hackster, GitHub repository README).
3. `POST /v1/jobs/{id}/confirm` applies all edits atomically.
4. In live mode, grounded search discovers seller pages and the verifier reads product offers.
5. `GET /v1/jobs/{id}` returns state, errors, events and the incremental report.

Send `X-Job-Token` on reads and confirmations. Keep that token in the client session and
out of URLs/logs. It is a local capability token, separate from the planned Firebase Auth.

In demo mode, all URLs receive the same fixture. URLs are validated but never fetched.
`demo: true` marks the response; prices, totals and compatibility grades are `null`.
`done` means processing finished. Inspect each report line for sourcing success or failure.

## Live YouTube extraction

In `backend/.env`, set:

```dotenv
BS_DEMO_MODE=false
BS_GEMINI_API_KEY=your-key-here
BS_GEMINI_MODEL=gemini-3.8-flash
BS_EXTRACTION_TIMEOUT_S=120
```

Keep the real key in the ignored `.env` file. Restart the server, then submit a public
YouTube `watch`, `youtu.be`, `shorts`, or `embed` URL, or a supported project page (see
[Project page extraction](#project-page-extraction)). Other sources return HTTP 400
`UNSUPPORTED_URL` in live mode. The backend sends a canonical YouTube URL to Gemini; it does
not download video locally or fetch arbitrary URLs. Live requests can incur Gemini usage charges.

The adapter uses `generateContent`, structured JSON output, and local Pydantic validation.
The default model appears in Google's [model catalog](https://ai.google.dev/gemini-api/docs/models).
Google documents direct YouTube input as a preview feature in its
[video guide](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding).
The [REST reference](https://ai.google.dev/api/generate-content) documents the request fields.
This first adapter does not yet use ADK or agentic video processing.

Live responses have `demo: false` and `extraction_model`. Each extracted line carries
model-reported `evidence` (timestamp and observation), which must be reviewed rather than
treated as independently verified. Counts the source does not state are
decided from project context and labelled `qty_source: inferred` with a `qty_reason`. User edits retain the original
evidence and set `user_edited: true` so the UI can distinguish them.

Errors transition the job to `failed` with a sanitized `error.code` and message. There
are bounded transient retries as described below, with no demo fallbacks. HTTP read timeout
is configurable; output is limited to 8,192 tokens and validated to at most 100 parts.
Compatibility is limited to declared-spec comparisons described below. Parts costing is available
after offer selection, with labelled GST and shipping estimates; the final payable total is never
claimed.

## Project page extraction

Live mode also accepts these project URLs (HTTP or HTTPS; query and fragment are dropped):

| Source | Accepted URL | Document fetched |
| --- | --- | --- |
| Instructables | `instructables.com/<slug>/` or legacy `/id/<slug>/` | `https://www.instructables.com/json-api/showInstructableModel?urlString=<slug>` (cited as `https://www.instructables.com/<slug>/`) |
| Hackster | `hackster.io/<user>/<project>` | `https://www.hackster.io/<user>/<project>` |
| GitHub | `github.com/<owner>/<repo>` (optional `.git`) | first of `README.md`, `readme.md`, `README.rst`, `README` at `https://raw.githubusercontent.com/<owner>/<repo>/HEAD/`, then up to 8 code/build files for deterministic code evidence |
| Adafruit Learn | `learn.adafruit.com/<guide>` (or `/<guide>/<page>`, `/<guide>.md`) | `https://learn.adafruit.com/<guide>.md?view=all` (cited as `<guide>?view=all`) |
| Tutorial blog | an article on a listed maker blog (Random Nerd Tutorials, DroneBot Workshop, Last Minute Engineers and others) | the page, reduced to its main article content |

A job may also carry up to three extra `sources` (at most one video in total); each is
extracted separately and fused into one BOM with `conflicts`, `lookalikes` and a
deterministic `confidence` per line. Rules, limits and fields:
[multi-source intake](../docs/contracts/multi-source-intake.md).

Other hosts, Instructables category/member/asset paths and multi-segment paths, GitHub
file/tree/gist URLs, Hackster section pages and reserved GitHub paths return HTTP 400
`UNSUPPORTED_URL`. Demo mode is unchanged: every URL gets the fixture and
nothing is fetched.

Pages are fetched only through the guarded `SafeFetcher` (HTTPS, public-address pinning,
robots.txt, 3 MB response limit, bounded redirects). A redirect must stay on the
source's host. HTML is reduced to visible text: scripts, styles, `nav`, `footer`, `aside`,
forms, buttons, hidden elements, ARIA navigation/banner/complementary regions and
`#comments`/`#related` blocks are removed, and a section whose heading is boilerplate
("Comments", "Credits", "You might also like", "Related projects", "Share" and similar) is
dropped up to the next heading of the same or higher level. Plain-text/Markdown READMEs are
used as text.

Instructables project pages are client-rendered: the server HTML is an empty React shell
(title only), so scraping it yields no parts. The page loads its content from the public
`/json-api/showInstructableModel` endpoint, which robots.txt allows; the backend fetches that
JSON and builds the text the page renders: title, `Supplies`, then the introduction and
`Step N: <title>` with each step body. Supplies come first, so the character budget trims late
steps rather than the parts list. Comments and related projects are not in this document.
Evidence `url` is the canonical project page, not the JSON endpoint. Drafts and responses
without steps give "no readable text". The text is bounded by
`BS_PROJECT_PAGE_CHARS` (default 60,000 characters) and sent to Gemini as JSON data with a
prompt that treats it as untrusted. The model returns, per part, evidence entries with a
verbatim `quote` and an `observation`. The server keeps evidence only when the
whitespace-normalised quote appears (case-sensitively) in the exact text sent to the model.
Parts left with no verified quote are dropped and lines are renumbered; if none remain the
job fails with `NO_BOM`. Fetch problems fail with `SOURCE_UNAVAILABLE` before any Gemini call
(robots refusal, non-200 status, missing README, off-host redirect, no readable text). HTTP
401/403/429/451/503 responses say the site refused automated access and include the status.

robots.txt is parsed with the stdlib parser after removing blank and comment-only lines
(which otherwise end a group early: Hackster's `User-Agent: *` group was being ignored), with
RFC 9309 `*`/`$` patterns and longest-match precedence (Allow wins ties). Sites whose
crawl-delay or request rate exceeds one request per second are still skipped.

Live-site status, checked 5 Oct 2026 with plain GETs from the development sandbox:

| Site | robots.txt for our user agent | Crawl-delay / rate | Fetch result |
| --- | --- | --- | --- |
| Instructables | project pages and the `json-api` model endpoint allowed (only `*.pdf`, `*.txt`, `*.html`, `/file/`, `/howto/`, `/image/` disallowed) | none for `*` (1 s only for Slurp) | JSON 200 for three projects; parsing covered by trimmed real fixtures |
| Hackster | `/<user>/<project>` allowed (`/projects/*`, `/users/*`, `/search*`, `*/*/embed` disallowed) | none | HTTP 403 Cloudflare "Attention Required" for every project page tried, with any user agent; listing pages return 200 |

Hackster extraction therefore fails with `SOURCE_UNAVAILABLE` ("refused automated access
(HTTP 403)") from that network, and no workaround is attempted. Whether production egress
is also blocked has not been checked. The Hackster parsing test uses a labelled synthetic
page modelled on the public section layout, not a captured page. No live Gemini call was
made for either site; only GitHub README extraction has passed a credentialed live check.

Page evidence has `source: "project_page"`, `quote`, `url` (the fetched document, e.g. the
raw README) and `timestamp: null`. Video evidence now also reports `source: "video"` with
`quote` and `url` null. Snapshots saved before this change have no `source` and still
validate as video evidence. A verified quote shows that the page mentions the text; the
part identity, quantity and suitability still need human review. A job uses one source;
video and page evidence are not merged and conflicts between them are not detected yet.
Code files other than the README are not read.

Automated tests use a mocked HTTP transport. A credentialed smoke test on 2 Oct 2026
successfully extracted four parts from YouTube Short `qSRrq_VZ4Fw` and reached
`awaiting_confirmation` in about eight seconds. This validates connectivity and response
parsing, not the accuracy or completeness of the BOM.

The live endpoint rejected the full Pydantic generation schema with HTTP 400. The adapter
now sends an inline schema without bounds or string constraints, then applies the full
Pydantic validator locally. Invalid quantities, timestamps, oversized results and extra
fields are still rejected. Public API schemas retain their validation constraints.

Jobs use memory storage by default, disappear on reload/restart, and require **one worker**
in that mode. For persistence, follow [Firestore setup](infra/README.md) for project
`hackathon-510415`, then select `BS_STORAGE_BACKEND=firestore`. Firestore stores jobs,
events, parts, reports and token hashes in private snapshots. Existing API routes still
work; the frontend does not need direct Firestore access.

A startup/periodic sweep resumes queued work and report creation. Expired work gets one
automatic recovery attempt per job, which can repeat a billed API request. Use this
server locally until durable task dispatch, retention, rate limits and Firebase
Auth/App Check are ready for public deployment. Firestore cloud access was verified on
2 Oct 2026 against `hackathon-510415` in Mumbai. Other developer machines need Application
Default Credentials; see the setup guide.
Live mode fails startup if `BS_GEMINI_API_KEY` is missing or empty.

## Extraction quality evaluation

`bharat_sourcer/evaluation.py` and `scripts/evaluate_extraction.py` score saved pipeline
results against labelled cases. **No human-reviewed labelled set exists yet**, so no
extraction accuracy figure has been measured. Two sets ship with the code:

- `evaluation/example_cases.json` and `evaluation/example_predictions/`: invented, marked
  `"synthetic": true`; they only demonstrate the file format.
- `evaluation/gold/`: an **agent-drafted** gold set for the 15-project evaluation plan
  (14 text projects transcribed from their public pages on 6 October 2026, plus 5
  candidate YouTube videos with empty BOMs). Every file is labelled
  `agent_draft_needs_human_review` or `needs_human_labelling`. It is not human gold; see
  [evaluation gold set](../docs/contracts/evaluation-gold-set.md) for the format, review
  workflow and status.

A case set is JSON with a required `synthetic` flag, a `description`, optional
`label_status`, `labelled_by`/`labelled_on`, and `cases`. Each case has an `id`, a `url`,
a `source_type` (`video`, the default, needs a YouTube URL; `page` accepts any public
http(s) project page) and `parts`. Each part has a canonical `name`, optional `aliases`, a
`qty` (`null` when the labeller could not establish it), a `qty_unit` (`pcs` by default;
`mm`/`cm`/`m` for lengths), optional `evidence_windows` (`MM:SS` start/end) and optional
gold-format detail (`canonical_chip`, `module`, `category`, `notes`). Cases may also carry
`must_flag` (`MAINS`, `LIPO`, `HIGH_CURRENT`, `LEVEL_SHIFT`) and `gold_substitutions`
(`original`, `aliases`, `acceptable`, `required_changes`, an inclusive `grade_range` such as
`["C", "X"]`, optional `case_ref` to the worked substitution cases). `--cases` also accepts
a gold `index.json`; unlabelled projects are skipped and listed as `excluded_cases`.

Predictions are one `<case_id>.json` per case: `case_id`, `items` (saved `BomItem`s), and
optional `source`, `extraction_model`, `error_code` and `synthetic`. Later pipeline stages
are optional and scored only when present (`null`/absent means "not produced"; an empty
list is scored): `safety_flags` (`[{code, line_id?, reason?}]`), `substitutions`
(`[{original, substitute?, grade?}]`), `offers` (`[{url, line_id?}]`, the URLs shown to the
user) and `listings` (`[{url, http_status?, title_match?, inr_price?}]`, what the pipeline
actually retrieved, with eval-time link checks).

Matching is deterministic, with no model involved. Names are NFKC/case-folded and split
into alphanumeric tokens; simple trailing plurals are trimmed. A part matches exactly when
tokens (or their joined form, so `ESP-32` = `ESP32`) equal its name or an alias. It matches
by containment when all of a name's tokens appear in the prediction. Pairs are assigned one
to one: exact first, then more specific names, then label and prediction order.
`--exact-names` disables containment. Reported metrics, per case and micro-averaged:

- recall (omissions) and precision (extras; repeated mentions of a matched part are
  reported as duplicates and count as extras);
- quantity agreement on matched parts whose label has a quantity: piece counts must match
  exactly, lengths within 10%; `null` predictions count as wrong and are reported
  separately;
- evidence hit rate: a matched part with labelled windows hits when any evidence
  timestamp falls inside any window (`--evidence-tolerance-s` widens windows);
- safety-flag recall overall and per code, with the plan's gate (every gold flag raised)
  and the count of raised flags the gold does not require;
- grade accuracy, exact (inside the gold range) and within one grade (A < B < C < D < X);
  each gold substitution is paired with at most one predicted substitution by the same name
  rules, and a missing or ungraded one counts as wrong;
- hallucinated-URL rate (offers whose URL is not in `listings`, compared without case in
  scheme/host, fragment or trailing slash) and link validity (listed offers with HTTP 200,
  title match and INR price, among those whose three checks were recorded).

`NO_BOM` errors score as an empty extraction. Other extraction errors are listed and
excluded from the aggregate, including the later stages. Synthetic sets produce a "FORMAT
CHECK ONLY" headline and `format-check.*` output. Sets whose `label_status` is not
`human_reviewed` (including legacy files without one) produce an "UNREVIEWED LABELS"
headline, a printed warning and `unreviewed-check.*` output instead of an accuracy
headline. Only human-reviewed sets write `report.*`. Each run writes `<stem>.md` (tables),
`<stem>.json` (full report) and `<stem>-metrics.json` (aggregate and per-case metrics).
Synthetic predictions cannot be scored against a real set.

```powershell
# Offline (default, no network): score saved predictions
.venv/Scripts/python scripts/evaluate_extraction.py --cases evaluation/example_cases.json --predictions evaluation/example_predictions
# Agent-drafted gold set (unreviewed: prints a warning, no accuracy headline)
.venv/Scripts/python scripts/evaluate_extraction.py --cases evaluation/gold/index.json --predictions path/to/predictions
# Live: one billable Gemini extraction per case; refused for synthetic sets
.venv/Scripts/python scripts/evaluate_extraction.py --cases path/to/labelled.json --live
```

Reports and live predictions are written to ignored `.data/evaluation/` and printed.
Rerun live predictions offline by passing `--predictions .data/evaluation/predictions`.
Live mode only produces `items`; the other stage fields must come from saved job results.
Many gold pages (Adafruit Learn, DroneBot, Random Nerd Tutorials, eater.net) are not yet
supported inputs, so live extraction records `UNSUPPORTED_URL` for them.
Limitations: name matching can't detect a wrong part with a matching name or a correct part
described in different words, so review omissions and extras by hand. A part that is
split across several predicted lines matches only one line. Required-change recall,
evidence-quote validity and compile rates from the plan are not computed. Small sets give
noisy rates.

## Seller sourcing

New live jobs source confirmed parts by default. Set `BS_SOURCING_ENABLED=false` to keep
new jobs extraction-only. Existing jobs retain the sourcing flag recorded at creation.
Demo jobs never call search or fetch sellers. Up to ten unowned parts are searched per
job (`BS_SOURCING_MAX_PARTS`), with five candidate pages per part by default.

Discovery uses Gemini Google Search grounding without a seller allow-list. Candidate
URLs come from grounding metadata, never generated prose. The verifier follows HTTPS
redirects, rejects non-public IPs at every hop, pins the checked address for TLS requests,
respects robots.txt, and limits response sizes. Pages with missing/blocked robots data,
long crawl delays, compression or unsupported product data can be skipped.

Only a single Product with a single Offer in seller JSON-LD qualifies. Its title must
match the query, currency must be INR, and price must be a positive decimal. Stock is
copied from explicit availability or marked unknown. Aggregate prices and unresolved
variant URLs are rejected. This verifies seller-published data, not merchant honesty,
delivery to the PIN, tax inclusion, electrical suitability or an independent stock check.
If the verified Product JSON-LD includes an HTTPS image URL, it is returned as optional
`image_url` for the frontend to display. The backend does not download or proxy seller
images; missing or invalid image metadata does not affect the offer. Placeholder assets are rejected; when the Product JSON-LD has no real
image, the page's `og:image` is used only for single-product pages. The legacy
`seller_trust` field stays `unverified`; the rule-based `trust` label is described below.
No offer is selected automatically.

When a product page has no Product JSON-LD, Shopify and WooCommerce stores are detected
from page markers and their public product JSON is read instead (Shopify
`/products/<handle>.json` for price and declared currency plus `.js` for availability;
WooCommerce Store API `?slug=` for simple products). The same fetch guards, robots.txt,
title gate and INR requirement apply; such offers carry `verification:
shopify_storefront_json` or `woocommerce_store_api`.

After verification, each seller host gets a cached, rule-based `trust` label
(`established`, `verified_basics`, `unverified`) from free checks: HTTPS, RDAP domain age,
a checksum-valid GSTIN on fetched pages, return/shipping/contact pages and a per-line
price anomaly flag. Checks have a 12 s deadline and fail open to `unverified`. Curated seed
sellers (`sourcing/known_sellers.json`) skip network checks. Google Web Risk is not called.
`BS_SELLER_TRUST_ENABLED=false` disables the step. See
[seller trust](../docs/contracts/seller-trust.md).

Seller specifications come from three sources on the verified page, each recorded in
`spec_evidence` with its `source`: the product title (`seller_title`), JSON-LD
`additionalProperty` (`seller_property`) and two-cell spec table rows or `dt`/`dd` pairs
(`seller_table`). Properties may use internal field names or a narrow set of common labels
(for example "Operating Voltage", "Interface", "Driver IC", "Resolution", "I2C Address").
Generic labels such as "Voltage" or "Frequency", alternatives such as "I2C / SPI",
single supply voltages and anything inside scripts are ignored. When sources disagree,
or an explicit property value is invalid, the field stays unknown and the offer lists a
`spec_conflicts` entry with every candidate value and source. Tables are read from the
whole verified page, so a related-product table can create a conflict, never a value.

Title matching treats inch notations (`0.96"`, `0.96″`, `0.91 in.`) as the same `inch`
token, and offer/variant URLs compare percent-escapes case-insensitively. A supply range
written without units is read only when the label states volts, e.g. "Operating Voltage
(VDC): 3.3 ~ 5"; "Pixel Resolution" is accepted as a resolution label. These came from a
labelled evaluation on 17 trimmed real seller pages; see
[seller-page evaluation](infra/seller-page-evaluation.md).

## Part image fallbacks

Images are presentation only; they never establish specifications, compatibility or
identity. Each report line can carry up to ten `image_candidates`: Product JSON-LD photos
from fetched seller pages whose product title matches the query, even when price/stock
could not be verified. `GET /v1/jobs/{job_id}/parts/{line_id}/image` returns, in order,
offer seller images, then those page references, deduplicated by URL, plus a `fallback`
code-authored SVG (a category diagram for resistors, capacitors, LEDs, wires and LDRs,
otherwise a generic placeholder), labelled "Illustration · not a product photo".

`POST` on the same path accepts `{"failed_urls": [...]}` (max 10) for images the browser
could not load and, when nothing else applies, may generate one AI illustration. Generation
requires `BS_IMAGE_GENERATION_ENABLED=true`, `BS_GEMINI_API_KEY`, and a non-demo job.
Results are 384px JPEG data URLs (≤150 KB) cached per owner, part name and model in
memory or the Firestore `<collection>_images` collection. Limits: `BS_IMAGE_DAILY_LIMIT`
(default 30) globally and 10 per owner per UTC day. A failure is cached for one hour;
an atomic lease prevents duplicate concurrent generation. `GET` never generates.
`generation_status` is `not_needed`, `not_requested`, `ready`, `pending` or `unavailable`.
With authentication enabled, image requests still require identity, CSRF header and job
ownership, but are exempt from the per-account action quota so broken-image retries
cannot block project actions.

General research accepts any part category, reads source text and text PDFs, and
extracts quoted specifications and candidate assessments. Discovery searches globally
for technical documentation and Indian sellers. Missing or blocked sources stay visible.
The original deterministic compatibility grades still cover Pro Micro, OLED, TTP223
and USB cables; other categories use the separate AI assessment and generic requirement
checks. No category needs a new enum or parser before it can be researched.

Lines are checkpointed in Firestore as sourcing progresses. An expired sourcing lease
queues unfinished work once, preserving completed lines and the sourcing limit. A second
interruption fails with `SOURCING_INTERRUPTED`. Per-line errors remain explicit in the report.

## Gemini extras (off by default)

`gemini_extras.py` adds three opt-in features, each behind its own flag
(`BS_EXPLAIN_ENABLED`, `BS_ZOOM_ENABLED`, `BS_SCAN_ENABLED`) and per-owner daily quota:
`POST /v1/jobs/{id}/explain` (deterministic script from saved data, optional translation,
TTS audio as base64 WAV, cached per script and language), `POST
/v1/jobs/{id}/items/{line_id}/zoom` (high-resolution re-read of a 10–20 s YouTube clip
around the item's timestamp) and `POST /v1/jobs/{id}/scan` (base64 photo, processed in
memory and never stored, matched to BOM lines with `box_2d`). Zoom and scan only run
while the BOM is awaiting confirmation and only produce reviewable chat proposals.
`GET /v1/jobs/{id}/extras` reports flags, remaining quota and zoom candidates. Demo jobs
get labelled samples without Gemini calls. See
[the contract](../docs/contracts/gemini-extras.md).

## Offer selection and costs

`POST /v1/jobs/{job_id}/selections` accepts a batch of `{line_id, offer_url, accept_changes}`
with the job token. Use null `offer_url` to clear a selection. Changes apply atomically.
Only completed live reports support selection. Offers must be in stock, checked within
24 hours, and graded A or B; B requires `accept_changes: true`. Nothing is purchased.
Unknown compatibility requires explicit research review as described below. Seller
adapters can lack sufficient specification evidence; gaps remain visible for review.

For v0.16, a verified quote with a current AI `potential_match` assessment can also be
selected with explicit `accept_research_assessment: true`. Generic requirements must
pass, known incompatibility blocks selection, and the report records research approval
without assigning an A/B grade. See the research contract for stale-assessment handling.

The line `price_inr` is the selected unit price; `subtotal_inr` multiplies it by quantity
using decimal arithmetic. Owned items contribute zero. `selected_parts_subtotal_inr`
contains the partial sum; `parts_subtotal_inr` is available only once all unowned lines
have selections. `unselected_line_ids` identifies gaps. Shipping, tax and `total_inr`
stay null. Costs are snapshots of seller quotes, not checkout totals or live guarantees.

`report.costing` adds a per-seller estimate: listed parts (known), GST added for ex-GST prices
(an assumed 18%, not tax advice), shipping from a dated, sourced seller policy table
(`src/bharat_sourcer/data/seller_policies.json`), and a total, each `known`, `estimated` or
`unknown` with its assumptions. Unknown sellers or unstated fees mean unknown shipping, never
zero. Offers carry seller-declared `tax_included`/`tax_evidence` (JSON-LD
`valueAddedTaxIncluded` or fixed page phrases; conflicts stay unknown). An optional import
comparison (heading 9804 duty, IGST, placeholder courier, dated FX in `data/tax_rates.json`)
appears when lines have a USD reference price (`POST /v1/jobs/{job_id}/import-references`, or
a quote-checked USD price fact from research). `GET /v1/jobs/{job_id}/plans` suggests
"cheapest" and "fewest sellers" carts without changing selections. See the
[costing contract](../docs/contracts/costing.md).

## Refresh stale or failed offers

Send `POST /v1/jobs/{job_id}/refresh` with the job token and `{"line_ids":["L01"]}`.
The backend returns 202 and searches only those parts, without extracting the video again.
Completed live sourcing reports and interrupted sourcing reports support refresh.
Requested lines lose their old offers and selections immediately; other selections survive.
New quotes must be selected again. Confirmed parts, specs and evidence remain unchanged.

Each job supports two accepted refresh batches, each within the configured sourcing part
limit. The counter and requested scope persist in Firestore. Invalid or concurrent requests
do not consume the budget. A repeated POST after completion starts a new batch, so clients
must check job status and `refresh_count` before retrying a lost response. A refreshed line
first re-fetches its previous offer pages (no Gemini search) and keeps them when at least
one offer is not out of stock; only otherwise does refresh incur paid search calls. Each
refresh run gets a fresh Gemini budget. It does not reset the automatic recovery budget. Interrupted refresh
reuses completed lines and resumes only unfinished requested lines.

## Automatic recovery

Gemini extraction and discovery retry timeouts, network errors and HTTP 429/500/502/503/504
up to three total attempts, with exponential delays and jitter. Numeric Retry-After is
honored up to ten seconds; longer or unsupported values stop retries. Authentication,
invalid requests and malformed output are not retried. Retry counts are logged without
request bodies or credentials. Repeated generation can incur additional charges.

The job's persisted `recovery_attempts` limits interrupted-worker recovery to one per job.
The periodic sweep requeues expired extraction or sourcing; a subsequent sweep claims it.
Completed sourcing lines are reused, including failed lines, so only unfinished lines run.
Worker IDs prevent late results from overwriting a recovered job. Extraction leases allow
at least three configured request timeouts plus 60 seconds. Exhausted recovery becomes a
visible failure; there is no automatic code editing, fabricated fallback, or infrastructure
repair. Firestore is required to retain progress across process restarts.

Run a targeted live check from `backend/` (uses paid search if your plan charges for it):

```powershell
.venv/Scripts/python scripts/check_sourcing.py --part "TTP223 touch sensor module"
```

A live check on 2 Oct 2026 returned two structured-data offers from five candidates:
Robocraze INR 9.00 and FlyRobo INR 18.00, both seller-reported in stock. This is historical
test evidence, not a price guarantee. The ignored `.data/sourcing-check.json` stores the
full local response. See the shared contract for attribution rendering requirements.

## Compatibility and clarification

Draft BOM items carry `specs` and `clarifications`. Answer questions using the `specs`
field of an existing confirmation `update` edit. Answers merge with saved specs; omitted
fields remain unchanged. Unknown answers can stay empty and the offer stays ungraded.
The backend distinguishes user assertions from literal name tokens and seller properties.
No model-generated electrical specifications are used by the rules engine.

Seller specs currently come from unambiguous title tokens and JSON-LD `additionalProperty`
entries whose names exactly match `PartSpecs` fields. Most seller pages will not provide
enough data for a positive grade. Generic voltage text is not assumed to describe logic
levels. Contradictory seller fields are discarded. Chip datasheets are rule references,
not a source of assumed module/clone wiring, regulators or voltage tolerance.

Every offer contains a `compatibility` assessment, with reasons, missing fields,
changes and reference links. This milestone implements:

- **A:** all required declared replacement specs match.
- **B:** the only mismatch is OLED I2C address; change the configured address.
- **X:** a known constraint differs or required supply range is not covered.
- **Unknown / null grade:** unsupported family or incomplete specs.

Grades have `scope: declared_specs_only`. They do not certify the complete circuit,
physical fit, current draw, firmware, seller claims, clone quality or every used MCU pin
function. `pinout` must identify the same ordered pin mapping; different strings block
approval. Controller swaps and rewiring are blocked until safe adapters exist. C/D grades
are reserved for future rules. Line-level grades appear after selection; payable totals stay null.

Rule references: [SparkFun Pro Micro guide](https://learn.sparkfun.com/tutorials/pro-micro--fio-v3-hookup-guide/all),
[Adafruit OLED guide](https://learn.adafruit.com/monochrome-oled-breakouts?view=all),
[Tontek TTP223-HA6 datasheet](https://www.tontek.com.tw/uploads/product/245/TTP223-HA6_V1.1_EN.pdf).
For TTP223, supply and output-mode rules are based on the exact declared module; the cited
chip datasheet is background and does not establish which chip revision a seller ships.

## Correct required specs after sourcing

`POST /v1/jobs/{job_id}/specs` accepts `{"updates":[{"line_id":"L01","specs":{"logic_v":5.0}}]}`
with the job token and returns the updated Job. It supports completed live reports only.
Saved answers merge atomically; explicit null clears an answer, though name inference can
still supply it. Invalid merged specs or repeated/unknown lines roll back the whole batch.

This updates required specs and reassesses saved offers without network calls or changes
to seller specs, prices, check times or video evidence. Changed lines lose selections;
other selections remain. Exact repeated answers are a no-op. Missing seller specifications
remain unknown, and stale quotes still need refresh before selection.

## Project conversation (v0.9)

Live smoke test on 3 Oct 2026 used YouTube Short `En4KD0c3XXs`: Gemini returned
five BOM lines, answered a question with a saved timestamp and line citation, and
produced ownership proposals that were rejected and accepted in an isolated memory job.
Acceptance left the job awaiting confirmation. The snapshot generator emitted the changed
state and heartbeat. One chat turn returned `CHAT_FAILED`; a new turn using the saved
extraction succeeded. The underlying failure cause was not captured. This validates live
adapter connectivity, not BOM accuracy or a deployed browser-to-server SSE connection.

Repeat from `backend/` with configured Gemini credentials (billable calls may occur):

```powershell
.venv/Scripts/python scripts/check_conversation.py --url https://www.youtube.com/shorts/En4KD0c3XXs
```

The test uses isolated memory storage, performs no sourcing, and saves a token-free
snapshot in ignored `.data/conversation-check.json`. Its ownership edit is test data.
Use `--resume` to reuse that snapshot and retry the acceptance step without re-extraction.

Users can ask questions alongside the BOM using persistent job chat. The live Gemini
adapter receives saved parts, evidence, offer assessments and the last 12 messages.
It can answer in every job state and propose draft BOM edits while awaiting confirmation.
Proposals require explicit acceptance; acceptance does not start sourcing. Stale proposals
are rejected, and existing deterministic edit validation applies atomically.

`POST /v1/jobs/{id}/messages` queues a turn using a client UUID for deduplication.
`POST /v1/jobs/{id}/messages/{message_id}/decision` accepts or rejects a proposal.
`GET /v1/jobs/{id}/stream` sends full job snapshots over SSE with token authentication.
Streams check saved state about once a second and close after about 60 seconds; reconnect
while the project is open. Each subscriber causes storage reads, including Firestore reads.
Replies appear once validated, rather than token by token. Polling GET remains supported.

Chat has separate queued/thinking/idle/failed state, a 20-turn limit and one active turn.
Queued turns resume after restart. Expired reply leases fail visibly without an automatic
generation replay; send a new message UUID to retry. Model HTTP calls use bounded transient
retries and may incur costs. Demo chat returns a labelled static response without Gemini.
Chat cannot run search tools directly or pause/cancel jobs; it only proposes reviewed
draft edits, seller refreshes and spec updates. Model answers are not independently
verified; only line-reference existence and proposal validity are checked.

Every proposal decision appends an entry to `job.actions` (kind, proposal `message_id`,
status, line IDs, timestamp and a short summary; the newest 50 are kept). Draft edits and
spec updates apply in the decision transaction and are recorded as `completed`; refreshes
are `accepted` until sourcing ends. When an approved refresh batch finishes (or is
interrupted and fails), the worker appends one deterministic assistant message, without a
model call, with `completes_message_id` set to the proposal and per-line `refresh_results`
(offer count, or no verified offers, or failed, and the lowest seller-listed price). The
proposal's `result_message_id` links back. Prices are seller-published, not verified totals.
The message ID is derived from the proposal and written in the same transaction as the
`done`/`failed` transition, so redelivered Cloud Tasks work never adds a second message.
Refreshes started with `POST /v1/jobs/{id}/refresh` have no proposal and add no history.

Frontend implementation details and a fetch/SSE client are in
[the conversation integration guide](../docs/contracts/conversation.md).

## Package layout

### Deterministic resistor advice (v0.10)

Chat may ask a contextual resistor-role question. Confirmed low-voltage single-LED
series-resistor inputs can be submitted to `/v1/jobs/{id}/resistor-advice`; see the
[frontend guide](../docs/contracts/conversation.md#contextual-resistor-suggestions-v010).
Decimal arithmetic selects the next E24 value considering 5% negative tolerance and
the smaller of desired current and driver design current. Power uses maximum voltage
drop and minimum resistance, with a 2x rated-power margin. Advice is saved separately
from extracted parts and never automatically changes quantities or selections.

Reference formula: [DigiKey LED series resistor calculator](https://www.digikey.ie/en/resources/conversion-calculators/conversion-calculator-led-series-resistor).
No board-specific GPIO current or LED forward voltage is inferred from the video.

Rule self-checks and an independent selection check detect exceptions or incorrect
standard values. A failing primary selector is quarantined for the worker process;
a bundled tested fallback is used for later calls, with its own output validation.
Both failing produces an unavailable result. Events `RULE_QUARANTINED` and
`RULE_UNAVAILABLE` provide diagnostic signals; advice stores version and fallback status.
This is bounded recovery, not autonomous source-code repair. A permanent correction
requires a regression case, a new version, checks and deployment. Restarted workers
repeat self-checks; quarantines are not synchronized across workers. Arbitrary formula,
hardware or shared-data defects are not guaranteed to be detected by these checks.

Run `python scripts/check_rules.py` from the installed backend development environment
before shipping a rule change. This runs the electrical reference examples, bounds,
injected selector failures, fallback checks and API isolation checks, with a nonzero exit
on failure. The existing CI `pytest` step includes this same test file. Add a failing
regression case for each discovered defect before changing a rule; bump its version when
behavior changes. Passing this suite alone does not prove every possible circuit safe.

On 3 Oct 2026, live Gemini was asked about the two unspecified resistors in the saved
`En4KD0c3XXs` BOM. It returned a structured question about each resistor's role and the
four LED-rule input bounds, without suggesting a value or changing the BOM. Reproduce with:

```powershell
.venv/Scripts/python scripts/check_conversation.py --url https://www.youtube.com/shorts/En4KD0c3XXs --resume --resistor-question
```

This command needs the earlier saved extraction and makes one billable chat operation
(with bounded HTTP retries). It validates the live clarification path, not the video's
actual circuit connections or component values.

```text
backend/
  src/bharat_sourcer/
    config.py       environment settings
    schemas.py      validated request/response models
    jobs.py         job state, atomic edits, fixture workflow
    storage.py      memory and transactional Firestore stores
    extraction.py   Gemini adapter, YouTube normalization, structured extraction
    evaluation.py   labelled-case schema, deterministic BOM matching and metrics
    project_pages.py  supported project URLs, readable page text, quote checks
    compat.py       declared-spec resolution, clarification and deterministic comparison
    sourcing/       grounded discovery, safe page fetching and JSON-LD verification
    main.py         API routes, errors, CORS
  scripts/          OpenAPI export/check, live checks, extraction evaluation
  evaluation/       synthetic format example and agent-drafted gold set (not accuracy data)
  tests/            API and job concurrency tests
  pyproject.toml    backend dependencies and tooling
```

Frontend code belongs in `../frontend/`. Shared contracts belong in `../docs/contracts/`.

## Checks (from backend/)

```powershell
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python scripts/export_openapi.py --check
```

After changing public routes or schemas, regenerate and commit the shared contract:

```powershell
.venv/Scripts/python scripts/export_openapi.py
```

## Next backend milestones

See the [agreed feature roadmap](../docs/contracts/backend-roadmap.md) for priorities and
the [Cloud Run guide](infra/cloud-run.md) for the shared frontend integration environment.

- Have two people review the agent-drafted gold set in `evaluation/gold/` (and label its
  candidate videos), then run the extraction evaluation harness on it.
- Fuse video and project-page evidence in one job and report conflicts; read code beyond READMEs.
- Add durable queue dispatch and broaden seller format support.
- Add seller trust checks and broader compatibility rules with module data; verify the import
  duty, courier and seller-policy assumptions used by costing.
- Extend the shared contract with the frontend teammate as those features become available.
