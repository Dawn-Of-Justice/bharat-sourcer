# Documentation index

Two ways through these docs:

- **Skim path** (≈10 min): files marked ⭐. Each starts with a short "In one minute" box so you can stop after it.
- **Deep path**: read in order. Every section links to its sources (`research/` reports or primary URLs).

Conventions used everywhere:

- **Must / Should / Could** = MVP / stretch / future.
- ⚠️ **Verify** = a fact that could not be confirmed on a primary page, or that changes often. All such items are also collected in the [day-1 verification list](03-delivery/03-roadmap-and-timeline.md#4-day-1-verification-list).
- Money: ₹ with Indian digit grouping (₹1,23,456), prices incl. 18% GST unless marked "ex-GST". USD for Google costs.
- Dates: 2026 unless stated. "Today" = 30 Sep 2026.

---

## 01 — Overview (what and why)

| File | What it answers |
|---|---|
| ⭐ [01-executive-summary.md](01-overview/01-executive-summary.md) | The whole project on one page: problem, solution, stack, wow features, plan, risks. |
| [02-problem-and-users.md](01-overview/02-problem-and-users.md) | Who suffers, how much, with numbers (import duty, price gaps, ATL/engineering student counts), personas, jobs-to-be-done. |
| ⭐ [03-solution-and-features.md](01-overview/03-solution-and-features.md) | Every feature, grouped Must / Should / Could, with the user journey and the "wow" moments. |
| [04-hackathon-strategy.md](01-overview/04-hackathon-strategy.md) | Rules, eligibility traps, timeline, prizes, theme choice, judging-criteria mapping, what past winners did. |
| [05-competitive-landscape.md](01-overview/05-competitive-landscape.md) | Octopart, PartGenie, Kitspace, Google Lens, YouTube Shopping, Buyhatke… and the gap we fill. "Why not just use Google Lens?" |

## 02 — Architecture (how it works)

| File | What it answers |
|---|---|
| ⭐ [01-system-architecture.md](02-architecture/01-system-architecture.md) | Components, deployment topology, request lifecycle (async job + Firestore live updates), regions, repo layout. |
| [02-google-tech-stack.md](02-architecture/02-google-tech-stack.md) | Every Google product used, exact model IDs, why each, config, limits, prices, gotchas (free-tier grounding, 60 s Hosting timeout, deprecated temperature…). |
| [03-agent-pipeline.md](02-architecture/03-agent-pipeline.md) | The ADK 2.x graph workflow node by node: inputs, outputs, model, tools, failure handling, events emitted. |
| [04-prompts-and-schemas.md](02-architecture/04-prompts-and-schemas.md) | All structured-output JSON schemas (BomItem, PartSpec, Offer, ImpactReport…) and the system prompts for each agent. |
| [05-compatibility-engine.md](02-architecture/05-compatibility-engine.md) | The core IP: knowledge graph, deterministic rules, A/B/C/D/X grades, matching algorithm, LLM judge, confidence, code-impact + compile loop. |
| [06-sourcing-and-seller-data.md](02-architecture/06-sourcing-and-seller-data.md) | **Open seller discovery** (no fixed store list): web search, Shopify Global Catalog, UCP probes, nightly scan; auto platform detection; trust scoring (Web Risk, RDAP, GSTIN); listing verification; caching; legal rules. |
| [07-data-model.md](02-architecture/07-data-model.md) | Firestore collections, document shapes, indexes, vector index, Cloud Storage layout, TTLs, security rules. |
| [08-api-spec.md](02-architecture/08-api-spec.md) | Backend REST endpoints, the job event stream, error codes, the optional MCP server. |
| [09-frontend-and-ux.md](02-architecture/09-frontend-and-ux.md) | Screens, components, agent-trace UI, evidence strip, confidence chips, INR/GST display, PWA share target, low-bandwidth, accessibility. |
| [10-safety-trust-and-compliance.md](02-architecture/10-safety-trust-and-compliance.md) | Mains 120 V→230 V safety, LiPo, hallucination prevention, scraping law/ToS, YouTube ToS, privacy (DPDP), Google grounding display rules. |

## 03 — Delivery (how we ship)

| File | What it answers |
|---|---|
| [01-deployment-and-devops.md](03-delivery/01-deployment-and-devops.md) | GCP project setup, APIs to enable, Cloud Run + Firebase config, secrets, CI/CD, observability, warm instances for judging. |
| [02-evaluation-plan.md](03-delivery/02-evaluation-plan.md) | 15-project gold eval set, metrics, `adk eval` config, link-validity tests, how the numbers reach the deck. |
| ⭐ [03-roadmap-and-timeline.md](03-delivery/03-roadmap-and-timeline.md) | Day-by-day plan 1–18 Oct, team roles, gates, day-1 verification list. |
| [04-demo-video-and-deck.md](03-delivery/04-demo-video-and-deck.md) | 2:45 video script shot by shot, 12-slide deck outline, submission checklist. |
| [05-risks-and-mitigations.md](03-delivery/05-risks-and-mitigations.md) | Full risk register with owner, trigger and fallback. |
| [06-cost-and-budget.md](03-delivery/06-cost-and-budget.md) | Cost per analysis, hackathon budget, spend caps, how to keep grounding costs down. |

## 04 — Reference

| File | What it answers |
|---|---|
| [01-worked-substitution-cases.md](04-reference/01-worked-substitution-cases.md) | 13 real substitutions worked out (original → Indian alternative → grade → wiring/power/code changes). Doubles as test cases. |
| [02-india-sellers-and-apis.md](04-reference/02-india-sellers-and-apis.md) | Every Indian seller and distributor API we researched: platform, endpoint, limits, shipping, brand authorisation. |
| [03-citations-and-news.md](04-reference/03-citations-and-news.md) | Research papers, dated AI news for the deck, impact statistics, all with links. |
| [04-glossary.md](04-reference/04-glossary.md) | BOM, MPN, Qwiic, UCP, A2UI, grounding, Vref… |
| [05-decision-log.md](04-reference/05-decision-log.md) | Every major decision (ADR-style) with alternatives considered, plus open questions. |

## research/ — raw reports

Five research agents, 30 Sep 2026, every fact linked. Read these when a doc says "see research".

| File | Topic |
|---|---|
| [01-google-stack.md](../research/01-google-stack.md) | Gemini models & features, ADK 2.x, Agent Platform (ex-Vertex), Firebase, Cloud Run, commerce protocols, costs |
| [02-india-parts-market.md](../research/02-india-parts-market.md) | Indian sellers, platforms & endpoints, distributor APIs, import duty, problem parts, legal, maker-community numbers |
| [03-compatibility-intelligence.md](../research/03-compatibility-intelligence.md) | BOM extraction, parametric matching, code impact, KG design, eval set, papers |
| [04-frontier-wow-factors.md](../research/04-frontier-wow-factors.md) | 2026 AI advances (incl. AlphaSignal), ranked wow features, pitch news timeline |
| [05-competition-ux-judging.md](../research/05-competition-ux-judging.md) | Official rules, competitors, past winners, UX patterns, naming |
