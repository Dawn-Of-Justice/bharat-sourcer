# Parts-finder flow audit: from a BOM line to offers

Paths are under `backend/src/bharat_sourcer/`. I edited no repo files. Evidence came from reading the code and from offline scripts in the scratchpad (`exp1.py`, `exp2.py`, `exp3.py`). The five sourcing test files pass (191 passed).

## 1. How one BOM line is processed

1. **Job layer.** `jobs.py:946-972`. If the line has known URLs, it tries `refresh_known` first. If the job's budget is spent, the line ends as `not_run` / `JOB_BUDGET_REACHED`. Otherwise it calls `source_for_project`. Any exception ends the line as `failed` / `SOURCING_FAILED`. Lines past the part limit (10 by default) end as `not_run` / `SOURCING_LIMIT` (`jobs.py:934-941`).
2. **Dedupe.** `service.py:318-353`. The same part within one job reuses one result for 300 s.
3. **Buying spec.** `part_spec.py:467`. The line uses its AI spec after `guard_spec`. Without one, it gets a seed spec from the name (`seed_spec`, `:386`).
4. **Free stage.** `service.py:509-523`.
   - **Queries.** `seller_queries` (`service.py:204`) takes the spec's first query, the first `query_variants` form of the raw name, then the rest, capped at 3.
   - **Search.** `SellerSearch.search` (`seller_search.py:427`) caps queries at 4. It runs 7 enabled sellers in a 6-thread pool with a **20 s overall deadline** (`:365, :454`).
   - **Per seller.** Each seller tries up to 3 queries, plus one `short_query` fallback if nothing was found. It stops at the first title with overlap 1.0 or at 10 hits (`:386-425`).
   - **Merge.** Results are merged round-robin, keeping 8 candidates (`seller_fetch_budget`, `:479`).
   - **Verify.** `_verify_urls` (`service.py:639`) fetches the candidates one after another. Per URL it tries, in order: `verify_page` (JSON-LD), `variant_url`, `storefront_offer`, `meta_offer`, then `build_candidate` / `shopify_variants` when a judge is configured. It stops early at 3 in-stock offers from 2 sellers (`:213`).
   - **Judge.** `_review` (`service.py:275`) calls `review_candidates` (`judge.py:491`). That uses the `shortcut_match` cache, then the Gemini judge on up to 8 candidates. Mismatches are dropped. If the judge returns `None`, it falls back to `title_matches(raw_name, title)`.
5. **Paid stage.** `service.py:528-548`. Runs only if no in-stock exact or compatible offer was found and `paid_allowed()` is true.
   - `GeminiDiscovery` (`:106`) makes one 45 s call with up to 3 retries.
   - URLs come only from the grounding metadata. They are ranked so Indian sellers come first and datasheets and distributors (`LOW_PRIORITY`) come last, but nothing is removed. The list is cut to 5 (`:172`).
   - The same verify and judge steps run on these URLs.
6. **After that.**
   - If discovery failed and there are no offers, the line returns early as `failed` / `DISCOVERY_FAILED` (`:559`).
   - Otherwise the trust labels run (guarded), then research (`review_or_skip`, guarded).
   - The line ends as `offers_found` or `no_verified_offers` / `NO_VERIFIED_OFFERS` (`:616`).
7. **Follow-up.** `service.py:364-430`. Runs once, grounded-only, when there is no offer and research returned `no_evidence`.

**Possible end states:** `already_owned`, `offers_found`, `no_verified_offers`, `failed` (`DISCOVERY_FAILED`, `SOURCING_FAILED`) and `not_run` (`SOURCING_LIMIT`, `JOB_BUDGET_REACHED`). `offers_found` is also used when every offer is partial or out of stock.

## 2. Failure modes, most damaging first

**F1. Bad seller queries, and no step that relaxes them.** (`seller_search.py:139-155`, `service.py:204`) Store searches need every word to match. Measured outputs of `seller_queries`:
- `"Wire, 22 AWG, solid core"` gives `['wire 22 awg solid core', '22 core']`. The "core form" rule keeps the numbers plus the *last* word, and here the last word isn't the noun.
- `"Arduino Uno R3 (compatible)"` gives `[…, 'compatible', 'uno r3']`. `"5mm LED (red) x5"` gives `[…, 'red', '5mm x5']`. `"0.1uF ceramic capacitor (104)"` gives `[…, '104', …]`. Any word in brackets becomes a query on its own.
- A one-word junk query scores `overlap('red','Red Jumper Wire 20cm') = 1.0`. That stops the seller's query loop (`:419`), the junk sorts to the top, and it uses up the 8 fetch slots.
- `"10k resistor 1/4W"` gives `['10k resistor 1/4w', '10k 1/4w']`. Neither query drops the rating, and the fallback adds nothing because both short forms were already tried (`:392`). So `"10k resistor"` is never searched.
- `"10kΩ Resistor (1/4 W, 5%)"` gives `['10kohm resistor 1/4 w 5', '10k resistor 1/4 w 5', '1/4 w 5']`. The seed's `normalise_text` glues `10kohm`, and `%` turns into a stray `5`.
- Counts and pack sizes stay in the query: `'10 x 220ohm resistors'`, `'2x 18650 …'`, `x5`.
- **Hindi text is mangled.** `normalise` turns `'पुश बटन स्विच'` into `'प श बटन स व च'`, and the second query becomes `'व च'`. The pattern `[^\w.\-/ ]` deletes Devanagari combining marks (`:105`). The category also stays `other`.
- `spec.synonyms` (for example HCSR04, GL5528) are never searched. No spelling variants are made for model numbers (`HC-SR04` / `HCSR04` / `HC SR04`; `LM7805` / `7805`).

**F2. The shared cache merges different queries and keeps bad responses.**
- The shared search cache key is `(seller, normalise_part(query))` and does not include the URL (`seller_search.py:377`). `normalise_part` treats `10kohm…` and `10k…` as the same text, so the second query is served the first query's response and is never sent. `exp3.py` confirmed this with the cache on (the default, `build_cache`): 2 of 3 queries were sent, while diagnostics report 3.
- Any HTTP 200 is cached for 6 h across jobs (`politeness.py:276-278`, Firestore when deployed). That includes an HTML page served instead of JSON, or an empty result. `exp2.py`: a second run made 0 network calls and still got `error: HTTP 200`.
- The first adapter error returns from the seller loop at once (`seller_search.py:403-409`), so the remaining queries are never tried.

**F3. The strict title gate takes over silently.**
- `judge_candidates` returns `None` when the budget is spent or the call fails. That throws away verdicts it already had, including deterministic `shortcut_match` exact matches (`judge.py:375-380`).
- `_review` then applies `title_matches`, which requires every word of the raw name in the title (`listings.py:71-109`). Measured:
  - `'10k resistor 1/4W'` against `'10k Ohm 1/4 Watt Resistor'`: False
  - `'HC-SR04'` against `'HCSR04 Ultrasonic Sensor'`: False
  - `'4.7µF 50V…'` against `'4.7 uF 50 V…'`: False
  - `'Breadboard 830 points'` against `'830 Point … Breadboard'`: False
  - `'5mm LED (red) x5'` against `'5mm Red LED (Pack of 10)'`: False
- Even when the judge works, `variant_url` and `page_images` still use this gate (`service.py:608, 678`). Variant pages whose title differs from the raw name are not followed.

**F4. A spent job budget also skips the free search.** `jobs.py:953-960` marks the remaining lines `JOB_BUDGET_REACHED` without running seller search, which costs nothing. The service was built for exactly this case: it keeps free results and skips only grounded discovery (`service.py:529`). A test asserts the current behaviour (`test_cost_controls.py:546`).

**F5. `DISCOVERY_FAILED` throws away free-stage evidence.** The early return (`service.py:559-572`) skips research, image candidates and the follow-up, even though seller pages were fetched. Its message says "Seller search failed" even when seller search worked and Gemini failed. This matches the 5 Oct incident, where most lines ended as `DISCOVERY_FAILED`.

**F6. The 20 s seller deadline throws away partial results.** A seller that hasn't finished is reported as `timeout` and loses every candidate it collected (`seller_search.py:456-459`). One request can take up to 8 s to connect and 12 s to read, plus the robots.txt fetch and per-host pacing. Three lines run at once and share a limit of 2 requests per host, so timeouts are likely under load. Abandoned threads keep running after `shutdown(wait=False)` and keep host slots busy, which slows the verify step.

**F7. Little room when no catalogue has the part.** Only 7 small Shopify/WooCommerce stores can be searched. The grounded stage fetches 5 URLs, and the discovery prompt asks for datasheets as well as sellers, which use up slots. Category or search-result pages are rejected (`listings.py:399`, more than one Product). Discovery searches only `raw_name`, not the spec's queries, synonyms or category (`service.py:536`).

**F8. Not every step is wrapped in error handling.** `_verify_urls` catches only `FetchError`, `ValueError` and `RecursionError` (`:708`). `assess_offer` (`:308`) and `page_images` (`:608`) are unguarded. Any other exception reaches `jobs.py:965`, and the line becomes `SOURCING_FAILED`, losing offers and paid calls already made. A 4,000-case fuzz of the listings parsers found no escaping exceptions, so this is a structural risk rather than one I could reproduce. Pydantic errors on an offer are counted as `blocked` with the reason "could not be read safely", which is misleading.

**F9. Old results are reused.**
- The shared page cache uses `TTL["page"] = 8 h` (`cache.py:32`, used at `politeness.py:186`). That overrides `BS_SELLER_PAGE_CACHE_S = 900`, so price and stock can be 8 h old while `checked_at` shows now.
- `SafeFetcher._allowed` stores a robots.txt result of `None` permanently when the fetch gets a 5xx or 403 (`fetch.py:163-171`). `SellerSearch` keeps one fetcher for the whole process, so one failed robots.txt fetch leaves that seller `robots_disallowed` until restart.
- `refresh_known` passes an unwrapped fetcher (`service.py:456`), so refreshes skip pacing and block detection.

**F10. Statuses and quantities don't say enough.** `offers_found` is used even when every offer is partial or out of stock. `qty_unit` can only be `"pcs"` (`schemas.py:406`), so wire sold by the metre and packs have nothing to normalise against.

## 3. Test gaps

- `query_variants` / `seller_queries` are tested only on four clean names (`test_seller_search.py:233, 682`). There are no cases for bracketed generic words, last-word-is-not-the-noun, counts or packs in the name, fractions like `1/4W`, `%`, non-Latin script, or model-number spelling variants.
- No test checks that a shared-cache hit serves the response the query actually asked for, or that 200 HTML or empty results are not cached for 6 h.
- No test checks that one query's error doesn't stop that seller's remaining queries.
- `test_service_falls_back_to_the_title_gate_when_the_judge_fails` (`test_judge.py:442`) covers the happy path only. No test checks that shortcut verdicts survive a judge failure or a spent budget, and none runs the gate against realistic seller titles.
- No test runs free seller search when the job budget is spent; the current test asserts the opposite.
- No test checks that research and images survive `DISCOVERY_FAILED` (`test_sourcing.py:359` checks only the two codes).
- No test covers a seller timing out with partial results, or several lines contending for one host.
- No test covers unexpected exceptions inside `_verify_urls`, `assess_offer` or `page_images`.
- No test covers caching of a failed robots.txt fetch or the page-cache TTL.

## 4. Recommendations

1. **A query-relaxation ladder (F1, F3).**
   - Build queries from the spec: model number, then value plus unit plus category noun, then category noun plus key parameters, then synonyms.
   - Remove counts and pack sizes (`10 x`, `x5`, `pack of`) and percentages.
   - Never send a one-word generic query (`compatible`, `red`, a bare number); require a category noun or a model number.
   - Make model-number variants (`HC-SR04` / `HCSR04`), and keep the bracketed alias only when it looks like a model number or abbreviation.
   - Convert units the way sellers write them (`10k ohm`, `0.25W` for `1/4W`).
   - Move down the ladder whenever a rung returns zero results or no title above an overlap threshold, and count only the category noun and model number toward overlap.
2. **Handle non-Latin input (F1).** Keep Unicode combining marks in `normalise` (allow categories Mn/Mc). Have the extraction or spec writer always produce an English `part_name` and queries, and fall back to those when the raw name isn't ASCII.
3. **Fix the cache (F2, F9).**
   - Key the shared search cache on the exact URL, or the exact normalised query text, plus the adapter version.
   - Cache only responses the adapter parsed successfully, with a short TTL for empty results.
   - Never cache a response whose content type is wrong.
   - Use `BS_SELLER_PAGE_CACHE_S` for shared page entries.
   - Never store a robots.txt failure permanently; give it a TTL of about 10 minutes.
4. **Keep each step's results when a later step fails (F3, F5, F8).**
   - On judge failure or a spent budget, return the shortcut and cached verdicts and leave the rest marked "unjudged". Show them as `partial` rather than putting them through the strict gate.
   - Use the spec-aware matchers (`title_conflicts`, `measure_conflicts`) instead of `title_matches` in `variant_url`.
   - Wrap each URL in `_verify_urls`, and `assess_offer` / `page_images`, in `except Exception` that records a per-URL reason.
   - On `DISCOVERY_FAILED`, still run research on the pages already fetched, and say which step failed.
5. **Run the free search when the budget is spent (F4).** Let `jobs.py` call the service even when the budget is spent; the service already skips the paid steps.
6. **Return partial results and set time budgets (F6).** Have `_search_one` return its partial results on the deadline, for example through a shared collector. Give each line one wall-clock budget across all steps, and size the deadline for `sourcing_parallelism`.
7. **More paid-stage coverage (F7).** Send the spec's best query plus synonyms to discovery. Ask for seller pages only, since research handles datasheets separately. Drop `LOW_PRIORITY` hosts before the 5-URL cut, not after.
8. **Make no-offer results explainable (all of the above).**
   - Record a per-candidate outcome: `no_jsonld`, `category_page`, `no_inr`, `title_gate`, `judge:mismatch`, `blocked` or `exception`.
   - Log one structured outcome line per line, with the queries actually sent and the cache hits.
   - Add `offers_partial_only` and `out_of_stock_only` sub-statuses.
   - Add tests for every item in section 3, using the tricky names here as fixtures.
