# Bharat Sourcer: research notes on routing, extraction and matching

Researched 2026-10-08. Items marked **[verified]** were checked live today. Items marked **[unverified]** are known conventions that need a live test before you depend on them.

## 0. Live platform fingerprints of the target sellers [verified, homepage GET only]

| Seller | Platform / signal | Best route |
|---|---|---|
| robocraze.com, quartzcomponents.com | Shopify (`cdn.shopify.com`) | `/search/suggest.json` (quartz returned 200) |
| zbotic.in | WordPress + WooCommerce | Store API worked: `price:"120006"`, `currency_minor_unit:2` = ₹1,200.06 |
| evelta.com | BigCommerce Stencil (`cdn11.bigcommerce.com`) | `/search.php?search_query=` HTML, then JSON-LD |
| probots.co.in | Magento 2 (`text/x-magento-init`) | `/catalogsearch/result/?q=` or `/graphql` |
| electronicscomp.com, flyrobo.in | OpenCart (`catalog/view/theme`) | `index.php?route=product/search&search=` |
| thingbits.in | Headless Next.js (`X-Powered-By: Next.js`) | JSON-LD on the product page (2 blocks seen). No platform API |
| robu.in | **403 + `Cf-Mitigated: challenge`, title "Just a moment..."** | Mark as blocked. Use Gemini discovery and the snippet only. Do not try to get around it |

Platforms change, so store the fingerprint per host with a `detected_at` date and re-detect weekly or whenever a parse fails.

## 1. Offer extraction

### Priority ladder (per page)
1. A platform JSON endpoint, when the platform is known. It is the most structured source.
2. JSON-LD `Product` / `ProductGroup`.
3. Microdata/RDFa (`itemprop="price" content="…"`).
4. Meta tags: `product:price:amount` + `product:price:currency`, `product:availability`, `og:price:amount` (an older Pinterest/OG variant). Source: https://developers.facebook.com/docs/marketing-api/catalog/guides/microdata-tags
5. Heuristic DOM price nodes. Store these with `confidence="low"` and never treat them as "verified".

Library: `extruct.extract(html, base_url=get_base_url(html, url), syntaxes=["json-ld","microdata","opengraph","rdfa"], uniform=True)` returns `@type`-normalised dicts for every syntax. RDFa is experimental and not uniformed. https://github.com/scrapinghub/extruct

### JSON-LD walking rules
- The root can be an object, an array, or `{"@graph":[...]}`. Flatten all three recursively and index nodes by `@id` so references like `"offers":{"@id":"#offer"}` resolve.
- `@type` can be a string or a list, and can be prefixed (`"schema:Product"`, `"http://schema.org/Product"`). Match on `endswith("Product")`.
- `offers` can be an `Offer`, a list of `Offer`, or an `AggregateOffer` (`lowPrice`, `highPrice`, `offerCount`, nested `offers`). Google merchant listings accept only `Offer`, not AggregateOffer: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing
- Read the price as `offer.price`, falling back to `offer.priceSpecification.price` (the spec can also be a list). `priceSpecification.priceType = https://schema.org/StrikethroughPrice` (or legacy `ListPrice`) means MRP or a struck price, not the selling price (same Google page).
- Variants: `ProductGroup` uses `hasVariant[]`, `variesBy`, `productGroupID`. Each variant `Product` has its own `sku` and `offers`. A variant can instead point back with `isVariantOf` / `inProductGroupWithID`. https://developers.google.com/search/docs/appearance/structured-data/product-variants
- Normalise availability by suffix: `re.sub(r'^https?://schema\.org/', '', v)`. This handles `http`/`https` variants and short names. Valid values include `InStock, OutOfStock, PreOrder, BackOrder, SoldOut, Discontinued, LimitedAvailability, OnlineOnly, InStoreOnly` (Google page above).
- Per schema.org, `price` should use `.` as the decimal mark and no currency symbol, with currency in `priceCurrency` (ISO 4217). Real pages break this rule (`"₹1,299"`, `"1299.00 INR"`), so always run the value through the price parser. https://schema.org/price

### Pitfalls
- Invalid JSON: trailing commas, comments, raw newlines in strings, `&quot;`. Try `json.loads(s, strict=False)`, then strip `//` and `/* */` comments and trailing commas, then `html.unescape` before parsing. On failure, skip that one block, not the whole page.
- One page can carry several Product blocks: related products, a theme block plus an SEO-plugin block, breadcrumb items. Prefer a block whose `url`/`@id` matches the canonical URL, or whose `name` best matches `<h1>`/`og:title`. Otherwise prefer the block that has `offers`. Never take the first block blindly.
- Stale structured data: on Shopify/Woo, JSON-LD can show the default variant or cached prices. If both a platform JSON source and JSON-LD exist, prefer the platform JSON, and flag disagreements larger than 5%.
- Escaped titles (`&amp;`, `&#8377;`) must go through `html.unescape`.

### Platform endpoints and fingerprints
Fingerprint rules come from the open Wappalyzer fork https://github.com/enthec/webappanalyzer (`src/technologies/*.json`).

- **Shopify.** Fingerprints: cookies `_shopify_y`, `_shopify_s`; headers `x-shopid`, `x-shopify-stage`; JS `ShopifyAnalytics`; `cdn.shopify.com`; `*.myshopify.com`.
  - Search: `GET /search/suggest.json?q=…&resources[type]=product&resources[limit]=10&resources[options][unavailable_products]=last`. Returns at most 10 results. Product fields include `price`, `price_min`, `price_max` (decimal strings), `available`, `url`, `handle`. A 429 comes with `Retry-After`. https://shopify.dev/docs/api/ajax/reference/predictive-search
  - Product: `GET /products/<handle>.js` returns `price`, `price_min`, `price_max`, `compare_at_price*`, `available`, and up to 250 `variants[]` (`id`, `title`, `option1..3`, `price`, `available`, `sku`). Money is in the presentment currency. https://shopify.dev/docs/api/ajax/reference/product
  - Units: the doc example `"price": 12900` is integer paise. `/products/<handle>.json` (undocumented) returns decimal strings like `"129.00"` [unverified]. Normalise at the boundary.
  - Variant deep link: `?variant=<id>`.
- **WooCommerce.** Fingerprints: `woocommerce_params` / `wc_add_to_cart_params`, `meta generator WooCommerce`, `/wp-content/plugins/woocommerce`.
  - Search: `GET /wp-json/wc/store/v1/products?search=…&per_page=…`. Also takes `sku=`, `stock_status=instock`, and `type=variation`.
  - Fields: `permalink`, `sku`, `is_in_stock`, `is_purchasable`, `low_stock_remaining`, and `prices{price, regular_price, sale_price, price_range, currency_code, currency_minor_unit, currency_prefix…}`. Prices are **strings in minor units**: `int(p)/10**minor_unit`. https://developer.woocommerce.com/docs/apis/store-api/resources-endpoints/products
- **Magento 2.** Fingerprints: `script[type="text/x-magento-init"]`, `static/_requirejs`, cookies `mage-cache-storage`, `X-Magento-Vary`.
  - Public GraphQL: `products(search:"…", pageSize:10){items{sku name url_key stock_status price_range{minimum_price{final_price{value currency} regular_price{value}}}}}`. https://developer.adobe.com/commerce/webapi/graphql/schema/products/queries/products/
  - GET requests to `/graphql?query=` are cacheable: https://developer.adobe.com/commerce/webapi/graphql/usage/requests/
  - HTML fallback: `/catalogsearch/result/?q=`.
- **OpenCart.** Fingerprints: cookie `OCSESSID`, `catalog/view/theme/`. Search: `index.php?route=product/search&search=…`. Product URL: `route=product/product&product_id=` or an SEO slug. No public JSON API, so parse the HTML or JSON-LD (often missing, so microdata or DOM `.price-new`/`.price-old` [unverified]).
- **BigCommerce.** Fingerprints: `cdn11.bigcommerce.com`, JS `bigcommerce_config`, `meta platform=bigcommerce`, `*.mybigcommerce.com`. Search: `/search.php?search_query=…`. The Storefront GraphQL API needs a token embedded in the page, so prefer HTML plus JSON-LD.
- **PrestaShop.** Fingerprints: cookie `PrestaShop-*`, JS `prestashop` (the global object holds `prestashop.currency`), `/modules/ps_*`, `meta generator PrestaShop`. Search: `/search?controller=search&s=…` [unverified].
- **Wix.** Fingerprints: headers `X-Wix-Request-Id`, `meta generator "Wix.com Website Builder"`, `static.parastorage.com`. A store shows `wixstores` in `#wix-viewer-model`. Product pages are `/product-page/<slug>` [unverified]. Use JSON-LD.
- **Dukaan / Instamojo / Zoho Commerce.** No documented public catalogue API was found. Dukaan's developer surface is theming (Nunjucks): https://apis.io/providers/dukaan/
  - Store hosts: Instamojo uses `<brand>.myinstamojo.com` (https://shiprocket.in/blog/how-to-sell-on-instamojo). Zoho supports free subdomains and custom domains (https://help.zoho.com/portal/en/kb/commerce/faqs/product-faq/articles/can-i-use-my-own-domain-name-with-zoho-commerce).
  - Route all three through generic JSON-LD/OG extraction, and fingerprint them by asset hosts (`mydukaan.io`, `instamojo`, `zohocommerce`/`zohostatic` CDN) [unverified].
- **Headless (Next.js/Nuxt).** Check `<script id="__NEXT_DATA__">` and JSON-LD.

## 2. Indian price parsing
- Symbols: `₹`, `&#8377;`/`&#x20B9;`, `Rs`, `Rs.`, `INR`, the `/-` suffix ("Rs. 499/-"), and sometimes the symbol and number in separate spans. Run `html.unescape` and collapse whitespace across adjacent nodes first.
- Lakh grouping: `1,23,456` = 123456 (https://en.wikipedia.org/wiki/Indian_numbering_system). Regex:
  ```
  (?:₹|\bRs\.?|\bINR)\s*((?:\d{1,2},)?(?:\d{2},)*\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*(?:/-)?
  ```
  Accept both groupings, then remove the commas. `price-parser` (`Price.fromstring`) handles general separators but documents no Indian or ₹ cases, so wrap it with your own regex. https://github.com/scrapinghub/price-parser
- **MRP vs selling price.** Indian law requires MRP declared in rupees, inclusive of all taxes, and e-commerce listings must repeat the label declarations (Legal Metrology (Packaged Commodities) Rules; https://ssrana.in/articles/legal-metrology-amendment-rules-2023/, https://www.foodnavigator-asia.com/Article/2017/07/12/Indian-e-commerce-products-to-carry-MRP-labelling-from-2018). Pages therefore show both "M.R.P.: ₹999" (often in `<del>`/`<s>`/`.price-old`/`compare_at_price`/`regular_price`) and the selling price.
  - Store `price` = the lowest current price, plus `mrp` kept separately.
  - Reject any value that is labelled `MRP`, struck through, or a "You save ₹X" figure.
- **GST.** "Inclusive of all taxes" is the norm for B2C. B2B stores (Evelta, Moglix, Industrybuying) often show "₹X + GST" or "excl. GST". Detect `(?i)(excl\.?|exclusive|\+)\s*(of\s*)?GST` and store `tax_included=false` with a `gst_rate` if one is shown (18% is typical for electronic components [unverified]). Never compare excl-GST and incl-GST prices without normalising.
- **Minor units.** Shopify `.js` and Woo Store API values are integers or strings in paise. JSON-LD and suggest.json use decimals. A sanity check: if the parsed value is ≥100× the median for the same part across sellers, suspect paise.
- **Ranges.** "₹120 – ₹450" or AggregateOffer low/high means there are variants. Resolve to the specific variant (pin count, pack size) or store it as a range, not as a single verified price.
- **Quantity pricing.** "₹5/pc, min 10" or a unit-sale-price line: store both `unit_price` and `pack_qty`.

## 3. Seller identification and page classification
- **Hosts.** Lowercase the host, strip the trailing dot, decode IDNA, then strip leading `www.`, `m.`, and `amp.` labels. Get the registrable domain with `tldextract` using `top_domain_under_public_suffix`. Bundle the PSL snapshot offline with `suffix_list_urls=()`. https://github.com/john-kurkowski/tldextract
  - The PSL includes `co.in`, `net.in`, `org.in`, `firm.in`, `gen.in`, `ind.in`. In its private section, `myshopify.com` and `wixsite.com` are listed, but **`myinstamojo.com` and `mydukaan.io` are not** [verified against https://publicsuffix.org/list/public_suffix_list.dat].
  - So set `include_psl_private_domains=True`, and keep your own `MULTI_TENANT_SUFFIXES` list (`myinstamojo.com`, `mydukaan.io`, …) so that each storefront is its own seller.
  - Path-based tenants (one domain with `/store-slug/` paths) need the first path segment in the seller key [unverified for Dukaan].
  - Also follow `<link rel="canonical">` and AMP `rel=canonical` back to the main host.
- **Marketplaces** (seller ≠ host): amazon.in, flipkart.com, meesho.com, indiamart.com, moglix.com, industrybuying.com.
  - Model these as `{marketplace, merchant}`. Read the merchant from the "Sold by" / "Seller" text near the buy box (Amazon `#sellerProfileTriggerId`/`#merchantInfo`; Flipkart `#sellerName` [unverified selectors, they change often]). If it can't be read, set `merchant=null` and do not invent one.
  - IndiaMART is RFQ/lead-based. Treat its prices as "indicative", never as verified offers.
- **robots.txt (RFC 9309, https://www.rfc-editor.org/rfc/rfc9309).** Amazon.in `User-agent: *` allows `/dp/` (except `/dp/product-availability/` and `/dp/rate-this-item/`) and disallows faceted `/s?` patterns. It also fully blocks named AI crawlers. Flipkart disallows `/search?` and allows `/p/` [verified]. For Amazon, the sanctioned route is the Associates **Creators API**: PA-API 5 was deprecated in spring 2026 and now returns 403, and Offers is replaced by OffersV2. https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation
- **Challenge and block pages** (classify, then stop; never get around them):
  - Cloudflare: header `cf-mitigated: challenge` (always `text/html`, https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/). Other signs are `<title>Just a moment...`, `/cdn-cgi/challenge-platform/`, and status 403/503.
  - Akamai: "Access Denied … Reference #" with `_abck`/`ak_bmsc` cookies. The cookies alone only mean Akamai is present (https://cooki.fi/cookies/-abck).
  - DataDome: `x-datadome` header or `captcha-delivery.com`.
  - HUMAN/PerimeterX: `_px*` cookies, "Press & Hold".
  - Generic: `g-recaptcha`, `h-captcha`, `cf-turnstile`, and Amazon's `/errors/validateCaptcha`.
  - Emit `status=blocked` and open the circuit for that host.
- **Soft 404s** (HTTP 200 with no product, https://developers.google.com/search/docs/crawling-indexing/http-network-errors#soft-404-errors). Signals:
  - Text such as `(?i)(product (is )?(not found|no longer available|unavailable)|page (not found|doesn't exist)|404|oops)`.
  - A redirect to `/` or to a category page.
  - A canonical that differs from the requested URL and is not a product URL.
  - No Product structured data and no price.
- **Listing vs product page.**
  - A product page has a Product or ProductGroup node (or `og:type=product`), one `<h1>`, an add-to-cart form (`form[action*="/cart/add"]`, `name="add-to-cart"`, `button.single_add_to_cart_button`, `#product-addtocart-button`, `route=checkout/cart/add`), and a URL like `/products/`, `/product/`, `/p/`, `/dp/`, or `product_id=`.
  - A listing has `ItemList`/`CollectionPage`/`SearchResultsPage`, more than 3 distinct prices, pagination, or `/collections/`, `/product-category/`, `/catalogsearch/`, `/search`.
  - Score these signals together; don't rely on any single one.

## 4. Matching parts to listings
- **MPN key.** Uppercase, NFKC, map `µ`/`μ` to `u`, then remove every `[\s\-_./]`. So `HC-SR04` and `HCSR04` both give `HCSR04`. Keep the suffix letters that matter, because LM2596 and LM2596S (package) differ and IRFZ44N is not IRFZ44. Match on the exact key first, and allow a suffix to differ only if the BOM part didn't specify one.
- **Passive values.** Parse with a regex into SI base units:
  - `(?i)(\d+(?:\.\d+)?)\s*([pnuµμmkKMG]?)\s*(Ω|ohms?|r|f|farads?|mfd|h|v|w|a)?` handles `10k`, `10K ohm`, `10kΩ`, `10000 ohm`, and RKM codes like `4K7` / `4R7` (needs its own regex `(\d+)([RKM])(\d+)`).
  - `MFD` means µF. `100uF`, `100µF` and `100 MFD` all equal 1e-4 F.
  - Wattage: `1/4W` = `0.25W`; parse fractions with `(\d+)/(\d+)\s*W`.
  - Compare normalised values with a 0.1% tolerance and treat a voltage or wattage of at least the requested value as compatible.
- **Pack size.** `(?i)(?:pack|set|lot|bag)\s*of\s*(\d+)|(\d+)\s*(?:pcs?|pieces?|nos?\.?|units?)\b|\bx\s*(\d+)\b`, plus jumper-wire counts like "40 pcs". Compute `unit_price = price / qty` for ranking, and flag "assorted kit" listings.
- **Variant-critical attributes** become hard filters when given: pin count `(\d+)\s*-?\s*pins?` (ESP32 30 vs 38), gender `M-F|M-M|F-F|male.to.female`, length `(\d+)\s*cm`, voltage (3.3V vs 5V), board revision (V1/V2, CH340 vs CP2102). A conflict means reject, not just down-rank.
- **Accessory and adjacent-product guard.**
  - Penalise titles containing `case|cover|enclosure|shield|adapter|cable for|compatible with|for (arduino|raspberry|esp32)|holder|mount|screen guard|replacement|kit` when the BOM item itself is not one of these.
  - Detect the "X **for** Y" pattern: the target part is Y, so the item is an accessory.
  - Also reject "breakout"/"module" vs "IC chip" mismatches (BME280 module vs bare BME280 IC) when the BOM says module.
- **Scoring.** score = 0.5·(required-token coverage, all-or-nothing gate) + 0.3·BM25 or token-set ratio (`rapidfuzz.fuzz.token_set_ratio`, https://github.com/rapidfuzz/RapidFuzz; BM25: https://en.wikipedia.org/wiki/Okapi_BM25) + 0.2·attribute agreement − accessory penalty. Required tokens are the MPN key plus the critical attributes. Keep `match_reason` for explainability.
- **Query backoff ladder**, stopping when there are 3 or more candidates above threshold:
  1. Exact MPN plus the key attribute ("ESP32 DevKit V1 30 pin").
  2. MPN alone ("ESP32 DevKit").
  3. Synonyms or aliases ("ESP32 WROOM-32 development board", "HC SR04 ultrasonic").
  4. Category plus value for passives ("10k resistor", then "resistor 10k ohm 1/4 watt").
  5. Gemini-grounded discovery.

  Store searches are often weak at tokenising hyphens, so issue both `HC-SR04` and `HCSR04` forms. Re-score every candidate against the original, un-relaxed spec so that query relaxation never loosens acceptance.

## 5. Router and pipeline patterns
- **Route per part.**
  - Classify the part: passive, module, IC, mechanical, cable.
  - Choose sellers by category affinity and health score.
  - Choose the strategy by fingerprint (platform API, then site HTML search, then grounded discovery, then a marketplace API).
- **Fallback ladder per seller.** API, then HTML search, then the product page's JSON-LD. Record which rung succeeded so the router learns per host.
- **Circuit breaker per host** (https://martinfowler.com/bliki/CircuitBreaker.html). The states are closed, open, and half-open.
  - Open after N consecutive failures, or immediately on `cf-mitigated`/captcha or a 429.
  - Honour `Retry-After`, and use exponential cooldown with jitter.
- **Health score.** An EWMA of success rate and p95 latency per (host, strategy), used to order and prune sources.
- **Hedging and budgets** (Dean & Barroso, "The Tail at Scale", https://research.google/pubs/the-tail-at-scale/).
  - Fan out across sellers in parallel with a global deadline (e.g. 8 s per BOM line) and a per-host concurrency of 1–2 for politeness.
  - Hedge only idempotent GETs, to a *different* source, after the p95 delay.
  - Return partial results as they arrive.
- **Caching.**
  - Positive offers: 6–24 h TTL, with stale-while-revalidate semantics (RFC 5861, https://www.rfc-editor.org/rfc/rfc5861).
  - Negative results: "no match" ~24 h, "blocked" ~6 h, "soft-404 URL" ~7 d. The idea mirrors DNS negative caching (RFC 2308, https://www.rfc-editor.org/rfc/rfc2308).
  - Platform fingerprint: 7 d.
  - robots.txt: 24 h, as RFC 9309 recommends.
- **Result contract.** Each offer carries `source_strategy`, `extraction_method` (platform_json, jsonld, microdata, og, heuristic), `confidence`, `fetched_at`, `merchant`, `marketplace`, `tax_included`, `mrp`, `pack_qty`, `variant`, `match_score`, `match_reason`. Only `platform_json` or `jsonld` with a matching price on the page counts as "verified". Label fixtures as demo.
- **Observability.** Use structured logs keyed by `run_id`, `bom_line`, and `host`. Emit per-host counters (ok, blocked, soft404, parse_fail, no_match, 429) and a histogram of extraction method. Keep a golden-page regression corpus (saved HTML per platform) so fingerprint and parser drift shows up in CI.
