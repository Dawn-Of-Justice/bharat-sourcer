# Countries and account settings

v0.23.0. Every project has a delivery country, and signed-in accounts save a default
country. **Only India (`IN`) is supported today**; this is the groundwork for adding more.
The PIN code is gone: parts are ordered online for delivery, so a postcode was never used.

Code: `backend/src/bharat_sourcer/countries.py` (registry), `access.py` (routes),
`schemas.py` (`CreateJob.country`, `AccountSettings`). Tests: `backend/tests/test_countries.py`.

## Routes

| Route | Auth | Returns |
| --- | --- | --- |
| `GET /v1/countries` | integration key only | `{default: "IN", countries: [{code, name, currency, locale, market_cities}]}` |
| `GET /v1/account/settings` | account or guest | `{country, updated_at, saved}`; guests and accounts that never saved get the defaults with `saved: false` |
| `POST /v1/account/settings` | account only, `X-Requested-With: BharatSourcer` | Body `{country}`; saves and returns `{country, updated_at, saved: true}` |

`POST /v1/account/settings` errors: 401 `ACCOUNT_REQUIRED` for guests, 401
`IDENTITY_REQUIRED`, 403 `REQUEST_HEADER_REQUIRED` / `ORIGIN_REJECTED`, 422
`VALIDATION_ERROR` for an unsupported or malformed code. It does not use the action
budget. Settings are stored in the `<jobs collection>_accounts` Firestore collection, one
document per owner, holding only preferences.

Use `GET /v1/countries` to build the country picker, so the frontend never offers a
country the backend rejects. Flags are a frontend concern (`frontend/src/CountryPicker.tsx`).

## Projects

`POST /v1/jobs` takes an optional `country` (ISO 3166-1 alpha-2, upper case). When it is
omitted, a signed-in account's saved country is used, otherwise `IN`. An unsupported code
is 422. The value is echoed in `job.input.country`; jobs saved before v0.23 read as `IN`.

`pin` was removed from `CreateJob`. Requests and saved snapshots that still carry it are
accepted and the value is dropped, so older clients keep working.

Nearby markets now take `city` (one of the country's `market_cities`) or coordinates
inside the job's country; see [nearby-markets.md](nearby-markets.md).

## What the registry holds

Each `Country` has: code, name, currency, locale, mains voltage and frequency, plug
types, tax name, local domain suffix, curated seller domains, a bounding box and market
cities. Code that needs one of these facts reads it from the registry: nearby markets
(cities, bounding box), grounded-search ranking (seller domains, domain suffix) and the
compatibility rules' mains voltage.

## Adding a country (checklist)

The registry entry alone does not make sourcing work in a new country. Before adding one
to `COUNTRIES`:

1. **Registry:** add the `Country` (sellers, currency, mains, plugs, tax, bounds, cities).
2. **Sellers:** catalogue search adapters and robots checks for its sellers
   (`sourcing/known_sellers.json`, `seller_search.py`), and shipping policies (`costing`).
3. **Prices and tax:** money fields are named `*_inr` and costing assumes INR and GST.
   Add a currency-neutral amount (or per-country fields) and the country's tax rules
   before showing prices in another currency.
4. **Prompts:** the extraction, spec writer and judge prompts say "Indian sellers"; pass
   the country name and seller conventions in instead.
5. **Safety and compatibility:** mains warnings and plug advice in `safety.py` and
   `compat_rules.py` name India's 230 V / 50 Hz and Type D/M plugs; read them from the
   registry and run them with the job's country.
6. **Pass the job's country through sourcing:** `SourcingService` and `source_rank` use
   India by default; route `job.input.country` to them.
7. **Frontend:** add the flag in `CountryPicker.tsx`; the list itself comes from
   `GET /v1/countries`.
