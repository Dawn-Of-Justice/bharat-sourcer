# Parts finder live audit, 2026-10-08

## Part 2: live probe of the free direct seller search

**Setup.** I called `SellerSearch._search_one` one seller at a time for each of the 7 enabled sellers, with the same queries production builds (`seller_queries(buyable_spec(item).queries, name, resolve_part(item).query)`, seed spec, no Gemini). `BS_*`/Gemini env vars were removed and no model calls were made. Requests: 179 search requests plus robots, 28 for the WooCommerce diagnosis, and about 35 for page verification, roughly 250 in total. Every search request returned HTTP 200. There were no blocks, robots refusals, timeouts or adapter exceptions. Median latency was 0.39 s on the Shopify sellers, 0.5 s on zbotic and 0.8 to 1.1 s on the other WooCommerce sellers (max 2.5 s).

**Hit/miss table.** H = the correct item is ranked first. h = the correct item is in the top 5 but not first. ~ = only a near variant was found. X = results came back, none correct. 0 = no results. `0*` = no results, although a one-word search showed the store stocks the item. The relevance calls are my manual judgement of the titles.

| Part | robocraze | quartz | thinkrob. | zbotic | sharvi | rytronics | compoindia |
|---|---|---|---|---|---|---|---|
| Arduino Uno R3 | H | H | H | h (acrylic case ranked 1st) | X (cases, DIY PCB) | H | H |
| ESP32 DevKit V1 | ~ | ~ | X (P4/S3 boards) | 0 | 0 | 0 | 0 |
| 10k ohm resistor | X (100K, thermistor, pots) | H | X (assortment) | 0 | X (resistor networks) | H | 0 |
| BME280 module | H | H | H | 0 | 0 | 0 | 0 |
| SG90 servo | H | H | H | 0* | 0* | 0* | 0* |
| HC-SR04 | H | H | H | 0* | 0 | h (holder 1st) | X (brackets) |
| 0.96" OLED I2C | H | H | X | ~ | X (LoRa boards) | 0 | 0 |
| LM2596 buck | H | H | h | 0* | 0 | 0 | 0 |
| TP4056 module | H | H | H | 0* | 0 | 0* | 0* |
| Jumper wires M-F | H | ~ (combo packs) | X (standoffs) | X | X (spacers) | X (relimate) | H |
| 18650 holder 2-cell | H | H | ~ | h | X | h | X |
| WS2812B strip | X (12 V white strip) | H | H | 0 | 0 | H | 0 |
| NEMA 17 stepper | H | X (28BYJ, drivers) | ~ (geared) | 0 | X (brackets) | 0 | X (couplings) |
| A4988 driver | H | H | H | H | 0 | H | H |
| 100uF 25V cap | H | H | X | 0 | 0 | 0 | 0 |
| IRFZ44N | X (IRLZ44N) | ~ (IRFZ44) | X | 0 | 0 | 0 | 0 |
| Raspberry Pi Pico | H | h | X | ~ (Pico 2/WH) | h (Pico H) | H | ~ (Pico W) |

Correct item in the top 5 (H or h), out of 17 parts: robocraze 13, quartz 13, thinkrobotics 8, rytronics 7, zbotic 3, compoindia 3, sharvi 1. All 40 empty cells are on the four WooCommerce sellers: 40 of their 68 cells (59%) returned nothing. No seller had a correct item for ESP32 DevKit V1 or IRFZ44N.

### Failure patterns observed

1. **WooCommerce Store API search treats the words as one phrase.** On zbotic, `sg90` returned 5 items, `servo sg90` returned 2, and both `sg90 servo` and `sg90 servo motor` returned 0. The store's title is "TowerPro SG90 … Servo Motor", so both words are there but not next to each other. `hc-sr04`, `tp4056` and `lm2596` return items on zbotic, compoindia and rytronics, yet the production queries for those parts returned `[]`. `short_query` keeps up to 3 words, and the fallback is dropped when it is a single word (`len(s.split()) > 1`), so the single part-number search that would work is never tried. Fixture: `probe/fixtures/woo_store_api_phrase_search.json`.
2. **WooCommerce results come back newest first, not by relevance.** `orderby=relevance` is rejected with HTTP 400, and the allowed values are date, modified, id, title, slug, price, popularity and similar. This is why accessories ("Acrylic Case … Arduino UNO R3", "Holder for HC-SR04") come out first.
3. **The fallback query's own score outranks the real query's results.** `candidate.score` is the overlap with whichever query found the candidate. "jumper wires male to female" falls back to **"to female"**, because `query_variants` takes the last two words when no word contains a digit. That fallback's junk then scores 1.0 and sorts above real hits: HDMI cables, M3 spacers and relimate connectors on zbotic, sharvi and rytronics, and a hex standoff first on thinkrobotics. Other bad fallbacks seen: `17 motor` (returned NEMA17 couplings and 28BYJ), `0.96 i2c` (a CAP1188 touch board), `tp4056 module` (thinkrobotics camera and relay modules at 0.5) and `18650 battery holder` (TTGO T-Beam and ESP32 boards at 1.0).
4. **Accessories score 1.0.** Token overlap cannot tell "Case for Arduino UNO R3", "Bracket for NEMA 17" or "Holder for HC-SR04" apart from the part itself.
5. **Tokenisation misses.** `nema 17` ≠ `nema17`, `irfz44n` ≠ `IRFZ44 N-Channel`, and "2 cell" is written as "Double Cell", "Dual", "18650 x 2" or "2 x 18650", so all of these score 0.6 to 0.8. Shopify predictive search also fuzzes 10K into 100K and IRFZ44N into IRLZ44N. "DevKit V1" appears in no seller's titles.
6. **Shopify suggest returns other items in the same category** (ESP32-P4, a 4.3" ESP32-S3 LCD board, 12 V warm-white strips) when there is no exact match. Nothing here was blocked; robu.in is still excluded by configuration.

### Page verification (21 product pages and 2 variant pages)

| Seller | Path | Result vs. visible page |
|---|---|---|
| robocraze (3) | JSON-LD | All correct: price, in_stock and title (matches og:price and H1). |
| quartz (3) | JSON-LD | **0/3 from the product page.** `"price": "2,650.00"` fails `sane_price` because of the comma, so `extract_product` returns None. `storefront_offer` is then skipped (JSON-LD exists) and so is `meta_offer` (Shopify), so any Quartz price of ₹1,000 or more is lost. Below ₹1,000, the Offer.url has `?variant=` and the page URL does not, so `resolved()` returns None. `variant_url` follows it only when the strict `title_matches(resolution.query)` passes, and that check runs even in judge mode. ESP32 failed the check and was dropped, because `build_candidate` discards pages with a single option. Fetching the `?variant=` URL directly verified ₹358.00, in stock, correctly. |
| thinkrobotics (3) | storefront JSON | No JSON-LD. Two single offers were correct (₹499.99 and ₹229.99, in stock). ESP32-P4 came back as a 4-variant group for the judge. |
| zbotic (3) | JSON-LD | Correct: ₹58.06 including GST (page shows "₹58.06 (₹49.20 + GST)"), and out_of_stock matches the disabled "Out of Stock" button. The "In stock" text elsewhere on the page belongs to related products. Risk: `product:price:amount` = 49.2 (ex-GST), so `meta_offer` would report the ex-GST price on a page without JSON-LD offers. |
| sharvi (3) | JSON-LD | Price and stock correct, ex-GST flagged. **The title is wrong**: the JSON-LD `name` has " \| Sharvielectronics: Best Online Electronic Products Bangalore" appended. The description also shows a stale "Rs. 37.01 (Inclusive of all Taxes)". |
| rytronics (3) | JSON-LD | Price and stock correct. The title has " - Rytronics.in" appended. |
| compoindia (3) | JSON-LD | Correct: ₹350.00 "(Exclusive GST Tax 18%)", tax_included False, and out-of-stock matches `p.stock`. |

Fixtures are in `scratchpad/probe/fixtures/`: `quartz_comma_price_jsonld.html`, `quartz_variant_offer_url_jsonld.html`, `sharvi_jsonld_name_site_suffix.html`, `rytronics_jsonld_name_site_suffix.html`, `zbotic_price_incl_gst_vs_og_ex_gst.html`, `compoindia_exclusive_gst_offer.html`. Full pages are in `probe/pages/`. Raw data is in `probe/search_results.json`, `search_requests.json`, `verify_results.json` and `summary.txt`.

## Part 1: production logs (bharat-sourcer-integration)

`gcloud` was authenticated. The read returned 13,668 entries, all of the 7-day window. The earliest entry is 2026-10-03 09:11Z, and a CreateService audit event shows the service is new. There were 19 jobs created (`POST /v1/jobs` 202) and 11 attempts rejected with 401.

| Category | Count |
|---|---|
| DISCOVERY_TRUNCATED (finishReason MAX_TOKENS, maxOutputTokens 2048) | 21 of 22 grounded discovery calls (95%); grounded_sources 0 to 19 |
| DISCOVERY_FAILED type=ValueError (truncated, 0 grounded sources) | 1 (2026-10-05T19:50:26Z) |
| "Part research failed: ValidationError" | 1 (2026-10-06T15:10:07Z) |
| Gemini retry ("attempt 2 of 3") | 1 |
| DISCOVERY_REJECTED, SELLER_SEARCH_FAILED, BLOCKED, FETCH_*, QUEUE_AGE_EXCEEDED, tracebacks | 0 |
| `/internal/work` 503 (`work_once` returns 503 while a job is incomplete, so Cloud Tasks retries; by design but logged at ERROR; latency up to 118 s) | 52 (vs 43 × 200) |
| `GET /v1/session` 503 (cause not logged) | 3 |

Gemini usage was 70 calls: discovery 22 (≈$0.28), research 20, judge 18, others 10.

**What the logs cannot show.** I could not get NO_VERIFIED_OFFERS counts, per-seller statuses or per-domain fetch failures, because they are not in the logs. The `SELLER_SEARCH …statuses=` line is INFO through a module logger, no logging config sets INFO (only `usage.py` does, for its own logger), so it is dropped. Line outcomes live in job records, which I did not read. A per-seller production breakdown is therefore **unverified**.
