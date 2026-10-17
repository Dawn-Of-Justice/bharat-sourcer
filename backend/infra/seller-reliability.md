# Seller discovery and reliability

## Request flow

Direct seller catalogue search and its bounded recovery run first. If no acceptable
in-stock offer is found, configured Shopify Catalog, Brave and Mouser discovery run
before Gemini grounding. `BS_SELLER_COMPARE_MORE=true` also runs configured providers
after a direct offer is found. It does not force extra Gemini calls.

Each provider makes at most one request per line's initial sourcing attempt, with up to
10 results, a bounded response size and timeout. The combined provider verification
budget is `BS_SELLER_SEARCH_FETCH_BUDGET`; results are interleaved across providers.
Provider errors are isolated. Search results are leads, never proof of compatibility.
Additional API usage is not included in the Gemini dollar ledger; set provider-account
quotas before enabling these integrations. Retries and repeated refreshes can incur
additional requests. The shared provider pacing default is one request per second.

## Enable providers

All integrations are opt-in. Put secrets only in ignored environment files or the
deployment's secret manager. Restart the backend after configuration changes.

```dotenv
# Publish your own valid UCP agent profile at a public HTTPS URL first.
BS_SHOPIFY_CATALOG_ENABLED=true
BS_SHOPIFY_CATALOG_PROFILE=https://YOUR-DOMAIN/ucp-agent-profile.json
# Use a Brave Web Search subscription key.
BS_BRAVE_SEARCH_API_KEY=YOUR-SECRET
# Use a Mouser Search API key, not a cart/order API key.
BS_MOUSER_SEARCH_API_KEY=YOUR-SECRET
BS_SELLER_PROVIDER_TIMEOUT_S=8
BS_SELLER_PROVIDER_INTERVAL_S=1
BS_SELLER_COMPARE_MORE=false
```

Shopify uses Global Catalog MCP `search_catalog`, shipping-to-India and availability
filters, plus India/INR buyer context. It supports JSON and SSE response envelopes.
Catalog search results and images are not written to the shared cache. Only candidate
URLs enter the ordinary seller verification flow; independently fetched seller evidence
retains its existing cache policy. Shopify's inferred fields and price ranges are not
accepted as verified offers. Coverage of specific Indian stores must be measured live.

Brave uses India targeting and disables spell correction to preserve model numbers.
Snippets and search prices are never treated as verified seller data.

Mouser uses the official Search API. A direct API offer requires explicit INR pricing
at quantity one, minimum quantity one, ordering multiple one, and no restriction message.
Stock comes from `AvailabilityInStock`, otherwise it stays unknown. USD prices, bulk
tiers and missing fields are not converted or guessed. Such candidates can still be
verified through the ordinary product-page path. Direct API offers use the existing
`seller_product_api` provenance and compatibility pipeline. Prices do not establish
shipping, duties, GST inclusion or delivery to a particular postal code. Configure the
Mouser account appropriately and verify its returned currency. DigiKey is not integrated.

Official references checked during implementation:
- https://shopify.dev/docs/agents/catalog/global-catalog
- https://shopify.dev/docs/agents/profiles
- https://shopify.dev/docs/agents/catalog#usage-guidelines
- https://api-dashboard.search.brave.com/api-reference/web/search/get
- https://api.mouser.com/api/docs/V1

## Shared pacing and cooldowns

Firestore-backed deployments use `<job-collection>_seller_hosts` for transactional
per-host request reservations and cooldowns. Local runs use a shared in-memory
coordinator. These operational documents contain hashed host IDs, scheduling timestamps
and reason codes, not queries, credentials or project content. `expires_at` supports an
optional TTL policy; this change does not enable that infrastructure policy.

SafeFetcher coordinates every network hop, including robots and redirect requests.
Requests wait at most ten seconds for a slot; longer queues return a `deferred` outcome.
Robots crawl delays up to ten seconds are paced instead of rejected. Longer delays are
reported separately as `crawl_delay_exceeds_worker_budget`; there is no durable delayed
retry queue yet. Explicit disallows remain disallows. Robots rules refresh hourly.
Coordination failure stops new network requests; it does not silently send unpaced traffic.

Bot challenges and exhausted 429/503 retries create shared cooldowns. Long Retry-After
values are respected without keeping a worker sleeping for that duration. Unexpired
cached pages/search responses remain usable during cooldown; expired data is not revived,
and explicit refresh continues to bypass cached pages.

## Measure results

`SELLER_FETCH` separates HTTP errors, throttling, unavailability, challenges, cache hits
and deferred requests. `SELLER_SEARCH_RESULT` records per-seller result counts and parsing
failures. `SELLER_PROVIDER` records provider status, duration and candidate count, without
response bodies, queries or credentials.

Export Cloud Logging entries for those events into JSON, then run:

```powershell
python scripts/seller_health.py events.json --output seller-health.json
```

This reports per-host outcomes and latency. It does not claim extraction or BOM accuracy.
Use `scripts/check_seller_search.py` for the existing live direct-seller probe. Before
production rollout, compare the same labelled projects with providers off and on:
correctly matched purchasable lines, complete BOMs, wrong variants, latency and API cost.
Include exact ICs, maker modules, generic passives and made-to-order components.

Mock transport tests cover API contracts and failure isolation. They do not establish
live seller coverage, provider account access or production Firestore throughput.

## Production rollout (2026-10-18)

The app at https://bharatsourcer.web.app uses Brave and Shopify. Mouser is disabled
pending Search API approval. Brave is mounted from Secret Manager
`bharat-sourcer-brave-search` as `BS_BRAVE_SEARCH_API_KEY`; never put its value in an
image, source file, frontend environment, or command argument.

The production profile is stored in `frontend/hosting/ucp-agent-profile.json` and
published at https://bharatsourcer.web.app/ucp-agent-profile.json?v=2026-10-18.
Its explicit public Cache-Control header is part of `frontend/firebase.json`.
Shopify rejected Firebase's default header without `public`; the version parameter
avoids the cached earlier profile error. Preserve these headers on future releases.

Runtime settings: `BS_SHOPIFY_CATALOG_ENABLED=true`, the production URL in
`BS_SHOPIFY_CATALOG_PROFILE`, and `BS_SELLER_COMPARE_MORE=true`. Compare-more makes
external discovery run even when direct sellers succeeded, to exercise both providers
in app testing; it increases API usage and latency. Set it to false to return to
fallback-only discovery. The deployment script preserves these live settings.

Cloud Run revision: `bharat-sourcer-integration-00123-fef`.
Previous revision for rollback: `bharat-sourcer-integration-00121-sc8`.
