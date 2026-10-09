# Robust parts routing engine — implementation plan

Status: **implemented and merged in backend v0.27.0**, 9 October 2026, through
PRs [#46](https://github.com/Dawn-Of-Justice/bharat-sourcer/pull/46),
[#47](https://github.com/Dawn-Of-Justice/bharat-sourcer/pull/47) and
[#48](https://github.com/Dawn-Of-Justice/bharat-sourcer/pull/48).

Both owner decisions were approved: retain labelled marketplace candidates without
inheriting merchant trust, and continue free catalogue search after the paid AI budget.
See the [implemented contract](../../contracts/seller-search.md) and
[validation report](../../../backend/infra/routing-evaluation.md). Human review of all
search results remains outstanding; the automated probe does not prove accuracy targets.

The sections below preserve the original 8 October design and pre-implementation audit.
Their line numbers, defects, branch instructions and approval questions are historical,
not a current task list. Repository boundaries remain in `AGENTS.md`.

---

## 1. What "routing engine" means here

The **parts finder and seller identification** in `backend/src/bharat_sourcer/sourcing/`:
for each BOM line, decide which searches to run where (direct seller catalogue
search → paid Gemini grounded discovery → research), then for each fetched page decide
**which seller it is** and **read a verified offer** (title, INR price, stock, variant,
tax) from it. Entry point: `SourcingService._source_attempt` in `sourcing/service.py`.

Current flow for one line (see `research/01-pipeline-audit.md` §1 for file:line detail):

1. `jobs.py` (~L946) → refresh known URLs → job budget check → `source_for_project`.
2. `part_spec.buyable_spec` → seed or AI buying spec (`BuyableSpec.queries`, synonyms…).
3. Free stage: `service.seller_queries` (L204) + `seller_search.query_variants` (L139) →
   `SellerSearch.search` (7 enabled sellers, 6 threads, 20 s deadline) → `merge`
   round-robin → `_verify_urls` (L639): `verify_page` (JSON-LD) → `variant_url` →
   `storefront_offer` (Shopify/Woo JSON) → `meta_offer` (OG/microdata) → `build_candidate`
   → `_review` (shortcut + Gemini judge, else `title_matches` gate).
4. Paid stage (only if nothing accepted and budget allows): `GeminiDiscovery.discover`
   (L101) → grounding URLs → `_verify_urls` → `_review`.
5. Trust labels (`trust.py`), research (`research.py`), final status
   `offers_found` / `no_verified_offers` / `failed` (`DISCOVERY_FAILED`).

Enabled direct-search sellers (`sourcing/known_sellers.json`): robocraze, quartzcomponents,
thinkrobotics (Shopify `shopify_suggest`); zbotic, sharvielectronics, rytronics,
compoindia (WooCommerce `woo_store_api`). Disabled (robots or bot protection): evelta,
probots, electronicscomp, flyrobo, robu (Cloudflare challenge), thingbits.

---

## 2. Evidence (why it fails) — summary

Full reports: `research/01..04`. Live probe data: `probe/` (fixtures are page excerpts
captured 2026-10-08 — historical snapshots, not current prices).

**Live probe (17 parts × 7 sellers, free search only, 179 requests, all HTTP 200):**
- Right item in top 5 out of 17: robocraze 13, quartz 13, thinkrobotics 8, rytronics 7,
  zbotic 3, compoindia 3, sharvi 1. No seller found ESP32 DevKit V1 or IRFZ44N correctly.
- WooCommerce search is phrase-like: zbotic `sg90` → 5, `servo sg90` → 2, `sg90 servo` → 0.
  `_search_one` drops one-word fallbacks (`len(s.split()) > 1`), so the model-number
  query that works is never sent. Woo results are newest-first (`orderby=relevance` → 400).
- Junk sub-queries outrank real hits: "jumper wires male to female" → query `"to female"`;
  candidates are scored against the query that found them, so junk scores 1.0
  (HDMI cables, spacers). Others: `17 motor`, `0.96 i2c`, `18650 battery holder` → ESP32s.
- Accessories score 1.0 ("Case for Arduino UNO R3", "Bracket for NEMA 17").
- Token misses: `nema 17`/`NEMA17`, `irfz44n`/"IRFZ44 N-Channel", "2 cell"/"Dual".
- **Quartz loses every price ≥ ₹1,000**: JSON-LD price `"2,650.00"` fails `sane_price`
  (comma); Shopify JSON fallback is skipped because JSON-LD exists; `meta_offer` skips
  Shopify. Below ₹1,000 the offer URL has `?variant=` but the page URL does not;
  `variant_url` requires strict `title_matches` even in judge mode. Fetching the
  `?variant=` URL directly verified ₹358.00 correctly.
- sharvi / rytronics JSON-LD names carry a site suffix (" | Sharvielectronics: …",
  " - Rytronics.in"). zbotic's `og:price:amount` is the ex-GST price (49.2) while the
  shown price includes GST — a risk for `meta_offer`.

**Production logs (Cloud Run `bharat-sourcer-integration`, since 2026-10-03):**
- Grounded discovery hit `MAX_TOKENS` in 21 of 22 calls (`maxOutputTokens: 2048`);
  one `DISCOVERY_FAILED` (truncated with 0 sources). One research `ValidationError`.
- No per-seller data: the `SELLER_SEARCH …` line is INFO and nothing configures INFO
  logging for `bharat_sourcer` loggers, so it is dropped.

**Code audit — pipeline (`research/01-pipeline-audit.md`):**
- F1 query building: `"Wire, 22 AWG, solid core"` → `'22 core'`; `"Arduino Uno R3
  (compatible)"` → `'compatible'`; `"5mm LED (red) x5"` → `'red'`, `'5mm x5'`;
  `"10kΩ Resistor (1/4 W, 5%)"` → `'1/4 w 5'`; Devanagari broken by `normalise` regex
  (`seller_search.py:105` strips combining marks). Model-number spellings never tried.
- F2 cache: shared seller-search key is seller + `normalise_part(query)`
  (`seller_search.py:377`) so different queries collide; any HTTP 200 (HTML, empty) is
  cached 6 h (`politeness.py:276`); first adapter error ends that seller's queries
  (`seller_search.py:403-409`).
- F3 judge failure / budget spent: `judge.judge_candidates` returns `None`
  (`judge.py` ~L375) discarding shortcut + cached verdicts → strict `title_matches`
  rejects real titles (`'10k resistor 1/4W'` vs `'10k Ohm 1/4 Watt Resistor'`,
  `HC-SR04` vs `HCSR04`, `4.7µF` vs `4.7 uF`). `variant_url`/`page_images` always use it.
- F4 spent job budget skips the free search too (`jobs.py:953`); a test asserts it
  (`test_cost_controls.py:546`). **Owner decision pending — see §6.**
- F5 `DISCOVERY_FAILED` early return (`service.py:559`) discards free-stage pages, skips
  research/images/follow-up; message says "Seller search failed" when Gemini failed.
- F6 20 s seller deadline drops a slow seller's partial results (`seller_search.py:456`).
- F7 grounded discovery searches only `resolution.query`, prompt also asks for
  datasheets, only 5 URLs fetched.
- F8 `_verify_urls` catches only FetchError/ValueError/RecursionError; `assess_offer`
  (`service.py:308`) and `page_images` (`:608`) unguarded → `SOURCING_FAILED` for the line.
- F9 stale data: shared page cache TTL 8 h (`cache.py:32`) overrides
  `BS_SELLER_PAGE_CACHE_S=900`; robots.txt 5xx/403 cached as disallowed for process life
  (`fetch.py:163-171`); `refresh_known` fetcher has no politeness (`service.py:456`).
- F10 `offers_found` even when all offers are partial/out of stock.

**Code audit — seller identification (`research/02-seller-identification-audit.md`):**
- Seller = raw final hostname (`listings.py:319,501`, `platforms.py:162,284`); five
  different host normalisations (trust `registrable_domain` trust.py:77, costing
  `seller_key` costing.py:46, seller_search `url_key`/`own_host` :165-174,
  `enough_offers` service.py:216, `source_rank` service.py:93).
- Valid offers rejected over URL details: `?srsltid=`/`?utm_*`, www vs bare, http offer
  URL, relative offer URL (`listings.py:299,304`; query-string rejections
  `platforms.py:103,183,239`, `listings.py:232`). No canonical-link reading.
- JSON-LD shapes not read: ProductGroup/hasVariant, Product in `mainEntity`,
  IndividualProduct, `type="application/ld+json; charset=utf-8"`, CDATA, trailing comma,
  duplicate identical Product (theme + SEO plugin → treated as category, `listings.py:399`),
  price only in `priceSpecification`, currency on Product or lowercase, untyped Offer,
  one unresolvable AggregateOffer range aborts all offers (`listings.py:347-355`).
- Platform-hosted stores inherit the platform domain's trust (`*.myshopify.com` simulated
  as 7526 days old, all policy pages "found" because they redirect home).
- Marketplaces (amazon.in, flipkart.com in `countries.py` seller_domains) credited as seller.
- Prices `"1,299.00"`, `"₹1,299.00"`, `"Rs. 1,299"`, `"1,23,456.00"` rejected; microdata
  price only from `content=`; MRP + sale both `itemprop=price` → rejected.
- `detect_platform`: one `cdn.shopify.com` image on WordPress → "shopify" (disables
  meta fallback); OpenCart/BigCommerce/PrestaShop/Wix/Dukaan/Instamojo → unknown.
- Stock: LimitedAvailability, OnlineOnly, BackOrder, Discontinued, `schema:InStock` →
  unknown (and acceptance requires in_stock, `service.py:197`).
- Meta fallback accepted a category page; a "Product not found" page with JSON-LD accepted.
- Trailing-dot host, `m.` host mismatch in costing; challenge detection skipped when
  seller search is off; Sucuri/Imperva 200 challenges undetected; trust fetches bypass
  politeness (`main.py:90`).
- Tax phrases "including 18% GST", "excluding 18% GST", "With/Without GST" missed;
  footer/related-product phrases cause false conflicts.

**Web research highlights (`research/04-web-research.md`):** extraction priority
platform JSON → JSON-LD → microdata → meta → (never prose); WooCommerce Store API prices
are minor-unit strings (`"120006"`, `currency_minor_unit: 2`); Shopify `.js` prices are
integer paise, `suggest.json` decimal strings; Public Suffix List private suffixes
(myshopify.com, wixsite.com) but not myinstamojo.com / mydukaan.io → keep our own list;
Amazon allows `/dp/` for `*` but PA-API 5 is deprecated (Creators API); Flipkart allows
`/p/`. No catalogue API for Dukaan/Instamojo/Zoho.

---

## 3. Target design

```
BOM line
  └─ route_queries(spec, item)            # ladder, most specific first
       └─ per seller: walk rungs until relevant hits (adapter-aware)
            └─ candidates scored against the PART (textmatch), accessories demoted
  └─ canonical_url → identify(url)        # seller domain/name/kind
  └─ read offer, layered + labelled:
       platform JSON → JSON-LD → microdata → meta → reject(reason)
  └─ judge (shortcut/cached verdicts survive failure; else improved token gate)
  └─ paid grounded discovery only if still nothing; earlier results always kept
  └─ trust (registrable domain aware of platform-hosted + marketplaces), research
  └─ line summary log + rejection-reason counts
```

Principles that must hold (existing contracts): prices/stock only from seller-declared
structured data or platform JSON, never prose; never circumvent bot protection or
robots.txt; generated prose URLs never accepted; demo data labelled.

---

## 4. Workstreams

### Stream 0 — shared base (do first, commit, then parallelise)

**New `sourcing/sellers.py`:**
- `host_of(url_or_host) -> str`: lowercase, IDNA-decode safe, strip trailing dot, strip
  leading `www.`, `m.`, `amp.`.
- `registrable_domain(host)`: `.in` second levels (co, net, org, firm, gen, ind, ac, edu,
  res, gov, mil — move `IN_SECOND_LEVEL` from trust.py); `PLATFORM_SUFFIXES` =
  {myshopify.com, mydukaan.io, dukaan.app, myinstamojo.com, instamojo.com,
  wixsite.com, zohocommerce.in, zohostore.in, blogspot.com} where the store label + suffix
  is the registrable domain.
- `identify(url) -> SellerIdentity(domain, name, kind)` with kind
  `direct | marketplace | platform_hosted`. Names from `known_sellers.json` (match on
  `domain` and `search.host`); `MARKETPLACES` table: amazon.in, flipkart.com, meesho.com,
  indiamart.com (incl. dir./m. subdomains), moglix.com, industrybuying.com, snapdeal.com,
  tatacliq.com, jiomart.com.
- `canonical_url(url)`: drop fragment and tracking params (`utm_*`, `srsltid`, `gclid`,
  `gbraid`, `wbraid`, `fbclid`, `msclkid`, `_pos`, `_psq`, `_ss`, `_sid`, `_v`, `_fid`,
  `ref`, `ref_`, `tag`, `pf_rd_*`, `pd_rd_*`, `sr`, `qid`, `keywords`, `spm`,
  `mc_cid`, `mc_eid`); keep functional params (`variant`, `id`, `product_id`, `route`,
  `p`, `pid`, `sku`, `attribute_*`). Never changes scheme/host of a URL for fetching
  except dropping a trailing dot.
- `listing_key(url)` / `same_listing(a, b, base=None)`: resolve relative against `base`,
  then compare `https` + `host_of` + path without trailing slash (percent-escape case
  insensitive) + remaining sorted query.

**New `sourcing/textmatch.py`:**
- `model_numbers(text)`: tokens with letters+digits, len ≥ 3, incl. hyphenated/spaced forms
  (`HC-SR04`, `IRFZ44N`, `NEMA 17`, `ESP32-WROOM-32`, `WS2812B`, `SG90`, `LM2596S`,
  `A4988`, `TP4056`, `BME280`, `18650`); `compact()` = alnum lowercase. Match = compact
  equality only, so LM2596S ≠ LM2596. When building title tokens, join a model token with
  a following single letter (`IRFZ44 N-Channel` → `irfz44n`) and a word with a following
  number (`NEMA 17` → `nema17`), keeping the unjoined tokens too.
- `values(text)`: resistance (10k = 10K ohm = 10kΩ = 10000 ohm, 4K7 = 4.7k),
  capacitance (100uF = 100µF = 100 MFD; nF/pF), voltage, current, wattage
  (1/4W = 0.25W = 1/4 watt), length (20cm/200mm), pins ("30 pin"/"30-pin"), cells
  ("2 cell"/"dual"/"double"/"x2"). Reuse `compat.parse_name` / `sourcing/specs.py` where
  they already parse; do not duplicate.
- `pack_size(text)`: "pack of 10", "10 pcs", "10pcs", "set of 5", "x10".
- `is_accessory_for(title, part)`: "case/holder/bracket/mount/cover/enclosure/shield
  cover/stand/clip … for X" when the part's category/name is not itself that accessory.
- `relevance(part_terms, title) -> float` and `title_gate(query, title) -> bool`
  (model numbers must match; values must not conflict; ≥ 80 % of noun tokens; plurals,
  `points`→`point`, `watt`→`w`, inch forms as today).
- Unit tests: `tests/test_textmatch.py`, `tests/test_sellers.py`.

### Stream A — search routing (`seller_search.py`, new `sourcing/routing.py`, `part_spec.py`)
- `routing.route_queries(spec, raw_name, resolution_query) -> list[Rung]` ordered:
  1. model numbers alone (+ hyphenless/spaced spellings);
  2. spec queries (`BuyableSpec.queries`);
  3. cleaned name: remove quantities/packs/`%`/tolerances/"(compatible)"/"xN"/brackets
     that are qualifiers; keep bracketed aliases that are model numbers;
  4. value + category noun ("10k resistor", "100uF capacitor", "20cm jumper wire");
  5. synonyms (`BuyableSpec.synonyms`).
  Each rung carries `kind` and the intended `part_terms` for scoring.
  Reject: one-word queries unless a model number; queries with no noun/model token;
  duplicates after normalisation.
- Replace `service.seller_queries` and `query_variants` usage with the ladder (keep
  `query_variants` exported for compatibility or update tests).
- `normalise`: keep Unicode letters, marks and digits (`unicodedata.category` L*/M*/N*),
  so Devanagari survives.
- `_search_one`: walk rungs (bounded by `queries_per_seller`, default 4); WooCommerce
  adapters put the model-number rung first; an adapter `ValueError`/parse error on one
  query is recorded and the next rung runs (Blocked/robots still stop the seller); early
  stop only when a candidate's `relevance` vs the part ≥ threshold **and** the rung is a
  model-number or ≥ 2-token rung.
- Score every candidate against the line's part terms (not the rung query), demote
  accessories, tie-break by store rank. `merge` keeps round-robin but uses this score.
- Deadline: each `_search_one` writes into a shared per-seller list; on timeout use what
  was collected and mark diagnostic `timeout_partial`.
- Update `docs/contracts/seller-search.md` (it says 2 queries per seller; code does 3+1).

### Stream B — page reading (`listings.py`, `platforms.py`, `tax.py`, `schemas.StorePlatform`)
- `ProductScripts`: accept `type` starting with `application/ld+json` (params allowed);
  strip `<!--`/`-->`/CDATA wrappers; on JSONDecodeError retry once with trailing commas
  removed and control chars escaped.
- `nodes`: also descend `mainEntity` (and `@graph` as today); never descend
  `itemListElement`/related products. Product types: Product, ProductGroup,
  IndividualProduct, ProductModel. ProductGroup: options from `hasVariant[].offers`
  with variant name/sku/url.
- Count identical Products once (same name+sku+offers, or same `@id`/url).
- `offer_options`: currency from Offer → `priceSpecification` → Product, case-insensitive;
  untyped dict with `price` inside `offers` treated as Offer; `priceSpecification`
  price when `price` missing (skip `priceType` ListPrice/StrikethroughPrice/MSRP);
  unresolvable AggregateOffer range → skip that entry (return None only if nothing else).
- `parse_inr(raw, declared_currency)`: numbers; strings with `₹`, `Rs`, `Rs.`, `INR`,
  `/-`, Western or lakh grouping (`1,23,456.00`), surrounding spaces/NBSP. Currency must be
  declared (field) **or** explicit in the string. Reject ambiguous (`1.234,56`), ranges,
  > 2 decimals unless trailing zeros, ≤ 0, > 10,000,000. Replace `sane_price`/
  `checked_price` call sites.
- `stock_of`: split on `/` and `:`; add LimitedAvailability, OnlineOnly → in_stock;
  BackOrder, PreOrder, PreSale → preorder; Discontinued, SoldOut → out_of_stock;
  InStoreOnly → unknown.
- Shopify: use `.json/.js` path when JSON-LD has **no usable offer** (not only when
  JSON-LD is absent). `variant_url` and `build_candidate` paths use `query=None` semantics
  when a judge is configured (pass through from service). Single-option variant pages kept.
- `meta_offer`: read microdata price from element text when no `content`; require a
  product-page signal (`og:type` = product/product.item, exactly one microdata
  `itemtype` Product, or a platform product path); if the page shows tax-inclusive text
  near a different visible price, set `tax_included=None` (zbotic og ex-GST risk).
- Soft-404 / not-a-product rejection: title/h1 "page not found", "product not found",
  "no longer available", "404"; final URL is home or `/collections/…`/`/category/…`
  after redirect from a product path. Return a reason code for diagnostics.
- `detect_platform`: score signals (headers, `Shopify.shop`, `shopify-digital-wallet`,
  `/cdn/shop/`, `shopify-section`, `x-shopid`; one `cdn.shopify.com` asset alone is not
  enough). Add opencart (`route=product/product`, `catalog/view/theme`), bigcommerce
  (`cdn11.bigcommerce.com`, `stencil`), prestashop (`prestashop`, `/modules/ps_`), wix
  (`x-wix-request-id`, `static.wixstatic.com`), dukaan (`mydukaan`, `dukaan.app`),
  instamojo (`instamojo`). Extend `StorePlatform` literal (additive).
- Title cleanup: strip a trailing `" | X"`, `" - X"`, `" – X"` when X matches the seller
  name/domain (from `sellers.identify`), else keep.
- `tax.py`: allow `"(incl|including|inclusive of|excl|excluding|exclusive of)\.? (\d+%
  )?GST"`, "with GST"/"without GST"; only phrases within N characters of the price element
  or in the offer/price block count.
- Fixtures: copy `probe/fixtures/*` to `backend/tests/fixtures/seller_pages/` with a
  labelled header comment (historical snapshot 2026-10-08), plus synthetic fixtures for
  each shape above.

### Stream C — never lose results (`service.py`, `judge.py`, `politeness.py`, `fetch.py`, `cache.py`, `trust.py`, `costing.py`, `main.py`, `schemas.py`)
- `_verify_urls`: `canonical_url` before `attempted`; catch `Exception` per URL (log
  `VERIFY_URL_FAILED type=…`), record `ResearchSource(status="unavailable", reason=…)`,
  count reason. Guard `assess_offer` and `page_images` per offer/page.
- `VerifyState.reasons: Counter` with codes `no_structured_price`, `category_page`,
  `not_inr`, `soft_404`, `blocked`, `robots`, `fetch_error`, `judge_mismatch`,
  `title_gate`, `error`; include counts in the NO_VERIFIED_OFFERS message and a
  `SOURCING_LINE line=… stages=… queries=… candidates=… fetched=… reasons=…` INFO log.
- Discovery failure: no early `DISCOVERY_FAILED` return when the free stage fetched pages;
  continue to trust/research with error code `DISCOVERY_FAILED` only if no offers and
  message "Web search failed; seller catalogue results were kept." Keep status `failed`
  only when nothing at all was fetched.
- Judge: `judge_candidates` returns the partial `results` (shortcut + cached) instead of
  `None` on call failure / budget; `review_candidates` treats `None` entries as unjudged
  → improved `textmatch.title_gate`; such offers keep `match=None` (unjudged label).
- `GeminiDiscovery`: query from spec (`part_name` + key params + first spec query);
  prompt asks for Indian seller product pages first, "answer in under 60 words";
  `maxOutputTokens` 4096; drop LOW_PRIORITY hosts before the
  `sourcing_candidates_per_part` cut when enough others exist.
- Politeness/cache: shared seller-search key = exact request URL (remove the
  `normalise_part(query)` shared key); cache a search response only if the adapter parsed
  it (pass a `cacheable` predicate or cache after parse); empty results short TTL (≤ 10
  min); `_shared_set` TTL = `min(TTL[name], configured ttl)` so `BS_SELLER_PAGE_CACHE_S`
  wins; `refresh_known` uses the polite fetcher.
- `fetch.py` robots: cache non-200/404 robots outcomes with an expiry (10 min) instead of
  forever.
- Challenge detection always on for product pages (wrap fetcher in `PoliteFetcher` even
  when seller search is disabled); add Sucuri (`sucuri_cloudproxy`, "Sucuri WebSite
  Firewall") and Imperva (`_Incapsula_Resource`, "Incapsula incident") markers.
- Seller identity: `_review` sets `offer.seller_domain`, `seller_name`, `seller_kind`
  via `sellers.identify`. `VerifiedOffer` gains these optional fields (additive).
  `enough_offers`, `source_rank`, `costing.seller_key`, `seller_search.url_key/own_host`
  use `sellers.host_of`/`registrable_domain`.
- Trust: cache key = registrable domain; platform-hosted stores get no inherited domain
  age (`unavailable` includes `domain_age`); marketplace kind → label explains the merchant
  is third-party and does not mark it `established`; policy page must contain policy words
  and not redirect to home; trust fetches through the polite fetcher (`main.py:90`).
- `main.py`: configure `logging.getLogger("bharat_sourcer")` at INFO (respect an env
  override) so `SELLER_SEARCH` / `SOURCING_LINE` lines reach Cloud Run.
- Job budget (F4): **owner decision, see §6** — if approved, `jobs.py` runs the free
  stage when the ledger is exhausted and only paid stages are skipped; update
  `test_cost_controls.py:546`.

### Stream D — explainable, measurable routing (added 2026-10-09; start after A/B/C merge)

Not part of the A/B/C split: agents already working on A/B/C must not pick this up. It
builds on C's reason codes and A's ladder. Owns: `schemas.ReportLine` trace fields,
`sourcing/evaluation` (new), `scripts/evaluate_routing.py` (new), docs.

**Invariants this stream writes down (in `docs/contracts/seller-search.md` and later
`AGENTS.md` if the owner agrees):**
1. *Fail loud.* Every skipped stage, dropped URL, timeout or failed model call leaves a
   reason code on the line, not only a log line. "No offers" is never reported without a
   reason breakdown.
2. *Pure router, opinionated workers.* Which rungs, sellers and stages run is a
   deterministic function of (spec, config, seller registry, budget). Model output (judge,
   discovery) can only add or reject candidates through typed verdicts; it never decides
   stage flow.
3. *Two layers of evidence.* Search hits, discovery URLs and AI research are background:
   shown as leads, never as prices. Only a seller-declared structured offer, read within
   its TTL, is authoritative. Nothing promotes a lead to an offer except a fresh page read.
4. *Bounded everything.* Every retry, rung walk, fallback and model call has a stated
   budget; the table in `seller-search.md` lists them all (rungs/seller, queries/seller,
   per-seller deadline, judge calls, discovery calls, retries).
5. *Eval and gate are the same code.* The offline routing eval imports `textmatch`,
   `routing` and `listings` from production; it never reimplements matching.

**D1 — per-line trace on the job (extends what exists).** `ReportLine.stages` and
`SellerSearchSummary` already record stages and queries. Add a bounded
`SourcingTrace` (≤ 40 entries, ≤ 4 KB per line): rungs tried with hit counts; per seller
`ok | empty | error | blocked | robots | timeout_partial`; fetched URLs with the C reason
code or `offer`; stages skipped with why (`budget`, `disabled`, `enough_offers`,
`no_candidates`); elapsed ms per stage. Store it on the line, exclude it from
`/v1/shared/*` and exports (`export.redact`), expose it on the owner job view (additive;
regenerate OpenAPI). `scripts/inspect_job.py` prints it. Goal: explain any "no offers"
line from the job alone, without re-running the probe.

**D2 — routing eval in CI.** New `sourcing/evaluation.py` modelled on
`bharat_sourcer/evaluation.py` (same `synthetic` / `label_status` rules: synthetic sets
check the harness only and their numbers are never reported as accuracy). Cases: part
spec → expected listing per seller (URL pattern or SKU) or `not_stocked`, labelled from
the 2026-10-08 probe. Offline mode replays saved adapter responses from
`tests/fixtures/seller_search/` (no network, runs in pytest); live mode reuses
`probe/scripts/search_probe.py` politely. Metrics: right listing in top 5 per
seller×part, junk-rung count, accessory-in-top-1 rate, wrong-part offers verified.
CI fails if offline recall drops below the stored baseline.

**D3 — sliding seller-search deadline.** Replace the fixed 20 s cut with: base 20 s,
extended by 5 s while any seller returned a parse in the last 5 s, absolute cap 35 s;
partial results always kept (A already keeps them). Configurable; test with fake clocks.

**D4 — known-good listings (proposal, owner decision 5).** After a line verifies an
offer, store `{part key → canonical URL, seller, checked_at}` (no prices) in Firestore.
Later jobs check those URLs first as a ladder rung 0; they are *leads* (invariant 3) and
are re-read before use. Entries that fail twice are dropped.

---

## 5. Execution plan

1. `git switch main && git pull` then `git switch -c be/routing-engine` (or reuse it).
2. Build **Stream 0** yourself with tests; commit.
3. Run Streams A, B, C in parallel (subagents in separate git worktrees branched from the
   Stream 0 commit). File ownership to avoid conflicts:
   - A: `seller_search.py`, `routing.py` (new), `part_spec.py`, their tests, `seller-search.md`.
   - B: `listings.py`, `platforms.py`, `tax.py`, `schemas.StorePlatform`, seller-page
     fixtures/tests, `seller-trust.md` page-reading parts.
   - C: `service.py`, `judge.py`, `politeness.py`, `fetch.py`, `cache.py`, `trust.py`,
     `costing.py`, `main.py`, `jobs.py`, `schemas.VerifiedOffer`, their tests.
   Interfaces between them: B exposes `verify_page(page, query, *, seller=None)` returning
   offer or `None` plus a `reject_reason(page)` helper; C consumes it. A exposes
   `route_queries(...)` used by C in `_source_attempt`.
4. Merge A, B, C into the branch; resolve conflicts; full test suite.
5. Re-run the live probe (`probe/scripts/search_probe.py`, then `verify_probe.py`;
   free search only, unset `BS_*` model keys, polite and sequential, < 400 requests) and
   compare with `probe/search-probe-summary.txt`. Target: every enabled seller finds the
   right item in the top 5 for ≥ 10/17 parts (where the store stocks it), Quartz prices
   ≥ ₹1,000 verified, no junk rung queries.
6. Docs: `docs/contracts/seller-search.md`, `seller-trust.md`, `part-matching.md`,
   `docs/contracts/README.md` changelog entry, `backend/README.md`; version 0.27.0 in
   `backend/pyproject.toml`; OpenAPI regen.
7. PR(s) → CI → merge → GitHub Actions deploys on push to `main`
   (`.github/workflows/backend.yml`). Verify live: `backend/scripts/check_deployed.py`,
   Cloud Run revision on the new image at 100 % traffic, and a real job's lines.

### Commands (from `backend/`)
```
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python scripts/export_openapi.py          # regenerate
.venv/Scripts/python scripts/export_openapi.py --check  # CI check
```
If dev deps are missing: `uv sync --all-extras --all-groups`. PDF tests skip without Pango
locally (expected). Deploy target: Cloud Run `bharat-sourcer-integration`, project
`hackathon-510415`, region `asia-south1`. A teammate has previously deployed manually and
overridden revisions — after deploy confirm the serving revision's image SHA matches the
merge commit.

### Test plan (new tests)
- `test_textmatch.py`: the 17 probe parts, HC-SR04/HCSR04, NEMA 17/NEMA17, IRFZ44N vs
  "IRFZ44 N-Channel", LM2596S ≠ LM2596, 10k/10K ohm/10kΩ, 4K7, 1/4W/0.25W, µF/uF/MFD,
  pack sizes, accessory titles.
- `test_sellers.py`: www/m./amp./trailing dot/IDNA, `.co.in`, myshopify/dukaan/instamojo
  subdomains, marketplaces, tracking-param stripping, functional params kept,
  same_listing http/https/relative.
- `test_routing.py`: ladders for all probe parts + "Wire, 22 AWG, solid core",
  "Arduino Uno R3 (compatible)", "5mm LED (red) x5", "10kΩ Resistor (1/4 W, 5%)",
  Hindi "पुश बटन स्विच"; no one-word generic rung; Woo model-number-first.
- Seller search: per-query error continues, partial results on deadline, scoring vs part,
  cache key per URL, unparsed response not cached.
- Page reading: one test per JSON-LD shape, price format, stock value, soft-404,
  category page, platform fingerprint, title suffix, tax phrase; the seven probe fixtures.
- Service: discovery failure keeps free results + research; judge failure keeps shortcut
  matches; exception on one URL isolated; reason counts in the message; seller fields set.
- Trust: platform-hosted no inherited age; marketplace label; policy redirect to home not
  counted.

---

## 6. Owner decisions (ask the user before implementing these)

1. **Marketplaces** (Amazon.in, Flipkart): proposal — keep as candidates, label
   `seller_kind="marketplace"`, merchant unknown unless the page names it, never credit
   marketplace trust to the merchant. Alternative: rank them last.
2. **Free search after the job budget is spent** (F4): proposal — run free catalogue
   search, skip only paid stages. Today a test asserts all sourcing stops.
3. **Frontend**: show `seller_name` / "Marketplace" badge, or leave the new fields to the
   frontend teammate (default: backend only).
4. **PR split**: proposal — three PRs (Stream 0 + A, B, C) for easier review/rollback,
   or one v0.27.0 PR.
5. **Stream D** (added 2026-10-09): ship D1–D3 as v0.28.0 after A/B/C; D4 (known-good
   listings store) only if approved, since it adds a Firestore collection.

---

## 7. Files in this folder

- `research/01-pipeline-audit.md` — pipeline map and failure modes with file:line.
- `research/02-seller-identification-audit.md` — seller identity and page parsing audit.
- `research/03-live-probe-and-logs.md` — live probe results and production log breakdown.
- `research/04-web-research.md` — techniques, platform endpoints, sources.
- `probe/fixtures/` — page excerpts captured 2026-10-08 (historical snapshots; not
  current prices; label them when copied into backend tests).
- `probe/search-probe-summary.txt` — per part × seller results (baseline for step 5).
- `probe/scripts/` — the probe and offline experiment scripts. They write output next
  to themselves (`raw/`, `pages/`, `*.json` are git-ignored). Line numbers in the
  research reports refer to commit b230306 and will drift.
