# Seller-page evaluation (2026-10-05)

Offline evaluation of offer verification, image extraction and spec parsing against real
Indian seller product pages. No paid APIs were used. Pages were fetched once with plain
HTTP GETs (user agent `BharatSourcer/0.4 (+product-data-verification)`), after checking
each site's `robots.txt` (including wildcard `Disallow` rules that `urllib.robotparser`
ignores). Product URLs came from the sellers' own category or search pages.

Fixtures: `backend/tests/fixtures/seller_pages/` (17 pages, 0.8–9.5 KB each). They keep
only JSON-LD, og/twitter meta tags and table/`dl` blocks, with a header giving the source
URL and fetch date. One reviewer's name was redacted. **Prices in fixtures are historical
snapshots for parsing tests; they are not current or verified prices.** Labels and tests:
`backend/tests/test_seller_pages.py` (20 labelled page/query cases).

## Coverage

| Seller | Pages | Parts | Notes |
| --- | --- | --- | --- |
| robocraze.com (Shopify) | 6 | 0.96" OLED, 10k resistor, Pro Micro, ESP32 devkit, 5mm LED, push button | JSON-LD images are all Shopify `no-image` placeholders |
| quartzcomponents.com (Shopify) | 4 | SSD1306 OLED, TTP223, 555 timer, LDR | Offer URL is the `?variant=` URL |
| compoindia.com (WooCommerce) | 2 | 7-pin OLED, TTP223 | Offer list with one Offer |
| electronicscomp.com (OpenCart) | 2 | 0.96" OLED, TTP223 | No Product JSON-LD at all |
| rytronics.in, flyrobo.in, evelta.com | 1 each | OLED 0.96" / 0.96" / Qwiic 0.91" | |
| robu.in | 0 | — | HTTP 403 Cloudflare challenge to plain GETs (search and product pages) |

Not fetched: evelta and flyrobo/electronicscomp search URLs (disallowed by `robots.txt`;
category pages were used instead).

## Results

Rates are against human labels; "before" is the code at `d8f2b51`.

| Check | Before | After | Notes |
| --- | --- | --- | --- |
| Offer verification agrees with label | 18/20 | 20/20 | 16 expected to verify, 4 expected rejections |
| Expected offers verified | 14/16 | 16/16 | 5 Quartz cases need the same-path variant fetch |
| Real product image extracted (JSON-LD pages) | 13/15 | 15/15 | 6 Robocraze pages rely on the `og:image` fallback; 6/6 placeholders rejected |
| Clearly stated spec fields extracted | 20/27 | 27/27 | 0 wrong values, 0 conflicts |

Expected rejections (intended):

- **No Product JSON-LD** (electronicscomp, 2 pages). Their tables include "MRP Rs. …";
  prices are never read from prose or tables.
- **Requested identifier not in title** ("SSD1306 OLED" vs Robocraze and Flyrobo titles
  without "SSD1306"). Flyrobo's spec table does say "Driver IC: SSD1306", but the title
  gate stays strict; such pages still appear as unverified research sources.

Bugs fixed:

1. Inch notation: `0.96″` (compoindia) and `0.91 in.` (evelta) did not match a query
   containing "inch", so offers and images were lost. Title and query tokens now
   normalise `"`, `″`, `”`, `inch(es)` and `in.` after a digit. Bare `in` is not treated as
   inch ("5 in 1").
2. A supply written as "Operating Voltage (VDC): 3.3 ~ 5" was unknown. Bare numbers are
   now accepted only when the label's parenthetical unit is volts and the whole value is
   one ascending range. "Pixel Resolution" was added as a resolution label.
3. Hardening: offer and variant URLs now compare percent-escapes case-insensitively.
   compoindia publishes lowercase escapes (`%e2%80%b3`), which a fetched URL may
   write in uppercase.

Stated but deliberately not extracted:

- "Driving Voltage: 3.3-5V" (Robocraze, electronicscomp OLED): for OLED panels the label
  can mean panel drive voltage, so it is not mapped to module supply.
- "5V 16M" in the Pro Micro title: "16M" is not read as 16 MHz, and a title's "5V" is not
  read as logic level.
- A single "Operating Voltage: 3.3V" (ESP32) or "12" (push button) is not a supply range.

Image caveat: Robocraze's Pro Micro page declares an `og:image` that shows a Pro Mini
(file `Resistor220390Ohm_4.png`). Metadata cannot reveal this, so seller images must
remain labelled "visual only".

## Recommendations

1. Consider letting a spec-table controller satisfy a controller-only query token when
   the title names the family (the Flyrobo SSD1306 case). This needs a design decision
   because it relaxes the title gate.
2. Ask electronicscomp-style OpenCart sellers to publish Product JSON-LD; until then they
   can only be research sources.
3. Robu.in needs a permitted access route (feed or partner API); plain fetches return 403.
4. Re-run this evaluation when adding labels. Add a label only when a fixture shows it,
   and keep ambiguous ones (e.g. "Driving Voltage") unmapped.
5. Expand fixtures for TTP223 output mode and active level, which no page stated in a
   table.
