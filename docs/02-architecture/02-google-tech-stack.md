# Google tech stack

> **In one minute.** Every AI call goes to the **Gemini API on a billed Tier 1 project**, because Search grounding is not available on the free tier.
> - **Models:**
>   - `gemini-3.8-flash`: workhorse for video, sourcing and diffs
>   - `gemini-3.5-flash-lite`: cheap parallel sub-agents
>   - `gemini-3.1-pro-preview`: the compatibility judge, with a fallback
>   - `gemini-embedding-2`: multimodal vectors
>   - `gemini-3.8-flash-tts`: Indic voice
> - **Orchestration and hosting:** ADK 2.x (Python) on Cloud Run; Firebase Hosting, Firestore and Auth; Cloud Storage; Secret Manager.
> - **Status:** Gemini 2.5 is legacy, Vertex AI is now "Gemini Enterprise Agent Platform", and `temperature` is deprecated.
>
> All facts are as of 30 Sep 2026. Re-check the [models](https://ai.google.dev/gemini-api/docs/models) and [pricing](https://ai.google.dev/gemini-api/docs/pricing) pages on day 1.

---

## 1. What changed in 2026

Tutorials from 2025 are now out of date on these points:

| Change | Date | Impact on us |
|---|---|---|
| Gemini 2.5 family is **legacy** (access limited to past active users) | 18 Sep 2026 | Use 3.x only |
| **Interactions API** (`client.interactions.create`) is the recommended API; `generateContent` is legacy but supported. New features launch on Interactions only | Dec 2025 → 2026 | Agentic video may need a direct Interactions call inside an ADK function node (⚠️ verify ADK pass-through) |
| `temperature`, `top_p`, `top_k` **deprecated** | 21 Jul 2026 | Don't set them. Use `thinking_level` and prompting (⚠️ verify whether they error or are ignored) |
| Built-in tools + function calling can be **combined** in one request | 18 Mar 2026 | A grounded seller search can also call our store-API functions |
| Structured output **combined with** Search grounding / URL context / code exec / File Search / function calling on Gemini 3 | 2026 | Grounded search that returns typed `Offer[]` JSON |
| **Agentic video understanding** (`processing: "agentic"`) | 1 Sep 2026 | Core of extraction. Google claims up to 88% fewer tokens and ~7% higher quality on long videos |
| **Vertex AI → Gemini Enterprise Agent Platform**; Agent Engine → Agent Runtime; ADK env `GOOGLE_GENAI_USE_ENTERPRISE` | 22 Apr 2026 (Next '26) | Use the new names in the deck |
| **ADK 2.x GA** with graph `Workflow`s; docs moved to adk.dev; Python v2.6.3 | 2026 | We build on 2.x graph workflows |
| **Firebase Studio sunset**: no new workspaces since 22 Jun 2026, shutdown 22 Mar 2027 | 2026 | Don't use it |
| Content API for Shopping **shut down**; Merchant API covers own data only | 18 Aug 2026 | No Google product-offers API → we build sourcing ourselves |

## 2. Models

| Role | Model ID | Status | Price (in → out per 1M tokens) | Key settings |
|---|---|---|---|---|
| Video extraction, page extraction, grounded sourcing, code diffs, report | **`gemini-3.8-flash`** | Stable, GA 2 Sep 2026 | **$0.75 → $3.75** (intro, until 31 Dec 2026; then $1.50 → $7.50) | 1,048,576 in / 65,536 out; `thinking_level` low/medium/high (default medium); supports Search, URL context, Maps, code exec, functions, structured output, File Search, caching, batch |
| Per-part spec resolution, cheap classification, listing title matching | **`gemini-3.5-flash-lite`** | Stable, GA 21 Jul 2026 | $0.30 → $2.50 | Google positions it as the "subagent" model; thinking default `minimal` |
| Compatibility judge (hard reasoning) | **`gemini-3.1-pro-preview`** | **Preview**, no free tier | $2.00 → $12.00 (≤200k ctx) | thinking `high`. **Behind a flag**, falling back to `gemini-3.8-flash` @ `high` |
| Multimodal similarity (part photos + text) | **`gemini-embedding-2`** | GA 22 Apr 2026 | ⚠️ verify in AI Studio | Text 8,192 tokens, ≤6 images/request, video ≤120 s, PDF ≤6 pages; 128–3,072 dims (MRL). **We use 768** (Firestore max 2,048) |
| Spoken explanations | **`gemini-3.8-flash-tts`** (or `-lite-tts`) | GA Sep 2026 | ⚠️ verify | Docs list Hindi, Tamil, Malayalam, Bengali, Telugu, Kannada, Marathi. Prompt-steerable style; ≤2 speakers |
| Audio input | **`gemini-3.5-transcribe`** | GA 26 Aug 2026 | $2.00 → $12.00 (~$0.003/min in) | 85+ languages incl. Indic, code-switching, timestamps, diarisation |
| Optional images (hero illustration, share card) | `gemini-3.1-flash-image` (Nano Banana 2), `gemini-3-pro-image` (Nano Banana Pro) | GA | no free tier | **Never** used for authoritative wiring diagrams |
| Optional browser verification | Computer Use tool on Gemini 3.x Flash | **Preview** | token-based | Stretch S11 only; stops before checkout |

**Pin explicit IDs.** Don't use `gemini-flash-latest` in the judged build: it hot-swaps. Model names live in `backend/app/config.py` (env-overridable).

## 3. Gemini API features we use

### 3.1 Video understanding
- Public YouTube URLs are passed directly; **private/unlisted aren't supported**. The free tier caps YouTube at 8 h/day; the paid tier has no length cap.
- Static mode:
  - ~100 tokens/s at default resolution, ~300 at high
  - 1 fps default, custom `fps`
  - clip with `start_offset` / `end_offset`
  - timestamps in `MM:SS`
- **Agentic mode** (`"processing": "agentic"`), on 3.8/3.7/3.6 Flash and 3.5 Flash-Lite:
  - the model navigates the timeline itself
  - navigation is billed as thinking tokens and loaded content as tool-use tokens
- **Our usage:**
  1. An agentic pass over the whole video returns the BOM with timestamps.
  2. A static high-resolution re-read of short clips handles low-confidence parts (stretch S4).
- **No bounding boxes for video** are documented. For boxes we use image understanding on uploaded frames or blog images only.

```python
from google import genai
client = genai.Client()
it = client.interactions.create(
    model=cfg.MODEL_VIDEO,                      # "gemini-3.8-flash"
    input=[
        {"type": "text", "text": PROMPT_VIDEO_BOM},
        {"type": "video", "uri": youtube_url, "processing": "agentic"},
    ],
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": VideoBom.model_json_schema()},
    generation_config={"thinking_level": "medium"},
)
```

### 3.2 Grounding with Google Search
- Tool `{"type": "google_search"}`. The response carries the queries run, `search_suggestions` HTML (**must be displayed per the ToS**), and `url_citation` annotations.
- **Gemini 3 bills per search query executed.** One prompt may run several.
- Pricing: **5,000 free queries/month on the paid tier** (shared across 3.x), then **$14 per 1,000**. **Not available on the free tier.**
- The API has no region or domain-filter parameters, which suits **open seller discovery**: any Indian shop Google has indexed can appear, including new ones. We bias toward India through the prompt ("price in INR", "ships in India", aliases). Afterwards we filter by page type, currency and a **blocklist** only, with no allow-list. Trust comes from onboarding checks ([06-sourcing-and-seller-data.md](06-sourcing-and-seller-data.md)).

### 3.2b Web Risk API (seller safety)
- `uris.search` checks a URL against Google's malware, social-engineering and unwanted-software lists.
- **Free up to 100,000 calls/month**, then $0.50 per 1,000 ([pricing](https://cloud.google.com/web-risk/pricing)).
- Used once per newly discovered seller domain, re-checked weekly. Any hit blocks the seller.
- It's a Google-native safety layer for open discovery.

### 3.3 URL context
- Tool `{"type": "url_context"}`: up to **20 URLs/request**, 34 MB each. Reads HTML, PDF, images, JSON.
- **Doesn't support** YouTube, paywalled or login pages, or localhost. Some JS-heavy stores (Amazon.in, Robu's Next.js front end) may fail, so we read `url_retrieval_status` and fall back.
- Used for: the blog and Instructables pages, the GitHub README and raw files, datasheet PDFs, and seller product pages during verification.

### 3.4 Structured output
- `response_format` with a JSON Schema generated from Pydantic.
- Supported keywords include `enum`, `required`, `minimum`/`maximum`, `items`, `minItems`/`maxItems` and `format`.
- All our schemas are in [04-prompts-and-schemas.md](04-prompts-and-schemas.md).

### 3.5 Function calling
- Parallel and compositional calls.
- `tool_choice`: `auto` | `any` | `none` | `validated` (schema-enforced).
- Can be mixed with built-in tools on Gemini 3.

### 3.6 Thinking
- `thinking_level`: `minimal` (Flash-Lite), `low`, `medium`, `high`.
- `thinking_summaries: "auto"` gives short summaries. We **stream these into the trace UI** as "what the agent is checking".

### 3.7 Grounding with Google Maps (stretch S2)
- Tool `{"type": "google_maps"}` with lat/lng. Billed per query (5,000 free, then $14/1k).
- **Must show Google Maps attribution.**
- The docs say it "may not be available in all regions", so ⚠️ **test from an Indian location on day 1**.

### 3.8 File Search (managed RAG)
- Store with `embedding_model = gemini-embedding-2`. Indexing is billed at embedding rates; **storage is free**; querying costs only the retrieved tokens.
- 1 GB free / 10 GB Tier 1; ≤100 MB per file.
- We index ~60 datasheets (ESP32, ESP8266, ATmega328P, RP2040, BME280/BMP280, SSD1306/SH1106, A4988/DRV8825/TMC2209, HC-SR04, DHT11/22, DS18B20, MPU6050, WS2812B…) plus our **known-substitutions notes**.
- The judge cites `file_citation` with page numbers.

### 3.9 Caching, Batch, Flex
- **Implicit caching** is on by default (min 4,096 tokens on 3.x). Put the long shared context first: system prompt + project summary + KG excerpt.
- **Explicit caching isn't supported in the Interactions API.**
- **Batch** (50% off) and **Flex** (`service_tier: "flex"`, 50% off, 1–15 min latency) are for nightly price refreshes of saved BOMs, never the live path.

## 4. Agent Development Kit (ADK) 2.x

- **Language:** Python (v2.6.x). TypeScript also exists, but our agent logic, rules engine and eval are Python.
- **Workflow style:** 2.x **graph `Workflow`**. Nodes are LLM agents, plain Python functions, tools or nested workflows, with conditional edges from router nodes and a **human-input node** for the confirmation step. Template agents (`SequentialAgent`, `ParallelAgent`, `LoopAgent`) are still available. We use a `ParallelAgent`-style fan-out (or an async gather in a function node) for per-part sourcing.
- **Built-in tool limitation:** historically `google_search` had to be alone in an agent. The docs say this applies to ADK Python ≤ v1.15.0, but we still:
  - wrap search in its own agent exposed via `AgentTool`, or
  - set `bypass_multi_tools_limit=True`

  ⚠️ Verify with 3.8 Flash.
- **Sessions:** in-memory for dev; database session service for prod (Firestore-backed or SQL). Session **state** keys carry `job_id`, `country`, `pin` and `lang`.
- **Artifacts:** a GCS artifact service (`gs://bs-artifacts`) for frames, datasheets and exports.
- **Plugins/callbacks:** `ReflectAndRetryModelPlugin` retries model errors. Our own `after_agent` callback writes trace events to Firestore.
- **Evaluation:** `adk eval` with evalsets. Criteria:
  - `tool_trajectory_avg_score`
  - `rubric_based_final_response_quality_v1`
  - `hallucinations_v1`
  - `safety_v1`

  See [../03-delivery/02-evaluation-plan.md](../03-delivery/02-evaluation-plan.md).
- **Deploy:** our own Dockerfile + `gcloud run deploy`, with ADK's `get_fast_api_app()` mounted in FastAPI (`web=False`).
- **Observability:** ADK OpenTelemetry → Cloud Trace. A screenshot of the trace goes in the deck.
- **A2A / MCP:** ADK can expose agents via A2A (`to_a2a`) and tools as an MCP server (stretch S12).

## 5. Google Cloud and Firebase

| Service | Use | Key config / limits |
|---|---|---|
| **Cloud Run** (service `bs-api`) | API + workflow | `asia-south1`, instance-based billing, `--timeout=3600`, `--concurrency=10`, `--min-instances=1` during judging, `--max-instances=5`, 2 vCPU / 2 GiB. Free tier: 240k vCPU-s + 450k GiB-s/month (instance-based) |
| **Cloud Run job** `bs-compile` | `arduino-cli compile` of code diffs | Image with cores pre-installed (arduino:avr, esp32:esp32, esp8266:esp8266, rp2040); 2 vCPU / 4 GiB; task timeout 300 s |
| **Firebase Hosting** | SPA + rewrite `/api/**` → `bs-api` | **60 s hard timeout on rewrites**, so only short calls go through Hosting |
| **Firestore** (Native, `asia-south1`) | Jobs, events, parts, listings cache, KG, BOM library, vectors | Free: 1 GiB, 50k reads/day, 20k writes/day. Doc ≤ 1 MiB. Vector ≤ 2,048 dims, `find_nearest` with pre-filters |
| **Firebase Auth** | Optional Google sign-in (save BOMs, vote) | Anonymous by default for the demo |
| **Cloud Storage** | Frames, datasheets, exports, compile logs | Bucket `bs-artifacts-<project>`, lifecycle delete after 30 days for `jobs/` |
| **Secret Manager** | `GEMINI_API_KEY`, `DIGIKEY_CLIENT_*`, `MOUSER_API_KEY`, `YOUTUBE_API_KEY`, `UCP_AGENT_PROFILE_URL` | Mounted via `--set-secrets` |
| **Cloud Logging / Trace** | Structured logs, agent traces | Log `job_id` on every line |
| **Artifact Registry** | Container images | `asia-south1-docker.pkg.dev/<project>/bs` |
| **Cloud Build** / GitHub Actions | CI/CD | See [../03-delivery/01-deployment-and-devops.md](../03-delivery/01-deployment-and-devops.md) |
| *(optional)* **Cloud Tasks** | Durable job execution | Upgrade path |
| **Web Risk API** | Safety check for every newly discovered seller domain | Free ≤ 100k lookups/month |
| **Cloud Scheduler** + Cloud Run job `bs-discover` | Nightly open seller-discovery scan (Batch/Flex grounding); price refresh of library BOMs | Should-level; the on-demand discovery path works without it |

**Considered and skipped:**

| Tool | Why skipped |
|---|---|
| Genkit | Redundant with ADK |
| Firebase Studio | Being sunset |
| Managed Agents / Antigravity agent | Preview churn: the 05-2026 version shuts down 5 Oct |
| Deep Research on the interactive path | Takes minutes |
| Document AI | Gemini reads PDFs natively |
| Video Intelligence API | Superseded by Gemini video |
| Cloud Translation | Gemini outputs Indic languages directly |
| Vertex AI Search / RAG Engine | File Search + Firestore vectors are enough |

## 6. Commerce and UI protocols (Google-led)

| Protocol | What it is | Our use |
|---|---|---|
| **UCP (Universal Commerce Protocol)** (Google + Shopify, Jan 2026) | Merchants publish `/.well-known/ucp`. Shopify stores expose an MCP endpoint with `search_catalog`, `lookup_catalog`, `get_product` | **Used in the MVP** as sourcing Tier A for Shopify-based Indian stores (Robocraze, Quartz…). A strong "Google protocol" story. See [06-sourcing-and-seller-data.md](06-sourcing-and-seller-data.md) |
| **A2UI v0.9** (Apr 2026) | Declarative agent-generated UI; official React renderer | Stretch S7 |
| **AG-UI** + CopilotKit | Agent↔frontend event/state protocol; Google blog shows ADK + AG-UI | Optional transport if we add SSE |
| **A2A v1.0** | Agent-to-agent protocol | Pitch: "seller agents" future |
| **AP2** | Agent payment mandates (UPI on the roadmap) | Pitch only |
| **NPCI Unified Agent Protocol** (India) | Agentic UPI payments framework (announced around GFF, Sep 2026) | Pitch only |

## 7. Access-mode decision: Gemini Developer API vs Agent Platform

| | Gemini Developer API (chosen) | Agent Platform (ex-Vertex) |
|---|---|---|
| Auth | API key in Secret Manager | Service account / ADC |
| New features | First (Interactions, agentic video, File Search) | Later |
| Grounding | Paid tier only | Available; same 5k free + $14/1k |
| Data use | Paid tier: not used to improve Google products | Enterprise terms |
| Switch cost | ADK: set `GOOGLE_GENAI_USE_ENTERPRISE=True` + project/location | — |

**Billing tiers** (Gemini API):

| Tier | Requirement | Spend cap |
|---|---|---|
| Tier 1 | Billing linked | $250 |
| Tier 2 | $100 paid + 3 days | $2,000 |
| Tier 3 | $1,000 + 30 days | — |

Set a **project spend cap** (feature since Mar 2026).
