# Seller trust labels and storefront JSON fast path

## Seller identity and resilience (v0.27.0)

Each verified offer adds optional `seller_domain`, `seller_name` and `seller_kind`.
The kind is `direct`, `marketplace` or `platform_hosted`. The original `seller` host is
retained for existing clients. Names come from the curated registry where available.

Marketplace offers remain candidates, but their trust label is `unverified` with a
third-party merchant explanation. Marketplace domain age and policies do not verify that
merchant. Hosted shops have separate store identities and `domain_age` is unavailable;
they never inherit the hosting platform's registration date. Policy checks require
relevant policy words, the same seller domain and a final path other than the home page.
All trust reads use the same pacing and challenge detection as product reads.

Implemented behaviour (M6b free checks and the M6 Shopify/WooCommerce fast path). The
architecture target is in `docs/02-architecture/06-sourcing-and-seller-data.md` §3.3 and §4.
Labels are **rule output, not verified seller facts**. Offers are never hidden by them.

## API: `offers[].trust` (optional)

Every `report.lines[].offers[]` entry may carry `trust` (null on older jobs, when the step
is disabled, or if the step failed). Shape:

| Field | Type | Meaning |
| --- | --- | --- |
| `label` | `established` \| `verified_basics` \| `unverified` | Rule-based label |
| `new_seller` | bool | Domain registered less than 365 days ago (RDAP) and not a curated seed seller |
| `reasons` | string[] | Plain-text reasons, in display order. Render as plain text |
| `signals.domain` | string | Registrable domain that was checked |
| `signals.https` | bool | Offer URL is HTTPS (always true today; non-HTTPS pages are never fetched) |
| `signals.known_seller` | bool | On the curated list `backend/src/bharat_sourcer/sourcing/known_sellers.json` |
| `signals.platform` | `shopify` \| `woocommerce` \| `magento` \| `opencart` \| `bigcommerce` \| `prestashop` \| `wix` \| `dukaan` \| `instamojo` \| `jsonld` \| `unknown` \| null | Detected from fetched page markup/headers |
| `signals.domain_registered` | datetime \| null | RDAP registration event |
| `signals.domain_age_days` | int \| null | Days since registration at `checked_at` |
| `signals.gstin` | string \| null | First GSTIN on fetched pages that passes format, state code and the GSTN mod-36 check character. **Not checked with the GST portal** (captcha) |
| `signals.policies` | (`returns` \| `shipping` \| `contact`)[] | Pages found and fetched (HTTP 200 HTML) |
| `signals.price_anomaly` | bool | This offer's price is under 40% of the median of at least two other verified offers on the same line |
| `signals.web_risk` | `not_checked` | Google Web Risk is not implemented (see below) |
| `signals.unavailable` | (`domain_age` \| `policies` \| `all`)[] | Checks that failed or timed out |
| `checked_at` | datetime | When the domain checks ran (cached result keeps its original time) |

`offers[].seller_trust` is unchanged (always `unverified`) for compatibility. Use `trust`.

`offers[].verification` gains three values besides `seller_structured_data`:
`shopify_storefront_json` and `woocommerce_store_api` (see the fast path below), and
`seller_product_api` (robu.in read through its GraphQL proxy, v0.31.0).

## Rules

Evaluated in order:

1. Not HTTPS → `unverified`.
2. Curated seed seller marked `established` → `established` (no network checks are made).
3. GSTIN + domain age ≥ 365 days + returns, shipping and contact pages → `established`.
4. Domain younger than 30 days and no GSTIN → `unverified`.
5. GSTIN, or all three policy pages → `verified_basics`.
6. Otherwise `unverified`.

The price anomaly flag never changes the label; it adds the reason "Unusually cheap: …".
`unverified` always adds "Check the seller before paying; prefer cash on delivery".

Signals are collected per seller host: RDAP (`rdap.nixiregistry.in` for `.in`,
`rdap.org` bootstrap redirect for other TLDs; `.co.in`-style second levels handled); the
fetched product pages (platform, footer links, GSTIN); and at most 3 policy pages, chosen
from same-host links whose path or text mentions return/refund/cancellation,
shipping/delivery or contact, plus Shopify's standard `/policies/refund-policy`,
`/policies/shipping-policy` and `/pages/contact` on Shopify stores.

## Limits and failure behaviour

- The step runs after offer verification. All hosts of a line are checked in parallel
  (4 workers shared by the process) with a **12 s deadline**. A check that misses it, or
  fails, leaves the label `unverified` with `unavailable: ["all"]` and the reason "Trust
  checks unavailable (timed out or failed)". A failed RDAP alone gives `domain_age`.
- Results are cached in memory per host: 24 h, or 15 min if any check was unavailable.
  Parallel lines share one in-flight check per host. No new storage or infrastructure.
- Fetch budget per new host: 1 RDAP request (plus its redirect) and up to 3 policy pages,
  through `SafeFetcher` (HTTPS, public-address pinning, size limits). Policy pages respect
  robots.txt; RDAP (RFC 9083, a machine API) is fetched without a robots.txt check.
- Disable with `BS_SELLER_TRUST_ENABLED=false`.

## Curated seed sellers

`known_sellers.json` lists Robocraze, Quartz Components, Evelta, ElectronicsComp, Robu,
Probots, Zbotic, Thingbits and FlyRobo as `established`, and Rytronics and Compoindia as
known but not established (they get the normal checks). The list is curated by the team
from `docs/04-reference/02-india-sellers-and-apis.md`; it is not seller-provided and its
`platform` values are research notes only. Owner should review it.

## Storefront JSON fast path (M6)

Used when a fetched product page has no usable JSON-LD offer. Explicit Shopify shop,
wallet, theme or header signals enable the Shopify fallback; one Shopify CDN asset alone
does not. WooCommerce, Magento, OpenCart, BigCommerce, PrestaShop, Wix, Dukaan and
Instamojo have deterministic fingerprints (only Shopify/WooCommerce have JSON adapters).

JSON-LD supports Product, ProductGroup variants, IndividualProduct and ProductModel,
including `mainEntity` and `@graph`, duplicate product entities, script parameters,
CDATA and bounded repair of trailing commas/control characters. Related-product lists
are not traversed. Prices require declared INR or an explicit rupee marker; Western and
Indian grouping are accepted, while ranges and ambiguous decimal formats are rejected.
Currency can be inherited from price specifications or the product. Unresolvable
aggregate ranges do not discard usable sibling offers.

Tracking parameters, relative URLs and equivalent seller host spellings are reconciled
for listing comparison; functional variant parameters remain significant. Soft 404 titles
and category pages are rejected. Meta/microdata fallback requires a product-page signal
and reads price element text as well as attributes. Tax phrases are scoped to price blocks
or nearby price text, excluding footers and recommendations. A visible inclusive price
that differs from the meta price leaves tax treatment unknown.

- **Shopify** (`/products/<handle>` URLs, optional locale/collection prefix, optional
  `?variant=<id>`): `GET /products/<handle>.json` gives title, variants, price and declared
  `price_currency`, which must be `INR`. One variant, or the explicitly chosen one, is
  required. `GET /products/<handle>.js` adds `available` → stock; if its minor-unit price
  disagrees with the `.json` price the offer is rejected; if `.js` is unavailable stock is
  `unknown`. Offer URL is `https://<host>/products/<handle>` (+ `?variant=`).
- **WooCommerce** (`/product/<slug>/` URLs): `GET /wp-json/wc/store/v1/products?slug=<slug>`;
  exactly one entry whose `permalink` equals the page, `type: simple`, `currency_code:
  INR`, price from minor units, `is_in_stock` → stock. Store API prices follow the store's
  tax display setting (Zbotic shows prices including GST); tax handling is out of scope here.
- Both require the shared title gate when no judge is configured, a positive price with
  no meaningful digits beyond two decimal places, and the fetch guards;
  specs come from the title and spec tables on the HTML page.
- robots.txt checked on 2026-10-06: robocraze.com and quartzcomponents.com allow
  `/products/*.json`, `/products/*.js` and `/search/suggest.json` (`Allow: /`; only cart,
  checkout, account and recommendation paths are disallowed). Their comments ask agents to
  prefer UCP/MCP for catalog access. zbotic.in allows `/wp-json/`. Stores that disallow
  these paths are skipped by the fetcher. `/search/suggest.json` is not used (discovery
  stays with grounded search).
- Offline fixtures: `backend/tests/fixtures/storefront/` (trimmed recorded responses with
  source URL and date; prices are historical snapshots).

## What the frontend should render

- Next to the seller name: the label as a badge.
  - `established`: plain seller name (optionally a subtle "Established" tag).
  - `verified_basics`: "Verified basics"; if `new_seller`, "New seller · GSTIN verified"
    when `signals.gstin` is set, otherwise "New seller · policies found".
  - `unverified`: "Unverified seller — check before paying" with a "prefer COD" hint.
- A separate **"New seller"** badge whenever `new_seller` is true.
- A **"Unusually cheap — check seller"** flag when `signals.price_anomaly` is true. Keep
  the offer visible and rankable.
- An expandable "Why?" list showing `reasons` as plain text, plus `checked_at`.
- Never present a label as a guarantee: the GSTIN is checksum-valid only, and the label is
  computed from public signals. Show `trust` absent as "Trust not checked".

## Not implemented (needs owner approval or keys)

- **Google Web Risk** (`uris.search`): keyed, metered API. A hook `web_risk_check()` in
  `sourcing/trust.py` marks where it plugs in; `signals.web_risk` is `not_checked` and no
  seller is blocked. Needs owner approval (paid third-party API).
- **Blocked label**, blocklist, user reports and "order arrived" votes (need storage).
- GSTIN state code vs stated address, GST portal lookup (captcha).
- **Shopify Global Catalog / Storefront UCP MCP** (needs a UCP agent profile) and
  **DigiKey / Mouser / element14** APIs (need keys or accounts).
- Magento GraphQL search; Magento is detected but has no fast path yet.
