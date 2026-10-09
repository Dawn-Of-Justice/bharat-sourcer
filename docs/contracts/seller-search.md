# Seller catalogue search

Implemented in `backend/src/bharat_sourcer/sourcing/seller_search.py` (adapters, orchestration),
`sourcing/politeness.py` (pacing, caching, backoff, challenge detection) and
`sourcing/known_sellers.json` (registry). Wired into `SourcingService` (`sourcing/service.py`).

## What it does

For each unowned line, the backend searches curated Indian sellers' own catalogues before any
paid call. Adapters return candidate product URLs with optional title, price and image
**hints**. Hints only order candidates. They are never offers: every candidate is fetched and
verified on its product page or product JSON by the existing verifier (JSON-LD, or the
Shopify/WooCommerce JSON fast path). Prices in `offers[]` are always the verified ones.

## Staged, cost-aware order per line

1. **`seller_search`** (free): search enabled sellers concurrently, then fetch and verify the
   top candidates (`BS_SELLER_SEARCH_FETCH_BUDGET`, default 8). Fetching stops early once
   there are 3 in-stock verified offers from at least 2 sellers.
2. **`judge`**: `SourcingService.judge(spec, offers)` runs once on the verified offers. The
   default is a stub (no model call) that treats any verified INR offer as `compatible`; the
   matching stream supplies the real judge. `SourcingService.accepts(match, offer)` decides
   whether a match ends the line: verdict `exact` or `compatible` **and** stock `in_stock`.
3. **`grounded`** (paid, one Gemini call): Gemini grounded discovery runs **only** if step 2
   accepted nothing. Its URLs keep Google's order; URLs already fetched are skipped. A second
   `judge` stage then sees the new offers only.
4. **`research`** (paid, unchanged): runs when research is enabled, as before.
5. **`followup`** (paid, unchanged): the existing one-time follow-up discovery when research
   found no evidence and there are no offers. It is grounded-only.

`judge` is recorded only when there was at least one offer to judge.

Other behaviour:
- Lines with `user_has_it` are `already_owned`; nothing is searched.
- Identical parts in one job (same normalised name, specs and requirements) are sourced once;
  the other lines get a copy (`gemini_calls: 0`). Sourcing the same line again (refresh) is
  always fresh. The window is 5 minutes per service instance.
- With `BS_SELLER_SEARCH_ENABLED=false`, the line starts at `grounded` as before.

## Response fields (additive, on `ReportLine`)

| Field | Meaning |
| --- | --- |
| `stages` | Stages in the order they ran, e.g. `["seller_search","judge"]` or `["seller_search","judge","grounded","judge","research"]`. `research_skipped` replaces `research` when the review was skipped (a sufficient offer or the budget), so no model call was made |
| `gemini_calls` | Paid model calls the line used: grounded discovery + research (only when the review ran) + follow-up discovery. Judge calls and the job-level `spec` call are not counted per line; see `job.cost_estimate.calls_by_site` |
| `seller_search` | `{queries, candidate_urls, sellers_checked, blocked_sellers, message}` or `null` when seller search did not run. `candidate_urls` are **unverified leads** |

`attribution` stays Google grounding only (and `null` when grounded discovery was skipped);
seller-search URLs are never shown as Google results. With no verified offer, the
`NO_VERIFIED_OFFERS` message includes the seller-search sentence, e.g.
"robu.in blocked automated access; seller search checked 7 other sellers and found 8
candidates."

## Queries

`routing.route_queries(spec, raw_name, resolution_query)` builds a ladder: model numbers
(with compact and spaced spellings), buying-spec queries, cleaned names, value plus category,
then synonyms. It removes quantities, packs, tolerances and generic bracket qualifiers.
One-word generic queries and nounless fragments are rejected. Unicode letters, combining
marks and digits survive normalisation, including Devanagari.

Each seller tries at most **4** rungs by default. WooCommerce tries model numbers first
because its catalogue search can require a contiguous phrase. Parsing errors are recorded
and the next rung is tried; robots refusals and bot challenges stop that seller. A result
scoring at least 0.8 against the original part stops the ladder only for a model or a query
with at least two tokens. The legacy `query_variants` helper remains available to callers.

## Ranking and dedupe

Every candidate is scored against the original part, including model and value conflicts;
accessories for another part are demoted. The score never uses the fallback query as its
reference. Within a seller, descending relevance comes first and catalogue order breaks
ties. Candidates are retained as unverified leads even at low scores. Across sellers the
merge is round-robin, with relevance ordering each round. Shared listing identity normalises
host aliases and tracking parameters while preserving functional variant/product parameters.

## Sellers, endpoints and robots findings (checked 2026-10-07)

One `GET /robots.txt` per seller with `BharatSourcer/0.4 (+product-data-verification)`. The
fetcher still re-checks robots.txt (strict RFC 9309 parser) before every request.

| Seller | Platform | Endpoint | Search allowed | Status |
| --- | --- | --- | --- | --- |
| robocraze.com | Shopify | `/search/suggest.json?q=…&resources[type]=product&resources[limit]=10` | Yes | Enabled. robots.txt asks agents to use UCP/MCP for catalogue/cart/checkout and forbids automated checkout (we never check out) |
| quartzcomponents.com | Shopify | same | Yes | Enabled |
| thinkrobotics.com | Shopify | same | Yes | Enabled |
| zbotic.in | WooCommerce | `/wp-json/wc/store/v1/products?search=…&per_page=10` | Yes | Enabled |
| sharvielectronics.com | WooCommerce | same | Yes | Enabled |
| rytronics.in (`www.`) | WooCommerce | same | Yes | Enabled |
| compoindia.com | WooCommerce | same | Yes (no `*` group) | Enabled |
| evelta.com | BigCommerce | `/search.php?search_query=…` | **No** (`Disallow: /search.php`) | Disabled; adapter tested on synthetic HTML |
| probots.co.in | Magento | `/catalogsearch/result/?q=…` | **No** (`/catalogsearch/result/`, `/search/`, `/*?*`) | Disabled; adapter tested on synthetic HTML |
| electronicscomp.com (`www.`) | OpenCart | `index.php?route=product/search&search=…` (generic template) | **No** (`/*?route=product/search`) | Disabled |
| flyrobo.in (`www.`) | OpenCart | same (generic template) | **No** (`/*?route=product/search`, `/*?keyword`) | Disabled |
| robu.in | custom | none | n/a | **Blocked by bot protection**: home page answers HTTP 403 with a Cloudflare "Just a moment..." challenge (`cf-mitigated: challenge`). Recorded as `access: blocked_by_bot_protection`; not circumvented |
| thingbits.in | custom | none | not reviewed | Disabled |

Product pages of disabled sellers are still verified when grounded discovery returns them.
The Shopify `/search?…&view=json` and `/products.json` paging fallbacks are not used:
`suggest.json` works on all three Shopify stores.

## Politeness

- Per-host concurrency ≤ 2 and ≥ 1 s between requests to a host (shared across lines).
- In-memory and shared search caches use the exact request URL. A response is stored only
  after the adapter parses it successfully. Successful nonempty results use the configured
  search lifetime (6 h by default); empty results live at most 10 min. Product pages and
  product JSON use the configured 15 min default. Shared TTLs cannot exceed configured TTLs.
  HTTP errors and unparsable responses are not cached. Up to 2,000 local entries are kept
  in LRU order; shared-cache errors fall back to fetching.
- Paid budget: before grounded discovery the service checks `usage.paid_allowed()`; when it
  is false, grounded is skipped (no `grounded` stage) and the no-offer message includes
  `usage.BUDGET_MESSAGE`.
- 429/503: up to 2 retries, honouring `Retry-After` (seconds or HTTP date); without it 1 s
  then 2 s. A `Retry-After` above 10 s is not waited for; the response is returned as is.
- User agent: the existing `BharatSourcer/0.4 (+product-data-verification)`; HTTPS only,
  public-address pinning and size limits from `SafeFetcher`.
- Seller search has a 20 s overall deadline. Results already collected from an unfinished
  seller are retained with `timeout_partial`; an empty unfinished seller is `timeout`.
  After the deadline, workers stop before starting another rung (an in-flight request can finish).

## Bot protection: detect and stop, never circumvent

A response is a challenge when it has `cf-mitigated: challenge`; a Cloudflare/PerimeterX/
DataDome interstitial marker (`<title>Just a moment…`, `_cf_chl_opt`,
`/cdn-cgi/challenge-platform/`, `captcha-delivery.com`, `px-captcha`); or, on HTTP
401/403/405/429/503, a captcha or WAF marker (hCaptcha, reCAPTCHA, Turnstile, Akamai
`errors.edgesuite.net`/"Reference #", DataDome). A captcha widget on a normal 200 page (for
example a contact form) is not a challenge.

On detection the host is marked blocked for `BS_SELLER_BLOCKED_COOLDOWN_S` (30 min default),
later requests to it fail immediately without a network call, and the line records
`blocked_by_bot_protection` (`seller_search.blocked_sellers`, the no-offer message, and
the source entry passed to research, reason "Seller blocked automated access"). There is no fingerprint
spoofing, user-agent or proxy rotation, captcha solving or headless browser. A headless
renderer for sellers that allow crawling but render prices client-side is a separate
proposal (`roadmap.md` §15) and would never run on challenge pages.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `BS_SELLER_SEARCH_ENABLED` | `true` | Run seller catalogue search first |
| `BS_SELLER_SEARCH_FETCH_BUDGET` | `8` (1–12) | Seller-search candidates fetched per line |
| `BS_SELLER_SEARCH_PER_SELLER` | `5` (1–10) | Results taken from each seller |
| `BS_SELLER_SEARCH_CACHE_S` | `21600` | Search response cache lifetime |
| `BS_SELLER_PAGE_CACHE_S` | `900` | Product page / product JSON cache lifetime |
| `BS_SELLER_BLOCKED_COOLDOWN_S` | `1800` | How long a challenged host is skipped |

`BS_SOURCING_CANDIDATES_PER_PART` (5) still caps grounded URLs per discovery.

## Historical live check (2026-10-07, before v0.27.0, no Gemini)

These results describe the old matcher. See the [v0.27.0 routing evaluation](../../backend/infra/routing-evaluation.md)
for the later probe and its validation limits.

`cd backend && python scripts/check_seller_search.py` runs seller search and the existing
verifier for 33kΩ resistor, 22µF 16V electrolytic capacitor, 5mm LED, LDR and bare copper
wire. Grounded discovery is not run (0 grounded candidates).

| Part | Seller-search candidates | Fetched | Extractable INR offer (title match ignored) | Verified by current matcher |
| --- | --- | --- | --- | --- |
| 33kΩ resistor | 8 | 8 | 8 | 4 (Robocraze, Quartz) |
| 22µF 16V electrolytic capacitor | 8 | 8 | 8 | 0 |
| 5mm LED | 8 | 8 | 6 | 6 (Robocraze, Quartz, Sharvi) |
| LDR | 8 | 8 | 8 | 7 (6 sellers) |
| bare copper wire | 8 | 8 | 7 | 0 |
| **Total** | **40** | **40** | **37** | **17** |

"Extractable" counts any INR price the verifier can read; it says nothing about whether the
product is the right part (the 33k row includes 330 Ω and 22k listings). The capacitor's
exact match ("22uF 16V SMD Electrolytic Capacitor", Quartz) failed the then-current title gate on
`µ`/`u` and the extra "SMD" word; the matching stream's judge decides relevance.

## Tests

`backend/tests/test_seller_search.py` (offline). Recorded search responses for "33k
resistor", "22uf 16v capacitor", "ldr" and "5mm led" from the seven enabled sellers are in
`backend/tests/fixtures/seller_search/` (trimmed; each file records its URL and date in
`_fixture`; price fields are hints). BigCommerce, Magento and OpenCart HTML and the Cloudflare
page are synthetic and labelled, because robots.txt disallows those search pages or the host
is challenged.
