# Hackathon strategy

> **In one minute.**
> - **Rules:** JAPAC-based team of 2–4 working professionals aged 21+, roster locked **4 Oct**, fresh code only, public GitHub repo, video strictly under 3 min, submit by **18 Oct** (we aim for 17 Oct).
> - **Theme:** Retail & Commerce.
> - **Scoring:** 65% of the score is technical merit plus innovation, so make the agents *visible*.
> - **Extra prizes in reach:** Best UI/UX, Most Impactful, Best use of Google Cloud AI tools.

Sources: [aibuildercup.com](https://aibuildercup.com/index.html), [themes](https://aibuildercup.com/themes.html), [FAQ](https://aibuildercup.com/Faqs.html), [rewards](https://aibuildercup.com/rewards.html), [T&C](https://docs.google.com/document/d/e/2PACX-1vRm7ChZ6Ij9fG7uFDkxzUMpwgVeBmnQ6cMDnAIEEX84AiLBOOQ9cYbl3S5OzFBbcVb8TF55s-eVpiXb/pub).

---

## 1. Eligibility and rule traps (read first)

| # | Rule | Exact wording (source) | Action |
|---|---|---|---|
| 1 | JAPAC only | FAQ: "all team members must be based out of JAPAC region itself." T&C: "physically based in and legal residents of countries within the JAPAC (Japan & Asia-Pacific) region" | **Confirm each member's residency.** Email support+aibuildercup@hack2skill.com with any doubt. The organisers may verify government ID, employment and age at any time |
| 2 | Team size | Site: "2-4 Team Member". FAQ: "You cannot participate solo." (T&C say 1–4) | Plan for at least 2 members |
| 3 | Roster lock | Site: team formation to 11 Oct. **T&C: "No team roster changes are allowed after October 4."** | **Register and finalise the team by 4 Oct** |
| 4 | Professionals only | "open to working professionals only. Students are not eligible." One student disqualifies the whole team | Every member employed or running a startup, aged 21+ |
| 5 | Fresh code | "Submissions must consist exclusively of fresh code and original assets created during the official hackathon timeline." | New repo; commit early and often so the history proves it. No code copied from older projects |
| 6 | IP | 6-month right of first refusal on an exclusive licence to all materials | Know this if the project might become a startup |
| 7 | Deliverables | Deployed prototype link · public GitHub repo · public video (YouTube/Vimeo/Drive), **strictly under 3 min** · PDF deck · chosen theme · English only | See [../03-delivery/04-demo-video-and-deck.md](../03-delivery/04-demo-video-and-deck.md) |
| 8 | Platform | Must use Google AI models (Gemini/Gemma) or Google agentic platforms (Agent Platform, Antigravity, AI Studio) and deploy on Cloud Run / GCP / Firebase. "Solutions built primarily on other cloud platforms will not be eligible." | All compute on GCP. Non-Google APIs only as data sources |
| 9 | Third-party rights | Must not infringe copyright or other third-party rights | Seller data via sanctioned endpoints and grounding; YouTube via official embed ([../02-architecture/10-safety-trust-and-compliance.md](../02-architecture/10-safety-trust-and-compliance.md)) |

## 2. Timeline

| Stage | Dates |
|---|---|
| Registration & team formation | 1 Sep – 11 Oct (**roster lock 4 Oct per T&C**) |
| Build & submission window | 7 Sep – 18 Oct |
| **Submission deadline** | **18 Oct** (no time zone stated → submit 17 Oct) |
| Evaluation | 19 Oct – 6 Nov (keep the deployment warm) |
| Finalists announced | 7 Nov |
| Grand finale / demo day | **4 Dec, Singapore**, in person, up to 2 members, travel sponsored (visa is the team's responsibility) |

## 3. Prizes

| Prize | USD |
|---|---|
| Winner | 10,000 |
| 1st runner-up | 7,000 |
| 2nd runner-up | 5,000 |
| Best use of Google Cloud AI tools | 2,000 |
| Most Impactful Solution | 2,000 |
| Social Choice Award | 2,000 |
| Best UI/UX | 2,000 |

TDS is deducted, and payment arrives within 60 days. No Google Cloud credit amount is published, so ask on the Discord ([discord.gg/x5GRzJbKpa](https://discord.gg/x5GRzJbKpa)).

## 4. Theme choice

Submit under **Theme 2 — Retail & Commerce** ("discovery, personalization, conversational shopping…").
Framing: **"video-to-cart commerce for India's maker economy."**

- Use **Sustainability & Social Impact** as a *narrative* layer: fewer imports, reuse of parts you already own, e-waste, accessibility through Indic voice.
- Use **Media & Content** ("content understanding") as a supporting line.
- Only one theme can be submitted.

The site's hero line, "Build in JAPAC. Build for the world.", matches our last slide: the same adapters work for any country's sellers.

## 5. Judging criteria → what we show

| Criterion | Weight | Official description | Evidence we put in front of judges |
|---|---|---|---|
| Technical Merit & GenAI | **40%** | Meaningful Gen AI use, technical soundness, scalability | Architecture diagram (required culture in Google hackathons) · named agents in the trace · agentic video · structured output + grounding · deterministic rules + LLM judge · compile-in-the-loop · `adk eval` numbers · cost per BOM · caching · Cloud Run autoscaling |
| Problem Alignment & Impact | 25% | Effective problem addressing, clear stakeholder value | ₹ saved and hours saved on the eval set · safety issues caught · ATL/engineering numbers · retailer benefit · JAPAC scale |
| Innovation & Creativity | 25% | Fresh perspective, creative Gen AI beyond basic | No known tool does video → localised, compatibility-checked BOM · "Why not Google Lens?" slide · Bharat layer |
| UX & Solution Design | 10% | Intuitive, user-friendly, accessible | Share from YouTube · evidence strip · plain chips · INR lakh format · aria-live progress · lite mode |

**Rule of thumb:** if a feature doesn't make one of these rows more convincing *on screen*, it waits.

## 6. What past Google-sponsored winners had in common

| Competition | Pattern |
|---|---|
| Gemini API Developer Competition | Multimodality + a clearly named beneficiary (Jayu, Vite Vere, Gaze Link, ViddyScribe) |
| ADK Hackathon (10,400+ participants) | Several specialised agents with clear roles. Regional specificity rewarded (Edu.AI for Brazil). Architecture diagram required |
| GKE Turns 10 | Grand prize "cart-to-kitchen" grocery agent. APAC and EMEA winners also commerce agents. "CO2-aware shopping assistant" got an honourable mention |
| Gen AI Exchange 2025 (same organiser, Hack2skill × Google Cloud, India) | Jury favoured "domain-specific, production-ready tooling" that could "provide auditability, and scale", moving "away from prototype-style demos towards agentic systems and explainable models" |
| Anti-pattern | *ExtractCode* (YouTube → on-screen code) didn't win. Extraction alone isn't enough; the downstream action is what matters |

Implications:

1. Name the agents.
2. Show citations everywhere (auditability).
3. Lead with multimodal input.
4. Name a local beneficiary (Ravi in Coimbatore).
5. Show production signals: Cloud Run, evals, cache, cost per query.

## 7. Team shape (2–4 people)

| Role | Owns | Suggested |
|---|---|---|
| **Agent/backend lead** | ADK workflow, Gemini calls, compatibility engine, eval | Anju (Python/FastAPI, Gemini in production) |
| **Frontend/UX lead** | React app, trace UI, PWA share target, accessibility, video capture | Teammate 2 |
| **Data/KG + sourcing** | Seller adapters, listing verifier, knowledge-graph seed (~150 modules), eval gold BOMs | Teammate 3 (or split between 1 and 2) |
| **Pitch & QA** | Deck, video, user tests, demo script, submission | Teammate 4 (or shared) |

With two people, frontend + pitch combine and backend + KG combine. The KG seeding can be parallelised by anyone.

## 8. Submission-day checklist (short)

Full version: [../03-delivery/04-demo-video-and-deck.md](../03-delivery/04-demo-video-and-deck.md#submission-checklist).

- [ ] Live URL works in an incognito window, on a phone, from India
- [ ] Cloud Run `min-instances=1` through 6 Nov
- [ ] Public repo, README with architecture diagram, no secrets in history
- [ ] Video public, < 3:00 (target 2:45), captions burned in
- [ ] PDF deck (Hack2skill template if the dashboard provides one)
- [ ] Theme: Retail & Commerce
