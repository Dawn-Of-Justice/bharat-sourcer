# Gemini cost: call sites, measurements and findings

Running log for reducing Gemini spend. Add a dated entry for every finding, measurement or
decision; never delete history, mark superseded entries instead. Prices change: always
record the source URL and the date you read it.

## Call sites (as of v0.19.3)

| Site (`GEMINI_USAGE` `site`) | Code | Calls per job | Input | Tools |
| --- | --- | --- | --- | --- |
| `extraction_video` | `extraction.py` `_extract_video` | 1 | YouTube video (`fileData`) + prompt | none |
| `extraction_project_page` | `extraction.py` `_extract_page` | 1 | up to `BS_PROJECT_PAGE_CHARS` (60k) chars of page text | none |
| `discovery` | `sourcing/service.py` `GeminiDiscovery` | 1 per sourced part, +1 for an alternative search | short part query | `google_search` grounding |
| `research` | `sourcing/research.py` | 1 per sourced part (2 with follow-up) | fetched page text, up to 16 sources | none |
| `judge` | `sourcing/judge.py` `GeminiJudge` (unreleased) | ≤ 1 per sourced part with unsettled candidates (≤ 2 with seller search) | spec + ≤ 8 compact listings | none |
| `chat_scope` | `conversation.py` `in_scope` | 1 per chat message | last messages + project context | none |
| `chat_reply` | `conversation.py` `reply` | 1 per allowed chat message | saved job context (items, report, 12 messages) | none |
| `image` | `images.py` | 0 unless generation enabled (≤10/owner/day) | short prompt | image output |
| `explain_translate` | `gemini_extras.py` `_speak` | 0 unless `BS_EXPLAIN_ENABLED`; 1 per uncached non-English explanation | ≤ 900-char script | none |
| `explain_tts` | `gemini_extras.py` `_speak` | 0 unless `BS_EXPLAIN_ENABLED`; 1 per uncached explanation | transcript | audio output (`BS_TTS_MODEL`) |
| `clip_zoom` | `gemini_extras.py` `zoom` | 0 unless `BS_ZOOM_ENABLED`; 1 per user click | 15 s YouTube clip, 2 fps, high resolution | none |
| `parts_scan` | `gemini_extras.py` `scan` | 0 unless `BS_SCAN_ENABLED`; 1 per uploaded photo | ≤ 1536 px JPEG + BOM names | none |
| `markets` | `markets.py` `nearby_markets` | 0–1 per user lookup (cached 7 days per rounded location + category set; ≤ `BS_MARKETS_DAILY_LIMIT` per owner per day) | short prompt with part categories + lat/lng | `googleMaps` grounding |

A 10-part live job is roughly 1 extraction + 10 discovery + 10–20 research calls
(21–31 calls), plus 2 per chat message. All text calls use `BS_GEMINI_MODEL`
(default `gemini-3.8-flash`).

## Measuring

Since v0.19.2 every call logs one line (`search_queries` since v0.19.3):

```text
GEMINI_USAGE {"site": "research", "model": "...", "prompt": 5123, "output": 410,
"thoughts": 96, "cached": 0, "tool_prompt": 0, "total": 5629, "grounded": false,
"search_queries": 0, "by_modality": {"TEXT": 5123}}
```

`python scripts/usage_report.py --days 7` (from `backend/`, with Cloud Logging read
access) prints calls, grounded calls, average input/output/thinking tokens and cached
share per site. Multiply by current prices to get cost; record results below.

## Findings log

### 2026-10-05: baseline audit (no measurements yet)

- Token usage was not recorded anywhere; `usageMetadata` was discarded. Fixed in
  v0.19.2 (`usage.py`). Decision: measure for a few days of real traffic before
  changing models or prompts.
- Likely largest costs, to confirm with measurements: `research` (large page-text
  input on every sourced part), `discovery` (one grounded search request per part),
  `extraction_video` (video tokens scale with duration).
- `chat_scope` is a yes/no classifier using the same model as replies: a candidate for
  a cheaper model if quality holds.
- Research findings: see the entries below.

### 2026-10-05: research on prices, URL context, Batch/Flex and caching

Full report with per-claim sources: [gemini-cost-research-2026-10-05.md](gemini-cost-research-2026-10-05.md).
Sources: [pricing](https://ai.google.dev/gemini-api/docs/pricing) (page last modified
2026-10-01), [Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search),
[URL context](https://ai.google.dev/gemini-api/docs/url-context),
[Batch API](https://ai.google.dev/gemini-api/docs/batch-api),
[Flex](https://ai.google.dev/gemini-api/docs/flex-inference),
[caching](https://ai.google.dev/gemini-api/docs/caching),
[explicit caching](https://ai.google.dev/gemini-api/docs/generate-content/caching),
[thinking](https://ai.google.dev/gemini-api/docs/thinking),
[media resolution](https://ai.google.dev/gemini-api/docs/media-resolution),
[video understanding](https://ai.google.dev/gemini-api/docs/video-understanding).

1. **Prices (`gemini-3.8-flash`, per 1M tokens):** input $0.75 and output (thinking included)
   $3.75 until 2026-12-31, then **$1.50 / $7.50 from 2027-01-01** (doubles). Cached input
   $0.075 (then $0.15); cache storage $0.50/M/hour. Batch and Flex: 50% off. Cheaper models:
   `gemini-3.1-flash-lite` $0.25/$1.50, `gemini-3.5-flash-lite` $0.30/$2.50,
   `gemini-2.5-flash-lite` $0.10/$0.40.
   *Action:* budget for the 2027 doubling.
2. **Thinking:** none of our calls set `thinkingConfig`; 3.8 Flash defaults to *medium*,
   billed as output. Levels available: low/medium/high (no minimal).
   *Action (pending A/B):* `thinkingLevel: low` for `chat_scope` and `discovery`.
3. **Search grounding (likely largest cost):** Gemini 3 bills **per executed search query**,
   5,000 free/month (shared across 3.x), then **$14 per 1,000**. A 20-part BOM at 2–3 queries
   per part is ~$0.56–0.84 per job after the free tier.
   *Done:* v0.19.3 logs `search_queries` per call. *Pending:* skip search when refreshing
   already-known offer URLs; ask for one consolidated query per part; cache discovery
   results per normalised part name for N days (verification still re-fetches pages).
4. **URL context tool:** up to 20 URLs/request, 34 MB each; content billed as input tokens
   (~$0.0075 per page); no per-request fee; reads from Google's index cache first; robots
   and Cloudflare behaviour undocumented; cannot read YouTube or private pages.
   *Decision:* do **not** replace our own fetch: offers must be verified from raw seller
   JSON-LD, which URL context does not return, and our fetch costs no tokens. Possible use:
   reading datasheets during research, labelled "AI-read, unverified".
5. **Batch API:** 50% off, 24 h target, expires at 48 h; supports `google_search` and cached
   content per request. *Fit:* offline extraction evaluation and future nightly
   re-verification only (not interactive work).
6. **Flex tier:** 50% off, 1–15 min latency target, requests may be shed (429/503), timeouts
   ≥ 600 s. *Fit:* Cloud-Tasks research/refresh. *Unknown:* whether grounding works on Flex
   and whether query fees are discounted; test before adopting.
7. **Context caching:** implicit caching is automatic above **4,096** prompt tokens on 3.x
   Flash (no guarantee); explicit caching is beta, default TTL 1 h. Explicit caching of a
   per-job chat snapshot only breaks even at about one turn per hour. YouTube `fileData`
   caching is not documented, so video cannot be reused between extraction and chat.
   *Action (pending):* order chat/research prompts as stable instructions → stable job
   snapshot → new message, to benefit from implicit caching.
8. **Video tokens:** ~70 tokens/frame at 1 FPS default resolution (280 at high) + 25/s
   audio; a 10-minute video ≈ $0.045. `fps: 0.5` halves frame tokens. Agentic video mode
   claims "up to 88% fewer" tokens on long videos but bills navigation as thinking.
   YouTube input is a free preview whose pricing may change.
   *Action (pending):* A/B fps and agentic mode with the evaluation harness.
9. **Image model:** the pricing page lists `gemini-2.5-flash-image` as deprecated with a
   2026-10-02 shutdown; on 2026-10-05 `models.list` still returned it. Generation is
   disabled in production (`BS_IMAGE_GENERATION_ENABLED=false`).
   *Done:* v0.19.3 defaults to `gemini-3.1-flash-lite-image` (~$0.034 per 1K image).
   Untested live; enable generation only after one check.

### 2026-10-06: new opt-in call sites (explain aloud, clip zoom, parts-bin scan)

Added in `gemini_extras.py`, all **off by default** with per-owner daily quotas
(`BS_EXPLAIN_DAILY_LIMIT` 10, `BS_ZOOM_DAILY_LIMIT` 10, `BS_SCAN_DAILY_LIMIT` 5) and a
per-feature global cap (`BS_EXTRAS_GLOBAL_DAILY_LIMIT` 200). Contract and frontend needs:
[gemini-extras.md](../../docs/contracts/gemini-extras.md). No live call was made; these
are **estimates** from the 2026-10-05 prices above, to be replaced by
`usage_report.py` numbers:

- `clip_zoom`: 15 s × 2 fps × 280 tokens/frame (high resolution, per the media
  resolution docs) ≈ 8.4K + ~0.4K audio input, ~0.7K output incl. thinking ≈ **$0.009**
  per call (doubles in 2027). `fps: 1` would halve the frame tokens; keep 2 until a
  harness shows markings read as well at 1.
- `parts_scan`: one ≤ 1536 px image (~1–1.5K tokens) + BOM names, 1–2K output ≈
  **$0.006–0.009**.
- `explain_translate`: ~0.5K in, 1–1.5K out ≈ **$0.005**, only for non-English.
- `explain_tts`: `gemini-3.8-flash-tts` pricing is **not verified** (the architecture
  docs mark it "⚠️ verify"; it is not in the 2026-10-05 research). At earlier Flash TTS
  list prices ($0.50 in / $10 out per 1M, ~25 audio tokens/s) a 60 s explanation is
  ~$0.015. Check [pricing](https://ai.google.dev/gemini-api/docs/pricing) before enabling.
- Explanations are cached per script and language, so repeats cost $0.
- Worst case per owner per day at default quotas ≈ $0.34.

### 2026-10-07: spec judge and buyable specs (branch `mvp/matching`, unreleased)

Estimates only (no live call made), at the 2026-10-05 prices above:

- **Buyable spec:** folded into the existing extraction call (`extraction_video` /
  `extraction_project_page`), so **no new call**. Adds a `buyable` block per part, roughly
  100–150 output tokens each: a 20-part BOM ≈ 2–3K extra output tokens on
  `gemini-3.8-flash` ≈ **$0.008–0.011 per job** (doubles in 2027). `maxOutputTokens` for
  extraction went from 8192 to 12288 so long BOMs are not truncated (only used tokens bill).
- **New site `judge`** (`sourcing/judge.py`): one call per BOM line **only** when some
  candidate is neither a deterministic exact hit nor cached; seller search may call it a
  second time for new grounded candidates. Model `BS_JUDGE_MODEL` (default
  `gemini-3.1-flash-lite`, $0.25 in / $1.50 out per 1M), `thinkingLevel: low`.
  Input ≈ 0.6K prompt + 0.3K spec/project + ~0.4K per candidate (title, ≤12 spec rows,
  300-char description, 800-char snippet, variants) → 2–4K tokens for 4–8 candidates;
  output ≈ 0.1–0.15K per verdict + low thinking ≈ 0.6–1.2K. ≈ **$0.0015–0.003 per call**,
  so ≤ $0.006 per line and ≈ $0.02–0.05 for a 10-line job before cache hits. Verdicts are
  cached per (spec hash, URL, listing hash) for 7 days, so refreshes of unchanged pages
  cost nothing.
- Untested: whether `thinkingLevel` is accepted by `gemini-3.1-flash-lite`. If it is
  rejected the judge fails safe to the title check (offers keep `match: null`); drop the
  thinking setting for that site. Make one live smoke call (with the owner's approval)
  before release.

**Next measurement:** after a few days of traffic on v0.19.3, run
`scripts/usage_report.py` and record per-site token and query averages here before
changing thinking levels, models or tiers.

### 2026-10-07: cost controls (cache, research rules, refresh, budget, accounting)

Branch `mvp/cost`; contract: [cost-controls.md](../../docs/contracts/cost-controls.md).
No live call was made. Prices are the 2026-10-05 entry above
([pricing](https://ai.google.dev/gemini-api/docs/pricing), page last modified 2026-10-01);
they are now a dated table in `config.py` (`GEMINI_PRICES`, switching to the 2027 prices on
2027-01-01) and every `GEMINI_USAGE` line carries `usd_est`, `job_id` and `line_id`.

Done:

- **Shared cross-job cache** (`sourcing/cache.py`): namespaces `discovery` (7 d), `judge`
  (7 d), `page` (8 h), `seller_search` (6 h), `research` (7 d); memory or Firestore
  `<collection>_cache`. Part names are normalised so `33kΩ`/`33K` share entries. Hits log
  `GEMINI_CACHE_HIT` and `usage_report.py` estimates the saving per namespace.
- **Research:** skipped when a verified in-stock compatible offer exists; total document
  text capped at 24,000 chars (was up to 3 × 12,000 = 36,000); quote-checked evidence
  reused from the cache; follow-up search only with no offer and no candidate; stable
  prefix order (instructions → project context → part → documents).
- **Thinking:** `thinkingLevel: low` by default for `chat_scope`, `discovery`, `judge`,
  `spec` (`BS_GEMINI_SITE_THINKING`); per-site models via `BS_GEMINI_SITE_MODELS`.
  Research keeps medium until the evaluation harness shows low holds quality.
- **Refresh without rediscovery:** known offer URLs are re-fetched first; grounded search
  only when all are gone or out of stock.
- **Budget guard:** `BS_JOB_GEMINI_BUDGET_USD` (default $0.25) per sourcing run.
- **Accounting:** `job.cost_estimate` (total, current run, calls/USD by site, queries,
  cache hits); `usage_report.py` prints estimated USD per site, per job and cache savings
  (`--job` filters one job).

**Estimates per 6-line job** (`gemini-3.8-flash` 2026 prices; assumptions: discovery
≈ 600 input + 1,400 output/thinking tokens at medium, ≈ 600 at low, and 2.5 queries per
call, 2 with the consolidated query; research ≈ 13K input / 2K output before, ≈ 10.5K
input after the text cap; judge ≈ 3K / 0.3K at low thinking; spec 1 batched call ≈ 4K /
1K). These are not measurements; replace them with `usage_report.py` numbers.

| Pipeline | Gemini calls | Grounded queries | Est. USD |
| --- | --- | --- | --- |
| Before (real failed job): 6 discovery + 6 research + 3 follow-ups (discovery + research each) | ~18 | ~22 | ~$0.51 |
| Staged, cold cache: free seller search for all 6; 6 judge + 1 spec; paid discovery for ~2 lines; research for ~2 lines without a sufficient offer; ~1 follow-up | ~13 | ~6 | ~$0.17 |
| Staged, warm cache (same parts within 7 days): discovery and research hits; ~half the judge verdicts hit (page content changes) | ~4 | 0 | ~$0.02 |
| Refresh of one line whose known offer is still in stock and compatible | 0 | 0 | $0 (was ~$0.05) |

Breakdown before: discovery 6 × ($0.0057 tokens + 2.5 × $0.014) ≈ $0.24; research
6 × $0.017 ≈ $0.10; follow-ups 3 × ($0.040 + $0.017) ≈ $0.17. After (cold): judge
6 × $0.0034 ≈ $0.02; spec ≈ $0.007; discovery 2 × ($0.0027 + 2 × $0.014) ≈ $0.06;
research 2 × $0.0155 ≈ $0.03; one follow-up (discovery + research) ≈ $0.05. The budget guard caps any run at about
$0.25 plus the calls in flight. The free grounding tier (5,000 queries a month) would make
real bills lower than these figures while it lasts.

**Owner decisions pending:**

1. **Firestore TTL policy** on `expires_at` for the `<collection>_cache` collection
   (infra change, needs approval). Without it, expired cache documents are ignored on read
   but stay in storage. The existing `_usage` and `_audio` collections would benefit from
   the same policy.
2. Whether to A/B `thinkingLevel: low` for research and the Flex tier for Cloud-Tasks
   research (grounding on Flex is still unconfirmed).
3. The default budget ($0.25 per run): about 5 cold paid discoveries plus research.

### 2026-10-07: nearby markets via Google Maps grounding (branch `mvp/markets`, unreleased)

One live call (owner-approved) from Bengaluru (12.9716, 77.5946) on `gemini-3.8-flash` with
`tools: [{googleMaps: {}}]` and `toolConfig.retrievalConfig.latLng`: HTTP 200, `STOP`, 5 SP
Road shops, 8 grounding chunks (places plus review links), **1 grounding query and about
783 total tokens**. So Maps grounding works for India.

- **Pricing:** Maps grounding shares the paid tier's **5,000 grounded queries/month free
  pool with Search grounding**, then **$14 per 1,000 queries**
  ([pricing](https://ai.google.dev/gemini-api/docs/pricing), as read 2026-10-05). Every
  Maps lookup eats into the pool that sourcing discovery uses.
- **Per lookup:** ≈ 1 query ($0.014 after the free pool) + ~800 tokens (≈ $0.001–0.003 at
  2026 Flash prices) ≈ **$0.015**. The usage line logs `search_queries` ≥ 1 for a
  Maps-grounded answer (`record_usage(..., queries=)`), so `usd_est` is an upper bound while
  the free pool lasts.
- **Controls:** site `markets`, `thinkingLevel: low`; cached 7 days per rounded lat/lng
  (2 decimals) + category set across all jobs; quota `BS_MARKETS_DAILY_LIMIT` (5/owner/day)
  and `BS_MARKETS_GLOBAL_DAILY_LIMIT` (200/day); blocked when the job's run budget is
  reached; demo jobs make no call. Worst case at the global cap ≈ 200 × $0.015 ≈ **$3/day**
  (≈ 6,000 queries/month, more than the whole free pool: lower the global cap if sourcing
  needs the pool).
- Untested: whether `thinkingLevel: low` changes Maps answers (the live call used the
  default). Check with `usage_report.py` and a few real lookups.
