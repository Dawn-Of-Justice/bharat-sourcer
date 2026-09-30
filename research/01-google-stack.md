# 01 — Google AI + Cloud stack survey for "Bharat Sourcer"

*Researched 2026-09-30. Every fact below comes from a page opened during this research, and each one is linked. Where the source was a secondary site, where a fetched summary was ambiguous, or where something is my inference, it is marked **[UNCERTAIN]**, **[secondary]** or **[inference]**. Model names, prices and limits change very fast (Google shipped a new Flash roughly every month in 2026), so re-check the pricing and models pages on the day you lock the stack.*

---

## 0. TL;DR (read this first)

1. **The stack has changed a lot since 2025. What still says "Gemini 2.5 / Vertex AI" is now out of date.**
   - The current stable workhorse is **`gemini-3.8-flash`** (GA on 2026-09-02). It has 1,048,576 input tokens, 65,536 output tokens, thinking levels `low`/`medium`/`high`, and supports Search grounding, URL context, code execution, function calling, structured outputs, File Search and Maps grounding ([model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [changelog](https://ai.google.dev/gemini-api/docs/changelog)).
   - The cheap sub-agent model is **`gemini-3.5-flash-lite`**. The top reasoning model is still a preview: **`gemini-3.1-pro-preview`** ([models](https://ai.google.dev/gemini-api/docs/models)).
   - **Gemini 2.5 is now "legacy"**, with access limited to past active users since 2026-09-18. **Do not build on 2.5** ([changelog](https://ai.google.dev/gemini-api/docs/changelog)).
2. **Google now recommends the Interactions API (`client.interactions.create`)** as the way to call Gemini. `generateContent` is "fully supported" but legacy, and "all new models, multimodal capabilities, tools, and agentic features will launch on the Interactions API" ([Interactions](https://ai.google.dev/gemini-api/docs/interactions)).
3. **Vertex AI has been renamed.** Since 2026-04-22 it has become the **Gemini Enterprise Agent Platform** ("Agent Platform"). Agent Engine is now **Agent Runtime**, and it also includes Agent Sessions, Memory Bank, Agent Sandbox and Model Garden ([Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)). The ADK env var is now `GOOGLE_GENAI_USE_ENTERPRISE=True` ([ADK Cloud Run](https://adk.dev/deploy/cloud-run/)).
4. **ADK 2.x is GA and adds graph `Workflow`s** (deterministic code nodes mixed with LLM nodes). Docs moved to **adk.dev**. The latest Python release is v2.6.3 (2026-08-07) ([adk.dev](https://adk.dev/), [releases](https://github.com/google/adk-python/releases)).
5. **Killer feature for our step 1: "agentic video understanding"** (`"processing": "agentic"`). It launched 2026-09-01 on 3.8/3.7/3.6 Flash and 3.5 Flash-Lite. The model navigates the video timeline itself and loads only the parts it needs. Google claims it is "up to 88% more token-efficient" and "~7% higher quality on long-form content" ([video docs](https://ai.google.dev/gemini-api/docs/video-understanding)).
6. **There is no public Google Shopping Graph / offers API for third parties.** The Merchant API only covers a merchant's own data, and the Content API for Shopping shut down on 2026-08-18 ([Merchant API updates](https://developers.google.com/merchant/api/latest-updates?hl=en)). UCP and AP2 are checkout and payment protocols, not product search. **Product discovery has to come from Grounding with Google Search + URL context (or scraping / partner APIs).**
7. **Two gotchas can break the demo:**
   - **Search grounding is "Not available" on the Gemini API free tier.** You need billing (Tier 1) ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
   - **Firebase Hosting rewrites to Cloud Run have a hard 60-second timeout** ([Firebase serverless overview](https://firebase.google.cn/docs/hosting/serverless-overview?hl=en)). Call Cloud Run directly for long/SSE runs, or use an async job + Firestore listener pattern.
8. **Hackathon eligibility flag (not a stack issue, but important).** The official site says the AI Builder Cup is for the **JAPAC region**, **teams of 2–4**, **working professionals only, 21+** ([aibuildercup.com](https://aibuildercup.com/index.html), [Metropolis Japan listing](https://metropolisjapan.com/events/ai-builder-cup-2026/) [secondary]). Registration closes **Oct 11, 2026**, submissions are due Oct 18, and the finale is in Singapore on Dec 4. Confirm that you qualify (region/residency and team size) before investing heavily.

---

## 1. Model lineup (as of 2026-09-30)

Sources: [models](https://ai.google.dev/gemini-api/docs/models), [changelog](https://ai.google.dev/gemini-api/docs/changelog), [pricing](https://ai.google.dev/gemini-api/docs/pricing), individual model pages.

### 1.1 Gemini text/multimodal models

| Model ID | Status | Notes | Paid price / 1M tokens (in → out) |
|---|---|---|---|
| `gemini-3.8-flash` | **Stable, GA 2026-09-02** | 1,048,576 in / 65,536 out; text, image, video, audio, PDF in; thinking `low`/`medium`/`high` (default `medium`); Search, URL context, code exec, function calling, structured output, caching, batch, File Search, Maps. No Live API. ([page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)) | **$0.75 → $3.75 intro price through 2026-12-31**; $1.50 → $7.50 from 2027-01-01. Free tier: yes. |
| `gemini-3.7-flash` | Stable (GA 2026-08-13) | Same price as 3.8 | same |
| `gemini-3.6-flash` | Stable (GA 2026-07-21) | | same |
| `gemini-3.5-flash` | Stable (GA 2026-05-19) | thinking `minimal`/`low`/`medium`/`high` | $1.50 → $9.00 |
| `gemini-3.5-flash-lite` | Stable (GA 2026-07-21) | "optimized for high-throughput, low-cost execution for subagent tasks and document parsing"; 1M in / 65,536 out; Search, Maps, URL context, File Search, computer use (preview) ([page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)); thinking default `minimal` | $0.30 → $2.50 (one price for text/image/video/audio) |
| `gemini-3.1-flash-lite` | Stable (GA 2026-05-07) | cheapest | $0.25 (audio $0.50) → $1.50 |
| `gemini-3.1-pro-preview` | **Preview** | 1M in / 65,536 out; thinking `low`/`medium`/`high` (default `high`); File Search AI Studio only; variant `gemini-3.1-pro-preview-customtools` for tool/bash-heavy agents ([page](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview)) | $2.00 → $12.00 (≤200k ctx); **no free tier** |
| `gemini-3-flash-preview` | Preview (older) | | $0.50 → $3.00 |
| `gemini-2.5-*` | **Legacy**: access limited to past active users since 2026-09-18 | Avoid | — |

Other changelog items that affect us ([changelog](https://ai.google.dev/gemini-api/docs/changelog)):
- **2026-07-21: sampling parameters `temperature`, `top_p` and `top_k` were deprecated.** Remove them from ADK `generate_content_config` and use thinking levels and prompting instead. **[UNCERTAIN: check whether they error or are silently ignored]**
- 2026-01-08: file inputs can now come from GCS buckets and pre-signed URLs, and the inline/file size limit went from 20 MB to 100 MB.
- 2026-03-18: "Built-in Tools and Function Calling Combination" launched, so built-in tools can now be mixed with custom functions in one request.
- 2026-04-01: new Flex and Priority inference tiers.
- 2026-05-04: webhooks for Batch and long-running operations.

Aliases: `gemini-flash-latest` / `gemini-pro-latest` exist and are "hot-swapped with every new release", with 2 weeks' email notice for breaking changes ([models](https://ai.google.dev/gemini-api/docs/models)). **Pin explicit IDs for a judged demo.**

### 1.2 Specialized models

| Model ID | What it is | Relevance |
|---|---|---|
| `gemini-3.5-transcribe` / `gemini-3.5-transcribe-live` | STT, GA 2026-08-26. 85+ languages with auto-detect and code-switching, incl. Hindi, Bengali, Kannada, Malayalam, Marathi, Odia, Punjabi, Telugu; word timestamps; diarization up to 8 speakers; custom vocab up to 1,000 terms; 1 h per file (30 min with diarization/timestamps) ([page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe)) | "Upload audio" input path; $2.00 in → $12.00 out per 1M (~$0.003/min in) ([pricing](https://ai.google.dev/gemini-api/docs/pricing)) |
| `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview` | Real-time audio-to-audio | Optional voice demo ("ask the BOM") |
| `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | TTS, 130 / 101 languages | Hindi voice-over of the build summary |
| `gemini-3.5-live-translate-preview` | Live speech translation | Optional |
| `gemini-embedding-2` | **Multimodal embeddings**, GA 2026-04-22. Text (8,192 tokens), images (≤6/request), audio (≤180 s), video (≤120 s), PDF (1 file, ≤6 pages); 128–3,072 dims (MRL, auto-normalized) ([embeddings](https://ai.google.dev/gemini-api/docs/embeddings)) | Embed part photos + text into one space for "same part" matching |
| `gemini-embedding-001` | Text-only, 2,048 tokens, `task_type` param | fallback |
| `deep-research-preview-04-2026`, `deep-research-max-preview-04-2026` | Deep Research agents (Interactions API, `background=true`, runs for minutes; tools: Search, URL context, code exec, **MCP servers**, File Search) ([deep research](https://ai.google.dev/gemini-api/docs/deep-research)) | Possibly for an "extended sourcing report", but too slow for the interactive path |
| `antigravity-preview-09-2026` | Managed Agent (Linux sandbox with Python 3.12 / Node 22, code, files, web) ([agents](https://ai.google.dev/gemini-api/docs/agents.md.txt)) | Public preview; the `-05-2026` version shuts down 2026-10-05, a warning about preview churn |
| `gemini-2.5-computer-use-preview-10-2025`, plus the Computer Use tool on 3.x Flash (3.5 Flash since 2026-06-24) | Browser/desktop/Android control through screenshots | Fallback for seller sites that block fetching (risky, slow) |
| `gemini-3.1-flash-image` (Nano Banana 2), `gemini-3-pro-image` | Image generation/editing | Optional "wiring diagram with Indian-part substitutions" visual (no free tier) |

### 1.3 Gemma

- The **Gemma 4** family (launched 2026-04-02) comes in E2B and E4B (edge), 12B, 31B dense, and 26B A4B MoE sizes. Context is 128K (small) / 256K (medium). All models take text and image input; audio and video are native on E2B, E4B and 12B. Weights are open and allow commercial use ([Gemma docs](https://ai.google.dev/gemma/docs/core)).
- Specialized variants: Gemma 3n, DiffusionGemma, **FunctionGemma**, **EmbeddingGemma**, PaliGemma 1/2, RecurrentGemma, ShieldGemma 1/2 ([Gemma docs](https://ai.google.dev/gemma/docs/core)).
- **Through the Gemini API**, `gemma-4-31b-it` and `gemma-4-26b-a4b-it` support function calling, system instructions, image input, `thinking_level` and Google Search grounding ([Gemma on Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)). Pricing and limits were not shown there **[UNCERTAIN: check the AI Studio rate-limit page]**.
- **Self-hosting:** Cloud Run GPUs (L4 24 GB, or RTX PRO 6000 Blackwell 96 GB) can serve Gemma 4 ([Cloud Run GPU](https://docs.cloud.google.com/run/docs/configuring/services/gpu)). L4 costs about $0.0001867/s non-zonal ([Cloud Run pricing](https://cloud.google.com/run/pricing)).
  - For the hackathon, the main reason to self-host would be an "innovation" point: a private on-prem/offline compatibility checker, or a Gemma sub-agent for cheap spec normalization.
  - **[inference]** That is not necessary to satisfy the rules, which accept "Gemini or Gemma".

### 1.4 Model → pipeline step mapping (recommendation)

| Pipeline step | Model | Why |
|---|---|---|
| A. Ingest YouTube video → raw BOM with timestamps and on-screen parts | `gemini-3.8-flash` with `processing: "agentic"` for videos longer than a few minutes; static mode with `fps` 1–2 and **high** media resolution for short close-up clips | Agentic mode is limited to the 3.5-Flash-Lite and 3.6/3.7/3.8 Flash lines; high res helps read chip markings |
| A'. Blog / Instructables URL | `gemini-3.8-flash` + `url_context` tool | Handles HTML + PDF + images up to 20 URLs |
| A''. Uploaded audio | `gemini-3.8-flash` directly (32 tok/s), or `gemini-3.5-transcribe` for timestamped transcripts | |
| B. Normalize / derive specs per part (voltage, interface, footprint, library) | `gemini-3.5-flash-lite` (parallel fan-out), structured output | Cheap, fast, `minimal` thinking |
| C. Search Indian sellers per part | `gemini-3.8-flash` + `google_search` + `url_context` (+ custom function tools for any seller API/scraper) | Per-query grounding billing; combining tools is now allowed |
| D. Compatibility judge (pinout, logic level, library/code changes) | `gemini-3.1-pro-preview` (thinking `high`) or `gemini-3.8-flash` at `high` | Hardest reasoning; Pro has no free tier |
| E. Report / INR BOM / Hindi summary | `gemini-3.8-flash` (+ TTS optional) | |
| F. Part-photo similarity cache | `gemini-embedding-2` + Firestore vector search | Multimodal |

---

## 2. Gemini API features in detail

### 2.1 Interactions API (the new default)

Source: [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions).

- `client.interactions.create(model=..., input=..., tools=..., response_format=..., generation_config=..., previous_interaction_id=..., background=..., store=..., stream=...)`
- **Stateful** mode chains turns with `previous_interaction_id`. `tools`, `system_instruction` and `generation_config` must be **re-sent every turn**.
- `background=true` is for long tasks; it is required by Deep Research.
- **Retention:** paid 55 days (configurable to 7/14/28/55), free 1 day. `store=false` disables storage, but then you cannot use `previous_interaction_id` or background.
- Tools exposed: Google Search, Google Maps, code execution, URL context, computer use, File Search.
- **Gotcha:** "Explicit caching ... is not supported in the Interactions API". Only implicit caching is available there ([caching](https://ai.google.dev/gemini-api/docs/caching)).
- **[UNCERTAIN / inference]** ADK (via `google-genai`) may still call `generateContent` under the hood. New-only features (e.g. `processing: "agentic"` video) may therefore need a direct `client.interactions.create` call wrapped in an ADK function tool / function node. Test this in the first hour.

### 2.2 Video understanding

Source: [video-understanding](https://ai.google.dev/gemini-api/docs/video-understanding).

```python
from google import genai
client = genai.Client()
it = client.interactions.create(
    model="gemini-3.8-flash",
    input=[
        {"type": "text", "text": "List every electronic part visible or mentioned ..."},
        {"type": "video", "uri": "https://www.youtube.com/watch?v=XXXX",
         "processing": "agentic"}          # or static mode with fps / offsets
    ],
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": Bom.model_json_schema()},
)
```

- **YouTube URLs:** public videos only (not private or unlisted). The **free tier is capped at 8 hours of YouTube video per day**; the paid tier has no length limit. Up to 10 videos per request (2.5+).
- **Formats:** mp4, mpeg, mov, avi, x-flv, mpg, webm, wmv, 3gpp. Files API up to 20 GB (paid) / 2 GB (free); inline under 100 MB.
- **Max length:** about 3 h at low resolution with 1M context, or about 1 h at high resolution.
- **Tokens (static mode):**
  - about **100 tokens/s at default (low)** media resolution and about **300 tokens/s at high**
  - frames cost 66 tokens (low) or 258 tokens (high); audio costs 32 tokens/s
- **Sampling:** the default is **1 fps**. Set a custom `fps` in the processing config (e.g. `0.5`). Clipping uses `start_offset` / `end_offset`. Timestamps in prompts use `MM:SS`.
- **Agentic mode** (`"processing": "agentic"`) works on `gemini-3.8-flash`, `3.7-flash`, `3.6-flash` and `3.5-flash-lite`. "The model dynamically navigates the video timeline, loading only the content it needs". It is "Up to 88% more token-efficient" for long-form content and gives "~7% higher quality". Navigation reasoning is billed as thought tokens and loaded content as tool-use tokens.
- **Design tip [inference]:** use a two-pass approach.
  1. Run agentic mode over the whole video to get a timestamped part list plus "frames of interest".
  2. For ambiguous parts (e.g. an unlabeled breakout board), run a clipped static call (`start_offset`/`end_offset`, high resolution, higher fps) on just that 10–20 s window.
  - Showing "we zoomed into 03:12–03:25 to read the IC marking" is a great demo moment.

### 2.3 Image understanding, detection, segmentation

Source: [image-understanding](https://ai.google.dev/gemini-api/docs/image-understanding).

- Bounding boxes come back as `box_2d: [ymin, xmin, ymax, xmax]`, **normalized to 0–1000**. Rescale them to pixel size.
- Segmentation returns `mask` as a polygon of `[x, y]` points (0–1000) plus `label`. For best results, set thinking to `minimal`.
- Tokens: 258 per image if both sides are ≤384 px; otherwise the image is tiled into 768×768 tiles at 258 tokens each. Up to 3,600 images per request. `media_resolution` controls tokens per image/frame.
- **Use:** draw boxes on keyframes from the video ("this blue board at 02:14 is an HC-05 Bluetooth module"). This is strong visual UX and evidence for judges.

### 2.4 Audio understanding

Source: [audio](https://ai.google.dev/gemini-api/docs/audio).

- 32 tokens/s (1 min = 1,920 tokens); up to 9.5 h per prompt; downsampled to 16 kbps mono.
- Formats: WAV, MP3, AIFF, AAC, OGG, FLAC, M4A, Opus, WebM, etc. Inline under 20 MB, otherwise use the Files API.
- Supports MM:SS timestamps, speaker identification, per-segment language detection, and non-speech sounds.

### 2.5 Structured output

Source: [structured-output](https://ai.google.dev/gemini-api/docs/structured-output).

- Interactions API: `response_format={"type":"text","mime_type":"application/json","schema": Model.model_json_schema()}`.
- Supported JSON Schema keywords:
  - `properties`, `required`, `additionalProperties`
  - `enum`, `format` (date-time/date/time)
  - `minimum`/`maximum`
  - `items`, `prefixItems`, `minItems`/`maxItems`
  - `title`, `description`
- **Gemini 3 can combine structured outputs with Search grounding, URL context, code execution, File Search and function calling.** This is essential: we get a grounded seller search that returns typed `Offer[]` JSON in one call.

### 2.6 Function calling

Source: [function-calling](https://ai.google.dev/gemini-api/docs/function-calling).

- Supports parallel calls (independent functions) and compositional/sequential chaining.
- `tool_choice` modes: `auto` (default), `any`, `none`, `validated` (enforces schema adherence).
- The SDKs handle **thought signatures** automatically.
- "Gemini 3 models can combine built-in tools with function calling out-of-the-box in Interactions."
- A maximum function count is not documented.

### 2.7 Thinking

Source: [thinking](https://ai.google.dev/gemini-api/docs/thinking).

- The control is `thinking_level` in `generation_config`. The page does not document a separate `thinking_budget` for the 3.x models.
- Values per model:
  - 3.8 / 3.7 Flash: `low`/`medium`/`high` (default `medium`)
  - 3.5 Flash: adds `minimal`
  - 3.5 Flash-Lite: default `minimal`
  - 3.1 Pro: default `high`
- Thought summaries use `"thinking_summaries": "auto"` (or `"none"`). Signatures are handled by the server in stateful mode; in stateless mode, resend the thought blocks unchanged.
- **UX idea:** stream the thought summaries into a "what the agent is checking" panel.

### 2.8 Grounding with Google Search

Source: [google-search](https://ai.google.dev/gemini-api/docs/google-search).

- Tool: `tools=[{"type": "google_search"}]`.
- Response contains:
  - `google_search_call` (the `queries` run)
  - `google_search_result` (with `search_suggestions` HTML, which **must be displayed per the ToS**)
  - `annotations` of type `url_citation` with `url`, `title`, `start_index`, `end_index`
- **Billing:** Gemini 3 is billed **per search query executed** (one prompt can trigger several queries); 2.5 and older were billed per prompt.
- **Pricing** ([pricing](https://ai.google.dev/gemini-api/docs/pricing)): 5,000 free queries/month on the paid tier (shared across Gemini 3.x), then **$14 / 1,000 queries**.
  - **Free tier: "Not available"** for 3.8 Flash and 3.5 Flash-Lite.
  - **[UNCERTAIN, fetched-summary; confirm in AI Studio]**
- **Controls:** the docs mention no locale, region, domain allow-list or domain exclude options. **[inference]** To bias toward India, put "site:robu.in OR site:robocraze.com OR site:amazon.in ... price INR" style guidance in the prompt, and post-filter citations by domain.
- On Agent Platform, grounding input tokens are "not charged". Grounding with Google Search / Web Grounding for Enterprise also gets 5,000 free queries/month, then $14/1,000 ([Agent Platform pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en)).

### 2.9 URL context

Source: [url-context](https://ai.google.dev/gemini-api/docs/url-context).

- Tool: `{"type": "url_context"}`. Up to **20 URLs per request** and **34 MB per URL**.
- Supports HTML, JSON, text, XML, CSV, RTF, PNG/JPEG/BMP/WebP and PDF.
- Does **not** support paywalled pages, **YouTube**, Workspace files, video/audio, login-protected pages, localhost/private networks, or tunnels (ngrok).
- Fetched content is billed as input tokens (`tool_use_input_tokens`). A `url_context_result` step reports retrieval status.
- Can be combined with Google Search: search first, then read the pages.
- **Gotcha [inference]:** Amazon.in and some Indian storefronts use heavy JS and bot protection, so URL context may fail on them. Handle `url_retrieval_status` failures and fall back to search-snippet data or a custom fetch tool.

### 2.10 Grounding with Google Maps

Source: [maps-grounding](https://ai.google.dev/gemini-api/docs/maps-grounding).

- Tool `google_maps`, with optional `latitude`/`longitude`. Returns place info, reviews and citations. Supported on Gemini 3 since 2026-03-18.
- Pricing: 5,000 free/month (paid tier), then $14/1,000.
- **Use:** "nearby electronics shops in Lamington Road, Mumbai / SP Road, Bengaluru / Ritchie Street, Chennai that likely stock this". This is a nice India-specific "buy today offline" feature and a UX differentiator.

### 2.11 Code execution

Supported on 3.8 Flash ([model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)). Use it for deterministic totals, GST/shipping math and currency conversion inside the model turn. **[inference]** Doing that math in plain Python in a function node is cheaper and more auditable.

### 2.12 File Search (managed RAG)

Source: [file-search](https://ai.google.dev/gemini-api/docs/file-search).

- `client.file_search_stores.create(config={'display_name':..., 'embedding_model':'models/gemini-embedding-2'})`, then `upload_to_file_search_store` / `import_file`.
- `chunking_config.white_space_config.{max_tokens_per_chunk, max_overlap_tokens}`; `custom_metadata`; `metadata_filter`; `file_citation` annotations with page numbers.
- **Multimodal image search** (PNG/JPEG up to 4K) when the store uses gemini-embedding-2.
- Limits: 1 GB free / 10 GB Tier 1; max 100 MB per file.
- **Pricing:** indexing is billed at embedding rates; **storage is free**; querying is free apart from retrieved tokens.
- **Use:** index datasheets (ESP32, common sensors, drivers) and a curated "known substitutions" knowledge base (e.g. DHT22 ↔ AM2302, A4988 ↔ DRV8825 pin-compatible). The compatibility judge can then cite datasheet pages. This is great for the "technical merit" score.

### 2.13 Context caching, Batch, Flex/Priority

- **Caching** ([caching](https://ai.google.dev/gemini-api/docs/caching)): implicit caching is on by default for 2.5+. The minimum is 4,096 tokens for 3.x Flash / 3.1 Pro. Watch `usage.total_cached_tokens`. **Put the long video / system prompt first** so repeated sub-agent calls get cache hits.
- **Batch** ([batch-api](https://ai.google.dev/gemini-api/docs/batch-api)): 50% off, 24 h target. Inline up to 20 MB or JSONL up to 2 GB. Google Search works in batch. Webhook `batch.succeeded`.
- **Flex** ([flex](https://ai.google.dev/gemini-api/docs/flex-inference)): `service_tier: 'flex'`, 50% off, 1–15 min latency, sheddable. `priority` costs 75–100% more. **Use Flex for a nightly "re-price saved BOMs" job**, not the live demo.

### 2.14 Live API, Computer Use, Deep Research, Managed Agents

- **Live API:** WebSockets, VAD, function calling, ephemeral tokens for client-side connections ([live](https://ai.google.dev/gemini-api/docs/live)). Note: the page fetched still showed a 2.5 model; the 3.8 Live models are GA per the changelog. **[UNCERTAIN on current session limits]**
- **Computer Use** ([computer-use](https://ai.google.dev/gemini-api/docs/computer-use)): a screenshot → action loop with 0–1000 coordinates. Browser, Android and desktop environments. Built-in safety policies block financial transactions. Needs your own sandbox (Docker + Playwright).
- **Deep Research:** see §1.2. It supports custom **MCP servers**, so you could expose a "seller catalog" MCP to it.
- **Managed Agents** (public preview since 2026-05-19): a single API call provisions an Ubuntu sandbox. Customize with `agent_config`, AGENTS.md / SKILL.md. Sandbox compute is not billed during preview; the free tier is available; typical interactions use 100k–3M tokens ([agents](https://ai.google.dev/gemini-api/docs/agents.md.txt), [blog](https://blog.google/innovation-and-ai/technology/developers-tools/managed-agents-gemini-api)). **Too heavy and unpredictable for the core path.**

### 2.15 Embeddings

See §1.2.
- Agent Platform lists Gemini Embedding at "$0.00015 per 1,000 queries" online **[UNCERTAIN: the unit looks odd; the Gemini API pricing page fetch did not return an embedding price, so check it in AI Studio]** ([Agent Platform pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en)).
- Batch embeddings are 50% of the default price ([embeddings](https://ai.google.dev/gemini-api/docs/embeddings)).

---

## 3. Agent Development Kit (ADK)

Sources: [adk.dev](https://adk.dev/) (the old `google.github.io/adk-docs` now redirects there), [releases](https://github.com/google/adk-python/releases).

### 3.1 State of ADK

- **Languages:** Python, TypeScript, Go, Java, Kotlin.
- **ADK 2.0 is GA** and adds **graph workflows**. Python keeps parallel v1.x (v1.38.0, 2026-08-07) and v2.x (v2.6.3, 2026-08-07) branches.
- **v2.6.0 (2026-07-30) added:**
  - `ReflectAndRetryModelPlugin` (self-healing on model errors)
  - `--extra_packages` for Agent Runtime deploys
  - MCP server support for agent deployment
  - OAuth2 refresh for OpenAPI tools
  - ManagedAgent instruction field
- **v2.5.0 (2026-07-16) added:** Cloud Run sandbox, MCP server hosting, workflow graph validation, artifact improvements.
- ADK is multi-model: Gemini, Claude, OpenAI, Ollama, vLLM.
- **Context management:** it filters irrelevant events, summarizes turns and tracks tokens. Sessions support "rewind".

### 3.2 Agent types

**Template workflows** (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, all extending `BaseAgent`) ([workflows](https://adk.dev/workflows/), [parallel](https://adk.dev/agents/workflow-agents/parallel-agents/)):

```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools import google_search

a = LlmAgent(name="ResearcherA", model="gemini-3.8-flash",
             instruction="...", tools=[google_search], output_key="result_a")
b = LlmAgent(name="ResearcherB", model="gemini-3.8-flash",
             instruction="...", tools=[google_search], output_key="result_b")
fanout = ParallelAgent(name="Fanout", sub_agents=[a, b])
merge  = LlmAgent(name="Merger", model="gemini-3.8-flash",
                  instruction="Combine {result_a} and {result_b}")
pipeline = SequentialAgent(name="Pipeline", sub_agents=[fanout, merge])
```

- `output_key` writes to session state, and `{key}` templating reads it.
- Parallel branches **do not share conversation history**. Share data through state or external storage.

**ADK 2.0 graph `Workflow`** ([graphs](https://adk.dev/graphs/)):

```python
from google.adk import Agent, Workflow, Event
agent = Agent(name="city_generator", model="gemini-flash-latest",
              instruction="Return a random city name only.")
def lookup_time(city: str): return {"city": city, "time": "10:10 AM"}
workflow = Workflow(name="root_agent", edges=[("START", agent, lookup_time)])
```

- Nodes can be LLM agents, plain functions, tools or nested workflows. Edges can be sequential or conditional (router nodes return route values).
- Data flows via `event.Output` with no state writes needed. There is a `/graphs/human-input/` feature for HITL.
- **Recommendation:** build Bharat Sourcer as a graph workflow. Deterministic nodes handle URL-type detection, currency and GST math, and dedupe; LLM nodes handle extraction, sourcing and judging. A human-input node lets the user confirm or edit the extracted BOM before sourcing. This shows "deterministic + agentic" design, which judges like.

### 3.3 Tools

- Function tools, MCP tools, OpenAPI tools and Google Search.
- **MCP** ([mcp-tools](https://adk.dev/tools-custom/mcp-tools/)): `McpToolset` with `StdioConnectionParams` or `StreamableHTTPConnectionParams`, plus `tool_filter`. You can also expose ADK tools as an MCP server.
- **Important limitation** ([limitations](https://adk.dev/tools/limitations/), [google-search](https://adk.dev/integrations/google-search/)):
  - Built-in Code Execution, Google Search and Agent Search historically had to be used "by itself within an agent instance".
  - For search tools this constraint affects "ADK Python v1.15.0 and lower".
  - Workarounds: (1) wrap specialists with `AgentTool(agent=search_agent)`; (2) `bypass_multi_tools_limit=True` for `GoogleSearchTool`/`VertexAiSearchTool`.
  - Built-in tools cannot run inside sub-agents except via that workaround.
  - **Pattern:** a `SellerSearchAgent` (google_search only) wrapped as an `AgentTool` for the orchestrator.
  - The ADK google_search page still says "only compatible with Gemini 2 models" and requires rendering search suggestions (`renderedContent`). **[UNCERTAIN: probably stale docs text; verify with 3.8 Flash]**

### 3.4 Sessions, state, memory, artifacts, callbacks

Source: [sessions](https://adk.dev/sessions/).

- **Sessions:** `SessionService` implementations cover in-memory (dev), database, and Agent Platform / Agent Runtime backends. State lives in `session.state`. `MemoryService` provides long-term searchable memory; `VertexAiMemoryBankService` is backed by Memory Bank ([express mode](https://adk.dev/integrations/express-mode/index.md)).
- **Artifacts** (videos, images, generated BOM CSV/PDF): use an artifact service with the `gs://bucket` URI (`--artifact_service_uri`) ([Cloud Run deploy](https://adk.dev/deploy/cloud-run/)).
- Callbacks (before/after model/tool) and state prefixes exist in ADK. **[UNCERTAIN: exact current prefix list not re-verified on the fetched page]**

### 3.5 Streaming

- The ADK API server exposes `/run`, `/run_sse` (Server-Sent Events) and `/apps/{app}/users/{user}/sessions...`. Bidi streaming uses `run_live` with Live models ([streaming → live](https://adk.dev/live/)).
- v1.37 added async non-blocking tools in Live mode, and v2.6 adds a state delta for Live.

### 3.6 Evaluation

Source: [evaluate](https://adk.dev/evaluate/).

- Test files (unit) and evalsets (multi-turn integration) share a Pydantic schema.
- Metrics:
  - `tool_trajectory_avg_score` (exact match, default threshold 1.0)
  - `response_match_score` (ROUGE-1, default 0.8)
  - `final_response_match_v2` (LLM judge)
  - rubric-based quality metrics
  - `hallucinations_v1`, `safety_v1`
- Run via the `adk eval` CLI, pytest, or the Web UI Eval tab. `adk conformance test` does regression against recorded baselines.
- **Hackathon win:** ship an evalset of 5–10 known projects (e.g. an "ESP32 weather station" with a hand-verified BOM). Report extraction recall and price-found rate in the README and demo video.

### 3.7 Deployment

- `adk deploy cloud_run --project=... --region=... --service_name=... [--with_ui] [--session_service_uri=...] [--artifact_service_uri=gs://...] [--allow_origins=...] AGENT_PATH` ([Cloud Run deploy](https://adk.dev/deploy/cloud-run/)).
- Alternatively, use `gcloud run deploy` with a Dockerfile and:

```python
from google.adk.cli.fast_api import get_fast_api_app
app = get_fast_api_app(agents_dir=AGENT_DIR,
                       session_service_uri="sqlite+aiosqlite:///./sessions.db",
                       allow_origins=["https://<your>.web.app"], web=False)
# then add your own FastAPI routes to `app`
```

- Env vars: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_ENTERPRISE=True` (Agent Platform). For the AI Studio key path, use `GOOGLE_API_KEY`.
- Other targets: **Agent Runtime** (managed, "sub-second cold starts", long-running agents) or GKE ([deploy](https://adk.dev/deploy/)).
- **A2A** ([a2a](https://adk.dev/a2a/)): expose agents with `to_a2a(...)` / `adk api_server --a2a`, and consume them with `RemoteA2aAgent`. A2UI v0.9 references "A2A Protocol 1.0" ([A2UI blog](https://developers.googleblog.com/a2ui-v0-9-generative-ui/)).

---

## 4. Gemini API (AI Studio) vs Agent Platform (ex-Vertex AI)

| | Gemini Developer API (AI Studio key) | Gemini Enterprise Agent Platform (ex-Vertex) |
|---|---|---|
| Auth | API key | Service account / ADC (`vertexai=True, project, location`); **express mode** allows an API key ([migrate](https://ai.google.dev/gemini-api/docs/migrate-to-cloud), [express mode](https://adk.dev/integrations/express-mode/index.md)) |
| Free tier | Yes for most Flash / Flash-Lite models. **No grounding on the free tier. Free-tier content is "used to improve our products"** ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). Free YouTube input capped at 8 h/day. | Express mode: no GCP project needed. Expires after 90 days; limits include 10 Agent Runtime deployments, 10 session create/update/delete per minute, 30 append-event per minute ([ADK express](https://adk.dev/integrations/express-mode/index.md)). A standard GCP free trial also exists **[UNCERTAIN: the $300 amount was not re-verified; the free-features page returned 404]** |
| Tiers | Free, Tier 1 (billing linked, spend cap $250), Tier 2 ($100 paid + 3 days, $2,000), Tier 3 ($1,000 + 30 days). Actual RPM/TPM are shown only in AI Studio ([rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)). Project spend caps (2026-03). | GCP quotas |
| Features | Everything new lands here first (Interactions API, agentic video, File Search, Managed Agents, Deep Research) | Agent Runtime, Sessions, Memory Bank, Agent Sandbox, RAG Engine, Vector Search, Model Garden (200+ models incl. Claude, Gemma 4), Agent Gateway/Registry/Identity, Agent Evaluation/Simulation/Observability ([Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)) |
| Model prices | 3.8 Flash $0.75 / $3.75 | Same list price (3.8 Flash $0.75 / $3.75 intro, "global") ([AP pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en)) |

**Agent Runtime pricing** ([Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?authuser=0)):
- Compute: free for the first **50 vCPU-h** and **100 GiB-h** per month; after that, $0.085/vCPU-h and $0.009/GiB-h. Idle time between turns is not billed.
- **Sessions and Memory Bank** (billing started 2026-09-01): $0.30/GiB-month storage; 1 vCPU-h ($0.085) per 3M reads or per 1M writes.
- **Agent Sandbox / code execution** is billed on vCPU and RAM.

**Hackathon credits:** none are mentioned on aibuildercup.com ([site](https://aibuildercup.com/index.html)). **[UNCERTAIN; check the participant email/Discord.]**

**Agent Platform's managed RAG:**
- RAG Engine, Vector Search and "Agent Search" (the Vertex AI Search successor naming) exist in the docs tree ([Agent Platform docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform)).
- **[inference]** For our scale, the Gemini API File Search (free storage) or Firestore vector search is simpler and cheaper.

---

## 5. Firebase and Cloud Run

### 5.1 Hosting

- **Firebase Hosting** is for static SPAs (React + Vite). **App Hosting** targets SSR frameworks (Next.js, Angular) ([frameworks overview](https://firebase.google.com/docs/hosting/frameworks/frameworks-overview)). **Use Hosting.**
- **Hard limit: "Firebase Hosting is subject to a 60-second request timeout."** This applies to rewrites to Cloud Run/Functions and returns a 504 ([serverless overview](https://firebase.google.cn/docs/hosting/serverless-overview?hl=en)). A full analysis will take longer than 60 s. Two ways to handle it:
  - **(a) Async job pattern (recommended):**
    1. `POST /api/analyses` (through the Hosting rewrite) creates a Firestore doc and returns an id in under 1 s.
    2. The backend runs the pipeline (Cloud Run with instance-based billing / Cloud Tasks / Cloud Run job).
    3. The backend writes progressive results to Firestore (`analyses/{id}/steps`, `.../parts`).
    4. React subscribes with `onSnapshot`, so the UI is live-updating, resumable and shareable by URL.
  - **(b)** The frontend calls the Cloud Run URL directly (CORS) for `/run_sse` streaming.

### 5.2 Firestore

- **Free quota** ([quotas](https://firebase.google.com/docs/firestore/quotas)): 1 GiB storage, 50k reads/day, 20k writes/day, 20k deletes/day, 10 GiB/month egress.
- Documents are limited to 1 MiB, so store frames and PDFs in Cloud Storage.
- **Vector search** ([vector-search](https://firebase.google.com/docs/firestore/vector-search)):
  - up to **2,048 dimensions**, so use `gemini-embedding-2` with `output_dimensionality=768` or `1536`
  - `find_nearest` supports `distance_threshold`, prefilters and limit
  - flat index created with gcloud / Firebase CLI
  - embeddings are generated externally
  - **Use:** a "parts catalog cache". Each resolved part (name, specs, image embedding) → offers. Repeat parts (ESP32-WROOM, SG90, DHT22) resolve instantly and cheaply.

### 5.3 Firebase AI Logic, Genkit, Firebase Studio

- **Firebase AI Logic** gives client SDKs (Web JS, Swift, Kotlin, Dart, Unity) with Gemini Developer API or Agent Platform providers, App Check, hybrid on-device, and server prompt templates ([AI Logic](https://firebase.google.com/docs/ai-logic)).
  - **Use:** only for small client-side features, such as a "quick part identify" from a phone camera photo. The core pipeline stays server-side in ADK.
- **Genkit:** TypeScript and Go, with Python and Dart in preview. Flows, tools, dev UI; deploys to Firebase or Cloud Run ([genkit.dev](https://genkit.dev/)). **Not needed if you use ADK.**
- **Firebase Studio is being sunset.** New workspaces have been disabled since 2026-06-22, and it shuts down on 2027-03-22. Google points users to Google AI Studio and **Google Antigravity** ([migration](https://firebase.google.com/docs/studio/migrating-project)). Don't start there.
- Auth: Firebase Auth (Google sign-in) to save BOMs per user. **[not re-verified — standard feature]**

### 5.4 Cloud Run

- **Timeout:** 5 min by default, **up to 60 min** (`--timeout`). If a response times out you get a 504, but the instance keeps running your code ([timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)).
- **Concurrency:** default 80×vCPU (CLI) or 80 (console), max 1,000 per instance ([concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)).
- **Pricing and free tier** ([pricing](https://cloud.google.com/run/pricing)):
  - Request-based billing: 180k vCPU-s, 360k GiB-s and 2M requests/month free; $0.000024/vCPU-s active.
  - Instance-based billing: 240k vCPU-s and 450k GiB-s free; $0.000018/vCPU-s.
  - Jobs get the same free tier as instance-based services.
  - **Use instance-based billing** (CPU always allocated) if you run the pipeline after returning 202. Set `min-instances=1` during judging to avoid cold starts **[inference]**.
- **GPUs:** L4 (24 GB) and RTX PRO 6000 Blackwell (96 GB). L4 regions include europe-west1/4, us-central1, us-east4, asia-southeast1, and asia-south1 (invitation only). Scale-to-zero, about 5 s startup, one GPU per instance ([GPU](https://docs.cloud.google.com/run/docs/configuring/services/gpu)).
- **Cloud Tasks / Pub/Sub / Workflows / Secret Manager / Logging / Trace / BigQuery:** not re-verified in this pass. **[inference]**
  - Secret Manager holds any seller API keys, with `--set-secrets` on deploy.
  - Cloud Trace + ADK OpenTelemetry give an agent trace screenshot for the submission.
  - Cloud Tasks gives a retryable per-part sourcing fan-out if you want resilience beyond the in-process `ParallelAgent`.
  - BigQuery is optional for price history and analytics ("how much India saves vs import").

---

## 6. Agentic commerce standards and product data

| Standard | What it is | Useful for Bharat Sourcer? |
|---|---|---|
| **UCP: Universal Commerce Protocol** (2026-01-11) | Open standard for agentic commerce. Merchants publish capabilities at `/.well-known/ucp` (checkout, discounts, fulfillment, payment handlers). Works with AP2, A2A and MCP. Partners include Shopify, Etsy, Wayfair, Target, Walmart, Stripe, Visa, Mastercard. **Focus is checkout, not product search.** India is not mentioned. Spec: ucp.dev, github.com/universal-commerce-protocol/ucp ([Google dev blog](https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/)). The Merchant API added a UCP account integration (Aug 2026) and UCP checkout notifications (May 2026) ([Merchant API updates](https://developers.google.com/merchant/api/latest-updates?hl=en)). | **Pitch / roadmap.** Probe `https://robu.in/.well-known/ucp` etc.; if any Indian seller supports it, show "cart-ready via UCP". **[inference]** Probably none do yet (Shopify-based Indian stores might). |
| **AP2: Agent Payments Protocol** | Open extension of A2A. Uses Verifiable Digital Credentials with **Checkout Mandate** and **Payment Mandate** in Open/Closed stages. v0.2. Cards today; **UPI, PIX and e-wallets are on the roadmap**. Standardization is via FIDO Alliance working groups ([ap2-protocol.org](https://ap2-protocol.org/)) | Roadmap slide only |
| **NPCI "Unified Agent Protocol"** (India) | Agentic UPI payments framework, expected to be unveiled around Global Fintech Fest (Sept 2026). Uses UPI Circle / Reserve Pay, rule-based limits. No stated link to AP2 ([The Star/Reuters, 2026-09-01](https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say)) [secondary] | Great "India-first" narrative for the impact section |
| **A2UI v0.9** (2026-04-17) | Framework-agnostic JSON spec for agent-generated UI. Renderers: **React (new)**, Lit, Flutter, Angular. `pip install a2ui-agent-sdk`. Integrates with A2A 1.0 and AG-UI ([dev blog](https://developers.googleblog.com/a2ui-v0-9-generative-ui/)) | **Yes, for the UX and innovation scores.** The agent streams A2UI components (part card, compatibility warning, alternative comparison table) that the React app renders. |
| **Merchant API / Content API** | Merchant API only covers **a merchant's own data**. Content API for Shopping shut down **2026-08-18**. The Merchant API added an MCP service (May 2026). **No third-party Shopping Graph query** ([updates](https://developers.google.com/merchant/api/latest-updates?hl=en)) | No |

**Conclusion:** Google gives us no API to query Indian offers. The sourcing layer has to be built from:
1. Gemini + `google_search` + `url_context` (grounded, citable)
2. optionally custom tools for seller sites (search pages / JSON endpoints, where the ToS allow)
3. our own Firestore cache

---

## 7. Other Google APIs (OCR, vision, speech, translation)

| API | Price / notes | Verdict |
|---|---|---|
| **Document AI** | Enterprise OCR $1.50/1k pages; Layout Parser $10/1k; Form Parser / Custom Extractor $30/1k ([pricing](https://cloud.google.com/document-ai/pricing)) | Not needed: Gemini reads PDFs and schematics natively. Maybe Layout Parser for bulky datasheets. |
| **Cloud Vision API** | 1,000 units/month free; text detection $1.50/1k; object localization $2.25/1k; **web detection $3.50/1k** ([pricing](https://cloud.google.com/vision/pricing)) | **Web Detection** (visually similar images and pages on the web) could help identify an unlabeled module from a frame. **[inference]** Optional. |
| **Video Intelligence API** | 1,000 free minutes/month per feature; text detection (OCR) $0.15/min, object tracking $0.15/min ([pricing](https://cloud.google.com/video-intelligence/pricing)) | Gemini video supersedes it; skip |
| **Speech-to-Text v2 (Chirp)** | $0.016/min standard; dynamic batch $0.003/min; v1 has 60 free min/month ([pricing](https://cloud.google.com/speech-to-text/pricing)) | Prefer `gemini-3.5-transcribe` (~$0.003/min, Indic support) |
| **Cloud Translation** | NMT: first 500k chars/month free, then $20/M; Translation LLM $10/M; Adaptive $25/M ([pricing](https://cloud.google.com/translate/pricing)) | Gemini can output Hindi/Tamil/etc. directly. Use Translation only if you want deterministic, glossary-controlled UI strings. |

**Indic support in Gemini:**
- `gemini-3.5-transcribe` explicitly lists hi-IN, bn-IN, kn-IN, ml-IN, mr-IN, or-IN, pa-IN, te-IN ([transcribe page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe)).
- The TTS models cover 130 languages (3.8 Flash TTS) and 101 (Flash-Lite TTS) ([models](https://ai.google.dev/gemini-api/docs/models)).
- A per-language matrix for text generation was not found on the pages opened (the Cloud language-support page needed permission). **[UNCERTAIN, but Hindi and major Indic languages are widely supported.]**
- **Demo idea:** output the BOM summary and "substitution notes" in Hindi or Tamil, plus a TTS audio explanation for a regional-language maker audience.

---

## 8. Cost of one full analysis (estimate)

Assumptions: a 15-minute YouTube build video, about 25 unique parts, and `gemini-3.8-flash` at intro pricing ($0.75 in / $3.75 out per 1M) ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). **All figures are [inference] and approximate.**

| Step | Tokens / units | Cost (USD) |
|---|---|---|
| Video extraction, static low-res (~100 tok/s × 900 s ≈ 90k in) + ~10k out incl. thinking | 90k in / 10k out | ≈ $0.07 + $0.04 = **$0.11** (agentic mode could be ~50–88% fewer input tokens) |
| 3 high-res clip re-checks (15 s each ≈ 300 tok/s) | ~14k in / 3k out | ≈ $0.02 |
| Spec normalization, 25 parts on `gemini-3.5-flash-lite` | ~60k in / 20k out | ≈ $0.02 + $0.05 = **$0.07** |
| Seller search: 25 parts × ~2 grounded queries | **~50 Search queries** | First **5,000/month free** (paid tier); after that, $14/1k = **$0.70** |
| Grounded search turns: tokens | 25 × (~8k in / 1.5k out) | ≈ $0.15 + $0.14 = **$0.29** |
| URL context reads of ~20 product pages (~15k tokens each) | ~300k in | ≈ **$0.23** |
| Compatibility judge on `gemini-3.1-pro-preview` (all parts in one call) | ~40k in / 10k out | ≈ $0.08 + $0.12 = **$0.20** |
| Report + Hindi summary | ~20k in / 5k out | ≈ $0.03 |
| Cloud Run (~3 min × 1 vCPU / 1 GiB) | ~180 vCPU-s | ≈ $0.004 (inside the free tier) |
| **Total** | | **≈ $0.95 while inside the free 5,000 grounding queries/month**; **≈ $1.65** past it. With Flash-Lite for sourcing and a Firestore cache hit on common parts: **≈ $0.40–0.60** |

**Hackathon budget [inference]:** about 200 dev/test runs plus judging traffic would use roughly 10k grounding queries (≈ $70 past the free 5k) plus about $100 of tokens. Set an **AI Studio project spend cap** (a feature since 2026-03) ([changelog](https://ai.google.dev/gemini-api/docs/changelog)). Tier 1 has a $250 cap ([rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)).

---

## 9. Recommendations for Bharat Sourcer

**Platform choice**
1. Use the **Gemini Developer API (AI Studio key) on a billed Tier 1 project**. That gives grounding, the new Interactions features (agentic video) first, and free-tier data-use concerns go away. Keep the key in **Secret Manager** and mount it in Cloud Run. Deploy the backend to **Cloud Run** (meets the rule) and the frontend to **Firebase Hosting**.
2. **Pin these models:**
   - `gemini-3.8-flash`: orchestrator, video, sourcing
   - `gemini-3.5-flash-lite`: per-part fan-out
   - `gemini-3.1-pro-preview`: the compatibility judge. Put it behind a flag so you can fall back to 3.8 Flash `high` if preview quota bites.
   - Drop `temperature` from all configs (deprecated 2026-07-21).
   - **Note:** 3.8 Flash's intro price ends on 2026-12-31, after the finale, so it is fine for the hackathon.

**Architecture: ADK 2.x graph `Workflow`**
```
START → classify_input (fn) ─┬─ video → VideoExtractor (LLM, genai interactions call w/ processing="agentic", structured BOM + timestamps)
                             ├─ url   → PageExtractor (LLM + url_context)
                             └─ audio → AudioExtractor (3.5-transcribe → LLM)
      → ClipVerifier (fn+LLM: high-res clipped re-reads for low-confidence parts; box_2d on keyframes)
      → HumanConfirm (human-input node: user edits BOM)
      → cache_lookup (fn: Firestore find_nearest on gemini-embedding-2)
      → ParallelAgent[ per-part SellerSearch (AgentTool w/ google_search + url_context, structured Offer[]) ]
      → CompatJudge (3.1 Pro + File Search over datasheets/known-substitutions KB)
      → price_math (fn: INR totals, GST, shipping, savings vs import)
      → Report (LLM; A2UI components; Hindi summary; Maps "local shops" optional)
```

**Build details**
- **Async job + Firestore live updates** avoids the 60 s Hosting timeout and makes progress feel alive. Cloud Run: instance-based billing, `--timeout=3600`, `min-instances=1` during judging, `concurrency` about 10 (these are LLM-bound async calls).
- **Evidence-first UX for technical merit:**
  - every part shows the video timestamp and a bounding-boxed frame (0–1000 → px)
  - every price shows its grounding `url_citation`
  - every substitution shows the datasheet citation (File Search `file_citation` with page)
  - render Google's `search_suggestions` as the ToS require
- **ADK tool limitation:** keep `google_search` in its own agent wrapped with `AgentTool`, or use `bypass_multi_tools_limit=True`. Since ADK Python is past v1.15, test whether direct mixing now works.
- **Evaluation:** ship an `adk eval` evalset (8–10 real projects with hand-labelled BOMs). Report part recall, correct-part precision, % parts with an Indian offer, and median savings. Include `hallucinations_v1`. This speaks directly to the 40% technical criterion.
- **Innovation hooks**, ranked by value to effort:
  1. agentic video + clip zoom-in re-read
  2. multimodal "same part" matching with `gemini-embedding-2`
  3. A2UI-rendered result cards
  4. Maps grounding for offline shops in electronics markets (Lamington Rd, SP Road, Ritchie St)
  5. Hindi / regional-language output with TTS
  6. UCP / AP2 / NPCI agentic-UPI "one-tap cart" as the roadmap
- **Avoid for the MVP:** Managed Agents / Antigravity (preview churn: the 05-2026 version dies 2026-10-05), Deep Research on the interactive path (takes minutes), Computer Use scraping, Genkit (redundant with ADK), and Firebase Studio (sunset).

**Risks to verify on day 1**
1. Whether ADK passes `processing: "agentic"` and `service_tier` through. If not, call `client.interactions.create` inside a function node.
2. Actual RPM/TPM for your tier on the AI Studio rate-limit page.
3. `url_context` success rate on amazon.in, robu.in and robocraze.com product pages.
4. That grounding is enabled once billing is linked.
5. Hackathon eligibility: JAPAC region, 2–4 person team, register before **Oct 11**.

---

### Source index (all opened during this research)
- Gemini API: [models](https://ai.google.dev/gemini-api/docs/models) · [3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) · [3.1 Pro preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) · [3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) · [3.5 Transcribe](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe) · [embedding-2](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2) · [pricing](https://ai.google.dev/gemini-api/docs/pricing) · [changelog](https://ai.google.dev/gemini-api/docs/changelog) · [interactions](https://ai.google.dev/gemini-api/docs/interactions) · [video](https://ai.google.dev/gemini-api/docs/video-understanding) · [image](https://ai.google.dev/gemini-api/docs/image-understanding) · [audio](https://ai.google.dev/gemini-api/docs/audio) · [thinking](https://ai.google.dev/gemini-api/docs/thinking) · [structured output](https://ai.google.dev/gemini-api/docs/structured-output) · [function calling](https://ai.google.dev/gemini-api/docs/function-calling) · [google search](https://ai.google.dev/gemini-api/docs/google-search) · [url context](https://ai.google.dev/gemini-api/docs/url-context) · [maps](https://ai.google.dev/gemini-api/docs/maps-grounding) · [file search](https://ai.google.dev/gemini-api/docs/file-search) · [caching](https://ai.google.dev/gemini-api/docs/caching) · [batch](https://ai.google.dev/gemini-api/docs/batch-api) · [flex](https://ai.google.dev/gemini-api/docs/flex-inference) · [embeddings](https://ai.google.dev/gemini-api/docs/embeddings) · [deep research](https://ai.google.dev/gemini-api/docs/deep-research) · [agents](https://ai.google.dev/gemini-api/docs/agents.md.txt) · [computer use](https://ai.google.dev/gemini-api/docs/computer-use) · [live](https://ai.google.dev/gemini-api/docs/live) · [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) · [migrate to cloud](https://ai.google.dev/gemini-api/docs/migrate-to-cloud)
- Gemma: [core](https://ai.google.dev/gemma/docs/core) · [on Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
- ADK: [adk.dev](https://adk.dev/) · [graphs](https://adk.dev/graphs/) · [workflows](https://adk.dev/workflows/) · [parallel](https://adk.dev/agents/workflow-agents/parallel-agents/) · [deploy](https://adk.dev/deploy/) · [Cloud Run](https://adk.dev/deploy/cloud-run/) · [evaluate](https://adk.dev/evaluate/) · [a2a](https://adk.dev/a2a/) · [sessions](https://adk.dev/sessions/) · [mcp](https://adk.dev/tools-custom/mcp-tools/) · [limitations](https://adk.dev/tools/limitations/) · [google search](https://adk.dev/integrations/google-search/) · [express mode](https://adk.dev/integrations/express-mode/index.md) · [releases](https://github.com/google/adk-python/releases)
- Cloud: [Agent Platform blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform) · [Agent Platform docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform) · [AP gen-AI pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing?hl=en) · [AP product pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing?authuser=0) · [Cloud Run timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout) · [GPU](https://docs.cloud.google.com/run/docs/configuring/services/gpu) · [concurrency](https://docs.cloud.google.com/run/docs/about-concurrency) · [Run pricing](https://cloud.google.com/run/pricing) · [Doc AI](https://cloud.google.com/document-ai/pricing) · [Vision](https://cloud.google.com/vision/pricing) · [Video Intelligence](https://cloud.google.com/video-intelligence/pricing) · [STT](https://cloud.google.com/speech-to-text/pricing) · [Translation](https://cloud.google.com/translate/pricing)
- Firebase: [frameworks](https://firebase.google.com/docs/hosting/frameworks/frameworks-overview) · [serverless 60 s](https://firebase.google.cn/docs/hosting/serverless-overview?hl=en) · [Firestore quotas](https://firebase.google.com/docs/firestore/quotas) · [vector search](https://firebase.google.com/docs/firestore/vector-search) · [AI Logic](https://firebase.google.com/docs/ai-logic) · [Studio sunset](https://firebase.google.com/docs/studio/migrating-project) · [Genkit](https://genkit.dev/)
- Commerce/UI: [UCP](https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/) · [AP2](https://ap2-protocol.org/) · [A2UI v0.9](https://developers.googleblog.com/a2ui-v0-9-generative-ui/) · [Merchant API updates](https://developers.google.com/merchant/api/latest-updates?hl=en) · [NPCI agentic UPI](https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say) [secondary]
- Hackathon: [aibuildercup.com](https://aibuildercup.com/index.html) · [Metropolis listing](https://metropolisjapan.com/events/ai-builder-cup-2026/) [secondary] · Vertex rename explainer: [Medium GDE](https://medium.com/google-developer-experts/vertex-ai-is-gone-here-is-what-google-built-instead-92556d1c64eb) [secondary]
