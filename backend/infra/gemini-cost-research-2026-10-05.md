> Copied from the research agent's report of 2026-10-05; see [the findings log](gemini-cost.md) for decisions and corrections. **Correction:** section 0 says `gemini-2.5-flash-image` was shut down on 2 October; on 5 October the model was still listed by the API (`models.list`). Treat the shutdown date as an announced retirement, not confirmed downtime.

# Gemini API cost reduction for Bharat Sourcer (researched 2026-10-05)

All Google docs below were fetched today as Markdown from ai.google.dev. The pricing page shows `last-modified: 2026-10-01`. Prices are paid-tier USD per 1M tokens.

## Call sites in the code today

| Call site | File | Model | Tools / config |
|---|---|---|---|
| Video and page extraction | `extraction.py:322` | `gemini-3.8-flash` | YouTube `fileData`, JSON schema, maxOutput 8192, no `mediaResolution`, no thinking setting |
| Seller discovery | `sourcing/service.py:105` | `gemini-3.8-flash` | `google_search`, maxOutput 2048 |
| Part research | `sourcing/research.py:320` | `gemini-3.8-flash` | JSON, 8192 |
| Chat scope classifier (one per message) | `conversation.py:81` | `gemini-3.8-flash` | JSON, 1024 |
| Chat reply | `conversation.py:197` | `gemini-3.8-flash` | JSON, 4096 |
| Image fallback | `images.py:136`, `config.py:14` | **`gemini-2.5-flash-image`** | TEXT and IMAGE output |

None of these set `thinkingConfig`. On `gemini-3.8-flash`, thinking defaults to **medium** and is billed as output ([thinking docs](https://ai.google.dev/gemini-api/docs/thinking)).

## 0. Urgent: the image model has been shut down

The pricing page says `gemini-2.5-flash-image` "is deprecated and will be shut down on **October 2, 2026**". It names `gemini-3.1-flash-image` or `gemini-3.1-flash-lite-image` as replacements ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). Today is Oct 5, so the default image model is probably failing in production now.

| Model | Price per image |
|---|---|
| `gemini-3.1-flash-lite-image` | $0.0336 per 1K image ($30/M output tokens, 1,120 tokens). Batch: $0.0168. Thinking defaults to minimal. Input $0.25/M. |
| `gemini-3.1-flash-image` | $0.045 per 0.5K image, $0.067 per 1K image |

Recommendation: switch the default to `gemini-3.1-flash-lite-image`. We downscale to 384 px anyway. Re-check the cache key (it includes the model, so the cache will miss once) and re-run the image tests. Risk: quality or style changes. The images remain labelled "visual only".

## 1. Current prices for our models

| Model | Input | Output (incl. thinking) | Cache read | Cache storage |
|---|---|---|---|---|
| `gemini-3.8-flash`, Standard | **$0.75 until 2026-12-31, then $1.50** | **$3.75, then $7.50** | $0.075, then $0.15 | $0.50/M/hr, then $1.00 |
| `gemini-3.8-flash`, Batch or Flex | $0.375 | $1.875 | $0.0375 | same |
| `gemini-3.5-flash-lite` | $0.30 | $2.50 | $0.03 | $1.00/M/hr |
| `gemini-3.1-flash-lite` | $0.25 | $1.50 | $0.025 | $1.00/M/hr |
| `gemini-2.5-flash-lite` | $0.10 | $0.40 | $0.01 | $1.00/M/hr |

Source: [pricing](https://ai.google.dev/gemini-api/docs/pricing).

**Budget note:** the 3.8 Flash promotional price **doubles on 2027-01-01**, so every per-job cost below doubles then unless something changes.

**Scope classifier.** It sends 5 messages plus part names (roughly 1–2K input tokens) and gets a tiny JSON back, but medium thinking can add hundreds of output tokens at $3.75/M. Two options:

- **Lowest risk:** keep 3.8 Flash and set `thinkingConfig.thinkingLevel: "low"`. Supported levels are low, medium and high; there is no minimal level on 3.8 Flash.
- **Cheapest:** move to `gemini-3.1-flash-lite` (about 3x cheaper input, 2.5x cheaper output) or `gemini-3.5-flash-lite` (thinking defaults to minimal). Expect roughly a 60–80% saving on this call.

Risk: the gate fails closed, so a weaker model means more false refusals. Measure it against a labelled set of in-scope and out-of-scope messages before switching.

**Thinking level elsewhere.** Setting `thinkingLevel: "low"` for discovery, and possibly research, cuts output tokens. Validate quality on the offline evaluation harness first.

## 2. Grounding with Google Search (discovery) is the likely biggest cost

Gemini 3 bills **per search query the model executes**: a prompt that issues 2 queries is billed twice, and empty queries are ignored ([Google Search grounding docs](https://ai.google.dev/gemini-api/docs/google-search), [pricing](https://ai.google.dev/gemini-api/docs/pricing)).

- The first 5,000 queries per month are free, shared across all Gemini 3.x models. After that it costs **$14 per 1,000 queries**.
- For comparison, Gemini 2.5 models bill per grounded prompt at $35 per 1,000 after 1,500 free requests per day.
- The pricing footnote says retrieved grounding context is not charged as input tokens. That statement appears in the image-model footnote.

Worked example: a 20-part BOM with about 2–3 queries per part is 40–60 queries, or **$0.56–0.84 per job** once the free tier is used up. That is far more than the token costs.

Savings:

1. Log `google_search_call.queries` and count them per part. Our `usage.py` already logs usage, so add the query count.
2. Prompt for one consolidated query per part, using known Indian seller domains.
3. For refreshes of **already-known offer URLs, skip search entirely** and re-fetch directly. This costs $0 in Gemini.
4. Cache discovery results per normalised part name for N days, across jobs.

Risk: fewer queries can lower recall. Stale cached URLs are harmless, because verification still re-fetches the page.

## 3. URL context tool

**What it is.** A `url_context` tool that reads up to **20 URLs per request, each up to 34 MB**. It handles HTML, JSON, XML, CSV, PDF and images. It cannot read paywalled or login pages, YouTube, Google Workspace files, or localhost and private networks ([URL context docs](https://ai.google.dev/gemini-api/docs/url-context)).

**How it fetches.** It retrieves "first … from an internal index cache", falling back to a live fetch. URLs that fail a safety check return `status: "unsafe"`. On Gemini 3 it can be combined with `google_search`.

**Billing.** There is no separate per-request fee. Retrieved content is counted as input tokens (`tool_use_input_tokens`; the docs example shows about 10K tokens for one page). That is about $0.0075 per page at the 3.8 Flash input price.

**Robots.txt.** The docs do not state how the tool handles robots.txt or Cloudflare-protected sites. I found nothing on this.

**Can it replace our page fetch and extraction?** No. Verification requires raw seller JSON-LD, and URL context returns only model-read text, possibly from a stale index copy. Our own `httpx` fetch costs nothing in Gemini tokens, while URL context adds input cost. It would also break the "JSON-LD only" verification guarantee.

**Can it replace grounded search?** Only when we already have the URL. It cannot discover pages.

**Where it might help:** reading a datasheet PDF or a spec page during part research as unverified evidence (about $0.0075 per page, versus $0.014 or more for search queries). Any such evidence must be labelled "AI-read, unverified".

## 4. Batch API and Flex tier

**Batch API.** Costs **50% of Standard**, with a target turnaround of **24 hours**. Jobs expire after 48 hours with no results. It accepts inline requests or JSONL files up to 2 GB, per-request `tools` (the docs example uses `google_search`), and per-request `cached_content` ([Batch docs](https://ai.google.dev/gemini-api/docs/batch-api)). Supported models are listed per model on the models page.

**Flex tier.** Also **50% off**, with a latency target of **1–15 minutes**. It is best-effort: requests can be shed and return 429 or 503, and the docs recommend client timeouts of at least 600 s ([Flex docs](https://ai.google.dev/gemini-api/docs/flex-inference)). 3.8 Flash Flex costs $0.375 in and $1.875 out. The Flex pricing table has no grounding row, so whether search works under Flex is unconfirmed. Test it.

Fit for our call sites:

| Call site | Batch | Flex |
|---|---|---|
| Interactive extraction, chat, scope check | No: 24 h turnaround | No: minutes of latency |
| Seller research and refresh | Only for scheduled overnight re-verification (a future feature) | **Yes.** Cloud Tasks already runs these in the background and retries; raise its timeout above 600 s. |
| Offline evaluation (`scripts/evaluate_extraction.py`) and bulk research | **Yes** | Yes |

Estimated saving: 50% of the token cost on sourcing and research. Grounding query fees are per query and are probably not discounted, so this needs confirming.

Risks: slower UX on sourcing progress, 429 storms (fall back to Standard after N sheds), and more lease and timeout tuning.

## 5. Context caching

**Implicit caching.** On by default for 2.5 and newer models, with no guaranteed saving. Minimum prefix is **4,096 tokens for Gemini 3.x Flash** (2,048 for 2.5). Put large, stable content first and send similar prefixes close together in time. Hits appear in `usage.total_cached_tokens` ([caching docs](https://ai.google.dev/gemini-api/docs/caching)).

**Explicit caching** ([explicit caching docs](https://ai.google.dev/gemini-api/docs/generate-content/caching)):

- It is in beta (v1beta) and only works with `generateContent`, not the Interactions API.
- TTL defaults to 1 hour, with no minimum or maximum.
- Billing is a reduced cache-read rate plus storage. For 3.8 Flash that is $0.075/M per read (90% off input) plus $0.50/M per hour of storage.
- Cached content is a prefix of the prompt, and batch requests can reference a cache.

**Video.** The docs' video caching examples use **Files API uploads**. They do not show caching a **YouTube `fileData` URI**. YouTube input itself "is in preview and is available at no charge. Pricing and rate limits are likely to change." The paid tier has no length limit; the free tier allows 8 hours per day ([video docs](https://ai.google.dev/gemini-api/docs/video-understanding)).

Reusing the video across extraction and chat is not supported by the docs. Our chat deliberately uses saved data only ("does not watch new video"), so there is nothing video-related to cache in chat today.

Where caching does apply:

1. Chat reply and research prompts. Order them as system prompt, then a stable job snapshot (BOM, evidence, report), then the new message, so implicit caching hits past 4,096 tokens. This is free to try.
2. Explicit caching is only worth it for a large per-job snapshot reused across many turns within the hour. At $0.50/M/hr, a 20K-token snapshot costs $0.01 per hour of storage, against savings of about $0.0135 per turn. It breaks even at about one turn per hour, so it is marginal. Prefer implicit caching.

Risk: prefix reordering can change model behaviour slightly.

## 6. Video tokens and resolution (extraction)

- **Static mode (default)** samples at 1 FPS. On Gemini 3, the default media resolution gives about **70 tokens per frame**; `high` gives 280. Audio is 25 tokens per second ([media resolution docs](https://ai.google.dev/gemini-api/docs/media-resolution)). The video docs give an older total of about 100 tokens/s at low resolution and about 300 tokens/s at high.
- A 10-minute video is roughly 57–60K input tokens, or about **$0.045** at $0.75/M.
- Setting `fps: 0.5` halves the frame tokens.
- **Agentic video mode** (3.8 Flash and 3.5 Flash-Lite) uses "up to 88% fewer" tokens on long-form video and gives about 7% better quality. It may add time-to-first-token on clips under 5 minutes. Its navigation tokens are billed as thinking (output) tokens, which cost 5x input.

Recommendation: leave resolution at the default or low. Use `high` only when the BOM needs on-screen part markings to be read via OCR. Then A/B test agentic mode on videos over 15 minutes using the extraction evaluation harness. The saving is modest per job, because video input is already cheap next to grounding.

## Ranked actions (saving vs effort)

| # | Action | Estimated saving | Effort |
|---|---|---|---|
| 1 | Replace the image model, which is shut down, with `gemini-3.1-flash-lite-image` | Restores the feature; $0.034 per image | S |
| 2 | Count grounding queries; skip search on known-URL refresh; cap queries per part; cache discovery per part name | Likely the largest $ saving, at $14 per 1K queries | S–M |
| 3 | Set `thinkingLevel: low` on the scope check and discovery; trial Flash-Lite for the scope check | 30–80% on those calls | S |
| 4 | Flex tier for Cloud-Tasks-driven research and refresh | 50% of tokens | M |
| 5 | Stable-prefix prompt ordering for implicit caching | Up to 90% on repeated input | S |
| 6 | Batch API for offline evaluation and future nightly re-verification | 50% | M |
| 7 | Agentic video and fps tuning for long videos | Up to 88% on long-video input | S (A/B) |
| 8 | Plan for the 2027-01-01 price doubling on 3.8 Flash | Budget | — |

**General risks.** Preview features (YouTube input, explicit caching beta, agentic video) may change price or behaviour. Model-read content, whether from URL context or LLM output, must never become verified price, stock or spec data. Any demo or fixture runs used to measure savings must be labelled as such.
