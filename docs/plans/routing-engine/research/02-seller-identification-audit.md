# Seller identification and offer extraction audit

Paths are relative to `backend/src/bharat_sourcer/` unless stated. Baseline: the 5 named suites pass (156 tests), plus `test_seller_search.py` (39 tests). The experiments ran offline and are in `scratchpad/exp_sellers.py`. Outputs are quoted below.

## 1. How a URL becomes a seller and a VerifiedOffer

- **Fetch.** `SafeFetcher.get` follows up to 6 redirects. Each hop is checked for HTTPS only, port 443 and robots.txt (fetch.py:182-198). The returned `Page.url` is the final URL (fetch.py:142,152). Hosts are IDNA-encoded only for the connection (fetch.py:46). Challenge detection (politeness.py:55-67) runs only when the service wraps the fetcher, which happens only if seller search is configured (sourcing/service.py:360-361).
- **Seller identity is the raw final hostname.** It is set at listings.py:319, listings.py:501, platforms.py:162 and platforms.py:284. Query strings and paths are not normalised, and `www.`/`m.` prefixes are kept. `VerifiedOffer` has no seller name, marketplace flag or merchant field (schemas.py:727-760). The `name` field in `known_sellers.json` is never read for offers.
- **Domain normalisation.** There are five separate normalisers:
  - `registrable_domain` strips `www.` and keeps the last 2 labels, or 3 for `.co.in`-style domains (trust.py:77-81).
  - `seller_key` strips only `www.` (costing.py:46-48).
  - `url_key`/`own_host` (seller_search.py:165-174).
  - `enough_offers` (sourcing/service.py:216) and `source_rank` (sourcing/service.py:93) each do `removeprefix("www.")`.
- **Trust.** `TrustChecker` caches results per host, not per domain (trust.py:283-306). A seeded `established` domain skips all checks (trust.py:316-319). Otherwise it checks the domain age over RDAP, looks for a GSTIN with a valid checksum, and fetches up to 3 policy pages. Any HTML page with status 200 and a body over 200 bytes counts as a found policy page (trust.py:343-349). Rules are at trust.py:157-209. `main.py:90` builds `TrustChecker()` with a bare `SafeFetcher`, so trust requests get no politeness layer and no challenge detection.
- **Platform detection.** `detect_platform` checks the `x-shopid`/`powered-by` and `x-magento*` headers, then substring markers for Shopify, WooCommerce and Magento. Otherwise it returns `jsonld` or `unknown` (platforms.py:30-33, 56-72; the `StorePlatform` type is at schemas.py:670). The result only feeds `signals.platform` and the choice of fallback.
- **Extraction order** (sourcing/service.py:676-697):
  1. `verify_page`: JSON-LD `Product` (listings.py:393-421).
  2. `variant_url` re-fetch (listings.py:202-239).
  3. `storefront_offer`: Shopify `.json`/`.js` or the WooCommerce Store API, used only when the page has no Product JSON-LD (platforms.py:296-308).
  4. `meta_offer`: OpenGraph or microdata (listings.py:468-512).
  5. `shopify_variants` for the judge.
- **JSON-LD parsing.** It reads the top level, lists and `@graph` only (listings.py:52-59). The page must contain exactly one `Product` (listings.py:399). `offer_options` accepts `Offer`, lists, and `AggregateOffer` (with nested offers or low==high) (listings.py:333-378). The price must be a plain decimal with at most 2 decimal places (listings.py:242-251), and `priceCurrency` must be exactly `"INR"` on the offer (listings.py:362). Stock is read from the last path segment of `availability` (listings.py:254-267).
- **Variants.** One option, or the option whose URL equals the page URL, is resolved. Anything else is left to the judge (listings.py:294-305). For Shopify, a variant must be named in `?variant=`, or the product must have exactly one variant (platforms.py:102-119).
- **Tax.** `valueAddedTaxIncluded` is read from the offer and `priceSpecification`, plus fixed regexes over the whole page text. The MRP guard looks back 60 characters. Conflicting signals give `None` (tax.py:210-273).

## 2. Ranked failure modes (all verified)

**F1 (high). The URL identity check rejects valid offers.** `resolved()` compares the Offer `url` with the page URL character for character, without resolving it first (listings.py:299-300, 304). All four structured paths also reject any query string (platforms.py:103, 183, 239; listings.py:232). Each of these returned `None` even though the price was valid:
- a page URL with `?srsltid=…` (Google) or `?utm_source=`
- an Offer URL on `www.` while the page is on the bare host
- an Offer URL using `http://`
- a relative Offer URL `/product/oled-096/`

Nothing strips tracking parameters or reads `<link rel=canonical>` (a grep finds no handling).

**F2 (high). Common JSON-LD shapes are missed.** Each of these returned `None`:
- `ProductGroup` + `hasVariant`
- `ItemPage.mainEntity` → Product (`nodes` only walks `@graph`, listings.py:59)
- `@type: IndividualProduct`
- `type="application/ld+json; charset=utf-8"` (exact match, listings.py:33)
- a `//<![CDATA[` wrapper
- a trailing comma
- **two identical Product nodes** (theme plus Yoast/RankMath/SEO app), rejected as a "category page" by listings.py:399
- price only in `priceSpecification`
- `priceCurrency` set on the Product instead of the Offer, or written in lowercase `inr`
- an Offer with no `@type`

One unresolvable `AggregateOffer` (low≠high) also discards valid sibling offers, because `offer_options` returns `None` for the whole list (listings.py:347-355).

**F3 (high, trust false positive). Stores on platform subdomains inherit the platform's domain.** `registrable_domain('store.myshopify.com')` returns `myshopify.com`. The same happens for `mydukaan.io`, `wixsite.com`, `instamojo.com` and `dir.indiamart.com`. A simulated brand-new `newstore.myshopify.com` got `age_days 7526`, `policies ['returns','shipping','contact']`, `label verified_basics` and `new_seller False`, because every policy URL redirected to the home page, which counts as found (trust.py:348). With a GSTIN on the page, rule 3 would give `established`.

**F4 (high). Marketplaces: the seller is not the domain.** `amazon.in` and `flipkart.com` are ranked as local sellers (countries.py:62-84). The offer is still credited to `www.amazon.in`, and trust is computed for the marketplace's own domain. Nothing captures the merchant shown on the listing ("Sold by"), nothing flags the listing as a marketplace, and IndiaMART supplier listings are treated the same way. No seller display name is surfaced from `known_sellers.json`.

**F5 (medium-high). Indian price formats outside clean JSON-LD.** `sane_price` rejects `'1,299.00'`, `'₹1,299.00'`, `'Rs. 1,299'`, `'1,23,456.00'` and `'₹ 299'`. Microdata is read only from `content=`, so `<span itemprop="price">₹299.00</span>` returns `None` (listings.py:444-449). A page with a sale price and an MRP both marked `itemprop=price` is rejected because it has two prices (listings.py:488). Magento's `data-price-amount` is not read.

**F6 (medium). Platform coverage and fragile markers.**
- Dukaan, Instamojo, Wix, PrestaShop, OpenCart, BigCommerce and Zoho Commerce all return `unknown`. BigCommerce and OpenCart are in `known_sellers.json` but not in `StorePlatform`.
- Magento is detected but has no fast path.
- A WordPress page that embeds a `cdn.shopify.com` image is detected as `shopify`, which also disables `meta_offer` (listings.py:483).
- A Shopify page whose JSON-LD Product has no offers is lost on every path: `storefront_offer` requires the JSON-LD to be absent (platforms.py:298) and `meta_offer` skips Shopify. Verified: verify, storefront and meta all returned `None`.
- WooCommerce works only for `/product/<slug>/` URLs (platforms.py:37) and `type: simple` products (platforms.py:255). `/shop/…` permalinks and variable products are rejected.
- Shopify requires the handle to match exactly, so a mixed-case URL handle fails (platforms.py:112).

**F7 (medium). Availability values.** `LimitedAvailability`, `OnlineOnly`, `BackOrder`, `Discontinued`, `schema:InStock` and a trailing slash all map to `unknown`. `accepted_offer` then drops them, because it requires `in_stock` (sourcing/service.py:197-201). `Discontinued` should map to `out_of_stock`.

**F8 (medium). Category, search and soft-404 pages.** `meta_offer` has no `og:type` or path check. A category page with one microdata item was accepted (`('299.00','in_stock','0.96 inch OLED','seller_meta_tags')`). A page titled "Product not found" that still has JSON-LD was accepted as an offer. Pages served as `application/xhtml+xml` or without a content type are rejected (platforms.py:41).

**F9 (medium-low). Host normalisation bugs.**
- `robocraze.com.` (trailing dot) gives `registrable=com.`, so the seed seller is missed (trust.py:78-81).
- `m.robocraze.com` matches in trust but not in costing (`costing_key=m.robocraze.com`), so the seller's shipping and GST policy is lost.
- `enough_offers` counts `m.x` and `x` as two sellers.
- The trust cache is keyed by host, so `www.x` and `x` are each looked up and labelled separately.

**F10 (low-medium). Challenge pages.** Detection is skipped entirely when seller search is off (sourcing/service.py:360). Sucuri and Imperva/Incapsula pages served with status 200 return `None` from `challenge_reason`. Trust policy fetches have no detection at all. Any 200 HTML challenge page over 200 bytes counts as a policy page. Risk is mostly to diagnostics and trust, because challenge pages have no Product.

**F11 (low). Tax phrases.**
- "excluding 18% GST", "including 18% GST", "(With GST)" and "(Without GST)" are not detected.
- Text from the whole page (related products, footer) conflicts with the product's own phrase. For example, `'Prices exclusive of GST. Related: ₹99 incl. GST'` gives `None` and a conflict.
- "₹254 Ex. GST ₹299 Inc. GST", a common dual display, gives `None` instead of identifying which price is which (tax.py:249-273).

## 3. Test coverage gaps

The fixtures cover only clean, single-Product JSON-LD with `priceCurrency:"INR"` (30 occurrences) and with `InStock`/`OutOfStock` in short, http and https forms. No test covers:
- tracking parameters, Offer URLs on another host (`www`), `http://` or relative Offer URLs, or canonical tags (F1)
- `ProductGroup`, `mainEntity`, duplicate Product nodes, a charset on the script type, CDATA, or prices only in `priceSpecification` (F2)
- platform subdomains or policy redirects in trust. `test_registrable_domain_and_rdap_endpoint` has no `myshopify`/trailing-dot cases (F3, F9).
- marketplace pages (F4)
- comma, `₹` or Indian digit-grouping prices, microdata price as element text, MRP plus sale price (F5)
- OpenCart, Magento-microdata, Dukaan or Instamojo pages, Shopify JSON-LD without offers, WooCommerce variable products or non-`/product/` permalinks (F6). The electronicscomp fixtures only assert rejection.
- other schema.org availability values (F7)
- category, search and soft-404 pages through `meta_offer` (F8)
- consistency between the costing and trust host normalisers (F9)
- Sucuri/Imperva challenges, or challenges in trust fetches (F10)
- the tax phrase variants above (F11)

## 4. Recommendations

1. **One seller registry and one host normaliser (F3, F4, F9).**
   - Write a single `seller_identity(url)` that lowercases the host, strips a trailing dot, `www.`, `m.` and `amp.`, IDNA-encodes, and uses the Public Suffix List (with private suffixes) so `*.myshopify.com`, `*.mydukaan.io`, `*.wixsite.com` and `*.instamojo.com` resolve to the store subdomain.
   - Return `{seller_id, display_name, domain, kind: direct|marketplace|platform_hosted}` from `known_sellers.json` with aliases (`www.rytronics.in`, `in.element14.com`).
   - Use it in trust, costing, `enough_offers`, `source_rank` and the trust cache key.
   - Add `seller_name` and `seller_kind` to `VerifiedOffer` and regenerate OpenAPI.
2. **Canonical URL reconciliation (F1).**
   - Before fetching, strip known tracking parameters (`utm_*`, `srsltid`, `gclid`, `fbclid`, `_pos`/`_sid`/`_ss`).
   - Read `<link rel=canonical>` and `og:url`.
   - Compare Offer URLs only after `urljoin`, and treat scheme, `www`/bare and trailing slashes as equivalent.
   - In the storefront paths, ignore non-variant parameters instead of rejecting the page.
3. **Layered extraction with a confidence level (F2, F5, F6, F7).**
   - Walk `mainEntity`, `hasVariant` and `@graph`, accept `ProductGroup`/`IndividualProduct`, and deduplicate identical Products (same name, SKU or URL) before the one-product rule.
   - Inherit currency from the Product or `priceSpecification`, and parse `priceSpecification.price`.
   - Skip, rather than abort on, an unresolvable `AggregateOffer`.
   - Add a strict INR price parser for microdata and meta values (`₹`/`Rs.`/`INR` prefixes, Western and Indian grouping), still requiring the currency to be declared.
   - Read microdata text content and Magento `data-price-type="finalPrice"`.
   - Map all schema.org availability values.
   - Record which layer produced the offer (`jsonld_exact`, `jsonld_dedup`, `storefront_api`, `meta`) so that weaker sources rank lower.
4. **Platform fingerprints and adapters (F6).** Score several signals (headers, `generator` meta, asset hosts, cookie names) rather than taking the first substring match. Add BigCommerce, OpenCart, PrestaShop, Dukaan and Instamojo to `StorePlatform`. Allow the Shopify `.json` path when the JSON-LD has no offers, and support WooCommerce variable products via `variations`.
5. **Marketplace handling (F4).** Mark marketplace domains in the registry. On those pages, extract the merchant shown on the listing ("Sold by" from JSON-LD `seller`/`offeredBy`), or report it as unknown. Never apply the marketplace domain's RDAP age, GSTIN or policy checks to a third-party merchant.
6. **Page-type, soft-404 and challenge gate (F8, F10).**
   - Require `og:type=product`, a product-like path or a Product JSON-LD before `meta_offer` runs.
   - Reject redirects to the home page or a category, and "not found" titles.
   - Add Sucuri/Incapsula markers, always apply `challenge_reason`, and route `TrustChecker` through `PoliteFetcher`.
   - Count a policy page only if its final URL is still on the policy path and its text contains policy keywords.
7. **Tax (F11).** Restrict text matching to the area around the price block, and allow a percentage between "incl/excl" and "GST".
8. **Fixtures.** Add one labelled fixture per failure mode above to `test_seller_pages.py`, `test_seller_trust.py` and `test_offer_extraction.py`. Label prices as historical snapshots, as `AGENTS.md` requires.
