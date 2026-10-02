# Indian sellers and data APIs (reference)

> **In one minute.** This is the lookup table for the sourcing layer. For every Indian maker store and distributor API it lists the platform, endpoint, limits, shipping terms and brand authorisation, as observed on **30 Sep 2026**. The tables are copied from [research/02](../../research/02-india-parts-market.md), where every row has its evidence links. How we *use* this data is described in [../02-architecture/06-sourcing-and-seller-data.md](../02-architecture/06-sourcing-and-seller-data.md).

**These are seed sellers only.** Sourcing is open-world ([D-16](05-decision-log.md)): any Indian seller found by discovery is auto-onboarded and can appear in results. The table below is the fast path.

Adapter status for the seed set:

| Seller | Tier | Adapter | MVP? |
|---|---|---|---|
| Robocraze | A | Shopify UCP/MCP → `/search/suggest.json` fallback | ✅ |
| Quartz Components | A | Shopify UCP/MCP → products.json | ✅ |
| Silicon TechnoLabs, ThinkRobotics | A | Shopify (UCP ⚠️ verify) | ✅ |
| Zbotic | A | WooCommerce Store API | ✅ |
| Probots | A | Magento GraphQL (⚠️ verify query) | ✅ |
| DigiKey India | B | Product Information v4 (+ Substitutions) | ✅ |
| Mouser India | B | Search API | ✅ |
| element14 India | B | Product Search API | Should |
| Nexar/Octopart | B | GraphQL `similarParts` (100 parts/month eval) | Demo only |
| Robu, Evelta, Thingbits, Amazon.in, ElectronicsComp, Hubtronics, Robokits, FlyRobo | C | Gemini Search grounding + URL context + verifier | ✅ |
| LCSC, TME | B | APIs; import options only | Could |
| Flipkart | C / affiliate | Affiliate API (feeds, search) | Could |
| Amazon.in | C / affiliate | Creators API (needs ≥ 10 qualifying sales in 30 days) | Could |

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


### 3.3 Who stocks originals (for "genuine" mode)

| Brand | Indian sources (confirmed on brand's own list unless noted) |
|---|---|
| Adafruit | Thingbits ("Official Distributor" in page title), Robu, Evelta, Fab.to.Lab, Crazy Pi, Silverline, Tenet, ProtoCentral, DNA, Adhira, Tanna TechBiz; plus Mouser/DigiKey/element14 |
| Pololu | Robu (Macfos), Fab.to.Lab, MG Super Labs (Nagpur), TME (ships from Poland) |
| SparkFun | I couldn't load SparkFun's distributor page. Zbotic's article lists Thingbits for SparkFun **[unverified]**. Mouser/DigiKey carry SparkFun |
| Raspberry Pi | Approved resellers per PiCockpit: Robocraze, Robu, Silverline Electronics. Robu authorised since 29 Oct 2018 |
| Teensy (PJRC) | ElectronicsComp (brand listed), Zbotic (listed, OOS). Mouser/DigiKey/SparkFun abroad |

---

