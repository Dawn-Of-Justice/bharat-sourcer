# Risks and mitigations

> **In one minute.** The top three risks, in order:
> 1. **Eligibility** (JAPAC residency, team size, 4 Oct roster lock)
> 2. **Wrong or hallucinated parts** in the demo
> 3. **Scope and time** (18 days)
>
> Every preview-only feature has a GA fallback, and every external data source can be switched off from `config/runtime`.

Scoring: Likelihood (L) and Impact (I) are each rated 1–5.

---

| # | Risk | L | I | Trigger / early signal | Mitigation | Fallback | Owner |
|---|---|---|---|---|---|---|---|
| R1 | **Not eligible**: a member isn't JAPAC-based, no team, or the roster isn't locked by 4 Oct | 3 | 5 | Organiser reply; team not formed by 3 Oct | Email support+aibuildercup@hack2skill.com now; recruit JAPAC-based professionals; register early | Don't enter; keep building as a portfolio project | Anju |
| R2 | A student or under-21 member slips in | 2 | 5 | – | Confirm each member's employment and age in writing | Replace the member before 4 Oct | Anju |
| R3 | **Hallucinated product or URL** | 3 | 5 | Eval hallucinated-URL rate > 0 | Only `listing_id`s reach the UI; verifier gate; allow-listed domains | Show "search suggestion" chips instead of products | BE |
| R4 | **Wrong compatibility grade** on a demo part | 3 | 4 | Grade accuracy < 0.7 | Rules decide the grade floor; KG curation; judge ×3; demo projects hand-checked | Hide the grade for low-confidence rows ("Check manually") | BE/KG |
| R5 | Agentic video misses parts or mislabels look-alikes | 3 | 4 | Recall < 0.8 on video-first projects | Multi-source fusion; look-alike list in prompt; human confirm; clip zoom (S4) | Static mode + description + page as the primary sources | BE |
| R6 | ADK doesn't pass `processing: "agentic"` through | 3 | 2 | Day-1 spike | Call `client.interactions.create` in a function node | Static mode | BE |
| R7 | **Grounding not available / quota exceeded** | 2 | 4 | 429s; billing console | Billed Tier 1 from day 1; cache; skip Tier C when A+B suffice; spend cap | `TIER_C_ENABLED=false` | BE |
| R8 | Gemini rate limits during judging | 2 | 4 | 429s | Concurrency limits from config; retries with backoff; pre-warmed library | Serve cached BOMs for the demo projects | BE |
| R9 | `gemini-3.1-pro-preview` changes or is throttled | 3 | 2 | Errors | Flag + fallback to `gemini-3.8-flash` @ high | – | BE |
| R10 | Firebase Hosting 60 s timeout breaks long calls | 4 | 3 | 504s | Async job + Firestore listener; only short calls via the rewrite | Call Cloud Run directly (CORS) | BE |
| R11 | Seller endpoint changes, blocks us or goes down | 3 | 3 | Adapter error rate | Adapter isolation + kill switch; multiple tiers | Tier C grounding | KG |
| R12 | UCP/MCP profile or protocol details differ from our assumptions | 3 | 2 | Day-1 test | Test early; Shopify `/search/suggest.json` fallback | Store JSON endpoints | KG |
| R13 | Legal/ToS complaint from a seller | 1 | 3 | Email | Sanctioned paths only; robots.txt; attribution; no image re-hosting | Remove the seller from the allow-list | Anju |
| R14 | **Scope creep** | 4 | 4 | Behind a gate | Gates G1–G3; no new Must after G3; one stretch at a time | Cut in the listed order | All |
| R15 | Compile job image too big / slow | 3 | 2 | Build > 20 min | Build once, cache; only the needed cores | Show "diff (not compiled)" | BE |
| R16 | PWA share target behaves differently on some phones | 3 | 2 | Test on 2–3 phones | Parse both `text` and `url`; paste fallback | Film on the phone that works | FE |
| R17 | Maps grounding not available for India | 2 | 2 | Day-1 test | Test early | Static curated list of markets per city (clearly labelled) | BE |
| R18 | Cold starts or outage during judging (19 Oct – 6 Nov) | 2 | 5 | Uptime check | min-instances=1; health pings; budget alert; don't deploy risky changes after submitting | Recorded video + README screenshots | BE |
| R19 | Cost overrun | 2 | 3 | Budget alerts | Spend cap; caching; App Check; per-IP limits | Temporarily disable new job creation, serve the library | Anju |
| R20 | Mains-safety advice misread by a user | 1 | 5 | – | Templated banners; X grade for US mains products; "consult an electrician"; beginner nudge | – | BE |
| R21 | Code-fresh rule challenged | 1 | 5 | – | New repo; frequent commits; no copied code | Commit history as evidence | All |
| R22 | IP: organisers' right of first refusal | 1 | 2 | – | Understand the terms before any commercial plans | – | Anju |
| R23 | Demo-day live failure (finale, 4 Dec) | 2 | 4 | – | Offline demo mode with recorded fixtures; pre-warmed library | Video playback | FE |
