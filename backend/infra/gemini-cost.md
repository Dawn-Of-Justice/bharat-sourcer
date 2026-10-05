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
| `chat_scope` | `conversation.py` `in_scope` | 1 per chat message | last messages + project context | none |
| `chat_reply` | `conversation.py` `reply` | 1 per allowed chat message | saved job context (items, report, 12 messages) | none |
| `image` | `images.py` | 0 unless generation enabled (≤10/owner/day) | short prompt | image output |

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

**Next measurement:** after a few days of traffic on v0.19.3, run
`scripts/usage_report.py` and record per-site token and query averages here before
changing thinking levels, models or tiers.
