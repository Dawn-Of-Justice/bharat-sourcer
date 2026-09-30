# Sourcing and seller data

> **In one minute.** Google has no public API for product offers, so we built a three-tier sourcing layer:
> - **Tier A:** merchant-sanctioned structured endpoints. These are Shopify **UCP/MCP** catalog tools (Robocraze and Quartz tell AI agents to use them in robots.txt), public Shopify, WooCommerce and Magento store APIs.
> - **Tier B:** official distributor APIs (DigiKey v4 with Substitutions, Mouser, element14, Nexar), used for chip-level parts.
> - **Tier C:** Gemini **Grounding with Google Search** + URL context for the long tail (Robu, Evelta, Thingbits, Amazon.in…).
>
> Nothing is shown until the **listing verifier** has fetched it. Prices are normalised to INR incl. GST and cached for 24 h.

Detailed seller-by-seller reference: [../04-reference/02-india-sellers-and-apis.md](../04-reference/02-india-sellers-and-apis.md). Research: [research/02](../../research/02-india-parts-market.md).

---

## 1. Tier map

```mermaid
flowchart LR
  P[ResolvedPart] --> C{cache < 24h?}
  C -- yes --> OUT
  C -- no --> A[Tier A<br/>Shopify UCP/MCP · products.json · suggest.json<br/>Woo Store API · Magento GraphQL]
  C -- no --> B[Tier B<br/>DigiKey v4 · Mouser · element14 · Nexar]
  C -- no --> G[Tier C<br/>Gemini google_search + url_context<br/>allow-listed Indian domains]
  A & B & G --> V[ListingVerifier]
  V --> OUT[verified Listing[] → cache]
```

Tiers run **in parallel** per part. Tier C is skipped when Tiers A+B already return ≥ 3 verified candidates, which saves grounding queries.

## 2. Tier A: merchant-sanctioned, structured

### 2.1 Shopify UCP/MCP (flagship)

What we found on 30 Sep 2026 (from research/02 §1.2):

- `robocraze.com/robots.txt` says *"Agents should use UCP/MCP for catalog, cart, and checkout"*. It points to `https://robocraze.com/agents.md` and `https://robocraze.com/.well-known/ucp`, and warns **"DO NOT complete checkout, payment, or order placement automatically."**
- The UCP discovery JSON lists version `2026-08-25`, transport `mcp` and endpoint `https://robocraze-com.myshopify.com/api/ucp/mcp`.
- The tools are `search_catalog`, `lookup_catalog` and `get_product`. Prices come back in minor units + currency, with per-variant `available`.
- Every request must include `meta.ucp-agent.profile`, the URL of **our agent's UCP profile**. We host this as a static JSON on Firebase Hosting (`/.well-known/ucp-agent.json`). ⚠️ Verify the exact profile schema at ucp.dev.
- **Shopify Global Catalog MCP** (`https://catalog.shopify.com/api/ucp/mcp`) supports `ships_to`/`ships_from` filters. In principle it covers every Indian Shopify store with `ships_to=IN`. ⚠️ Verify coverage.
- Quartz Components has the same Shopify agent notice. Silicon TechnoLabs and ThinkRobotics are also Shopify stores (UCP likely, ⚠️ verify).

Adapter: `backend/sourcing/ucp.py`, an MCP client over streamable HTTP. ADK's `McpToolset` with `StreamableHTTPConnectionParams` can load these as tools directly. We still call them from a function node so we control rate limits and normalisation.

**Deck line:** "We use Google & Shopify's Universal Commerce Protocol the way merchants ask agents to."

### 2.2 Public store JSON endpoints (fallback within Tier A)

| Store | Platform | Endpoint | Notes |
|---|---|---|---|
| Robocraze, Quartz, Silicon TechnoLabs, ThinkRobotics | Shopify | `/search/suggest.json?q=…&resources[type]=product`, `/products/<handle>.js`, `/products.json` | Live, INR. Suggest relevance can be poor (a "feather" query returned weather kits), so re-rank with Flash-Lite |
| Zbotic | WooCommerce | `/wp-json/wc/store/v1/products?search=…&per_page=10` | Live: `currency_code` INR, `sku`, `is_in_stock` (e.g. Teensy 4.1 ₹3,538.82, out of stock) |
| Probots | Magento | `/graphql` `products(search:"…")` | Endpoint answers; robots.txt allows AI bots. ⚠️ Verify the query shape |

Rules: low rate (≤ 1 req/s per domain), honour robots.txt and crawl-delay, cache aggressively, identify our user agent (`BharatSourcerBot/0.1 (+https://<site>/bot)`).

## 3. Tier B: distributor APIs (chip-level, substitutions)

| API | Use | Auth / limits | INR |
|---|---|---|---|
| **DigiKey Product Information v4** | KeywordSearch, ProductDetails, **Substitutions**, RecommendedProducts, Associations | OAuth2 (client credentials); ~1,000 searches/day; 429 + `Retry-After` | Locale headers `x-digikey-locale-site/-currency/-shiptocountry` (⚠️ verify INR) |
| **Mouser Search API** | Keyword/part search, price breaks, datasheet URL, stock | Free key; **30 calls/min, 1,000/day** | Mouser India invoices INR; DDP incl. GST for GST-registered buyers |
| **element14 Product Search** | India store pricing | API key; `storeInfo.id` for India ⚠️ verify | Per-store currency |
| **Nexar (Octopart)** `similarParts` | "Similar in spec and function" showcase | OAuth2; **Evaluation: 100 matched parts/month free** (similar parts included). Save for the demo | `country`/`currency` args ⚠️ verify |
| LCSC | Cheapest raw ICs | Application; 1,000/day | USD; FCA/EXW, buyer pays duty, **CHIMS + DHL KYC** for chips. Shown as "import option" only |
| TME | Pololu Gold distributor shipping to India | Token/secret | Multi-currency |

Distributor results are **chip-level, genuine parts**. They're the right answer for ICs and genuine-brand boards, and are marked "Authorised distributor". Maker-clone modules come from Tiers A/C.

## 4. Tier C: grounded search (long tail)

- **Agent:** `SellerSearchAgent` (Gemini 3.8 Flash) with `google_search` + `url_context`, structured output `Offer[]` (prompt P4). It's wrapped as an `AgentTool` so the orchestrator can call it (ADK built-in tool constraint).
- **Allow-listed domains** (initial):
  - robu.in, evelta.com, thingbits.in, amazon.in, flipkart.com
  - electronicscomp.com, hubtronics.in, robokits.co.in, flyrobo.in
  - probots.co.in, quartzcomponents.com, robocraze.com, zbotic.in
  - silicontechnolabs.in, thinkrobotics.com, sunrom.com, campuscomponent.com, ktron.in
  - mouser.in, digikey.in, in.element14.com
- **Post-filter:** drop citations outside the allow-list, drop category or search pages, dedupe by canonical URL.
- **Cost control:**
  - Skip when Tiers A+B already have ≥ 3 verified candidates.
  - One grounded call covers the part *and* its candidate substitutes.
  - Cache per `(module_id, country)` for 24 h.
- **ToS:** render Google's `search_suggestions` HTML in the Sources footer.

## 5. Listing verification (the anti-hallucination gate)

```python
async def verify(offer: Offer) -> Listing | None:
    r = await fetch(offer.url, respect_robots=True, per_domain_delay=DELAYS.get(domain, 1.0))
    if r.status != 200 or is_home_or_search(r.final_url): return None
    title = extract_title(r)                        # og:title / h1 / JSON-LD Product.name
    match = title_match(title, offer.module_guess)  # token + fuzzy; Flash-Lite tie-break when 0.5–0.8
    if match < 0.6: return None
    price, incl_gst = extract_price(r)              # JSON-LD offers.price, meta, site-specific selectors
    stock = extract_stock(r)                        # JSON-LD availability, "Out of stock" text
    if price is None: return None
    inr = price if incl_gst is not False else round(price * 1.18, 2)
    return Listing(..., price_inr_incl_gst=inr, gst_added_by_us=(incl_gst is False), stock=stock, ...)
```

- JSON-LD `Product`/`Offer` is tried first (most Shopify and WooCommerce themes emit it), then site-specific selectors, then URL context as a last resort for JS-rendered pages.
- The **recommender only receives `listing_id`s**. The UI renders URLs from the DB. **The model never emits a URL that reaches the user.**
- Stale thresholds: price 24 h, stock 6 h (re-verified on open for saved BOMs).

## 6. Normalisation

| Field | Rule |
|---|---|
| Price | INR incl. 18% GST. If a site shows ex-GST (Evelta; Zbotic shows both), × 1.18 and flag it |
| Shipping | Per-seller threshold table (config), e.g. Robocraze ₹999, Quartz ₹500 prepaid, ElectronicsComp ₹499, Silicon TechnoLabs ₹999. Below the threshold, a flat fee estimate (⚠️ verify per store) |
| Stock | `in_stock | out_of_stock | unknown`; unknown ranks below in-stock |
| Seller reputation | Optional score from our own 👍/👎 data. Never scraped reviews |
| Authorised flag | From brands' distributor lists (Adafruit: Thingbits, Robu, Evelta…; Pololu: Robu, Fab.to.Lab, MG Super Labs; Raspberry Pi: Robocraze, Robu, Silverline) |

## 7. Caching

| Collection | Key | TTL |
|---|---|---|
| `listings` | `sha1(url)` | price 24 h / stock 6 h |
| `part_offers` | `module_id + country` | 24 h |
| `bom_library` | `source_key` (`yt:<id>`) | indefinite; prices re-verified on open |
| `grounding_cache` | hash(prompt) | 24 h |

## 8. What we will NOT do

- Automate checkout or payment (Robocraze/Quartz `agents.md` forbid it, and so do we).
- Scrape login-only or paywalled pages, or bypass bot protection or CAPTCHAs.
- Re-host seller images (link or thumbnail by URL only).
- Use Robu's undocumented GraphQL proxy (`/api/proxy/graphql`), even though robots.txt allows crawling it. It isn't a documented API.

## 9. Partnerships (pitch and roadmap)

Email Robu, Robocraze, Quartz and Evelta about a data or affiliate partnership. Even one reply ("happy for you to use our catalog") is a strong deck slide. The Flipkart Affiliate API (Product Feed, Search) and the Amazon Creators API (needs qualifying sales) are the affiliate options.
