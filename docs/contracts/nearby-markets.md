# Nearby markets (Google Maps grounding)

Unreleased (`mvp/markets`). "Pick it up today": electronics markets and shops near the
maker, from one Gemini call grounded in Google Maps (roadmap S2). **On by default**
(`BS_MARKETS_ENABLED`); India availability was checked with one live call on 2026-10-07.
The results describe shops, not stock: **nothing here confirms that a shop has a part.**

Code: `backend/src/bharat_sourcer/markets.py`. Tests: `backend/tests/test_markets.py`
(Gemini is mocked; fixtures use the recorded response shape with synthetic content).

## Request

`GET /v1/jobs/{job_id}/markets?pin=560002` or `GET /v1/jobs/{job_id}/markets?lat=12.97&lng=77.59`

Send the job token (`X-Job-Token`) or the signed-in credentials, like `GET /v1/jobs/{id}`.
The job needs a parts list (`items`). Send either `pin` or both `lat` and `lng`.

- **PIN:** 6 digits, not starting with 0. The PIN prefix maps to an **approximate city
  centre** from a static table (no geocoding): Bengaluru (56x), Chennai (600), Mumbai (400),
  Delhi (110), Hyderabad (500), Kolkata (700), Pune (411), Kochi (682), Ahmedabad (380),
  Coimbatore (641), Jaipur (302), Lucknow (226), Thiruvananthapuram (695), Gurugram (122),
  Chandigarh (160), Indore (452), Nagpur (440), Surat (395), Visakhapatnam (530). Other
  prefixes return 422 `PIN_NOT_SUPPORTED`: offer "use my location" instead.
- **Coordinates:** must be inside India; they are rounded to 2 decimals (about 1 km)
  before they are sent to Gemini or used as a cache key.

Only a short list of part categories from the BOM (e.g. "resistors, LEDs, sensors") is
sent to Gemini, never part names or project text. Lines marked "I have it" are skipped.

## Response `MarketsResult`

```json
{
  "demo": false,
  "location": {"source": "pin", "pin": "560002", "city": "Bengaluru",
               "latitude": 12.9716, "longitude": 77.5946, "approximate": true,
               "label": "Approximate: PIN 560002 mapped to the centre of Bengaluru."},
  "categories": ["resistors", "LEDs", "sensors"],
  "summary": "1. … (SP Road)\n2. …",
  "summary_label": "Shops likely to carry these parts — call first; stock is not confirmed",
  "places": [{"title": "Shop name", "uri": "https://maps.google.com/maps?cid=…",
              "address": "2nd Floor, …", "place_id": null}],
  "attribution": {
    "provider": "Google Maps",
    "sources": [
      {"title": "Shop name - Google Maps", "uri": "https://maps.google.com/maps?cid=…", "kind": "place"},
      {"title": "Review of Shop name", "uri": "https://www.google.com/maps/reviews/data=…", "kind": "review"}
    ],
    "rules": "Show these Google Maps sources immediately after the summary, …"
  },
  "cached": false,
  "model": "gemini-3.8-flash",
  "label": "AI summary grounded in Google Maps"
}
```

- `summary` is the model's text. It is **null when Gemini returned no Maps sources**
  (ungrounded text could name shops that do not exist); then `places` and `sources` are
  empty and `label` says nothing was found.
- `places` come from the grounding chunks, not from the text: the title without
  " - Google Maps", the Maps URI, the address when the chunk states one, and `place_id`
  when Gemini returns it. Review chunks are not places.
- `attribution.sources` is the exact source list in Gemini's order (places, reviews and
  any web sources), with titles exactly as returned. Duplicate and non-http(s) URIs are
  dropped.
- `cached: true` means the result came from the 7-day cache (same rounded location and
  category set, possibly from another project); no call was made.

## Attribution rules (Google Maps grounding terms — must follow)

1. Render `attribution.sources` **immediately after** the summary and places, in the
   given order, as links (`title` → `uri`). Do not put other content between them.
2. The sources must be **viewable within one user interaction** (visible, or behind a
   single tap/expand at most).
3. **Do not modify the text "Google Maps"** in any way (no translation, abbreviation,
   restyled spelling or line break inside it). Show titles as returned.
4. Show `summary_label` with the summary: "Shops likely to carry these parts — call first;
   stock is not confirmed".
5. Show `location.label` (PIN results are approximate city centres).

Demo responses (`demo: true`) contain fictional shops marked "(demo)", no URIs and no
sources; label them as a sample and do not show a Google Maps attribution for them.

## Cost controls and configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BS_MARKETS_ENABLED` | `true` | Enables the endpoint (503 `FEATURE_DISABLED` when false) |
| `BS_MARKETS_DAILY_LIMIT` | `5` | Uncached lookups per owner per UTC day |
| `BS_MARKETS_GLOBAL_DAILY_LIMIT` | `50` | Uncached lookups across all owners per UTC day (keeps Maps inside the 5,000/month free grounding pool it shares with sourcing) |
| `BS_MARKETS_CACHE_TTL_S` | `604800` | Shared cache lifetime (7 days; 0 disables writes) |

The model is `BS_GEMINI_MODEL` (per-site override `BS_GEMINI_SITE_MODELS={"markets": …}`)
with `thinkingLevel: low` (`BS_GEMINI_SITE_THINKING`). Usage is logged as site `markets`
with at least one grounding query and added to `job.cost_estimate`. Cache hits do not
use the quota. The cache stores only the summary, places and attribution, never project
data. "Owner" is the account or guest identity when authentication is on, otherwise the
job. The quota is charged before Gemini is called, so a failed call still counts. Like
other `GET` endpoints it does not spend the project action budget.

## Errors

| Status | Code | When |
| --- | --- | --- |
| 422 | `INVALID_PIN` | PIN is not 6 digits |
| 422 | `PIN_NOT_SUPPORTED` | PIN prefix not in the city table |
| 422 | `INVALID_LOCATION` | Neither or both of `pin` and `lat`/`lng` |
| 422 | `LOCATION_OUTSIDE_INDIA` | Coordinates outside India |
| 409 | `NOTHING_TO_SOURCE` | The parts list is not ready |
| 409 | `JOB_BUDGET_REACHED` | The job's current sourcing run reached its AI budget |
| 429 | `FEATURE_QUOTA` | Daily limit reached (`Retry-After`: seconds to UTC midnight) |
| 503 | `FEATURE_DISABLED` / `FEATURE_UNAVAILABLE` | Flag off / no Gemini key |
| 502/503/504 | `UPSTREAM_ERROR`, `INVALID_OUTPUT` / `UPSTREAM_QUOTA` / `UPSTREAM_TIMEOUT` | Gemini failed |
