# Decision log

> **In one minute.** Each major choice is recorded with the alternatives we considered and the reason for the pick. Open questions for Anju and the team are at the bottom. To reverse a decision, add a new entry rather than editing the old one.

Format: **D-nn · Title** · Status (Accepted / Proposed / Superseded) · Date.

---

### D-01 · Project: Bharat Sourcer · Accepted · 30 Sep 2026
- **Context:** several hackathon ideas were considered and rejected. Anju's own idea is maker parts localisation for India.
- **Decision:** build Bharat Sourcer.
- **Why:** it's a real, felt problem for Indian makers, has strong technical depth, and it fits the "local need → global scale" brief.

### D-02 · Theme: Retail & Commerce · Proposed · 30 Sep 2026
- **Alternatives:** Sustainability & Social Impact; Media & Content.
- **Why:** the theme's scope literally names discovery and conversational shopping. Judges would read the project as commerce anyway. Sustainability stays as a narrative layer.
- **Open:** Anju to confirm (comment in the overview doc).

### D-03 · Gemini Developer API (billed Tier 1) over Agent Platform · Accepted
- **Why:** new features ship here first (Interactions API, agentic video, File Search). Grounding needs billing anyway, and setup is simpler.
- **Reversible:** ADK env var switch.

### D-04 · ADK 2.x graph workflow (Python) · Accepted
- **Alternatives:** Genkit (TypeScript), a hand-rolled orchestrator, ADK TypeScript.
- **Why:** Google's flagship agent framework, which counts toward the "Google stack" criterion. It has deterministic and LLM nodes, a human-input node and a built-in eval. The Python ecosystem suits the rules engine, and it matches Anju's stack.

### D-05 · Async jobs + Firestore listeners (not direct SSE) · Accepted
- **Why:** Firebase Hosting's 60 s rewrite timeout. This approach is also resumable and shareable, and gives cheap re-runs.

### D-06 · Model tiering: 3.8 Flash / 3.5 Flash-Lite / 3.1 Pro (flagged) · Accepted
- **Why:** follows Google's own positioning (Flash-Lite as the "subagent" model). Pro is preview-only and has no free tier, so it sits behind a flag with a 3.8 Flash `high` fallback.

### D-07 · Rules decide, LLM explains · Accepted
- **Why:** PCEval, EmbedBench and IoT-SkillsBench evidence. It also makes safety and auditability defensible.

### D-08 · Three-tier sourcing with UCP/MCP first · Accepted
- **Why:** Google has no offers API. UCP is a Google-co-created protocol that Indian Shopify merchants explicitly invite agents to use, and it's the compliant option. Grounded search covers the long tail.

### D-09 · Only verified listings reach users · Accepted
- **Why:** the top risk is hallucinated links. The model never emits a user-facing URL.

### D-10 · Compile-in-the-loop via Cloud Run job · Accepted (may degrade)
- **Why:** it's a strong technical-merit demo, backed by research.
- **Degrade path:** "diff (not compiled)".

### D-11 · Region asia-south1 (Mumbai) · Accepted
- **Why:** user latency and the India story. ⚠️ Check that all services are available there (Cloud Run, Firestore, GCS, Artifact Registry are standard).

### D-12 · Anonymous by default, optional Google sign-in · Accepted
- **Why:** frictionless for judges and minimal personal data (DPDP).

### D-13 · Keep the name "Bharat Sourcer"; output named "Desi BOM" · Proposed
- **Why:** memorable to Indian judges; no conflicts found.
- **Downsides:** "Sourcer" reads as recruiting jargon.
- **Alternatives:** Desi BOM, BuildLocal, JugaadKart.
- **Tagline:** "Watch it in America. Build it in India."
- **Open:** Anju to decide; check domain availability.

### D-14 · No auto-checkout, no payments · Accepted
- **Why:** safety, regulation, and the sellers' own `agents.md` rules. Agentic payments (NPCI UAP / AP2 / UCP checkout) are pitch-only.

### D-15 · Electronics-first scope · Proposed
- **Why:** the highest pain and the most checkable specs. 3D-printer hardware and fasteners are stretch.
- **Open:** Anju to confirm.

---

## Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Is every team member JAPAC-based? Who are the teammates (2–4, professionals, 21+)? | Anju | **4 Oct** |
| Q2 | Theme: Retail & Commerce (recommended) or Sustainability? | Anju | 4 Oct |
| Q3 | Keep the name "Bharat Sourcer"? Domain? | Anju | 6 Oct |
| Q4 | Electronics-only MVP, or include 3D-printer parts? | Anju | 3 Oct |
| Q5 | Which 3 demo projects (one hero YouTube build, one mains, one savings)? | Team | 12 Oct |
| Q6 | Which two stretch features: Indic TTS, Maps markets, parts-bin scan, clip zoom? | Team | 13 Oct |
| Q7 | Are Google Cloud credits available (ask on Discord)? | Anju | 2 Oct |
| Q8 | Contact Robu / Robocraze / Quartz / Evelta for a data or affiliate blessing? | P | 7 Oct |
