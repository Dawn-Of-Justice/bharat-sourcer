# Executive summary

> **In one minute.** Bharat Sourcer is a multi-agent Gemini app. You paste a link to a maker project built in the US/UK, and it returns a costed parts list you can buy in India. Every substitute is graded for compatibility and comes with the wiring and code changes. It runs on ADK 2.x on Cloud Run with a Firebase frontend. It uses Gemini's newest capabilities: agentic video understanding (1 Sep 2026), Search/Maps grounding, multimodal embeddings and Indic TTS. The entry goes under **Retail & Commerce**. The biggest risk is **eligibility**: JAPAC-based team of 2–4 professionals, roster locked 4 Oct.

---

## 1. The problem

- Indian makers learn from English-language YouTube and blogs, where projects are made in the US, UK and Europe.
- The parts lists name brands and stores that are unavailable, very expensive or unsafe in India. Examples:
  - A Pololu DRV8825 stepper driver costs **$15.95**. An Indian clone costs **₹100 incl. GST**, about 13× less.
  - A US PowerSwitch Tail runs on 120 V mains. India is **230 V / 50 Hz with Type D/M plugs**.
  - An Adafruit Feather is often sold out at Indian resellers.
- Personal imports pay basic customs duty (cut from 20% to 10% on 1 Apr 2026) plus surcharge and IGST. That is roughly **30–42% tax overhead** on top of international courier fees. AliExpress has been blocked in India since Nov 2020.
- The workaround today is hours of manual searching across 5–10 Indian store sites, Quora, Reddit and TechEnclave threads. On top of that comes guesswork about 3.3 V vs 5 V logic, I2C addresses, libraries and pinouts.
- Scale:
  - **10,000 Atal Tinkering Labs** with **1.1 crore students**, heading to 50,000 labs
  - About **14 lakh engineering students enrolled a year**
  - India's electronics imports hit a record **$116 B in FY25-26**

Details and sources: [02-problem-and-users.md](02-problem-and-users.md).

## 2. The solution

Paste a link, get a **Desi BOM**.

1. **Extract.** Gemini watches the video in *agentic* mode, reads the description, linked blog and GitHub code, and fuses them into a BOM. Every line carries evidence: a timestamp, a quote or a `file:line`.
2. **Confirm.** The user checks and edits the list (human-in-the-loop).
3. **Resolve.** Each part becomes *chip + module + ecosystem* with specs (Flash-Lite, run in parallel).
4. **Source (open discovery).** A parallel agent per part searches **all** Indian sellers; there's no fixed store list:
   - open web discovery via **Google Search grounding**
   - the **Shopify Global Catalog** (`ships_to=IN`)
   - **UCP/MCP** and store APIs for sellers it already knows
   - distributor APIs (DigiKey, Mouser)

   A shop that launched last week can win on price. New sellers are auto-onboarded (their platform is detected so structured access is automatic) and **trust-labelled** using Google Web Risk, domain age, GSTIN and policy checks. Every listing is fetched and verified before it's shown.
5. **Judge.** Deterministic rules (voltage, logic level, I2C clashes, mains, pin functions) plus a Gemini judge that reads datasheets. The result is a grade: **A drop-in · B config · C rewire · D functional alternative · X not recommended**.
6. **Adapt.** Gemini writes the code diff (e.g. `Adafruit_SSD1306` → `Adafruit_SH110X`), and we **compile it** with `arduino-cli` in Cloud Run.
7. **Cost and deliver.** INR totals incl. GST and shipping thresholds, compared with the landed import cost. Optional extras: spoken explanation in Indian languages, nearby electronics markets via Maps grounding, and share/export.

Full feature list: [03-solution-and-features.md](03-solution-and-features.md).

## 3. Why it can win

| Criterion (weight) | Our answer |
|---|---|
| Technical merit & GenAI (40%) | ADK 2.x graph workflow mixing deterministic nodes and LLM nodes. Agentic video understanding. Structured output combined with grounding. Multimodal embeddings. Datasheet File Search. Compile-in-the-loop. `adk eval` with a 15-project gold set. |
| Problem & impact (25%) | Rupees and hours saved per project. Safety (mains) caught. Large student/maker base. Local need that scales to any JAPAC country. |
| Innovation (25%) | We found no tool that turns *video → localised, compatibility-checked, costed BOM*. Closest are Octopart (needs part numbers, no Indian stores), PartGenie (MPN-only) and Google Lens (one item at a time, no compatibility). |
| UX (10%) | Share from the YouTube app (PWA share target). Live agent trace. Timestamp evidence strip. Plain-language confidence chips. INR with lakh grouping. Accessible and low-bandwidth. |

Google-sponsored hackathons have repeatedly rewarded **multi-agent commerce assistants tied to an everyday task**, for example the GKE hackathon's "cart-to-kitchen" grand prize. Bharat Sourcer is "project-to-cart".

## 4. The stack in one line

**Gemini** (3.8 Flash · 3.5 Flash-Lite · 3.1 Pro preview · Embedding 2 · 3.8 Flash TTS · 3.5 Transcribe) → **ADK 2.x** (Python) on **Cloud Run** `asia-south1` → **Firestore** (jobs, cache, knowledge graph, vector search) + **Cloud Storage** → **React + TypeScript** on **Firebase Hosting**.

Details: [../02-architecture/02-google-tech-stack.md](../02-architecture/02-google-tech-stack.md).

## 5. Wow features (MVP)

1. **Agentic video BOM + "show me the part".** Each row jumps the embedded YouTube player to the moment the part appears.
2. **Live multi-agent trace.** The judges watch N part-agents work in parallel.
3. **Compatibility judge + compiled code diff.** "It didn't just find a cheaper part, it proved the code still builds."
4. **Bharat layer.** Mains-safety flags, explanations spoken in Hindi/Tamil/Malayalam, and "pick it up today at SP Road / Lamington Road" via Maps grounding.

## 6. Plan

18 days, 1–18 Oct:

- **Oct 1–4:** team, registration and the video-extraction spike. Registration must close by **Oct 4**.
- **Oct 13:** working end-to-end deployed demo.
- **Oct 15–17:** eval numbers, video and deck.
- **Oct 17:** submit, a day ahead of the deadline.

Details: [../03-delivery/03-roadmap-and-timeline.md](../03-delivery/03-roadmap-and-timeline.md).

## 7. Top risks

| Risk | Mitigation |
|---|---|
| **Eligibility** (JAPAC residency, team of 2–4, roster lock 4 Oct) | Email support+aibuildercup@hack2skill.com now. Form a JAPAC team. |
| Hallucinated parts/links | The recommender can only reference a verified `Listing` id. URLs come from the DB, never from the model. |
| Wrong compatibility call | Hard rules in code. Datasheet citations. 3-run judge consensus. "Verify on arrival" tests. |
| Preview APIs change (3.1 Pro, A2UI, Wokwi MCP) | Keep the demo path on GA features only. Flags and fallbacks for everything else. |
| Grounding needs billing | Billed Tier 1 project from day 1. Budget cap. Cache. |

Full register: [../03-delivery/05-risks-and-mitigations.md](../03-delivery/05-risks-and-mitigations.md).

## 8. Cost

About **$0.40–1.65 per full analysis**, depending on cache hits and whether we're past the 5,000 free grounding queries a month. Total hackathon budget is estimated at **< $200**. See [../03-delivery/06-cost-and-budget.md](../03-delivery/06-cost-and-budget.md).
