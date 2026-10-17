# Live seller discovery comparison — 18 October 2026

Implementation pushed as `50f80a7` on `feat/robust-seller-discovery`.

## Result

Seven distinct core components from three real published projects were searched live.
After conservative title review, excluding unavailable listings and collapsing the same
product path with/without a Shopify variant/tracking query, relevant in-stock listing
options increased from **17 to 22 (+29%)**. All five incremental options came from Brave.
Shopify returned results on all seven queries, but added **zero unique qualifying listings**
in this small sample. Component coverage stayed **6/7**. These are candidate listings,
not independently confirmed electrical compatibility, shipping, or checkout availability.

| Component | Direct sellers | With Brave + Shopify | Added |
|---|---:|---:|---:|
| ESP32 DOIT DevKit V1 | 0 | 0 | 0 |
| BME280 sensor module | 2 | 2 | 0 |
| Arduino Uno | 1 | 3 | 2 |
| HC-SR04 ultrasonic sensor | 3 | 4 | 1 |
| DHT22 temperature humidity sensor | 5 | 5 | 0 |
| 28BYJ-48 5V stepper motor | 4 | 5 | 1 |
| ULN2003 driver board | 2 | 3 | 1 |

## Project baskets

| Published project | Core lines covered | Listing options, before → after |
|---|---:|---:|
| [ESP32/BME280 weather station](https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/) | 1/2 → 1/2 | 2 → 2 |
| [Arduino HC-SR04 with temperature correction](https://dronebotworkshop.com/hc-sr04-ultrasonic-distance-sensor-arduino/) | 3/3 → 3/3 | 9 → 12 |
| [Arduino stepper, demo 1](https://dronebotworkshop.com/stepper-motors-with-arduino/) | 3/3 → 3/3 | 7 → 10 |

Arduino Uno is shared by two baskets and counted once in the overall totals. Wiring,
breadboards and power supplies were excluded; this is not a complete-BOM claim.

## Method and limitations

- Fixed component names from the published guides; no extraction comparison. Existing
  repository labels were agent drafts, not human-reviewed gold data.
- Each unique component: one direct-catalog stage (up to eight candidates), then one
  request to each provider and up to eight combined external candidates. Existing robots,
  pacing, cooldowns and page verification were used. No bot protection bypass.
- Baseline is direct seller search, NOT the full providers-off production pipeline:
  Gemini grounding, AI judge, buyer and recovery were omitted. This isolates discovery
  contribution but cannot quantify improvement over the entire old application.
- 7 Brave + 7 Shopify search requests. Both returned `ok` on every query. Provider
  subscription charges are not included in the app's Gemini cost ledger.
- Direct stage ran first with shared in-memory cache/pacing. Extra provider search plus
  seller verification took 10.5–22.4 seconds per component (median 16.0 seconds).
  These are single-run local timings, not randomized or Cloud Run latency estimates.
- Raw page-verifier count rose 31 → 43, but that metric overstates useful improvement:
  it includes wrong Arduino generations/accessories, a sensor holder, bulk packs,
  out-of-stock entries and duplicate Shopify variant URLs.
- Conservative review excluded Arduino R4/Q, shields and cables; the ambiguous HC-SR04
  listing with HY-SRF05 URL, Easy-Plug variant, 20-pack and bracket; and the motor+driver
  bundle when counting standalone ULN2003 options. Remaining titles were not bench-tested.
- Deduplication by product path is a reporting choice only, suitable for these observed
  duplicate listings; do not apply it globally because legitimate variants can differ.
- Exact DOIT DevKit V1 remained unresolved by the deterministic matcher despite leads.
  Production's AI judge may perform differently; no claim of zero actual market supply.

## Next actions

Keep Brave available: it added two Uno R3 listings, one HC-SR04 listing, one 28BYJ-48
listing and one ULN2003 listing. Shopify needs a broader niche-store sample before
claiming added coverage. Avoid interpreting successful API calls as sourcing improvement.
Prioritize wrong-product rejection and variant deduplication, then repeat with the full
AI-judged pipeline. Comparison mode remains enabled in production; no runtime settings
were changed by this evaluation.
