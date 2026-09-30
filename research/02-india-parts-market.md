# 02 — The Indian Maker-Parts Market & Programmatic Data Access

**Project:** Bharat Sourcer (Google Cloud AI Builder Cup 2026)
**Research date:** 2026-09-30
**Method:** Live WebFetch/WebSearch of primary pages (seller homepages, robots.txt, public JSON endpoints, official API docs, government/customs pages). Direct `curl` from the research sandbox was blocked by the egress proxy, so endpoint probes were done via WebFetch. The tag **[unverified]** marks anything I could not confirm on a primary page this session.

---

## 0. TL;DR for the build team

1. **The best data source is one nobody else is using yet: Shopify's UCP/MCP catalog endpoints.** Robocraze and Quartz Components are Shopify stores. Their robots.txt files tell AI agents to use `/.well-known/ucp` and `POST /api/ucp/mcp`, which expose `search_catalog`, `lookup_catalog` and `get_product` with prices, currency and per-variant `available`. Shopify also runs a **Global Catalog MCP** at `https://catalog.shopify.com/api/ucp/mcp` with `ships_to`/`ships_from` filters. UCP was co-launched by **Google** and Shopify (12 Jan 2026), so it fits a Google hackathon story well.
2. **Some stores expose clean public JSON:**
   - Robocraze, Quartz Components, Silicon TechnoLabs and ThinkRobotics serve Shopify `/products.json`, which I confirmed live.
   - Zbotic serves the WooCommerce Store API `/wp-json/wc/store/v1/products?search=`, also confirmed live with INR prices and `is_in_stock`.
   - Probots (Magento) answers on `/graphql`.
   - Robu.in is now a Next.js headless store with a GraphQL proxy. It's undocumented, so don't use it.
3. **Official distributor APIs work from India, but they cover "real" components, not maker clones:**
   - Mouser: free, 30 calls/min and 1,000/day.
   - DigiKey v4: OAuth2, about 1,000/day, with a **Substitutions** endpoint.
   - LCSC: application required, 1,000/day and 200/min.
   - Nexar/Octopart: free Evaluation tier of 100 matched parts per month, and the only tier below Enterprise that includes "similar parts".
   - Mouser India offers **DDP in INR with GST** for GST-registered buyers.
4. **Google Search grounding is the compliant catch-all for long-tail Indian sellers.** On Gemini 3.x it includes 5,000 free search requests per month, then $14 per 1,000. It is paid tier only.
5. **Import reality:** Budget 2026 cut basic customs duty on personal-use imports (heading 9804) from **20% to 10%** from 1 April 2026. IGST and surcharge still apply on top, and AliExpress has been blocked in India since Nov 2020. Imported Adafruit/Pololu originals typically cost several times the price of Indian clones. Example: Pololu DRV8825 at **$15.95** vs an Indian clone at **₹100 incl. GST** (about $1.1).
6. **Safety is a real differentiator:** US projects assume 120 V/60 Hz and plug types A/B. India is **230 V/50 Hz with Type D/M plugs**. The agent must flag every mains-side part.

---

## 1. Catalogue of Indian maker-electronics sellers

### 1.1 Master table

"Platform" comes from what I observed (robots.txt patterns, live JSON endpoints, page structure). "Data access" is the cleanest programmatic path I found.

| Seller | HQ | What they sell / positioning | Platform (evidence) | Programmatic data access | Shipping / terms (as stated) | Official brand status |
|---|---|---|---|---|---|---|
| **Robu.in** (Macfos) | Pune | India's largest maker store by its own claim; 140+ authorised brands and 15,000+ products (per Elecrow's partnership post); drones, 3D printing, dev boards, PCB and laser-cutting services | **Next.js headless.** `/_next/image` URLs; robots.txt allows `/api/proxy/graphql` and says pages "fetch their data client-side via this XHR". WooCommerce Store API returns 404 | No public API or feed. The GraphQL proxy is undocumented, so don't rely on it. Use Google Search grounding or the product sitemap (`/sitemap.xml`) | "Same Day Shipping" claimed on the homepage. The shipping-policy page body didn't render for me **[unverified threshold]** | Pololu distributor, Adafruit distributor, Raspberry Pi Approved Reseller since Oct 2018 |
| **Robocraze** (TIF Labs) | Bengaluru | Broad maker catalogue, STEM kits, Atal Tinkering Lab packages, test equipment | **Shopify** (valid `/products.json`; robots.txt header) | `/products.json`, `/search/suggest.json?q=`, and **UCP/MCP** at `/api/ucp/mcp` plus `/.well-known/ucp` (UCP version 2026-08-25). `agents.md` published | Free delivery above ₹999. Dispatch in 0–2 business days (up to 5). COD for ₹500–3,000. 7-day returns | Raspberry Pi Approved Reseller (per PiCockpit list) |
| **Quartz Components** | Jaipur | 5,000+ components/modules; batteries, SMPS, 3D-printer parts; claims 300,000+ orders delivered | **Shopify** (valid `/products.json`; UCP/MCP agent notice in robots.txt) | `/products.json` (the `price` field is INR even though the tool rendered "$"), UCP/MCP | Free above ₹500 on prepaid orders (₹50 below). COD ₹30/₹80. Dispatch within 24 working hours. Delivery 3–7 working days | – |
| **Evelta** | Navi Mumbai | Semi-B2B: 18,000+ in-stock parts plus 100,000+ on short lead time; ST/TI/Yageo; RFQ and BOM quotes; prices shown **ex-GST** | **BigCommerce** (`_bc_fsnf`, `/remote.php`, `/__socialshop/` in robots.txt) | No public product JSON. BigCommerce storefront GraphQL needs a token. robots.txt applies **Crawl-delay 10** to a long list of AI/scraper bots (ClaudeBot, GPTBot, **Google-Extended**, **GoogleOther**, Scrapy …) | "Shipped in 24 hours from Mumbai warehouse" | Adafruit distributor (Adafruit list) |
| **Probots** | Bengaluru | Dev boards and modules (Waveshare, Sipeed, LILYGO, Mean Well); claims 10,000+ SKUs; also design services | **Magento** (robots.txt; `/graphql` endpoint answers with GraphQL errors) | Magento GraphQL `products(search:)` is likely usable. Robots.txt (updated 2 Sep 2026) explicitly **allows** AI bots (ClaudeBot, GPTBot, Claude-User …) and blocks Bytespider | "1–3 days express" claimed; standard 1–15 days | – |
| **ElectronicsComp** | India | Budget components, Arduino/RPi/BeagleBone, Seeed, M5Stack, Teensy, Mean Well | **OpenCart** (`?route=` in robots.txt) | HTML only. Search pages (`route=product/search`) are disallowed in robots.txt | Free delivery above ₹499. "Maximum delivery time is between 7 to 30 days". COD | – (TechEnclave users flag poor service) |
| **Zbotic** | India | Drone/FPV parts, 3D printing (Bambu), kits; self-described "premium" | **WordPress + WooCommerce** | **WooCommerce Store API is public**: `/wp-json/wc/store/v1/products?search=…` returns INR prices (`currency_code`), SKU and `is_in_stock`. Verified with "teensy" and "DRV8825" | Free shipping above ₹999 (per its own article) | – |
| **Thingbits** | India | **"Adafruit Official Distributor in India"** (page title); SparkFun and other international brands; premium pricing | Custom/SPA. `/t/brands/...` URL style is Spree-like, but `/api/v2/storefront` is disallowed and pages render client-side | robots.txt disallows `/api/`. The HTML shell has no product data (JS-rendered). **Hard to scrape → use Search grounding** | Free above ₹2,000 (per Zbotic's comparison) **[unverified on Thingbits]** | Adafruit distributor (confirmed on Adafruit's list) |
| **Hubtronics** | India | Well-regarded on TechEnclave for "good prices, fast shipping" | **OpenCart** (Google sitemap feed route) | Homepage returned 403 to the fetcher. robots.txt: Googlebot unrestricted, all other bots **Crawl-delay 10** | – | – |
| **Silicon TechnoLabs** | India | MCUs/ICs (TI, ST, Microchip), dev boards, PCB services | **Shopify** (robots.txt header; valid `/products.json`) | `/products.json` (probably also UCP/MCP like other Shopify stores **[unverified]**) | Free shipping above ₹999; "same-day dispatch" | – |
| **ThinkRobotics** | India | Robotics, Seeed/Jetson edge-AI hardware | **Shopify** (valid `/products.json`, INR prices) | `/products.json` | – | Raspberry Pi distributor per Zbotic's article **[unverified]** |
| **Robokits India** | India (Gujarat numbers) | Drones/T-Motor, motors & drivers, LiPo (own GenX brand), CNC, 3D printer parts | Legacy PHP (**Zen Cart-like**; CEON URI mapping, `/tcpdf/`) | HTML only. robots.txt Crawl-delay 5; blocks sort/query URLs because of past crawl-trap load spikes | Not stated on homepage | – |
| **FlyRobo** | India | Student-focused budget store | **OpenCart** | HTML only. Crawl-delay 1; search disallowed | – | – |
| **Sunrom Technologies** | Ahmedabad | Long-running embedded-parts shop, own modules | Unknown | **Connection refused/timeout from the fetcher** (proxy CONNECT 403). Also sells via IndiaMART | – | – |
| **Rhydolabz** | Kochi | SMD parts, tools, genuine Arduino, quad parts (per EFY) | Unknown | TLS certificate hostname mismatch on `rhydolabz.com` at time of test, which is a reliability red flag | – | – |
| **Amazon.in** | – | Huge long tail of clone modules; variable quality/sellers | Proprietary | **Creators API** (PA-API 5 retired 2026). Needs an Associates account with ≥10 qualifying sales in 30 days. Amazon.in robots.txt blocked even this research fetcher | Prime 1–2 days in metros | – |
| **Flipkart** | – | Some modules/kits | Proprietary | **Flipkart Affiliate API**: Product Feed, Delta Feed, keyword Search; headers `Fk-Affiliate-Id` and `Fk-Affiliate-Token` | – | – |
| **element14 India** (Farnell) | Bengaluru | Authorised distributor: RPi, Arduino, BBC micro:bit, industrial | Proprietary | **element14 Product Search API** (`api.element14.com/catalog/products`, API key). Store ID for India likely `in.element14.com` **[unverified]** | Not visible on homepage **[unverified]** | Authorised |
| **Mouser India** | Bengaluru entity (Mouser Electronics India Pvt Ltd) | Authorised distributor, huge catalogue incl. Adafruit/SparkFun/Pololu lines | Proprietary | **Mouser Search API** (free key) | **GST Business Invoice: DDP in INR with GST added at checkout, duty paid by Mouser (GSTIN required, no credit cards).** Standard invoice: FCA, duties collected on delivery | Authorised |
| **DigiKey India** (digikey.in) | – | Authorised distributor | Proprietary | **DigiKey Product Information API v4** with locale headers (`x-digikey-locale-site/-currency/-shiptocountry`) | INR/duty terms not visible on the pages I opened **[unverified]** | Authorised |
| **LCSC** | Shenzhen | Cheapest source for raw ICs/passives (JLCPCB's parts library) | Proprietary | **LCSC official API** (apply at `lcsc.com/agent/apply`): product, shipping-cost, cart, order endpoints | **FCA/EXW, buyer pays all Indian duties.** India orders need **DHL KYC**, and chips need **CHIMS registration** | – |
| **TME** | Poland | Pololu Gold distributor that ships to India | Proprietary | **TME API** (token/secret; products, prices in multiple currencies, stock) | Ships from Poland | Pololu Gold distributor for India |
| Others worth indexing | | Campus Component (Pune), eBhoot (Anand), Ktron (Ahmedabad, GST-inclusive single units), Silverline (RPi Approved), Crazy Pi, Tenet Techtronics, ProtoCentral, Fab.to.Lab (Pololu + Adafruit), MG Super Labs (Pololu), Semikart, Makerbazar, Sharvi, Etstore (Kerala) | | Mostly HTML → grounding | | |

### 1.2 Evidence notes per store

- **Robocraze (Shopify + UCP).** robots.txt says: "Agents should use UCP/MCP for catalog, cart, and checkout", points to `https://robocraze.com/agents.md` and `https://robocraze.com/.well-known/ucp`, and warns: "DO NOT complete checkout, payment, or order placement automatically."
  - The UCP discovery JSON lists version `2026-08-25`, transport `mcp`, and endpoint `https://robocraze-com.myshopify.com/api/ucp/mcp`, with catalog, cart, checkout and Google Pay handlers.
  - `agents.md` says read-only browsing needs no auth and asks agents to supply buyer context (country, currency).
  - Live `/products.json` returned INR prices, `compare_at_price` and `available:false/true`.
  - Live `/search/suggest.json?q=feather` works, but relevance was poor: it returned weather kits, not Adafruit Feathers. That suggests Robocraze doesn't stock Feathers, which is itself useful signal.
  - Sources: robots.txt https://robocraze.com/robots.txt · agents.md https://robocraze.com/agents.md · UCP https://robocraze.com/.well-known/ucp · products https://robocraze.com/products.json?limit=2 · shipping https://robocraze.com/policies/shipping-policy
- **Quartz Components.** Same Shopify agent notice; `/products.json` live. Sources: https://quartzcomponents.com/robots.txt, https://quartzcomponents.com/products.json?limit=2, https://quartzcomponents.com/policies/shipping-policy, https://quartzcomponents.com/
- **Zbotic.** Sources: https://zbotic.in/wp-json/wc/store/v1/products?search=teensy&per_page=10 and `?search=DRV8825`. The search for "teensy" returned:
  - Teensy 4.1 at ₹3,538.82
  - Teensy 4.0 at ₹2,926.40
  - All out of stock at the time
  - robots.txt: https://zbotic.in/robots.txt
- **Robu.in.** Sources: robots.txt https://robu.in/robots.txt; homepage https://robu.in/; Elecrow partnership post https://www.elecrow.com/blog/elecrow-partners-with-robu.html; RPi reseller post https://robu.in/robu-in-is-now-official-raspberry-pi-authorized-reseller/
- **Evelta.** https://www.evelta.com/robots.txt and https://www.evelta.com/
- **Probots.** https://probots.co.in/robots.txt, https://probots.co.in/, GraphQL probe https://probots.co.in/graphql?query=…
- **ElectronicsComp.** https://www.electronicscomp.com/robots.txt and https://www.electronicscomp.com/
- **Thingbits.** https://www.thingbits.in/robots.txt and https://www.thingbits.in/t/brands/adafruit?page=2. The Adafruit brand page showed INR prices, e.g. BNO055 at ₹3,468.02 and BMP580 at ₹919.22.
- **Silicon TechnoLabs.** https://www.silicontechnolabs.in/robots.txt, https://www.silicontechnolabs.in/products.json?limit=2, https://www.silicontechnolabs.in/
- **Hubtronics** https://hubtronics.in/robots.txt · **FlyRobo** https://www.flyrobo.in/robots.txt · **Robokits** https://robokits.co.in/robots.txt, https://robokits.co.in/ · **ThinkRobotics** https://thinkrobotics.com/products.json?limit=1
- **Third-party overviews:**
  - EFY buyers' guide (Dec 2025): https://www.electronicsforu.com/buyers-guides/leading-online-suppliers-of-electronics-components-india
  - EFY shop list (updated Sep 2025): https://www.electronicsforu.com/special/cool-stuff-misc/online-shops-electronics-enthusiasts
  - Zbotic's 2026 ranking, which is **competitor-biased**: https://zbotic.in/best-online-electronics-stores-india-2026/
  - TechEnclave megathread (89 Indian sites, user reviews): https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-for-tools-and-components/271822

### 1.3 Price-level heuristics (qualitative)

| Tier | Stores | Notes |
|---|---|---|
| Budget / clone-heavy | ElectronicsComp, FlyRobo, Robokits, Amazon.in marketplace sellers, Robu for generic modules | Chinese-clone modules at near-AliExpress-plus-margin prices, e.g. DRV8825 clone at ₹85 + GST on Zbotic |
| Mid | Robu, Robocraze, Quartz, Probots, Hubtronics | Mix of clones and genuine brands |
| Premium / genuine | Thingbits, Evelta (ex-GST), Fab.to.Lab, element14/Mouser/DigiKey | Genuine Adafruit/SparkFun/Pololu; import cost baked in |

Pitfall: **some stores show prices ex-GST** (Evelta, and Zbotic shows both). TechEnclave users complain that "GST not included in listed prices" inflates the final cost. The BOM engine must normalise everything to **INR incl. 18% GST** and include shipping thresholds.

---

## 2. Official component APIs usable from India

| API | Auth | Limits | Cost | INR? | Parametric | Alternates / similar | Notes |
|---|---|---|---|---|---|---|---|
| **Nexar (Octopart)** GraphQL | OAuth2 client credentials; tokens valid 24 h | Monthly **matched-parts** quota: Evaluation 100 · Standard 2,000 · Pro 15,000 · Enterprise custom. Only `sup*` queries that return parts count; `des*` and category queries are free; quota resets on the 1st with no rollover | Evaluation free; paid prices "available after sign-up" | Nexar's `sup` queries take `country`/`currency` arguments **[schema knowledge, unverified this session]** | Tech specs: Evaluation, Pro, Enterprise | **"Similar parts": Evaluation and Enterprise only** (not Standard/Pro) | Best for MPN-level cross-distributor offers. Indian maker shops (Robu etc.) are probably **not** indexed **[unverified]** |
| **Mouser Search API** (JSON/XML) | API key from My Mouser → request form | **30 calls/min, 1,000/day**, 50 results per call | Free | Currency not documented. Mouser India invoices in INR or USD; DDP for GST buyers | Category, RoHS, lead time, 4 price breaks, datasheet | No explicit alternates endpoint | Also Cart, Order and Order History APIs. India office: Bengaluru |
| **DigiKey Product Information API v4** | OAuth2 (2- and 3-legged), sandbox available | About **1,000 searches/day** by default (forum answer). Burst limit per minute; forum mentions ">120 per minute" as excessive. 429 + `Retry-After` | Free | Locale headers `x-digikey-locale-currency`, `-site`, `-shiptocountry`, `-language` (INR support implied by digikey.in) **[INR unverified]** | KeywordSearch, ProductDetails, Categories, Media | **`Substitutions`, `RecommendedProducts`, `Associations`, `AlternatePackaging`** endpoints | The strongest official "find me an equivalent" endpoint set |
| **element14 Product Search API** | `callInfo.apiKey` (24-character key); signature for contract pricing | Not stated in the (2012-era) doc page | Free key | Price is per store (`storeInfo.id`); India store id **[unverified]** | Attributes via response groups | None documented | One API covers Newark/Farnell/element14 regional stores |
| **LCSC API** | Account + application form | **1,000 searches/day, 200/min** (raise via support@lcsc.com) | Not stated | USD shown; no INR | Product details, categories, manufacturers | None | Also shipping-cost estimate, cart and order endpoints. India: FCA/EXW, buyer pays duty, DHL KYC, CHIMS for chips |
| **TME API** | Token + secret (registration) | Not on landing page | Free with account | Multi-currency pricing | Tech data in many languages | Not stated | Pololu Gold distributor that ships to India |
| **Arrow Pricing & Availability API** | API key (developers.arrow.com) or sales rep for premium | Arrow page states 50 req/s standard and 3 req/s premium (odd, as written) | **Free** | Not specified | – | – | Prerequisite for Arrow Orders API |
| **SiliconExpert** | Enterprise | – | Quote only | – | Deep parametric | Cross-reference / alternates is their core product | Overkill for a hackathon |
| **Z2Data** | Trial | – | Free trial; claims "1B+ cross references" | – | Form-fit-function equivalents with lifecycle | Yes (web) | API tier unclear |
| **Amazon Creators API** (replaced PA-API 5) | OAuth 2.0 client credentials (Client ID/Secret → bearer) | New credentials: **1 TPS / 8,640 TPD** for the first 30 days. Then +1 TPD per $0.05 and +1 TPS per $4,320 of shipped revenue (max 10 TPS). Access revoked without qualifying sales in each 30-day window | Free, but needs Associates status and **≥10 qualifying sales in last 30 days** | amazon.in marketplace listed | Item attributes | "Variations" only | PA-API 5 now returns **HTTP 403** (dev.to cites deprecation 30 Apr 2026 and retirement 15 May 2026) |
| **Flipkart Affiliate API** | `Fk-Affiliate-Id` + `Fk-Affiliate-Token` (one token per account) | Not documented | Free for affiliates | INR | Category feeds | – | Product Feed, Delta Feed, keyword/ID search, Offers/DOTD. Maker-parts coverage is thin |
| **Shopify Storefront Catalog MCP (UCP)** | Every request must include `meta.ucp-agent.profile` (your agent's UCP profile URL) | Not documented; `agents.md` asks agents to "respect rate limits" | Free | `price_range` in minor units + currency code | Options/variants/tags | – | Per-store endpoint `POST https://{store}/api/ucp/mcp`. Tools: `search_catalog`, `lookup_catalog`, `get_product` (`search_shop_catalog` renamed per Shopify community threads) |
| **Shopify Global Catalog MCP** | Same UCP agent profile | Not documented | Not documented | Buyer-context currency | Filters: availability, price, condition, rating, category, **`ships_to`/`ships_from`** (ISO country) | – | `https://catalog.shopify.com/api/ucp/mcp`. Searches "across the entire Shopify ecosystem", so in principle it covers Indian Shopify stores with `ships_to=IN` **[coverage unverified]** |
| **Gemini Grounding with Google Search** | Gemini API key (paid tier) | – | **Gemini 3.x: 5,000 free search requests/month shared, then $14 per 1,000 search queries.** Not available on the free tier. One prompt may trigger several queries | Returns web snippets and citations; INR comes from the pages | – | – | The compliant way to reach long-tail Indian sellers with no API |

Sources:
- Nexar: plans https://nexar.com/compare-plans; Altium plans page https://developer.altium.com/octopart-api-plans; part counting https://support.nexar.com/support/solutions/articles/101000476314; OAuth/migration https://support.nexar.com/support/solutions/articles/101000434416-migration-from-octopart-v3-api
- Mouser: https://www.mouser.com/en/api-search/ (30/min, 1,000/day, 50 results); API hub https://www.mouser.in/api-hub/; India incoterms https://www.mouser.in/corporate-information-india/
- DigiKey: v4 endpoint list https://developer.digikey.com/zh-hans/products/product-information-v4/productsearch/substitutions; locale headers and throttling https://developer.digikey.com/faq/api-response-unexpected-response-and-error-codes; 1,000/day https://forum.digikey.com/t/increase-daily-limit/67915
- element14: https://partner.element14.com/docs/read/Product_Search_API_REST_Characteristics
- LCSC: https://www.lcsc.com/agent; customs FAQ https://fat.lcsc.com/faqs/shipping-delivering/customs-duties-taxes
- TME: https://developers.tme.eu/
- Arrow: https://www.arrow.com/en/resources/api-solutions.html
- Z2Data: https://www.z2data.com/landing/lpa/cross-reference · SiliconExpert: https://www.siliconexpert.com/?p=693
- Amazon: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation, rates https://affiliate-program.amazon.com/creatorsapi/docs/en-us/concepts/api-rates, migration article https://dev.to/th3nate/amazon-pa-api-v5-is-shutting-down-april-30-2026-here-is-what-changes-at-the-auth-layer-22ek
- Flipkart: https://affiliate.flipkart.com/api-docs/affiliate_index.html, https://affiliate.flipkart.com/api-docs/af_register.html
- Shopify: Storefront MCP https://shopify.dev/docs/agents/catalog/storefront-mcp; Global Catalog https://shopify.dev/docs/agents/catalog/global-catalog; rename thread https://community.shopify.dev/t/storefront-mcp-search-shop-catalog-returning-tool-not-found-renamed-to-search-catalog/33256
- UCP launch (Google + Shopify, 12 Jan 2026): https://www.shopifreaks.com/google-and-shopify-launch-universal-commerce-protocol/
- Gemini grounding: https://ai.google.dev/gemini-api/docs/pricing; community clarification https://discuss.ai.google.dev/t/grounding-free-quota-clarifying-2026-rules-for-gemini-2-5-flash-paid-tier-1/144593 (2.5 Flash: 1,500 RPD free, then $35 per 1,000 grounded prompts)

### 2.1 Recommended data architecture for Bharat Sourcer

```
Parts list (Gemini extraction)
   │
   ├─► Normaliser: generic part ("SG90 servo", "0.96in SSD1306 I2C OLED") vs MPN ("TMC2209", "BNO055")
   │
   ├─► Tier A — Indian maker stores with open structured endpoints (fast, INR, stock):
   │      Shopify UCP/MCP + /products.json (Robocraze, Quartz, Silicon TechnoLabs, ThinkRobotics)
   │      Shopify Global Catalog MCP (ships_to=IN)
   │      WooCommerce Store API (Zbotic)  ·  Magento GraphQL (Probots)
   │
   ├─► Tier B — Official distributor APIs for MPN-level parts & substitutes:
   │      DigiKey v4 (Substitutions/Recommended) · Mouser Search · LCSC · element14 · Nexar (similar parts)
   │
   ├─► Tier C — Gemini + Google Search grounding for everything else
   │      (Robu, Evelta, Thingbits, Amazon.in, Hubtronics …) → cite URLs, never claim live stock
   │
   └─► Cache (Firestore) with TTL: price 24 h, stock 1–6 h; store source + fetched_at on every line
```

Design rules:
- **Respect `Crawl-delay`** (Evelta 10 s for AI bots, Hubtronics 10 s, Robokits 5 s, FlyRobo 1 s).
- **Never automate checkout.** Robocraze's and Quartz's robots.txt and `agents.md` say this explicitly. Deep-link to product/cart pages instead.
- Label every price with source and timestamp: "₹3,538.82 incl. GST @ Zbotic, 30-Sep-2026, out of stock".
- Budget the quotas. DigiKey (about 1,000/day) and Mouser (1,000/day) are fine for a demo but need caching at scale. Nexar Evaluation (100 parts/month) is only enough for a few demo BOMs, so save it for the "similar parts" showcase.

---

## 3. Import realities

### 3.1 Duty on personal imports (courier/post)

| Item | Finding | Source |
|---|---|---|
| Classification | "All personal imports shall be classified under heading (CTH) 9804" | Mumbai Customs Zone-I postal FAQ https://www.mumbaicustomszone1.gov.in/Info/PostalAppraising |
| Budget 2026-27 change | "Tariff rate on all dutiable goods imported for personal use … reduced from 20% to 10%", **effective 1 April 2026** (excludes vehicles, alcohol, tobacco; jewellery treated separately) | Thomson Reuters ONESOURCE (19 Mar 2026) https://www.thomsonreuters.com/en-us/help/onesource-global-trade/regulatory-insights/2026/march-19th/india-union-budget-key-trade-customs-measures.html · Outlook Business https://www.outlookbusiness.com/budget/budget-slashes-customs-duties-on-17-cancer-drugs-eases-baggage-rules · Outlook Money https://www.outlookmoney.com/tax/budget-2026-government-halves-customs-duty-on-personal-imports-to-10-per-cent-offers-big-relief-to-consumers · EximPe https://eximpe.com/blog/b2b/import-duty-changes-in-budget-2026-complete-guide-for-importers-exporters-travelers |
| Stacking | 10% BCD + Social Welfare Surcharge (10% of BCD) + IGST on (value + BCD + SWS). Mumbai Customs quotes **42.08% total** for 10% BCD + 10% SWS + 28% IGST. **[uncertain]:** GST rate rationalisation since 2025 may have changed the IGST applied to 9804, and HSN aggregators still show 28%. Present it as "roughly 30–42% landed-tax overhead on personal courier imports" and let users verify | Mumbai Customs FAQ (above); HSN 9804 GST 28% https://www.registerkaro.in/hsn/gst-rate-hsn-code-9804 |
| Low-value exemption | Postal goods up to ₹1,000 CIF duty-free (per Mumbai Customs FAQ) | Mumbai Customs FAQ |
| Gifts | Gift imports face 77.28% total duty and are restricted to life-saving drugs and Rakhi via post (per the same FAQ). **Don't** tell users to mark parcels as "gift" | Mumbai Customs FAQ |
| Chips / CHIMS | LCSC says India shipments of chips need a **CHIMS registration certificate** plus DHL KYC. The government removed mandatory registration for certain items in Dec 2024 | LCSC FAQ https://fat.lcsc.com/faqs/shipping-delivering/customs-duties-taxes · Deccan Herald https://www.deccanherald.com/business/govt-removes-mandatory-registration-for-certain-items-under-chip-imports-monitoring-system-3299070 |
| Distributor DDP | Mouser India: **DDP with GST added at checkout, duty and customs paid by Mouser** (GST Business Invoice, INR, GSTIN required). Standard invoice: duties collected at delivery | https://www.mouser.in/corporate-information-india/ |
| LCSC | FCA/EXW. "Customers are expected to pay any amount charged by the government or customs at the destination" | LCSC FAQ |
| AliExpress | Blocked in India since **24 Nov 2020** under IT Act §69A (43 apps). TechEnclave users say this creates "local monopoly pricing" | GSMArena https://www.gsmarena.com/indian_government_bans_43_more_chinese_apps_including_aliexpress-news-46430.php · TechEnclave p.11 https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-for-tools-and-components/271822?page=11 |

### 3.2 Why US maker parts are expensive or hard to get in India

1. **Landed cost.** US retail + international courier ($20–40+ typical for small parcels **[unverified; varies by courier]**) + 10% BCD + SWS + IGST + courier clearance fees. On a $15 board, shipping often costs more than the part.
2. **Thin official distribution.** Adafruit lists 11 Indian distributors: Adhira, Crazy Pi, DNA, Evelta, Fab.to.Lab, ProtoCentral, Robu, Silverline, Tanna TechBiz, Tenet, Thingbits. Pololu lists Fab.to.Lab, MG Super Labs, Robu (Macfos) and TME (ships from Poland). Stock depth at these resellers is limited. Example: Thingbits' Adafruit ESP32-S3 Reverse TFT was **Sold Out** at ₹2,889.82.
3. **Clone economics.** The Indian market runs on Chinese clones of the same designs. Pololu DRV8825 carrier: **$15.95**. Clone DRV8825 with heatsink on Zbotic: **₹85 + GST = ₹100.30**, about a 13× difference.
4. **Branded ecosystems.** Feather, Qwiic/STEMMA QT and Teensy are brand ecosystems with few Indian clone equivalents, so substitution needs *functional* reasoning (same chip, different form factor/connector). Teensy 4.1 appears on Zbotic at ₹3,538.82 but **out of stock**. ElectronicsComp also lists the Teensy brand.
5. **Chip-import paperwork** (CHIMS/KYC) discourages hobbyists from direct LCSC/DigiKey orders of ICs.

Sources: Adafruit distributors https://www.adafruit.com/distributors · Pololu distributors https://pololu.com/distributors · Pololu 2133 https://www.pololu.com/product/2133 · Zbotic Store API queries above · Thingbits Adafruit page https://www.thingbits.in/t/brands/adafruit?page=2 · Adafruit 5323 ($17.50) https://www.adafruit.com/product/5323

### 3.3 Who stocks originals (for "genuine" mode)

| Brand | Indian sources (confirmed on brand's own list unless noted) |
|---|---|
| Adafruit | Thingbits ("Official Distributor" in page title), Robu, Evelta, Fab.to.Lab, Crazy Pi, Silverline, Tenet, ProtoCentral, DNA, Adhira, Tanna TechBiz; plus Mouser/DigiKey/element14 |
| Pololu | Robu (Macfos), Fab.to.Lab, MG Super Labs (Nagpur), TME (ships from Poland) |
| SparkFun | I couldn't load SparkFun's distributor page. Zbotic's article lists Thingbits for SparkFun **[unverified]**. Mouser/DigiKey carry SparkFun |
| Raspberry Pi | Approved resellers per PiCockpit: Robocraze, Robu, Silverline Electronics. Robu authorised since 29 Oct 2018 |
| Teensy (PJRC) | ElectronicsComp (brand listed), Zbotic (listed, OOS). Mouser/DigiKey/SparkFun abroad |

---

## 4. Common "problem parts" and Indian substitutes

Substitution logic the agent should apply, with typical Indian equivalents. Where I had live INR data it's cited; otherwise mark as a pattern.

| US/UK part in the video | Problem in India | Usual Indian substitute | Compatibility notes the agent must emit |
|---|---|---|---|
| **Adafruit Feather ESP32-S3 / HUZZAH32** ($17.50 US) | Only through a few Adafruit resellers; often OOS; premium | Generic **ESP32-S3 DevKitC-1** or **ESP32 DevKit V1 / NodeMCU-32S** clone (widely stocked) | Different pinout/footprint (Feather vs DevKit); no LiPo charger or STEMMA QT on most clones (add a TP4056 module); check the USB-UART chip (CP2102/CH340) for drivers; CircuitPython support differs |
| **Adafruit NeoPixel ring/strip/Jewel** | Brand premium | **WS2812B** rings/strips (generic) | Same protocol. Check 5 V vs 12 V strips (WS2815), LED density, and **3.3 V logic level** (add a 74AHCT125 or run at 4.5 V) |
| **Pololu DRV8825 / A4988 / TIC** ($15.95) | 10×+ price | Clone DRV8825/A4988 StepStick (~₹100 incl. GST) | Pinout-compatible. **Sense-resistor value differs between clones** (Zbotic sells "low" and "high current limiting resistance" versions), so the Vref formula differs. Heatsink needed |
| **Pololu micro metal gearmotors** | Import only | N20 gear motors (generic) | Same 12×10 mm form factor; stall current/torque specs vary widely; encoders sold separately |
| **SparkFun Qwiic / Adafruit STEMMA QT breakouts** | Few stockists | Generic I2C breakout of the **same sensor chip** (BME280, MPU6050, VL53L0X, SSD1306) + JST-SH cables or Dupont wiring | Check the I2C address (jumper differences), onboard regulator (3.3 V vs 5 V tolerant) and pull-ups |
| **Teensy 4.x** (audio/MIDI projects) | OOS / expensive | **ESP32-S3** or **RP2040/RP2350** for USB-MIDI/HID; STM32 "Black Pill" | Teensy Audio library & USB types don't port directly: flag as "code changes required" |
| **Specific Adafruit TFTs/FeatherWings** | Pricey | ST7789/ILI9341 SPI TFT modules (generic) | Driver IC and resolution must match the library (TFT_eSPI config); touch controller varies (XPT2046 vs FT6206) |
| **Arduino Nano 33 IoT / Nano ESP32 / MKR** | Genuine available but costly | ESP32 dev boards | Library and pin differences |
| **US mains relays/Kill-A-Watt/smart plugs (NEMA 1-15/5-15)** | **Wrong voltage/plug; safety risk** | 230 V-rated relay modules with proper creepage; Indian Type D/M plug hardware; BIS-certified SMPS (Hi-Link HLK-PM01 etc.) | See §4.1. **Never** recommend a direct swap for mains-side parts without a voltage/frequency check |
| **120 V transformers, 60 Hz synchronous clock motors, US wall warts** | Designed for 120 V/60 Hz | 230 V/50 Hz equivalents; universal-input (100–240 V) SMPS adapters | 60 Hz synchronous motors run about 17% slower at 50 Hz. 60 Hz transformers on 50 Hz see about 20% higher core flux, which risks saturation and overheating |
| **LiPo packs sized in US listings, 18650 brands** | Availability OK, quality varies | Robokits (GenX own brand), Robu, Quartz | Check C-rating, protection BMS and connector (XT60/JST) |
| **US-sourced filament/3D-printer parts** | Mostly available locally | Robu, Robokits, Quartz, Zbotic | Nozzle/thread standards (MK8 vs V6) |

Live price anchors:
- Zbotic Teensy 4.1: ₹3,538.82, OOS
- Zbotic DRV8825 clone: ₹100.30
- Pololu DRV8825: $15.95
- Adafruit ESP32-S3 Feather: $17.50
- Thingbits Adafruit BNO055: ₹3,468.02
- Thingbits Adafruit BMP580: ₹919.22

### 4.1 Mains-voltage and plug-standard safety angle (must-have feature)

| | India | USA | UK |
|---|---|---|---|
| Voltage | **230 V** | 100–127 V ("almost always") | 230 V |
| Frequency | **50 Hz** | 60 Hz | 50 Hz |
| Plugs | **Type D** (6 A, small devices) and **Type M** (16 A, heavy appliances); Type C sometimes seen with imports but "unstable connections" | Types A and B | Type G (the UK moved to Type G; India kept the older British D/M) |

Sources: WorldStandards India page https://www.worldstandards.eu/electricity/plug-voltage-by-country/india/ · WorldStandards plugs overview (US A/B, 100–127 V) https://www.worldstandards.eu/plugs-and-sockets/ · 60→50 Hz transformer effects (20% flux increase, saturation, overheating, 5/6 voltage derating) https://industrialmonitordirect.com/blogs/knowledgebase/using-60hz-transformers-on-50hz-power-systems

Rules for the agent:
- **Tag every part as `low-voltage` or `mains`.** For `mains` parts:
  - Require a 250 V AC rating
  - Warn about the 230 V difference (about 2× the peak voltage of the US build)
  - Flag 60 Hz-specific parts
  - Recommend Type D/M plugs and BIS-marked adapters
  - Add a "get a qualified electrician to review" note
- **UK videos are a gift:** UK is also 230 V/50 Hz, so mains-side parts often transfer directly, apart from the Type G plug and UK fuse ratings.
- US project power supplies labelled "100–240 V" (universal SMPS) are fine; the agent should say so explicitly to reduce false alarms.

---

## 5. Legal and ethical notes on scraping Indian e-commerce

**Legal framework (not legal advice):**
- **IT Act 2000 §43** covers unauthorised access or extraction (civil compensation). **§66** makes the same acts criminal when done dishonestly or fraudulently: up to 3 years and/or up to ₹5 lakh.
- **Copyright Act 1957:** compilations can be "literary works" (§2(o)). The Supreme Court in *Eastern Book Co. v. D.B. Modak* (2007) applied a "skill and judgment" originality test, so factual price/stock data alone is weakly protected, but site text, images and descriptions are protected. Source: S.S. Rana & Co. (2020) https://ssrana.in/articles/data-scraping-issues-india/
- **Contract/ToS:** most sites' terms prohibit robots and data-mining. Amazon.in's robots.txt even blocked our research fetcher from reading its Conditions of Use page and robots.txt.
- **robots.txt signals seen this session:**
  - Evelta: Crawl-delay 10 for ~40 AI/scraper bots, including Google-Extended and GoogleOther
  - Probots: explicitly **allows** AI crawlers
  - Robocraze/Quartz: say "use UCP/MCP" and forbid automated checkout
  - Thingbits: `/api/` disallowed
  - ElectronicsComp/FlyRobo: search result pages disallowed
- **MeitY's stance on scraping for AI training** has been contested (223 experts' letter, Feb 2025): https://www.medianama.com/2025/02/223-experts-concerned-about-meitys-stance-on-web-scraping-to-train-ai-models/ (search-result reference; not opened in full).

**Recommended compliant approach (in priority order):**
1. **Merchant-sanctioned agent protocols first.** Use Shopify UCP/MCP, which merchants explicitly invite agents to use, plus the Shopify Global Catalog.
2. **Official APIs:** DigiKey, Mouser, LCSC, element14, Nexar, TME, Amazon Creators, Flipkart Affiliate. Affiliate links also create a revenue model.
3. **Public, documented storefront endpoints** (Shopify `/products.json`, WooCommerce Store API), used at low rate with caching, honouring robots.txt. These are publicly served by design, but still check each site's ToS. Ideally, email the three or four biggest stores for permission; that's a good slide ("partnered with X").
4. **Gemini Grounding with Google Search** for everything else. Google has already crawled the pages under each site's own robots rules, and you only show snippets and citations plus a deep link. Present prices as "last seen" with a link and never as guaranteed.
5. **Caching and attribution:** store `source_url` and `fetched_at`; TTL 1–24 h; no image re-hosting (link to the seller's image or show none); no personal data collected (DPDP Act 2023 isn't triggered by product data, but user accounts are).
6. **Never automate purchase.** Deep-link to the product or cart for the human.

---

## 6. Maker community in India: numbers for the impact slide

| Metric | Number | Source |
|---|---|---|
| Atal Tinkering Labs established (as of Oct 2025) | **10,000** ATLs in schools | PIB document, 5 Dec 2025 https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/dec/doc2025125718301.pdf |
| Students engaged in ATLs | **>1.1 crore (11 million)** | Same PIB document |
| Innovation projects from ATLs | **>16 lakh (1.6 million)** | Same PIB document |
| ATL expansion target | **50,000 ATLs** rolling out for 2025–26 | Same PIB document |
| New regional ATL push | 500 ATLs planned in J&K (May 2026) | Drishti IAS https://www.drishtiias.com/state-pcs-current-affairs/500-atal-tinkering-labs-to-be-established-in-jammu-kashmir/print_manually |
| Engineering (BTech/BE) enrolment | AISHE: **36.6 lakh** (2021) vs 40.9 lakh (2016) | Careers360 on AISHE/AICTE https://news.careers360.com/btech-engineering-college-aicte-data-course-placement-admission-graduation-aishe-vacant-seats |
| AICTE engineering intake / annual enrolment (2021–22) | **25.4 lakh seats; 14.1 lakh enrolled** | Same Careers360 article |
| Maker events | MakerFest Vadodara 2026: **10,000+ visitors, 70+ makers** (10–11 Jan 2026) | SSIP Gujarat report https://ssipgujarat.in/admin20/files/event/report1_path/7504/Report%20of%20Makerfest%20Vadodara%202026%2010%20and%2011%20Jan%202026.pdf |
| Retail scale signal | Quartz Components claims **300,000+ orders delivered** to 18,000+ PIN codes; Robu claims 140+ authorised brands | https://quartzcomponents.com/ · https://www.elecrow.com/blog/elecrow-partners-with-robu.html |
| Community seller directory | TechEnclave thread lists **89 Indian electronics retailers** | https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-for-tools-and-components/271822 |
| Institutional demand | Robocraze sells packaged "Atal Tinkering Lab – Package 5" kits (₹21,347) | Robocraze `/search/suggest.json` result |

Not found or unverified: a reliable size for r/IndianMakers or similar Indian maker subreddits (I didn't locate an authoritative page), and a market-size figure for Indian hobby electronics. Don't put invented numbers on the slide. Suggested impact framing:

> "10,000 Atal Tinkering Labs and 1.1 crore students today, scaling to 50,000 labs, plus ~14 lakh new engineering students a year. They all learn from US/UK YouTube tutorials whose parts lists don't match what they can buy."

---

## 7. Open questions / to verify before demo

1. Hit `POST https://robocraze.com/api/ucp/mcp` with a UCP agent profile. Confirm `search_catalog` works for "SSD1306" and returns INR plus availability. Also check whether the Global Catalog returns Indian stores with `ships_to: "IN"`.
2. Confirm the element14 India `storeInfo.id` and whether prices come back in INR.
3. Confirm DigiKey returns INR with `x-digikey-locale-site: IN` / `currency: INR`.
4. Confirm the current IGST rate on heading 9804 post GST rationalisation. The Mumbai Customs page shows 28%, which may be stale.
5. Check the Nexar `country`/`currency` arguments and whether any Indian maker stores are indexed.
6. Robu.in's free-shipping threshold (the policy page didn't render server-side).
7. Contact Robu, Robocraze, Quartz and Evelta about a data or affiliate partnership (no public affiliate programme found for Robu or Robocraze).
