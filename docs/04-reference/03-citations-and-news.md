# Citations, news and statistics

> **In one minute.** This file lists everything worth citing in the deck, the video or the README: research papers (for rigor), dated AI news items (to show we use brand-new capabilities) and impact statistics. All links were opened by the research agents on 30 Sep 2026.

---

## 1. Research papers

| Paper | Venue / year | Result to cite | How we use it |
|---|---|---|---|
| [EmbedAgent / EmbedBench](https://arxiv.org/abs/2506.11003) | ICSE 2026 | Arduino→ESP-IDF migration only **29.4% pass@1**; RAG + compiler feedback improves results | Compile-in-the-loop; stay in the Arduino framework |
| [PCEval](https://arxiv.org/abs/2601.02404v1) | 2026 | 13 LLMs are strong at code and logic but "struggle significantly with… proper pin connections" | Deterministic pin and voltage rules |
| [Skilled AI Agents for Embedded & IoT (IoT-SkillsBench)](https://arxiv.org/pdf/2603.19583) | 2026 | Human-expert skills **42/42** on Arduino; LLM-generated skills inconsistent | Curated KG |
| [DRCY: Agentic Hardware Design Reviews](https://arxiv.org/html/2603.15672) | 2026 | Production multi-agent pin-by-pin datasheet checks with multi-run consensus | Judge ×3, datasheet grounding |
| [pcbGPT](https://arxiv.org/pdf/2606.01188) | 2026 | NL→KiCad pass@1 0.90; failures are missing support parts (59.1%) and wrong interfaces (40%); comparator κ = 0.941 | Extra-parts rule; judge agreement metric |
| [SchGen](https://alphaxiv.org/abs/2605.30345) | 2026 | Semantic representation lets a 20B model beat bigger generalists (60.5%) | Representation matters (the KG) |
| [LLM workflows for SMPS design](https://arxiv.org/abs/2507.10639) | 2025 | Simulation feedback lifts solve rate from 15% to **91%** | Tool feedback loops |
| [D2S-FLOW](https://arxiv.org/abs/2502.16540v2) | 2025 | Datasheet parameter extraction EM 0.86 / F1 0.92 | Datasheet → KG |
| [DocEDA](https://arxiv.org/abs/2412.05301) | 2024 | Layout analysis + CoT parameter extraction | Datasheet → KG |
| [LLM4-IC8K / ICGeo8K](https://arxiv.org/abs/2508.03725) | 2025 | LMMs have poor geometric perception of IC footprints | Don't trust vision for pin geometry |
| [Exploring LLMs for Embedded Systems](https://arxiv.org/abs/2307.03817v2) | 2023 | Human-AI workflow raised success from 25% to **100%** | Human-confirm step |
| [From Words to Wires (Pins100/Micro25)](https://arxiv.org/abs/2305.14874) | EMNLP Findings 2023 | 60–96% pass@1 on MCU circuit tasks | LLMs know pinouts partly |
| [ElectroCom61](https://pmc.ncbi.nlm.nih.gov/articles/PMC11847280) | Data in Brief 2025 | 61-class component detection, YOLOv9s 95.9% mAP@50 | Class-level cross-check (not used in MVP) |

**Deck narrative:** "Benchmarks show LLMs write embedded code well but fail on physical pin and voltage reasoning (PCEval, EmbedBench). Production systems solve this with datasheet-grounded, multi-run checks (DRCY) and curated expert knowledge (IoT-SkillsBench). Bharat Sourcer applies the same recipe to India's sourcing problem."

## 2. Dated AI and industry news (for "we use what's new")

| Date | Item | Link |
|---|---|---|
| 26 Sep 2025 | ADK + AG-UI + CopilotKit for rich agent frontends | [Google Developers Blog](https://developers.googleblog.com/delight-users-by-combining-adk-agents-with-fancy-frontends-using-ag-ui/) |
| Dec 2025 | Interactions API and Deep Research agent for developers | [blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/interactions-api/) |
| 11–12 Jan 2026 | Google + Shopify launch the **Universal Commerce Protocol (UCP)** | [Google Developers Blog](https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/) · [InfoQ](https://infoq.com/news/2026/01/google-agentic-commerce-ucp) |
| 12 Feb 2026 | Agentic Vision in Gemini 3 Flash | [noqta](https://www.noqta.tn/en/news/google-gemini-3-flash-agentic-vision-2026) |
| Feb 2026 | Razorpay, Cashfree, PayU ship agentic payments on UPI Reserve Pay | [stellagent](https://stellagent.ai/insights/india-agentic-commerce-fintech-payment) |
| Mar 2026 | UCP heads to India with Flipkart | [stellagent](https://stellagent.ai/insights/google-ucp-india-flipkart-launch) |
| 1 Apr 2026 | India halves customs duty on personal imports (20% → 10%) | [Thomson Reuters](https://www.thomsonreuters.com/en-us/help/onesource-global-trade/regulatory-insights/2026/march-19th/india-union-budget-key-trade-customs-measures.html) |
| 9 Apr 2026 | A2A v1.0; 150+ organisations | [Linux Foundation](https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year) |
| Apr 2026 | Gemma 4 (E2B/E4B on-device) | [InfoQ](https://infoq.com/news/2026/04/gemma-4-android-ai-inference) |
| 16 Apr 2026 | India electronics imports hit a record **$116.17 B** (FY25-26) | [The Week](https://www.theweek.in/news/biz-tech/2026/04/16/electronics-trade-deficit-fy25-26.html) |
| 17 Apr 2026 | A2UI v0.9 with official React renderer | [Google Developers Blog](https://developers.googleblog.com/a2ui-v0-9-generative-ui/) |
| 22 Apr 2026 | Next '26: Gemini Enterprise Agent Platform (ex-Vertex); Cloud Run GPUs, managed MCP | [Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform) · [Cloud Run at Next '26](https://cloud.google.com/blog/products/serverless/whats-new-for-cloud-run-at-next26) |
| 22 Apr 2026 | Gemini Embedding 2 GA (multimodal) | [embeddings docs](https://ai.google.dev/gemini-api/docs/embeddings) |
| 19 May 2026 | Google I/O 2026: Gemini 3.5 Flash, agentic Gemini era | [blog.google](https://blog.google/innovation-and-ai/sundar-pichai-io-2026/) |
| 7 Jul 2026 | ADK v2.4.0: workflows as tools | [forkast](https://forkast.news/google-adk-v2-4-0-lets-agents-compose-entire-workflows-as-tools/) |
| 9 Jul 2026 | NPCI plans Unified Agent Protocol for UPI | [Outlook Business](https://www.outlookbusiness.com/news/india-plans-ai-powered-upi-payments-framework-through-unified-agent-protocol) |
| 12 Aug 2026 | Gemini passes 1 B MAU; MCP app connections | [AlphaSignal](https://alphasignal.ai/news/google-s-gemini-hits-1-billion-users-and-adds-14-app-connections) |
| 1 Sep 2026 | **Agentic video understanding in Gemini** | [blog.google](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-agentic-video-in-gemini/) |
| 1 Sep 2026 | India preparing agentic payments on UPI (Reuters) | [The Star](https://www.thestar.com.my/tech/tech-news/2026/09/01/india-preparing-rollout-of-agentic-payments-on-upi-sources-say) |
| 2 Sep 2026 | Gemini 3.8 Flash GA | [changelog](https://ai.google.dev/gemini-api/docs/changelog) |
| Sep 2026 | Gemini 3.8 Flash TTS (Indic languages) | [speech-generation docs](https://ai.google.dev/gemini-api/docs/speech-generation) · [AlphaSignal](https://alphasignal.ai/news/google-ships-gemini-3-8-flash-tts-with-prompt-directed-emotional-speech) |
| 15 Sep 2026 | Gemini 3.8 Live: 97 languages | [AlphaSignal](https://alphasignal.ai/news/google-s-gemini-3-8-live-adds-real-time-reasoning-to-voice-ai) |
| 24 Sep 2026 | Google Cloud deepens Gemini in India (Pine Labs UPI agents) | [YourStory](https://yourstory.com/2026/09/google-cloud-brings-gemini-deeper-into-india-businesses) |

**Pitch line:** "On 1 Sep 2026 Google gave Gemini the ability to watch video like an agent. Two weeks later it could speak Malayalam. We used both so a maker in Kochi can build what a maker in Kansas built, with parts from Broadway instead of a $40 import."

## 3. Impact statistics

| Stat | Value | Source |
|---|---|---|
| Atal Tinkering Labs (Oct 2025) | 10,000; target 50,000 | [PIB, 5 Dec 2025](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/dec/doc2025125718301.pdf) |
| Students engaged in ATLs | > 1.1 crore | same |
| ATL innovation projects | > 16 lakh | same |
| Engineering enrolment (AICTE 2021-22) | 14.1 lakh enrolled / 25.4 lakh seats | [Careers360](https://news.careers360.com/btech-engineering-college-aicte-data-course-placement-admission-graduation-aishe-vacant-seats) |
| India electronics imports FY25-26 | $116.17 B | [The Week](https://www.theweek.in/news/biz-tech/2026/04/16/electronics-trade-deficit-fy25-26.html) |
| E-waste FY24-25 | 13.97 lakh tonnes | [UNI / CPCB](https://test.uniindia.com/over-13-97-lakh-tonnes-e-waste-generated-in-2024-25-cpcb-data/parliament/news/3542425.html) |
| MakerFest Vadodara 2026 | 10,000+ visitors, 70+ makers | [SSIP report](https://ssipgujarat.in/admin20/files/event/report1_path/7504/Report%20of%20Makerfest%20Vadodara%202026%2010%20and%2011%20Jan%202026.pdf) |
| Personal-import duty | BCD 10% (from 1 Apr 2026) + SWS + IGST | [Mumbai Customs FAQ](https://www.mumbaicustomszone1.gov.in/Info/PostalAppraising), [Outlook Money](https://www.outlookmoney.com/tax/budget-2026-government-halves-customs-duty-on-personal-imports-to-10-per-cent-offers-big-relief-to-consumers) |
| AliExpress blocked in India | since 24 Nov 2020 | [GSMArena](https://www.gsmarena.com/indian_government_bans_43_more_chinese_apps_including_aliexpress-news-46430.php) |
| Price gap example | Pololu DRV8825 $15.95 vs clone ₹100.30 incl. GST | [Pololu](https://www.pololu.com/product/2133), Zbotic Store API |
| Indian retailer directory | 89 sites listed by makers | [TechEnclave](https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-for-tools-and-components/271822) |

## 4. Design guidance cited

- Google PAIR Guidebook: [Explainability + Trust](https://pair.withgoogle.com/chapter/explainability-trust/), [Errors + Graceful Failure](https://pair.withgoogle.com/chapter/errors-failing/)
- Smashing Magazine: [AI transparency patterns](https://smashingmagazine.com/2026/05/practical-interface-patterns-ai-transparency/), [agentic UX patterns](https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)
- Google Design: [Connectivity, Culture and Credit](https://design.google/library/connectivity-culture-and-credit)
- [WCAG 2.2 quick reference](https://www.w3.org/WAI/WCAG22/quickref/)
- [Web Share Target](https://developer.chrome.com/docs/capabilities/web-apis/web-share-target)
