# Proposal register — status reviewed 9 October 2026

Implemented behavior is described in [backend/README.md](backend/README.md) and
[docs/contracts/README.md](docs/contracts/README.md), currently v0.27.0.
The remaining sections preserve proposals and estimates written on 6 October; they
are not current deployment instructions or independently rechecked prices.

## Status updates

- YouTube description intake and nearby markets are implemented. Markets now use
  `city`, not PIN code; see [nearby markets](docs/contracts/nearby-markets.md).
- Firestore TTL policies, the queue-age alert and API max instances of 3 were provisioned;
  see the [operations runbook](backend/infra/README.md). Future minimum-instance changes
  remain scheduled proposals, not completed work.
- Safety flags, costing, export/share, multi-source intake, catalogue compatibility and
  seller trust are implemented. Export is PDF/HTML; CSV was removed in v0.26.0.
- Routing is complete in v0.27.0. [Code adaptation](docs/plans/code-adapt/PLAN.md)
  tiers 1–2 (curated recipes; AI drafts behind a flag) shipped diff-only in v0.28.0, with
  no compile. Web Risk, browser rendering, compile infrastructure and other new-service
  proposals below are not implemented.
- New services, indexes, schedulers, paid third-party APIs and IAM changes require
  owner review before provisioning.

## Original proposal context (6 October 2026)

- **Written:** Tue 6 Oct 2026. MVP freeze (G3) is **13 Oct**, submission (G4) is **17 Oct**
  and judging runs 19 Oct to 6 Nov. Mondays and Thursdays are light days.
- **Prices** were checked on 6 Oct 2026 unless a row gives another date. The sources are listed
  at the end. Effort counts one developer's working days and includes tests and contract/README
  updates.
- **Historical baseline (6 Oct):** backend v0.19.3 on Cloud Run `bharat-sourcer-integration` in `asia-south1`
  (Cloud Run pricing **Tier 1**), 1 vCPU / 512 MiB, request-based billing, min 0 / max 1 instances,
  Cloud Tasks + Scheduler dispatch, Firestore `(default)`, and the Gemini Developer API key in
  Secret Manager.
- **Original exclusions (subsequently implemented):** safety flags, costing and
  the cart optimiser, export and share links, multi-source intake and fusion, the parts catalogue
  and compatibility grades, free-signal trust labels with the Shopify/Woo JSON fast path,
  flagged-off TTS, clip zoom and parts-bin scan, and the eval gold set.

---

## Recommended for approval before 13 Oct

The ranking is by demo impact per day of effort. Every item uses only GA services and costs close
to nothing inside the free tiers.

| Rank | Item | Effort | Cost to 6 Nov | Why |
| --- | --- | --- | --- | --- |
| 1 | [Ops bundle](#13-ops-alert-policy-max-instances-min-instances): `min-instances=1` on both services 15 Oct – 6 Nov, `max-instances=3`, one `QUEUE_AGE_EXCEEDED` alert | 0.25 d (owner runs 3 commands) | ≈ $15 | A cold start or a stuck queue while the demo is being recorded or judged costs more than any feature adds. Judges open the live URL at random times |
| 2 | [YouTube Data API `videos.list`](#4-youtube-data-api-v3-videoslist) | 0.75 d | $0 (10,000 units/day free; 1 unit per call) | The description often holds the full parts list and links. It feeds the multi-source intake being built now, so every video demo gains recall and gets the "Reading the description… following 3 links" trace line |
| 3 | [S2 nearby markets (Maps grounding)](#5-s2-nearby-markets-via-gemini-grounding-with-google-maps) | 1 d backend + 0.5 d frontend | ≈ $0 inside the shared 5,000 free prompts/month; then $14 / 1,000 queries | This is the visible "Bharat" moment from the pitch ("Pick it up today: SP Road, 2.1 km"). It needs no new infrastructure or secret. One live call first checks that it works for India (V10) |

Next if time allows: [M6b Web Risk](#2-m6b-google-web-risk-api-for-seller-urls). It takes 0.5 d and
is free up to 100k lookups a month, but judges barely see it.

Not before submission: [M9 compile check](#1-m9-code-impact--compile-check). It is the strongest
"wow" moment, but it needs about 5.5 days and a 2 GB image, and it depends on code intake and
compatibility findings that are still being built. A **diff-only** version (no compile, no new
infrastructure) is the fallback the timeline already names. It needs no approval beyond normal
Gemini use.

---

## Summary of all proposals

| # | Item | New infra / IAM / secrets | Cost (demo scale) | Effort | Recommendation |
| --- | --- | --- | --- | --- | --- |
| 1 | M9 code impact + compile | Cloud Run job or private service, 2 GB image, service account, invoker grant | < $1/month + Gemini ≈ $0.04 per line | 5.5 d | After submission (diff-only allowed now) |
| 2 | M6b Web Risk | Enable API, API key secret | $0 ≤ 100k/month | 0.5 d | Now if time allows, after the top 3 |
| 3 | M6 structured sources | Up to 4 API keys/OAuth clients, UCP agent profile URL | $0 (free keys) | 1–1.5 d each | After submission (DigiKey first) |
| 4 | YouTube Data API | Enable API, API key secret | $0 | 0.75 d | **Now (#2)** |
| 5 | S2 Maps markets | None (same Gemini key) | ≈ $0; $14/1k queries after the shared free pool | 1.5 d | **Now (#3)** |
| 6 | S6 visual matching | Firestore vector index, new collection | < $1 | 3 d | After submission |
| 7 | S7 A2UI | New frontend renderer dependency | $0 | 4–5 d (mostly frontend) | Never for this build |
| 8 | S8 Wokwi badge | Wokwi CI token (third-party account), depends on #1 | $0–7/month | 2–3 d after #1 | After submission |
| 9 | S11 Verify live | New Cloud Run service (Chromium), service account | ≈ $0.03–0.05 per check | 3–4 d | After submission |
| 10 | S12 MCP server | New public endpoint, per-user tokens | Gemini cost of the jobs it starts | 2–3 d | After submission |
| 11 | S13 audio input | Upload endpoint (new public surface) | ≈ $0.05 per 10 min | 2 d | After submission |
| 12 | S9 public library + votes | Firestore composite index, public collection, moderation | ≈ $0 | 4–5 d | After submission |
| 13 | Ops bundle | Alert policy, scaling changes | ≈ $15 to 6 Nov | 0.25 d | **Now (#1)** |
| 14 | Could list C1–C9 | — | — | — | Not before submission |
| 15 | Optional headless renderer for client-side prices | New private Cloud Run service (Chromium), service account, invoker grant | ≈ $0.15–0.30 per 1,000 renders (estimate) | 2–3 d | Not now; no enabled seller needs it (7 Oct check) |

---

## 1. M9 code impact + compile check

**What it adds.** When a substitute changes code (SSD1306 → SH1106, BME280 → BMP280, a new I²C
address, a pin remap or a new board target), the report shows a unified diff of the maker's
sketch and a "Compiles for ESP32 Dev Module" badge. If the build fails, it shows "Didn't compile,
here's why". This is wow moment 3 in `docs/01-overview/03-solution-and-features.md`, and the MVP
definition of done asks for "at least one compiled code diff" in the demo.

**Dependencies.** The backend reads no code today. It extracts from video and README text only.
M9 needs (a) the GitHub code intake from the multi-source stream (`#include`, `platformio.ini`,
`.ino` files) and (b) compatibility findings from the catalogue/rules stream. Both are being
built now, so M9 cannot be tested end to end before about 9–10 Oct.

**Infrastructure, IAM and secrets.**

| Item | Detail |
| --- | --- |
| Compute | Cloud Run **job** `bs-compile` (as in `docs/03-delivery/01-deployment-and-devops.md` §5) **or**, preferred, a **private Cloud Run service** `bharat-sourcer-compile` (`--no-allow-unauthenticated`, concurrency 1, max 2 instances, 2 vCPU / 4 GiB, timeout 300 s). With a service the API gets a synchronous HTTP result, so there is no polling of job executions and no result bucket. A job needs either a GCS bucket for results (new infrastructure) or `roles/logging.viewer` to read logs |
| Image | `debian:bookworm-slim` + `arduino-cli` + cores `arduino:avr`, `esp32:esp32`, `esp8266:esp8266` + an allowlisted set of about 12 libraries. Published images with the ESP32 3.x core are **1.5–2.0 GB** (Docker Hub, 6 Oct 2026). Add RP2040 only if the eval set needs it |
| Registry | Same `cloud-run-source-deploy` Artifact Registry repo, new image name. Storage beyond 0.5 GB free is about $0.10/GB-month, so ≈ $0.20/month |
| Build | A new workflow, `.github/workflows/compile-image.yml`, triggered only by changes under `backend/compile/`. The backend workflow builds the API image on every merge, so the 2 GB image must not join it |
| Identity | New service account `bharat-sourcer-compile@` with **no roles** (it reads nothing and writes nothing). `bharat-sourcer-api@` gets `roles/run.invoker` on the compile service only. The deploy identity `bharat-sourcer-deploy@` needs `roles/run.developer` on it and `roles/iam.serviceAccountUser` on the new service account |
| Network | No egress needed at run time, because cores and libraries are pre-baked. Blocking egress fully would need Direct VPC egress to a VPC with no NAT, which is more infrastructure. Proposed instead: an identity with no roles, no secrets, and no library installs at run time (`arduino-cli` runs with `--config-file` pointing to a read-only, offline config) |
| Secrets | None |

**Cost.** Request-based Tier 1 pricing is $0.000024/vCPU-s and $0.0000025/GiB-s, with 180,000
vCPU-s free each month. One ESP32 compile of ~90 s on 2 vCPU / 4 GiB costs ≈ $0.005, so a line
with 2 repairs costs ≈ $0.016. That fits the free tier at demo scale. The Gemini diff costs one
3.8 Flash call per affected line (~8k in / 2k out ≈ $0.014), and the 2 repair calls bring the
maximum to ≈ $0.04 per line.

**Implementation against the current code.**

1. `backend/compile/Dockerfile` + `backend/compile/server.py`: a tiny HTTP handler. It accepts
   `{fqbn, files: {name: text}}` with an FQBN from an allowlist and at most 20 files of 200 KB
   each. It rejects absolute paths, `..`, and `#include` of anything outside the sketch or the
   pre-baked libraries. It runs `arduino-cli compile --fqbn … --build-path /tmp/b` with a 120 s
   timeout and returns `{ok, log_tail}`. At image build time a blank sketch is compiled for each
   FQBN, so core objects are cached in the image and cold compiles are faster.
2. `backend/src/bharat_sourcer/code_impact.py`: given the job's code files (from intake) and one
   line's compatibility findings, ask Gemini for a structured patch, either `CodeImpact` from
   `docs/02-architecture/04-prompts-and-schemas.md` or a unified diff. Apply it locally with a
   strict patcher; a patch that doesn't apply cleanly is rejected. Call the compile service with
   an ID token (`google.oauth2.id_token`, as `dispatch.py` already does for Cloud Tasks). On
   failure, feed `log_tail` back up to 2 times. Store `diff`, `compiled`, `fqbn` and `attempts`
   on the report line. Never store code outside the job snapshot, which is capped at 800 KB, so
   cap the diff size.
3. Run it through Cloud Tasks as a new `Work.kind = "code_impact"`, triggered on demand per line
   ("Check code changes"), so it never sits inside the sourcing request path. Flag:
   `BS_CODE_IMPACT_ENABLED`, `BS_COMPILE_URL`.
4. Contracts: a `code_impact` object on report lines, an OpenAPI regeneration, and a frontend diff
   viewer (teammate, ≈ 1 d).

**Sandboxing.** `arduino-cli compile` runs the GCC preprocessor and compiler and the platform's
recipe hooks. It does **not** execute the sketch. The risks are compiler-level ones: huge
includes, `#include "/etc/…"`, and pathological templates that use CPU and memory. Mitigations:
path and include validation, request size caps, a 120 s compile timeout and a 300 s request
timeout, concurrency 1, max 2 instances, no credentials on the identity, an allowlisted FQBN and
library set, and a read-only, offline arduino-cli config. Cloud Run's sandbox (gVisor in first
generation) gives kernel isolation.

**Image size and cold start.** Cloud Run streams image blocks, so a 2 GB image boots in seconds.
The first ESP32 compile still reads hundreds of MB of toolchain lazily, so expect **30–90 s for a
cold first compile** and much less when warm (estimate; measure). Pre-compiling cores at build
time helps. During judging, a `min-instances=1` on this service would add ≈ $0.65/day (2 vCPU /
4 GiB idle), so the recommendation is to pre-warm by hand before recording instead.

**Risks.** Gemini patches may compile but be wrong. "Compiles" must never be shown as "works", so
the badge says *compiles*, not *verified*. Library-name drift breaks `#include` mapping. Most demo
projects may have no code repository at all. The new image and pipeline add CI time.

**Effort.** Image + service 1 d · code-impact node + patcher + repair loop 2 d · dispatch, schema,
contract, tests 1.5 d · frontend viewer 1 d (teammate) ≈ **5.5 d**.

**Recommendation: after submission.** The full version does not fit before 13 Oct alongside its
dependencies. **Before submission:** if the owner wants the moment in the video, build the
diff-only variant (step 2 without the compile call, labelled "diff (not compiled)"), about 1.5 d.
It needs no new infrastructure.

---

## 2. M6b Google Web Risk API for seller URLs

**What it adds.** Each newly seen seller domain is checked against Google's malware,
social-engineering and unwanted-software lists. A hit blocks the offer, and a clean result adds a
"Google Web Risk: no threats found" signal to the free-signal trust labels being built now.
Demo impact is modest (one line in the trace and the trust drawer), but it is a Google-native
safety layer for open discovery.

**Infrastructure, IAM and secrets.** Enable `webrisk.googleapis.com` in `hackathon-510415`. Create
an API key restricted to the Web Risk API and store it in Secret Manager as `BS_WEBRISK_API_KEY`,
pinned in `scripts/deploy_integration.py` like the existing keys. (Option: ADC with the runtime
service account instead of a key; verify the role name, probably `roles/webrisk.user`, before
granting it.)

**Cost.** Lookup API `uris.search`: **free for 1–100,000 calls/month**, then $0.50 per 1,000 up to
10M. At one lookup per new domain per week, demo usage is far below the free tier.

**Implementation.** Add `sourcing/webrisk.py` with
`check(url) -> Literal["clean", "threat", "unchecked"]`, calling
`GET https://webrisk.googleapis.com/v1/uris:search?threatTypes=MALWARE&threatTypes=SOCIAL_ENGINEERING&threatTypes=UNWANTED_SOFTWARE&uri=…`
over `httpx`, with a 3 s timeout and a per-job domain cache. Call it from `SourcingService`
before an offer is accepted. On error, return `unchecked`. Fail open for the label but never call
the domain "safe". Pass the result to the trust-label signals. Tests use a stub client; there are
no live calls in CI.

**Risks.** A key leaked from the logs is the main one, so never log URLs with the key. API errors
must not block sourcing. Check the Web Risk terms for required warning wording before showing a
"threat" banner.

**Effort.** 0.5 d. **Recommendation:** do it now **if** the top 3 are done. Otherwise do it right
after submission.

---

## 3. M6 structured sources

**What it adds.** More verified offers. The original coverage audit noted that many parts
end with no verified offer because sellers lack JSON-LD or Cloudflare blocks them. Structured
APIs return price and stock without page scraping, and DigiKey adds an official `Substitutions`
endpoint.

| Source | Access | Limits | INR | Terms / notes | Effort |
| --- | --- | --- | --- | --- | --- |
| **Shopify Global Catalog MCP** `https://catalog.shopify.com/api/ucp/mcp` | Each request must include `meta.ucp-agent.profile`, a URL to our UCP agent profile (a static JSON we host on our own domain, which is a small new public file) | Not documented | Buyer-context currency; `ships_to=IN` filter | Coverage of Indian maker shops is **unverified** (V8). Pricing and rate limits are not stated in the docs. Personalised search is "coming soon" | 1 d |
| **DigiKey Product Information v4** | OAuth2 client credentials; register an app at developer.digikey.com | ~1,000 searches/day default; burst limits with 429 + `Retry-After` | **Yes:** `X-DIGIKEY-Locale-Currency: INR`, `X-DIGIKEY-Locale-Site: IN` | Free. Also has `Substitutions` and `RecommendedProducts`. Mostly genuine/premium parts, few clone modules | 1.5 d |
| **Mouser Search API** | API key (My Mouser request form) | 30 calls/min, 1,000/day (30 Sep 2026) | Not documented in the API; Mouser India invoices INR/USD (DDP for GST buyers) | Search API Terms at mouser.in/apiterms. The page timed out on 6 Oct; **read before use** for caching and display rules | 1 d |
| **element14 Product Search API** `api.element14.com/catalog/products` | `callInfo.apiKey` | Not stated | Per store; India store id **unverified** (`in.element14.com`?) | Free key | 1 d |
| **Affiliate programmes** | Amazon Creators API needs an Associates account with ≥ 10 qualifying sales in 30 days. Flipkart Affiliate API needs an approved affiliate id/token | Amazon: 1 TPS / 8,640 TPD at first | INR | Not reachable by 13 Oct (Amazon's sales gate). Affiliate links also require disclosure in the UI | — |
| **Robu.in** | No public API or feed. The Next.js GraphQL proxy is undocumented, Cloudflare blocks automated reads, and no affiliate programme was found on 6 Oct 2026 | — | — | Do **not** bypass Cloudflare. Option: email Robu for a product feed or sitemap allowance; until then Robu stays reachable only through grounded discovery | email only |

**Infrastructure, IAM and secrets.** New Secret Manager secrets: `BS_DIGIKEY_CLIENT_ID` and
`BS_DIGIKEY_CLIENT_SECRET`, `BS_MOUSER_API_KEY`, `BS_ELEMENT14_API_KEY`, plus a public UCP agent
profile URL. No new services. Each provider is a separate account and set of terms the owner must
accept.

**Cost.** All $0 at these limits. Indirectly, offers from structured APIs can skip some grounded
searches (5,000 free/month, then $14 / 1,000 queries).

**Implementation.** Add a `StructuredSource` protocol next to `Discoverer` in `sourcing/service.py`,
with one adapter per provider returning offers already in the existing verified-offer shape, with
`evidence.source = "api:<provider>"`. Run the adapters before grounded discovery for parts that
have an MPN. Keep fixture-based tests. Label USD-only results "import option". Distributor prices
are ex-GST plus shipping, so they go through the costing stream's GST/shipping inputs.

**Risks.** Distributors rarely stock the clone modules makers buy, so coverage gains are mostly
ICs and genuine boards. Each provider's terms may forbid caching or showing prices next to
competitors (Mouser in particular). Global Catalog coverage is unknown.

**Recommendation: after submission.** Exception: a 2-hour **Global Catalog spike** (curl only, no
adapter) is worth doing if the owner approves hosting the agent profile, because it answers V8. If
one distributor is wanted for the "DigiKey (API) ✓" trace line, start with DigiKey (INR confirmed,
substitutions endpoint).

---

## 4. YouTube Data API v3 `videos.list`

**What it adds.** Today the backend passes the YouTube URL to Gemini as `fileData`
(`extraction.py`), which watches the video but does not reliably read the description. Makers often
put the full parts list and links to the blog, GitHub and affiliate pages in the description.
`videos.list?part=snippet` returns title, description, tags and channel. The description becomes
another evidence source for the **multi-source intake** being built now, with server-checked quotes
(`project_pages.quote_found`) and links to follow.

**Infrastructure, IAM and secrets.** Enable `youtube.googleapis.com`. Create an API key restricted
to the YouTube Data API v3 and store it as `BS_YOUTUBE_API_KEY` in Secret Manager, pinned like the
others. Cloud Run has no static egress IP, so the key cannot be IP-restricted; API restriction plus
the secret is the control.

**Cost.** $0. `videos.list` costs **1 quota unit**. The default quota is **10,000 units/day**
(search.list has its own 100/day bucket, which we don't use). One call per job is far below the
limit.

**Implementation.** Add `youtube_meta.py` with
`description(video_id) -> {title, description, links}`, using `httpx` with a 5 s timeout. The
video id comes from `extraction.youtube_url`. Skip it when the key is unset or the call fails; it
is never fatal to extraction. Hand the text to the intake/fusion stream as a source with
`source = "youtube_description"`. Quotes are checked against the returned description exactly as
page quotes are. Links are classified by the existing `project_page_source` and follow robots.txt
through `SafeFetcher`. Tests use fixtures only.

**Policy and risks.** YouTube API Services developer policies require refreshing or deleting stored
API data after 30 days. Quotes saved in job snapshots therefore need a retention rule (there is
none yet; see `backend/infra/README.md`). Store only short quotes and the links, not the full
description. Quota increases require a compliance audit, but we don't need one.

**Effort.** 0.75 d. **Recommendation: now (rank 2).**

---

## 5. S2 nearby markets via Gemini grounding with Google Maps

**What it adds.** "Pick it up today" shows the electronics market and shops near the maker's PIN
(SP Road, Lamington Road, Ritchie Street, Lajpat Rai Market, Broadway Kochi…) with Maps links,
hours and ratings. This is wow moment 4 ("It speaks Bharat").

**India availability.** The docs say Maps grounding "is globally available" but "may not be
available in all regions". India is not named either way. **One live test call from a Bengaluru
lat/lng (V10) is needed before building.** Under standing instruction 4 that call needs the owner's
OK. If it fails, drop the item.

**Infrastructure, IAM and secrets.** None. It uses the existing Gemini key with the
`google_maps` tool and `toolConfig.retrievalConfig.latLng`. PIN → lat/lng uses a small static table
of PIN prefixes for the ~10 demo cities, labelled as approximate, so no Geocoding API is needed.

**Cost.** The paid tier gets **5,000 prompts/month free, shared across Gemini 3** with Search
grounding, then **$14 per 1,000 search queries**. Gemini 3 bills each query the model executes.
One market lookup is likely 1–3 queries (≈ $0.014–0.042 after the free pool) plus about $0.005 of
tokens. **The pool is shared**, so Maps use eats into the sourcing grounding budget. Cap it at one
lookup per job and cache place IDs per city for the session.

**Attribution rules (must follow).** "The Google Maps sources must immediately follow the generated
content" and remain "viewable within one user interaction". "Don't modify the text Google Maps in
any way." Each source links to the annotation URL. The frontend card must render these exactly.

**Implementation.** Add `markets.py` with `nearby(pin) -> {places: [{title, uri, place_id}],
summary, attribution}`. It makes one Gemini call with the Maps tool, a prompt for electronics
component markets and shops, and structured output. Add the route
`GET /v1/jobs/{job_id}/markets?pin=` (job-token auth, counted against the existing quotas) and the
flag `BS_MARKETS_ENABLED`. Generated text is labelled "Shops likely to carry these parts — call
first". Maps cannot confirm stock. Add a contract doc in `docs/contracts/` and regenerate OpenAPI.

**Risks.** India availability is unproven. Results describe shops, not stock. The shared free pool
may run out. The frontend must render attribution exactly.

**Effort.** 1 d backend + 0.5 d frontend card (teammate). **Recommendation: now (rank 3)**, gated
on the V10 test.

---

## 6. S6 visual part matching

**What it adds.** Seller listings with different titles ("0.96 inch I2C display module") can be
matched to the part seen in the build by image similarity, which improves recall and ranking.

**Infrastructure.** A new Firestore collection, e.g. `part_vectors`, holding 768-dim
`gemini-embedding-2` vectors, plus a **single-field vector index** (new index = infrastructure):

```sh
gcloud firestore indexes composite create --project=hackathon-510415 --collection-group=part_vectors \
  --query-scope=COLLECTION --field-config=field-path=embedding,vector-config='{"dimension":"768","flat":"{}"}'
```

The runtime identity already has `roles/datastore.user`. No new secrets.

**Cost.** `gemini-embedding-2` costs $0.20/M text tokens and $0.45/M image tokens (≈ $0.00012 per
image), and the free tier is available. Firestore vector queries bill 1 read per 100 index entries
scanned plus 1 per returned document. Demo scale costs well under $1.

**Implementation.** Embed seller `image_url`s (v0.15 offers) and the build's reference image, then
`find_nearest` with pre-filters by category. Use the result only as a **ranking signal**; never use
it to verify an offer.

**Key risk (blocking).** The build side has no frame crops. The backend never downloads YouTube
video (a non-goal and a ToS issue), and Gemini returns no video bounding boxes. Reference images
would come only from project pages, GitHub or Instructables images, or the parts-bin photo. Coverage
for video-only projects is close to zero.

**Effort.** 3 d. **Recommendation: after submission**, and only once reference images exist for
most jobs.

---

## 7. S7 A2UI generative UI

**What it adds.** The agent sends declarative UI JSON (part card, diff widget, map card) that a
React renderer draws. Mostly a technical story for judges; users would see the same cards they see
now.

**Status.** A2UI v0.9 shipped 17 Apr 2026 with an official React renderer, now listed as stable
(v0.9.1). v1.0 is a candidate, so the protocol may still change.

**Infrastructure.** None on GCP. It adds a new frontend dependency and a new SSE message type.
This is frontend-owned work under `AGENTS.md`. The backend would emit A2UI messages next to
the existing snapshots.

**Cost.** $0, plus some output tokens if Gemini writes the UI JSON.

**Risks.** It duplicates the existing custom UI, the protocol may churn before v1.0, and the
frontend teammate's time goes to the demo path instead.

**Effort.** 4–5 d, mostly frontend. **Recommendation: never for this build.** Revisit after v1.0
if the product becomes chat-first.

---

## 8. S8 Wokwi simulation badge

**What it adds.** "Simulated: serial output OK" for 3–4 supported boards and parts, a step beyond
"compiles".

**Infrastructure, IAM and secrets.** A Wokwi account and a `WOKWI_CLI_TOKEN` in Secret Manager
(third-party service). `wokwi-cli` runs inside the M9 compile image. Firmware and diagrams are
uploaded to Wokwi's cloud simulation server, which "does not permanently store uploaded firmware".

**Cost.** Free plan: 50 simulation minutes/month. Hobby: $7/month for 200 CI minutes. Hobby+ and
Pro: 500 and 2,000 minutes. A 30 s simulation × 3 demo projects × a few runs fits the free plan.
Check that the Wokwi licence allows this use.

**Implementation.** Requires M9 (#1). Hand-author `diagram.json` and `wokwi.toml` plus a serial
`expect` scenario for each demo project. Auto-generating wiring diagrams is unreliable. The badge
shows only when a scenario exists.

**Risks.** It depends on M9, needs hand-made diagrams (which don't scale), and the MCP mode is
experimental. Not every part has a Wokwi model.

**Effort.** 2–3 d after M9. **Recommendation: after submission.**

---

## 9. S11 "Verify live" button

**What it adds.** A browser agent opens the seller page, checks price, stock and PIN delivery,
returns a screenshot and **stops before checkout**. Strong visually, but it repeats what the
verified JSON-LD fetch already does for most offers.

**Infrastructure, IAM and secrets.** A new private Cloud Run service `bharat-sourcer-browser` with
Playwright and headless Chromium (image ≈ 1.5–2 GB, 2 vCPU / 2–4 GiB, concurrency 1, max 1–2). A
new service account with no roles. The API service account gets `roles/run.invoker` on it. It uses
the existing Gemini key.

**Cost.** Computer Use is **preview** and is billed as regular tokens for the model
(`gemini-3.8-flash`: $0.75 in / $3.75 out per 1M until 31 Dec 2026, then doubling). It has no free
tier. At an estimated 10–20 steps with screenshots, that is ≈ 30–60k input tokens, or **≈
$0.03–0.05 per check**. Cloud Run time is inside the free tier.

**Safety (from the docs).** Run in a sandboxed container. The model returns `safety_decision`
`require_confirmation` for sensitive actions. The docs forbid CAPTCHA solving, accepting terms,
creating accounts and completing financial transactions. Our code also enforces an action
allowlist: same-domain navigation only, no clicks on cart or checkout elements, and a step cap.

**Risks.** It is preview. Cloudflare-protected sellers (robu.in, as observed in the original audit) will show
challenges we must not solve. Seller pages can carry prompt injection. Typing the maker's PIN into
third-party sites raises privacy questions and needs consent. Latency is 30–90 s.

**Effort.** 3–4 d. **Recommendation: after submission** (preview feature; scope guardrail "nothing
preview-only on the demo path").

---

## 10. S12 MCP server

**What it adds.** `source_bom(url)` and `find_indian_equivalent(part)` as MCP tools for Gemini,
Antigravity, IDE agents and others. A good story for "Bharat Sourcer as a tool", with a small demo
moment.

**Infrastructure, IAM and secrets.** Cloud Run hosts MCP servers over streamable HTTP. Its docs
cover only IAM-invoker, proxy or OIDC authentication, and do not present public unauthenticated
access. A public MCP endpoint therefore needs **app-level auth**. There are two options. (a) Mount
the Python MCP SDK at `/mcp` on the existing service, behind a new per-user **API token**
(issued to signed-in accounts and stored hashed, like job tokens). (b) Implement OAuth 2.1 under
the MCP authorization spec (more work). Option (a) needs no new service but is a **new public
surface**.

**Cost.** No platform cost. Each `source_bom` starts a normal job (≈ 21–31 Gemini calls for 10
parts), so the existing transactional quotas (`access.py`) must apply per token.

**Implementation.** `source_bom` creates a job and returns `job_id`. A second tool,
`get_job(job_id)`, polls, because jobs take minutes and the confirmation step needs a human, so
tool calls cannot block. `find_indian_equivalent` runs single-part research.

**Risks.** Abuse and cost from automated clients, token leakage, and confirmation semantics (an
MCP client cannot easily show the BOM review step).

**Effort.** 2–3 d. **Recommendation: after submission.**

---

## 11. S13 audio input (`gemini-3.5-transcribe`)

**What it adds.** A voice note or podcast describing a build becomes a BOM. Impact rated 2/5 in
the feature list.

**Infrastructure.** A multipart upload endpoint, which is a new public surface: size cap, MIME
sniffing, no storage (bytes go straight to Gemini). No bucket and no secret. Check Gemini's current
inline request size limit, or use the Files API for longer audio.

**Cost.** Audio input $2.00/M tokens (≈ $0.003/min) and text output $12.00/M (≈ $0.002/min). A free
tier is available. A 10-minute note costs ≈ $0.05 plus the normal extraction call.

**Implementation.** Transcribe, then feed the transcript to the page-text extractor with quote
checks against the transcript (the same mechanism as page quotes, with timestamps from the
transcript).

**Risks.** Upload abuse, personal voice data (privacy and retention), low demand.

**Effort.** 1.5 d backend + 0.5 d recorder UI. **Recommendation: after submission.**

---

## 12. S9 public BOM library + votes

**What it adds.** A gallery of finished BOMs on the start screen, deduplicated by video, with
"substitution worked" votes feeding ranking.

**Infrastructure.** A new public collection, e.g. `public_boms`, and a **composite index** (for
example `status ASC, votes DESC, published_at DESC`) for the listing. A votes subcollection with one
vote per account. Firestore rules stay locked because all access is backend-only. A public
unauthenticated listing route is a new public surface.

**Cost.** ≈ $0 at demo scale (free 50k reads / 20k writes per day).

**Privacy and moderation.** Job snapshots hold chat messages, owner ids and editable AI-written
titles. Publishing must be **opt-in** and copy only a sanitised projection (title, parts, chosen
offers with timestamps, no chat). User-edited titles and descriptions need a moderation step (a
Gemini classifier plus a report button), and votes need per-account limits (guests cannot vote).

**Overlap.** The share-link stream already gives judges a read-only link to a specific BOM. Seeded
demo BOMs can be pre-warmed without a public library.

**Effort.** 3 d backend + 1.5 d frontend. **Recommendation: after submission.**

---

## 13. Ops: alert policy, max instances, min instances

**What it adds.** No feature. It protects the demo recording (15–16 Oct) and judging (19 Oct – 6
Nov), when judges open the live URL at arbitrary times.

| Change | Command (owner runs; the agent's service account is read-only) | Cost |
| --- | --- | --- |
| **Log-based alert** on stuck work. One policy with condition filter `resource.type="cloud_run_revision" AND resource.labels.service_name="bharat-sourcer-integration" AND (textPayload:"QUEUE_AGE_EXCEEDED" OR textPayload:"SWEEP_TRUNCATED")`, notification rate limit 1 per hour (the sweep repeats every 5 min), auto-close 1 h, email channel to the owner | `gcloud alpha monitoring policies create --policy-from-file=queue-age-alert.json` (policy JSON to be added under `backend/infra/` on approval). Needs Monitoring AlertPolicy and NotificationChannel editor rights (owner) | Alerting charges began no sooner than 1 May 2026: **$0.10 per condition per month** (log-match pricing: verify) |
| **Max instances 1 → 3** on the API. Leases and Firestore transactions are already multi-instance safe; spend stays bounded by the existing daily quotas (`global_daily_actions=1000`) | `gcloud run services update bharat-sourcer-integration --region asia-south1 --max-instances=3`. Check the Cloud Tasks queue `maxConcurrentDispatches` too. The deploy workflow keeps scaling settings | Pay per use only |
| **Min instances 1** on API **and** web, 15 Oct – 6 Nov, then back to 0 | `gcloud run services update bharat-sourcer-integration --min-instances=1` (same for `bharat-sourcer-web`) | Request-based Tier 1 idle rate: $0.0000025/vCPU-s + $0.0000025/GiB-s. 1 vCPU / 512 MiB ≈ **$0.32/day per service** → ≈ $0.65/day for both, **≈ $15 for 23 days** (web sizing assumed equal; check) |

**Risks.** Forgetting to set min instances back to 0 after 6 Nov costs ≈ $20/month, so put a
calendar reminder in the runbook. More instances increase concurrent Gemini spend within the
quotas.

**Effort.** 0.25 d. **Recommendation: now (rank 1).** Alert and max instances now; min instances
from 15 Oct.

---

## 14. Could list (C1–C9)

| # | Idea | Decision |
| --- | --- | --- |
| C1 | One-tap buy (UPI Reserve Pay, UCP checkout, AP2) | Not before submission; payments and regulation, and sellers' `agents.md` forbid automated checkout |
| C2 | ONDC / Beckn discovery | Not before submission; buyer-app onboarding and certification |
| C3 | Live voice build buddy | Not before submission; unpublished pricing, risky demo |
| C4 | WhatsApp channel | Not before submission; Meta business verification time |
| C5 | Gemma on-device parts scan | Not before submission; Android build effort |
| C6 | Price-drop watch (Scheduler + Flex) | Not before submission; new scheduler job |
| C7 | Public substitution dataset | Not before submission; needs curation over time |
| C8 | ATL lab-kit mode | Not before submission; needs bulk pricing data |
| C9 | Other countries | Not before submission; seller adapters per country |
| C9b | Nightly discovery scan + "add a shop" | Not before submission; new Scheduler + Cloud Run job |

---

## 15. Optional headless renderer for sellers that render prices client-side (proposal only)

**Problem.** Seller catalogue search (`sourcing/seller_search.py`, see
[seller search](docs/contracts/seller-search.md)) finds product URLs, and the verifier reads
prices from server-rendered JSON-LD or the public Shopify/WooCommerce product JSON. A seller
whose product page builds the price in the browser (a JavaScript storefront with no JSON-LD
and no public product JSON) yields "no supported offer" even when robots.txt allows the page.

**Evidence today (7 Oct 2026).** The live check (`scripts/check_seller_search.py`, five parts,
seven enabled sellers) fetched 40 seller-search candidates; 37 had an extractable INR offer
without any rendering. All seven enabled sellers are Shopify or WooCommerce. No enabled seller
needs a renderer yet, so this stays a proposal until one does.

**What it would add.** A separate private Cloud Run service (`bharat-sourcer-render`) running
Playwright with Chromium, called by the API only for sellers whose registry entry has
`"render": true`. It returns the rendered HTML (or only the Product JSON-LD it finds); the
existing verifier then reads it, so the INR/title/variant rules do not change.

**Rules (non-negotiable).**
- Only for hosts in `known_sellers.json` with `render: true`, after a dated robots.txt review
  that allows the product path for `*`; robots.txt is checked again before every render.
- **Never for challenge pages.** If the plain fetch saw a bot-protection challenge
  (`blocked_by_bot_protection`: Cloudflare, captcha, Akamai, PerimeterX, DataDome), the
  renderer is not called. If the rendered page itself shows a challenge, the result is
  discarded and the host is marked blocked. No stealth plugins, fingerprint spoofing,
  user-agent or proxy rotation, or captcha solving; the user agent stays `BharatSourcer/…`.
- Same politeness as the fetcher: per-host concurrency 1, ≥ 2 s between renders, cached
  rendered result (≤ 1 h), images/fonts/media blocked, 15 s page deadline, 3 MB cap.
- Never logs in, never adds to cart, never checks out.

**Size and cost (estimates; verify before approval).**

| Item | Estimate |
| --- | --- |
| Image | Playwright Python base with Chromium only ≈ 1.2–1.6 GB (Microsoft's full image with all browsers is ≈ 2 GB) |
| Instance | 1 vCPU / 2 GiB, concurrency 2, min instances 0, max 2, request timeout 30 s |
| Per render | ≈ 3–6 s at 1 vCPU / 2 GiB: Cloud Run request-based Tier 1 (≈ $0.000024/vCPU-s + $0.0000025/GiB-s) ≈ **$0.0001–0.0002 per render, ≈ $0.15–0.30 per 1,000 renders**, mostly inside the free tier at demo scale |
| Cold start | ≈ 5–10 s with Chromium; acceptable because renders are only a fallback |
| New infra / IAM | One Cloud Run service, one service account, `run.invoker` grant for the API identity; no secrets |

**Effort.** 2–3 d (service, client in `sourcing/`, registry flag, offline tests with
recorded rendered HTML, contract update).

**Recommendation.** Not now. Re-evaluate when a robots-allowed seller that matters is found
to render prices client-side; approval needed because it is a new service (rule 3).

---

## Sources (read 6 Oct 2026 unless noted)

- Gemini API pricing (page updated 2026-10-06): embedding-2, 3.5 Transcribe, Maps grounding, Computer Use, 3.8 Flash. <https://ai.google.dev/gemini-api/docs/pricing>
- Maps grounding availability and attribution: <https://ai.google.dev/gemini-api/docs/maps-grounding>
- Computer Use (preview, safety, sandboxing): <https://ai.google.dev/gemini-api/docs/computer-use>
- Web Risk pricing: <https://cloud.google.com/web-risk/pricing>
- Cloud Run pricing (Tier 1 request-based, idle and free tier figures via search summary of the official page; verify in the console): <https://cloud.google.com/run/pricing>
- Cloud Run pricing tiers by region (asia-south1 = Tier 1): <https://docs.cloud.google.com/run/docs/locations>
- Hosting MCP servers on Cloud Run: <https://docs.cloud.google.com/run/docs/host-mcp-servers>
- Cloud Monitoring alerting pricing: <https://cloud.google.com/monitoring/pricing>, <https://cloud.google.com/monitoring/alerts/cost-control>
- Firestore vector search billing: <https://firebase.google.com/docs/firestore/pricing>
- YouTube Data API quota costs: <https://developers.google.com/youtube/v3/determine_quota_cost>
- Shopify Global Catalog MCP: <https://shopify.dev/docs/agents/catalog/global-catalog>
- DigiKey locale headers (INR): <https://developer.digikey.com/faq/api-response-unexpected-response-and-error-codes>
- Mouser Search API and terms: <https://www.mouser.com/api-search/>, <https://www.mouser.in/apiterms/> (terms page timed out on 6 Oct; limits from `docs/04-reference/02-india-sellers-and-apis.md`, 30 Sep 2026)
- element14 Product Search API: <https://partner.element14.com/docs>
- Amazon Creators API and Flipkart Affiliate API: see `docs/04-reference/02-india-sellers-and-apis.md` (30 Sep 2026)
- Wokwi CI limits and pricing: <https://docs.wokwi.com/wokwi-ci/getting-started>, <https://wokwi.com/pricing>
- A2UI v0.9: <https://developers.googleblog.com/en/a2ui-v0-9-generative-ui/>, <https://a2ui.org/roadmap/>
- arduino-cli + ESP32 image sizes (community images, 0.8–2.0 GB): <https://hub.docker.com/r/mircopergreffi/arduino-cli/tags>
- Cloud Run image streaming and cold starts: <https://cloud.google.com/blog/topics/developers-practitioners/a-guide-to-ai-cold-starts-on-cloud-run/>
