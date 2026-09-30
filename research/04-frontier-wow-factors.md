# Bharat Sourcer: Frontier "Wow" Features (research as of 30 Sep 2026)

Scope: the latest Google AI capabilities (late 2025 to Sep 2026) and ideas that could make Bharat Sourcer stand out in the Google Cloud AI Builder Cup 2026. Each idea is tied to a technology that exists today, with links I opened. Effort is sized for one developer with about 18 days of build time (S = 1 day or less, M = 2 to 4 days, L = 5 days or more).

---

## 0. Read this first: competition facts checked on the official site

I checked these on aibuildercup.com on 30 Sep 2026 because they affect planning more than any feature does.

| Fact | Detail | Source |
|---|---|---|
| Dates | Registration and team formation Sep 1 to **Oct 11**. Build Sep 7 to **Oct 18**. **Submission deadline Oct 18, 2026**. Evaluation Oct 19 to Nov 6. Finalists announced Nov 7. Grand Finale in Singapore Dec 4. | https://aibuildercup.com |
| Judging | Technical Merit & Gen AI Implementation 40%, Problem Alignment & Impact 25%, Innovation & Creativity 25%, UX & Solution Design 10% | https://aibuildercup.com/themes.html |
| Mandatory tech | Gemini or Gemma models. Deploy on Google Cloud through Cloud Run or Firebase. Agent Platform, Antigravity or AI Studio are also allowed. | https://aibuildercup.com/themes.html |
| Deliverables | Deployed prototype link, demo video under 3 min, **public GitHub repo**, PDF proposal / presentation deck, chosen problem statement | themes.html and https://aibuildercup.com/Faqs.html |
| Themes | BFSI, Retail & Commerce, Manufacturing, Media/Content, Future of Work, **Sustainability & Social Impact** | themes.html |
| **Eligibility** | **JAPAC region only. "All team members must be based out of JAPAC region itself."** The FAQ says UK residents are not eligible. **Teams must have 2 to 4 members; solo entries are not allowed.** Working professionals only, no students. Only projects started after the program launched count. | https://aibuildercup.com/Faqs.html |

**Action item:** the FAQ bars entrants based outside JAPAC and requires a team of at least 2 by Oct 11. If you're based in the UK, confirm eligibility with the organisers (Discord: https://discord.gg/x5GRzJbKpa) before putting 18 days into this. A teammate based in India could also resolve the team-size rule. Everything below assumes eligibility is sorted.

**Theme fit:** Bharat Sourcer fits **Retail & Commerce** (discovery and substitution across Indian sellers) and **Sustainability & Social Impact** (fewer imports, local sourcing, reuse of e-waste and second-hand parts). Pick one as the primary category and use the other in the narrative.

---

## 1. The 2026 Google AI landscape relevant to this build

All of the following comes from the Gemini API models page (https://ai.google.dev/gemini-api/docs/models), the changelog (https://ai.google.dev/gemini-api/docs/changelog) and Google blog posts.

**Models (stable unless marked):**
- `gemini-3.8-flash`: newest and strongest Flash, GA in September 2026. Built for "long-horizon software engineering, autonomous agents, and complex enterprise workflows." Use it as the orchestrator and compatibility judge.
- `gemini-3.7-flash` (GA Sep 2026), `gemini-3.6-flash` (GA Jul 2026) and `gemini-3.5-flash` (GA at I/O, May 19 2026).
- `gemini-3.5-flash-lite`: described as a "low-latency, highly cost-effective subagent option." Use it for the fan-out sub-agents, one per part.
- `gemini-3.1-pro-preview` is the only Pro model you can call. **Gemini 3.5 Pro is still unreleased.** Google said on Jul 21 it was "testing with partners" (https://letsdatascience.com/news/gemini-35-pro-launch-remains-unconfirmed-a09db704). Do not plan around it.
- `gemini-3.8-live` and `gemini-3.8-live-extended-thinking`: real-time voice models, GA Sep 15 2026. They switch among **97 languages** mid-conversation (https://alphasignal.ai/news/google-s-gemini-3-8-live-adds-real-time-reasoning-to-voice-ai).
- `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`: the docs mark **Hindi, Tamil, Malayalam, Bengali, Telugu, Kannada and Marathi** as supported (https://ai.google.dev/gemini-api/docs/speech-generation).
- `gemini-3.5-transcribe` and `-live`: speech-to-text with diarisation, GA August 2026.
- Image models: **Nano Banana 2** (`gemini-3.1-flash-image`), **Nano Banana 2 Lite** and **Nano Banana Pro** (`gemini-3-pro-image`, better for "complex layouts" and structured graphics).
- Video models: **Gemini Omni 1.1 Flash** (GA Aug 2026; any-to-video with native audio) and Veo 3.1 / 3.1 Lite (preview).
- `gemini-embedding-2`: GA April 2026. Puts text, image, video, audio and PDF in one embedding space, supports 100+ languages and uses MRL dimensions from 128 to 3072 (https://ai.google.dev/gemini-api/docs/embeddings).
- Gemma 4 (Apr 13 2026): E2B, E4B, 26B MoE and 31B, with image understanding and on-device Android support through AICore / ML Kit GenAI (https://infoq.com/news/2026/04/gemma-4-android-ai-inference).
- Agents available through the API: `deep-research-preview-04-2026` / `deep-research-max`, `antigravity-preview-09-2026` (a managed general agent that plans, runs code and browses), and **Computer Use** on Gemini 3.x (https://ai.google.dev/gemini-api/docs/computer-use).

**Platform features:**
- **Agentic video understanding** (Sep 1 2026): set `processing: "agentic"`.
- **Agentic Vision** for images (Feb 2026): a think, act, observe loop that crops, zooms and annotates with code.
- **Grounding with Google Maps** (Gemini 3 support since Mar 2026).
- **URL context** tool, **File Search** (multimodal since May 2026), **Interactions API** (the unified model and agent interface), **Managed Agents** and **Webhooks**.
- **ADK v2.4.0** (Jul 7 2026): Python, TypeScript, Go, Java and Kotlin; workflows can be used as tools; ManagedAgent (https://forkast.news/google-adk-v2-4-0-lets-agents-compose-entire-workflows-as-tools/).
- **Vertex AI is now the "Gemini Enterprise Agent Platform"**, announced at Next '26 in April (https://www.hpcwire.com/aiwire/2026/04/23/google-unveils-gemini-enterprise-agent-platform/). Use the new name in the deck.
- **Cloud Run at Next '26** (Apr 22 2026): RTX PRO 6000 Blackwell GPUs are GA, a fully managed remote MCP server is GA, Cloud Run Instances and ephemeral disk are in preview, and Sandboxes are "coming soon" (https://cloud.google.com/blog/products/serverless/whats-new-for-cloud-run-at-next26).

---

## 2. Idea catalogue

Each idea has what it is, the technology and its status, effort, judge impact (1 to 5), and risks.

### A. Video and multimodal understanding (the core technical showpiece)

#### A1. "Agentic BOM extraction" from long YouTube build videos
- **What:** paste a YouTube link. Gemini watches the video goal-first ("find every component, where it first appears, its part number, quantity and how it is wired") instead of sampling at a fixed frame rate. It also cross-checks the description and linked blog text.
- **Tech:** Gemini API video understanding with `"processing": "agentic"`, available on 3.8, 3.7 and 3.6 Flash and 3.5 Flash-Lite. Public YouTube URLs are accepted directly. Google claims "reduces analysis costs by up to 66% and token consumption by up to 88%, while improving accuracy by up to 7%" (blog, Sep 1 2026: https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-agentic-video-in-gemini/; docs: https://ai.google.dev/gemini-api/docs/video-understanding). **Status: generally available in the Gemini API and AI Studio. No extra fee beyond tokens.**
- **Limits:** public videos only (no private or unlisted). The free tier allows 8 hours of YouTube per day. Agentic mode can raise time-to-first-token on short clips, so use `static` with `fps` and `media_resolution: high` for videos under about 10 minutes, where small part markings matter.
- **Effort:** S. This is your baseline pipeline anyway.
- **Judge impact:** 5. The feature was announced 4 weeks ago, so almost no other entry will use it. Say "agentic video understanding" by name in the demo.
- **Risk:** hallucinated part numbers. Mitigate with A3 and B-series verification. Ask for strict JSON: `{part, qty, evidence: [{t: "MM:SS", source: "frame|audio|description"}], confidence}`.

#### A2. "Show me the part": timestamped evidence strip
- **What:** each BOM row gets a thumbnail and a "▶ 03:42" chip. Clicking it seeks an embedded YouTube player to the moment the part appears or is named. This makes provenance visible ("the AI didn't make this up; here is where it saw it").
- **Tech:** timestamps from A1 in `MM:SS` (the docs say "timestamps are added every second"). Use the YouTube IFrame Player API `seekTo()` so you never download the video, which avoids YouTube ToS problems.
- **Effort:** S.
- **Judge impact:** 5 for UX and trust. It demos very well in a 3-minute video.
- **Risk:** timestamps may be off by a few seconds. Show a small window ("03:40 to 03:45").

#### A3. Pixel-precise bounding boxes on the part (uploaded videos, blog images and datasheets)
- **What:** draw a box around the exact component in a frame or blog photo, then crop and zoom into markings (for example "ADS1115" printed on the chip) to confirm the part number.
- **Tech:** Gemini object detection returns `box_2d` as `[ymin, xmin, ymax, xmax]` normalised to 0 to 1000, plus segmentation polygons (https://ai.google.dev/gemini-api/docs/image-understanding). **Agentic Vision** (Gemini 3 Flash, Feb 2026) adds a think, act, observe loop in which the model writes Python to "crop, zoom, annotate, or calculate over the image" and gets 5 to 10% better on vision benchmarks (https://www.noqta.tn/en/news/google-gemini-3-flash-agentic-vision-2026).
- **Important caveat:** the video docs **do not document bounding boxes for video**. For YouTube, don't try to get boxes on the stream. Use them on (a) user-uploaded MP4s, where you extract frames at the A1 timestamps with ffmpeg on Cloud Run, (b) blog images fetched through URL context, and (c) the YouTube thumbnail or storyboard where allowed.
- **Effort:** M.
- **Judge impact:** 4. A "the model zoomed in and read the chip marking" reveal is memorable.
- **Risk:** frame extraction from YouTube is a ToS grey area. Keep it to uploads and blogs.

#### A4. Multi-source fusion: video + description + blog + GitHub repo + audio
- **What:** many maker videos link a GitHub repo or Instructables page. Pull the firmware (`#include <Adafruit_SSD1306.h>`, pin definitions) and the text BOM, then reconcile them with what the video shows. Disagreements get flagged ("video shows a 0.96" OLED but the code initialises a 128x64 SH1106").
- **Tech:** URL context tool (up to 20 URLs per request, 34 MB each; HTML, PDF and images supported; **YouTube is not supported through URL context**, so use the video path for that) combined with Google Search grounding (https://ai.google.dev/gemini-api/docs/url-context). For audio-only input (podcast or voice note), use `gemini-3.5-transcribe`.
- **Effort:** M.
- **Judge impact:** 4. Shows genuine multi-agent reasoning rather than a single prompt.
- **Risk:** scope creep. Restrict to YouTube description links and one repo.

### B. Sourcing intelligence and verification

#### B1. Visual part matching with Gemini Embedding 2 (cross-modal)
- **What:** embed the video frame or crop of the original part and the product images from Indian sellers into one space. Rank candidates by visual and text similarity, which catches "same module, different listing title" (for example an HC-SR04 clone listed as "Ultrasonic Distance Sensor Module").
- **Tech:** `gemini-embedding-2` GA with text, image, video, audio and PDF in one space. Up to 6 images per request and 8,192 tokens. Use 768 dimensions for cost (https://ai.google.dev/gemini-api/docs/embeddings). Store vectors in Firestore vector search or AlloyDB/pgvector (you've used Pinecone before, but staying on Google gives a better "Google stack" score).
- **Effort:** M.
- **Judge impact:** 4. It's a real multimodal RAG story, and multimodal embeddings are a 2026 capability.
- **Risk:** seller images are noisy (stock photos). Use it as one signal among several, not the only one.

#### B2. Datasheet-grounded compatibility judge ("electrical diff")
- **What:** for each substitution, fetch both datasheets (PDF) and produce a structured diff: supply voltage, logic level (3.3 V vs 5 V), interface (I²C address, SPI), pinout, current draw and physical size. Output a verdict (Drop-in / Minor change / Needs adapter / Incompatible) plus the exact wiring and code changes.
- **Tech:** `gemini-3.8-flash` with URL context on PDFs and File Search (multimodal since May 2026) to cache common datasheets. Enforce a structured output schema.
- **Effort:** M.
- **Judge impact:** 5. This is the core IP and the "technical merit" of the product. Show the reasoning trace.
- **Risk:** hard-to-find datasheets. Fall back to the manufacturer's family datasheet and show "confidence: medium."

#### B3. Simulation-verified code patch (strongest differentiator)
- **What:** when a substitution needs code changes (for example DHT11 to DHT22, SSD1306 to SH1106, NodeMCU to ESP32-C3 pin remap), the agent writes the patched sketch **and runs it in a virtual circuit**, then shows a "✅ Simulated: serial output matches expected" badge.
- **Tech:** Wokwi CI and CLI simulate firmware on virtual hardware, with scripted automation ("push buttons, change the state of the sensors, check the serial output"). **Wokwi has an experimental MCP server** (`wokwi-cli mcp`) that lets AI agents run simulations (https://docs.wokwi.com/wokwi-ci/getting-started, https://docs.wokwi.com/wokwi-ci/mcp-support). Free tier: 50 simulation minutes per month; Hobby: 200.
- **Effort:** M to L. Limit it to Arduino Uno / ESP32 plus 3 or 4 common sensors and displays for the demo.
- **Judge impact:** 5. "The agent didn't just suggest a cheaper part, it proved the code still works" is exactly the kind of closed-loop verification judges reward under technical merit.
- **Risk:** the MCP server is experimental, and not every part has a Wokwi model. Scope to supported parts and show "not simulatable" otherwise. Cloud Run Sandboxes (coming soon) or a Cloud Run job can host `wokwi-cli`.

#### B4. Live price and stock verification with a Computer Use agent
- **What:** for the top pick per part, a browser agent opens the Indian seller page, checks stock, price, shipping-to-PIN and GST, and returns a screenshot as evidence. Stretch: add to cart, then stop and hand over to the user.
- **Tech:** Gemini API **Computer Use on Gemini 3.x** (3.8 Flash current). It supports browser, Android and desktop environments, includes an `intent` field per action, configurable safety policies, optional **prompt-injection detection on screenshots**, and `require_confirmation` for sensitive steps (https://ai.google.dev/gemini-api/docs/computer-use). **Status: preview.** Run Playwright headless Chromium in a Cloud Run container.
- **Effort:** M.
- **Judge impact:** 4. Highly visual in a demo, and it uses a Google agentic model, which matters for the 40% criterion.
- **Risk:** slow (tens of seconds per site), anti-bot pages and CAPTCHAs. Use it only as "Verify live" on demand, cache the result, and never make it the main search path. Stop before checkout so no real money moves.

#### B5. Deep Research mode for hard-to-find parts
- **What:** for obscure US/UK-only parts (Adafruit or SparkFun breakout boards, Pololu drivers), launch a Deep Research job that finds equivalent ICs, Indian distributors, and forum reports of substitutions working.
- **Tech:** `deep-research-preview-04-2026` / `deep-research-max-preview-04-2026` through the Interactions API, with webhooks for completion (Gemini API changelog). Launch context: https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api
- **Effort:** S to M.
- **Judge impact:** 3.
- **Risk:** latency of minutes. Present it as an async "research card" that fills in later.

### C. Generative UI and agent transparency (10% UX plus the "wow" in the video)

#### C1. Agent-driven UI with A2UI + AG-UI + CopilotKit on ADK
- **What:** the agent streams *UI*, not just text: a BOM table that fills in row by row, substitution cards with Accept/Reject buttons (human-in-the-loop), a compatibility diff widget, and a map card. The user can edit a row (for example "I already have this") and the agent reacts through shared state.
- **Tech:**
  - **A2UI v0.9** (Apr 17 2026), Google's open generative-UI protocol. Agents send declarative component JSON that the client renders with native widgets. The official **React renderer** has launched, alongside Flutter, Lit and Angular. The v0.9 approach is "prompt-first": the schema lives in the system prompt and a validator self-corrects (https://www.copilotkit.ai/blog/a2ui-whats-new-in-google-generative-ui-spec).
  - **AG-UI** handles transport and state sync. Google's own guide pairs **ADK + AG-UI + CopilotKit** with generative UI, shared state, human-in-the-loop and frontend tools. Starter: `npx copilotkit@latest create -f adk` (https://developers.googleblog.com/delight-users-by-combining-adk-agents-with-fancy-frontends-using-ag-ui/).
- **Effort:** M. This matches your React/TypeScript strengths, and ADK has TypeScript.
- **Judge impact:** 5. It's Google's own protocol, it's new, and it's visible.
- **Risk:** protocol churn (v0.9). Pin versions. If A2UI slows you down, AG-UI with custom React components still delivers 80% of the effect.

#### C2. Live agent trace ("mission control" panel)
- **What:** a side panel showing the orchestrator fanning out to N part agents in parallel, each with a status line ("Searching Robu.in… 3 candidates, judging compatibility, verified ✔"). Judges see the multi-agent system working.
- **Tech:** ADK parallel workflows. ADK v2.4 lets workflows be used as tools (https://forkast.news/google-adk-v2-4-0-lets-agents-compose-entire-workflows-as-tools/). Stream events through AG-UI. Cloud Trace / Agent Platform observability are optional.
- **Effort:** S to M.
- **Judge impact:** 4. It makes the technical merit visible to the judges.
- **Risk:** none significant.

#### C3. MCP server: "Bharat Sourcer as a tool"
- **What:** expose `source_bom(url)` and `find_indian_equivalent(part)` as a remote MCP server so Gemini (which now uses MCP app connections, announced Aug 12 2026: https://alphasignal.ai/news/google-s-gemini-hits-1-billion-users-and-adds-14-app-connections), Antigravity, Claude or VS Code can call it. Optionally return an MCP Apps `ui://` resource for a BOM widget.
- **Tech:** Cloud Run fully managed remote MCP server hosting (GA at Next '26).
- **Effort:** S once the core exists.
- **Judge impact:** 3. It's a good "platform, not just an app" slide.
- **Risk:** low.

### D. Voice and Indic language (impact and inclusivity)

#### D1. Multilingual narration and "explain the change" in Indian languages
- **What:** a "🔊 Explain in Malayalam / Hindi / Tamil…" button reads out the build summary and any wiring changes ("Connect the sensor's VCC to 3.3 V, not 5 V…"). This is aimed at students in tier-2 and tier-3 towns who are more comfortable in their own language.
- **Tech:** `gemini-3.8-flash-tts` / `-lite-tts` (GA Sep 2026). The docs mark Hindi, Tamil, Malayalam, Bengali, Telugu, Kannada and Marathi as supported. It is prompt-steerable ("explain like a friendly lab instructor") and supports up to 2 speakers per request (https://ai.google.dev/gemini-api/docs/speech-generation; AlphaSignal, "Gemini 3.8 Flash TTS With Prompt-Directed Emotional Speech": https://alphasignal.ai/news/google-ships-gemini-3-8-flash-tts-with-prompt-directed-emotional-speech).
- **Effort:** S.
- **Judge impact:** 4 for the "Bharat" impact story at very little cost.
- **Risk:** check technical-term pronunciation. Keep part numbers in English.

#### D2. Live voice "Build buddy" (Gemini 3.8 Live)
- **What:** hold-to-talk in Hinglish ("bhai, ye wala sensor Chennai mein kahan milega?"), or point the phone camera at your workbench, and the agent answers in real time and updates the BOM through tool calls.
- **Tech:** `gemini-3.8-live` GA (Sep 15 2026). It switches among 97 languages without configuration, runs background tool calls and accepts image input. Use ephemeral tokens for browser clients (https://ai.google.dev/gemini-api/docs/live).
- **Effort:** M.
- **Judge impact:** 4.
- **Risk:** audio in a noisy demo video, and Live pricing isn't published yet (per AlphaSignal). Keep the session short.

#### D3. WhatsApp channel
- **What:** forward a YouTube link to a WhatsApp number and get back the INR BOM as a formatted message, plus a PDF and a voice note in your language. WhatsApp is how India shares links.
- **Tech:** Meta WhatsApp Cloud API webhook to Cloud Run. Not Google, but it's only a delivery channel; Gemini does the AI work.
- **Effort:** M. Meta business verification can be slow, so start early or use the test number.
- **Judge impact:** 3 to 4. Strong for India realism.
- **Risk:** Meta onboarding time. Leave it for the pitch if it's blocked.

### E. Physical world, local markets and sustainability

#### E1. "Scan my parts bin": skip what you already own
- **What:** take a photo of your drawer or breadboard. The app detects modules (Arduino Nano, HC-05, 18650 cells) and marks matching BOM rows "✔ You have this," removing them from the cost. It's the simplest sustainability story: the cheapest part is the one you already own.
- **Tech:** Gemini 3.8 Flash object detection with bounding boxes and Agentic Vision zoom for markings. The on-device option is Gemma 4 E2B/E4B on Android (AICore / ML Kit GenAI) or **Firebase AI Logic hybrid inference** in Chrome (Gemini Nano, `PREFER_ON_DEVICE`, text+image, preview, desktop Chrome only: https://firebase.google.com/docs/ai-logic/hybrid/web/get-started).
- **Effort:** S (cloud) / L (on-device).
- **Judge impact:** 4. A good visual demo moment, with boxes drawn on the photo.
- **Risk:** the on-device path is fiddly. Use cloud detection and mention Gemma 4 on-device as future work.

#### E2. Physical-market finder with Google Maps grounding
- **What:** for each part, offer "or pick it up today" with the nearest electronics markets and shops, such as Lamington Road (Mumbai), SP Road (Bengaluru), Ritchie Street (Chennai), Lajpat Rai Market / Bhagirath Palace (Delhi) and Kochi's Broadway, with hours, ratings and a map.
- **Tech:** Grounding with Google Maps, supported on all Gemini 3 models. Enable with `tools: [{type: "google_maps"}]` and pass lat/lng. Billing is per search query for Gemini 3. You **must show Google Maps attribution** right after the generated content. The docs say it "may not be available in all regions" and give no India-specific note, so **test it from an India location early** (https://ai.google.dev/gemini-api/docs/maps-grounding).
- **Effort:** S.
- **Judge impact:** 4. It's a very "Bharat" feature, and physical markets are how Indian makers actually buy.
- **Risk:** Maps can't tell you whether a shop has a specific part in stock. Present results as "shops likely to carry…" and suggest calling first.

#### E3. Carbon and import impact card
- **What:** each BOM shows "₹ saved vs importing (incl. customs duty + intl shipping)," "days saved," and an estimated shipping CO₂ comparison (international air parcel vs domestic courier). A "local-sourcing score" counts how many parts are made or assembled in India.
- **Tech:** Gemini computes the numbers with code execution from simple emission factors. Present them as estimates and cite the source of each factor.
- **Context stats for the pitch:** India's electronics imports hit a record **$116.17 billion in FY2025-26**, up 17.76%, with domestic value addition of only 18 to 20% (The Week, Apr 16 2026: https://www.theweek.in/news/biz-tech/2026/04/16/electronics-trade-deficit-fy25-26.html). India generated **13.97 lakh tonnes of e-waste in FY2024-25**, up from 12.54 lakh tonnes, per CPCB figures given in Parliament (https://test.uniindia.com/over-13-97-lakh-tonnes-e-waste-generated-in-2024-25-cpcb-data/parliament/news/3542425.html).
- **Effort:** S.
- **Judge impact:** 3 to 4. It supports the Sustainability theme and the 25% impact score.
- **Risk:** don't overclaim precision. Label everything as an estimate.

#### E4. Second-hand and salvage suggestions
- **What:** "This 28BYJ-48 stepper and ULN2003 driver is common in old printers. Salvage it," or search OLX / Facebook Marketplace for used dev boards.
- **Tech:** Gemini with Google Search grounding.
- **Effort:** S (suggestions only).
- **Judge impact:** 3.
- **Risk:** the quality of scraped listings. Keep it to suggestions.

### F. Agentic commerce and payments (mostly pitch-level)

#### F1. Unified cart and hand-off checkout
- **What:** group the BOM by seller to minimise shipping ("Buy 6 items from Robu.in, 2 from Robokits; saves ₹120 shipping"), then deep-link to each cart.
- **Tech:** plain optimisation in Gemini code execution or Python.
- **Effort:** S to M.
- **Judge impact:** 3 (practical UX).
- **Risk:** low.

#### F2. Agentic payments (future vision, don't build live)
- **What is current:**
  - **NPCI Unified Agent Protocol (UAP)** will let AI agents make small UPI payments without per-transaction approval. It builds on **UPI Circle** (delegation) and **UPI Reserve Pay** (fund blocking, bank cap ₹10,000 for up to 90 days). It was expected to be unveiled at Global Fintech Fest, Mumbai, in early September 2026 (Reuters via The Star, Sep 1 2026: https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say; Outlook Business, Jul 9 2026: https://www.outlookbusiness.com/news/india-plans-ai-powered-upi-payments-framework-through-unified-agent-protocol).
  - Razorpay, Cashfree and PayU shipped agentic payments on UPI Reserve Pay in February 2026. Swiggy built MCP servers exposed to ChatGPT, Claude and Gemini. Bigbasket enabled conversational commerce with embedded UPI (https://stellagent.ai/insights/india-agentic-commerce-fintech-payment).
  - **Google UCP (Universal Commerce Protocol)** is heading to India through Flipkart as its first international rollout (https://stellagent.ai/insights/google-ucp-india-flipkart-launch; InfoQ: https://infoq.com/news/2026/01/google-agentic-commerce-ucp).
  - **AP2 (Agent Payments Protocol)** has 60+ payments organisations and is "fully compatible" with **A2A v1.0** (A2A reached its first stable spec at its one-year anniversary; 150+ organisations and 22k GitHub stars per the Linux Foundation: https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year).
  - Google Cloud India (Sep 24 2026) highlighted **Pine Labs** AI agents for SMB commerce integrated with UPI (https://yourstory.com/2026/09/google-cloud-brings-gemini-deeper-into-india-businesses).
- **For Bharat Sourcer:** include a pitch slide showing a "one-tap buy whole BOM" future, with a UAP / Reserve Pay mandate, UCP or A2A to seller agents, and AP2 mandates for auditability. Hackathon hobbyist-component sellers (Robu, Robocraze etc.) don't expose UCP or MCP endpoints today, so building this live isn't realistic.
- **Effort:** a mock A2A "seller agent" is M. The slide is S.
- **Judge impact:** 3 as vision; building it gives little in return.
- **Risk:** don't process real payments. Regulatory surface.

#### F3. ONDC / Beckn as a seller source
- **What:** query India's open commerce network for electronics sellers.
- **Reality check:** joining ONDC as a buyer app requires registry subscription, cryptographic signing and Pramaan certification. The toolbox (https://www.ondc.org/pramaan/toolbox.html) offers sandbox, signing and log-validation tools, but I found **no public search API a hackathon could just call**. BecknGPT exists as an open-source ChatGPT-based demo on Beckn (https://indiaai.gov.in/article/beckngpt-exploring-future-shopping-trends-with-beckn-in-fide-s-ai-collaboration). Beckn is open, and the ONDC org is on GitHub (https://github.com/ONDC-Official).
- **Effort:** L for a real integration.
- **Judge impact:** 3.
- **Recommendation:** pitch-only ("the A2A seller adapter is ONDC-ready"), or a mock Beckn `search` call against a sandbox if time allows.

### G. Generative media

#### G1. Updated wiring diagram for the substituted build
- **What:** after substitutions, show a clear "before vs after" wiring diagram with changed wires highlighted.
- **Recommended tech (hybrid):** generate the diagram **deterministically** as SVG or Mermaid, or from a Wokwi `diagram.json` (which B3 already produces), because generative image models can draw pins wrongly. Then optionally use **Nano Banana Pro** (`gemini-3-pro-image`, strongest on "complex layouts" and multilingual text rendering, up to 4K) to render a friendly "hero" illustration of the finished build with Indian parts, clearly labelled "illustration" (https://www.analyticsvidhya.com/blog/2026/02/nano-banana-2-vs-nano-banana-pro/).
- **Effort:** S (Wokwi diagram render) / S (Nano Banana hero image).
- **Judge impact:** 4. Using Google image models counts toward "best use of Google AI tools."
- **Risk:** a generated wiring image with wrong connections would hurt credibility. Never present an AI-generated image as the authoritative schematic.

#### G2. Localised "build card" and share image
- **What:** a one-page poster (Nano Banana 2 for speed) listing the project name, total ₹ cost, savings and a QR code to the BOM, in English plus a regional language, for WhatsApp sharing.
- **Effort:** S.
- **Judge impact:** 2 to 3.

#### G3. Demo-video assets
- **What:** use Gemini Omni 1.1 Flash (GA Aug 2026, any-to-video with native audio) or Veo 3.1 for the 5-second intro or problem-framing shot in your 3-minute video (for example "a maker in Kochi staring at a $40 Adafruit cart…"). Keep the product footage real.
- **Effort:** S.
- **Judge impact:** 2 (polish).

### H. Community and data flywheel

#### H1. Crowd-verified "India BOM" library
- **What:** every completed BOM is saved (Firestore) and becomes a public page ("Bharat BOM for 'ESP32 weather station' by Andreas Spiess, 18 parts, ₹1,840"). Users vote 👍 "substitution worked" or 👎, attach a photo, and those votes feed back into ranking. On the next paste of the same video, results are instant.
- **Tech:** Firestore plus Gemini Embedding 2 to deduplicate "same project, different link." Firebase Auth with Google sign-in.
- **Effort:** M.
- **Judge impact:** 4. Network effects and defensibility make a strong innovation and impact story.
- **Risk:** cold start. Seed it with 10 to 20 popular projects before submission.

#### H2. Substitution knowledge graph
- **What:** a growing graph of pairs such as "ADS1115 ≈ ADS1015 (lower resolution)," "SH1106 ↔ SSD1306 (driver change)" and "NodeMCU v3 → ESP32-C3 SuperMini (pin remap)," with evidence links.
- **Effort:** M. Pitch-level visualisation only.
- **Judge impact:** 3.

#### H3. Price-drop watch
- **What:** "Watch this BOM" re-checks prices weekly and notifies you when the total drops below your target.
- **Tech:** Cloud Scheduler to Cloud Run job to Gemini re-verification, plus a push or email. This mirrors the "Gemini Spark watches the web" consumer pattern (Jul 6 2026, US-only beta: https://alphasignal.ai/news/google-s-gemini-spark-now-watches-the-web-and-acts-without-being-asked).
- **Effort:** S to M.
- **Judge impact:** 3.

---

## 3. Recommended architecture that shows off the stack

```
[React + CopilotKit / A2UI renderer]  <--AG-UI (SSE)-->  [ADK (TS or Py) orchestrator on Cloud Run]
                                                              |-- VideoAgent: gemini-3.8-flash, processing=agentic (YouTube)
                                                              |-- SourceFusionAgent: URL context + Search grounding (desc, blog, GitHub)
                                                              |-- ParallelWorkflow( per part ) -> PartAgent (gemini-3.5-flash-lite)
                                                              |      |-- seller search tools (scrapers/APIs, cached)
                                                              |      |-- Embedding-2 visual match (Firestore vector)
                                                              |      |-- CompatibilityJudge (gemini-3.8-flash, datasheet PDFs)
                                                              |      `-- [on demand] ComputerUse verifier (Playwright container)
                                                              |-- CodePatchAgent -> Wokwi MCP (simulate) 
                                                              |-- MapsAgent: google_maps grounding (local markets)
                                                              |-- NarratorAgent: gemini-3.8-flash-tts (Indic)
                                                              `-- Firestore: BOM library, votes, cache
Exposed also as: Remote MCP server (Cloud Run) + optional A2A agent card
```

Model choices that come across well in the deck: **3.8 Flash** for reasoning and judging, **3.5 Flash-Lite** for cheap fan-out sub-agents (Google itself positions it as the "subagent option"), **Embedding 2** for multimodal retrieval, **3.8 Flash TTS** for Indic voice, and **Nano Banana Pro** for visuals. Mention that the design follows Google's own model-tiering guidance to control cost. A per-BOM cost figure ("₹0.40 of AI per BOM") is a strong slide.

---

## 4. Ranked shortlist

### Must-have wow features for the MVP (pick 3 or 4)

1. **Agentic video BOM extraction with timestamped "Show me the part" evidence (A1 + A2).** Effort S+S. It's the most current Google capability (announced Sep 1 2026), it's the core of the product, and it looks great on video. Add a confidence indicator and multi-source cross-checking (A4, lite version) to each row.
2. **Generative agent UI with a live multi-agent trace (C1 + C2):** ADK + AG-UI/CopilotKit, with A2UI components if time allows. Effort M. It makes the 40% technical-merit criterion *visible*, uses Google's own open protocols, and plays to your React/TS strengths.
3. **Datasheet-grounded compatibility judge with a code-patch diff (B2), and ideally Wokwi-simulated verification (B3) for 3 or 4 common parts.** Effort M to L. This is the "only we do this" feature: the system proves a substitution works rather than just finding something cheaper.
4. **Bharat layer: Indic TTS narration plus a Google Maps local-market finder (D1 + E2).** Effort S+S. Cheap to build, directly supports the "Bharat" name and the impact score, and uses two more Google capabilities (3.8 Flash TTS, Maps grounding).

*If B3 is too risky, swap in E1 "Scan my parts bin" (S effort, very visual).*

### Stretch (if the MVP is solid by about day 12)
- **E1 Scan my parts bin** (cloud detection with bounding boxes).
- **B1 Embedding-2 visual matching** for candidate ranking.
- **B4 Computer Use "Verify live" button** with screenshot evidence, stopping before checkout.
- **H1 Crowd-verified India BOM library**, seeded with 10 to 20 projects.
- **E3 Import / carbon savings card.**
- **C3 MCP server** exposing Bharat Sourcer as a tool.
- **G1 Wokwi-diagram render** plus a Nano Banana Pro hero image.

### Pitch-only / future vision
- **F2 one-tap agentic checkout** through NPCI UAP / UPI Reserve Pay, UCP (Flipkart) and AP2 mandates over A2A.
- **F3 ONDC/Beckn** seller discovery.
- **D2 Live voice "build buddy"** and **D3 WhatsApp** channel (build only if cheap).
- **Gemma 4 on-device** parts-bin scanning for offline makers and labs.
- **H3 price-drop watch**, **H2 substitution knowledge graph**, and "school and college lab kits" bulk BOMs for Atal Tinkering Labs (an impact angle worth checking before you claim it).

---

## 5. Suggested 18-day plan (solo, adjust for a team)

| Days | Work |
|---|---|
| 1–2 | Registration and team check (eligibility!). Cloud Run + ADK skeleton + CopilotKit ADK starter. Agentic video call returning JSON BOM with timestamps. |
| 3–5 | Seller search tools for 3 or 4 Indian sites (with a cache). Per-part parallel sub-agents. INR BOM table streaming into the UI. |
| 6–8 | Compatibility judge with datasheets. Structured verdicts plus a wiring/code-change diff. YouTube evidence strip. |
| 9–11 | Wokwi MCP simulation for a small curated part set, **or** the parts-bin scan. Maps local markets. Indic TTS. |
| 12–14 | Polish: A2UI cards, agent trace, import-savings card, Firestore library with seeded projects. |
| 15–16 | Hardening: failure modes, caching, cost logging, rate limits. Public GitHub README with architecture diagram. |
| 17–18 | 3-minute video (real footage plus optional Omni/Veo intro), PDF deck, submission. |

---

## 6. Recent AI news to cite in the deck (dated, verified)

| Date | Item | Link |
|---|---|---|
| Sep 26, 2025 | Google blog: ADK + AG-UI + CopilotKit for rich agent frontends | https://developers.googleblog.com/delight-users-by-combining-adk-agents-with-fancy-frontends-using-ag-ui/ |
| Dec 2025 | Interactions API and Deep Research agent opened to developers | https://blog.google/innovation-and-ai/technology/developers-tools/interactions-api/ |
| Jan 2026 | Google launches Universal Commerce Protocol (UCP) for agentic commerce | https://infoq.com/news/2026/01/google-agentic-commerce-ucp |
| Feb 12, 2026 | Agentic Vision in Gemini 3 Flash (think, act, observe with code) | https://www.noqta.tn/en/news/google-gemini-3-flash-agentic-vision-2026 |
| Feb 26, 2026 | Nano Banana 2 released | https://www.analyticsvidhya.com/blog/2026/02/nano-banana-2-vs-nano-banana-pro/ |
| Feb 2026 | Razorpay, Cashfree and PayU ship agentic payments on UPI Reserve Pay | https://stellagent.ai/insights/india-agentic-commerce-fintech-payment |
| Mar 2026 | UCP to launch in India with Flipkart | https://stellagent.ai/insights/google-ucp-india-flipkart-launch |
| Apr 9, 2026 | A2A v1.0 stable; 150+ orgs; AP2 compatible via mandates extension | https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year |
| Apr 13, 2026 | Gemma 4 released (E2B/E4B on-device) | https://infoq.com/news/2026/04/gemma-4-android-ai-inference |
| Apr 16, 2026 | India electronics imports hit a record $116.17B (FY25-26) | https://www.theweek.in/news/biz-tech/2026/04/16/electronics-trade-deficit-fy25-26.html |
| Apr 17, 2026 | A2UI v0.9 with official React renderer | https://www.copilotkit.ai/blog/a2ui-whats-new-in-google-generative-ui-spec |
| Apr 22–23, 2026 | Next '26: Gemini Enterprise Agent Platform (Vertex AI successor); Cloud Run GPUs, managed MCP server | https://cloud.google.com/blog/products/serverless/whats-new-for-cloud-run-at-next26 |
| May 19, 2026 | I/O 2026 "agentic Gemini era": Gemini 3.5 Flash, Omni Flash, Spark agent, Antigravity 2.0; 8.5M developers monthly; 3.2 quadrillion tokens a month | https://blog.google/innovation-and-ai/sundar-pichai-io-2026/ |
| Jul 7, 2026 | ADK v2.4.0: workflows as tools, ManagedAgent | https://forkast.news/google-adk-v2-4-0-lets-agents-compose-entire-workflows-as-tools/ |
| Jul 9, 2026 | NPCI plans a Unified Agent Protocol for AI-agent UPI payments | https://www.outlookbusiness.com/news/india-plans-ai-powered-upi-payments-framework-through-unified-agent-protocol |
| Aug 12, 2026 | Gemini passes 1B MAU; 14 new MCP app connections | https://alphasignal.ai/news/google-s-gemini-hits-1-billion-users-and-adds-14-app-connections |
| Sep 1, 2026 | **Agentic video understanding in Gemini** (up to 88% fewer tokens) | https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-agentic-video-in-gemini/ |
| Sep 1, 2026 | India preparing agentic payments rollout on UPI (Reuters) | https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say |
| Sep 2026 | Gemini 3.8 Flash GA; 3.8 Flash TTS with Indic languages | https://ai.google.dev/gemini-api/docs/changelog |
| Sep 15, 2026 | Gemini 3.8 Live: 97 languages, real-time reasoning voice | https://alphasignal.ai/news/google-s-gemini-3-8-live-adds-real-time-reasoning-to-voice-ai |
| Sep 24, 2026 | Google Cloud deepens Gemini in India (Mumbai/Delhi regions; Pine Labs UPI agents) | https://yourstory.com/2026/09/google-cloud-brings-gemini-deeper-into-india-businesses |
| Aug 2025 (data) | India e-waste 13.97 lakh tonnes FY24-25 (CPCB) | https://test.uniindia.com/over-13-97-lakh-tonnes-e-waste-generated-in-2024-25-cpcb-data/parliament/news/3542425.html |

Suggested pitch line: *"Sep 1, 2026: Google gave Gemini the ability to watch video like an agent. Two weeks later, it could speak Malayalam. We used both so a maker in Kochi can build what a maker in Kansas built, with parts from Lamington Road instead of a $40 import."*

---

## 7. Risks and caveats across the plan

- **Eligibility** (section 0) is the biggest risk. Confirm it before building.
- **Preview features** (Computer Use, Deep Research, Wokwi MCP, A2UI v0.9, Firebase hybrid) can break. Give every one of them a fallback path, and keep the demo happy path on GA features: 3.8 Flash, agentic video, TTS, Maps grounding, Embedding 2.
- **Seller data:** most Indian hobby sellers have no public API. Scraping has ToS and anti-bot risks, so cache results and consider Google Search grounding restricted to seller domains as a lighter-touch discovery method. (Another research track covers this in depth.)
- **Hallucinated part numbers or prices:** always show evidence (timestamp, URL, screenshot) and confidence, and never state a price without a source link and a "checked at" time.
- **Region availability:** the Maps grounding docs say "may not be available in all regions." Gemini Spark / Chrome auto-browse is US-only and excludes the UK and EEA. Test all APIs from the deployment region, and consider Cloud Run in `asia-south1` (Mumbai) to support the India story.
- **Live API pricing** isn't published yet for 3.8 Live, so keep Live out of the critical path.

---

## Sources opened

- https://alphasignal.ai/ (homepage headlines, 30 Sep 2026) and the AlphaSignal articles linked above
- https://aibuildercup.com, https://aibuildercup.com/themes.html, https://aibuildercup.com/Faqs.html
- https://ai.google.dev/gemini-api/docs/models ; /changelog ; /video-understanding ; /image-understanding ; /computer-use ; /maps-grounding ; /url-context ; /embeddings ; /speech-generation ; /live
- https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-agentic-video-in-gemini/
- https://blog.google/innovation-and-ai/sundar-pichai-io-2026/
- https://www.noqta.tn/en/news/google-gemini-3-flash-agentic-vision-2026
- https://www.copilotkit.ai/blog/a2ui-whats-new-in-google-generative-ui-spec
- https://developers.googleblog.com/delight-users-by-combining-adk-agents-with-fancy-frontends-using-ag-ui/
- https://forkast.news/google-adk-v2-4-0-lets-agents-compose-entire-workflows-as-tools/
- https://cloud.google.com/blog/products/serverless/whats-new-for-cloud-run-at-next26
- https://letsdatascience.com/news/gemini-35-pro-launch-remains-unconfirmed-a09db704
- https://infoq.com/news/2026/04/gemma-4-android-ai-inference
- https://firebase.google.com/docs/ai-logic/hybrid/web/get-started
- https://www.analyticsvidhya.com/blog/2026/02/nano-banana-2-vs-nano-banana-pro/
- https://docs.wokwi.com/wokwi-ci/getting-started ; https://docs.wokwi.com/wokwi-ci/mcp-support
- https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- https://stellagent.ai/insights/google-ucp-india-flipkart-launch ; https://stellagent.ai/insights/india-agentic-commerce-fintech-payment
- https://www.outlookbusiness.com/news/india-plans-ai-powered-upi-payments-framework-through-unified-agent-protocol
- https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say
- https://yourstory.com/2026/09/google-cloud-brings-gemini-deeper-into-india-businesses
- https://www.nasdaq.com/articles/google-rolls-out-upgraded-gemini-deep-research-and-opens-agent-access-developers
- https://www.ondc.org/pramaan/toolbox.html ; https://indiaai.gov.in/article/beckngpt-exploring-future-shopping-trends-with-beckn-in-fide-s-ai-collaboration
- https://www.theweek.in/news/biz-tech/2026/04/16/electronics-trade-deficit-fy25-26.html
- https://test.uniindia.com/over-13-97-lakh-tonnes-e-waste-generated-in-2024-25-cpcb-data/parliament/news/3542425.html

*Note: several pages were read through a summarising fetch tool. Before quoting exact figures in the deck, re-open the primary Google docs for model IDs, language lists and limits, since these pages change often.*
