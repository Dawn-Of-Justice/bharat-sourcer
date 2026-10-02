# Roadmap and timeline

> **In one minute.** There are 18 days, 1–18 Oct.
> - **Gate 0 (4 Oct):** team registered, eligibility confirmed.
> - **Gate 1 (6 Oct):** video → BOM JSON works on real videos.
> - **Gate 2 (10 Oct):** end to end on 5 projects, deployed.
> - **Gate 3 (13 Oct):** MVP frozen, eval run.
> - **15–17 Oct:** polish, video, deck. Submit on **17 Oct**.
>
> Mondays and Thursdays are Anju's day-job days, so they're planned as light (review, KG curation, testing).

---

## 1. Milestones

| Gate | Date | Exit criteria | If missed |
|---|---|---|---|
| **G0 Team & eligibility** | Sat 4 Oct | Team of 2–4 registered on Hack2skill; every member JAPAC-based, 21+, working professional; organiser reply on any doubt | **Stop or restructure.** Without eligibility, nothing else matters |
| **G1 Extraction spike** | Mon 6 Oct | `VideoExtractor` returns valid `VideoBom` JSON with timestamps on 5 real YouTube builds; recall eyeballed ≥ 70% | Switch to static mode + description + page fusion; keep agentic as a flag |
| **G2 Thin end-to-end** | Fri 10 Oct | Deployed on Cloud Run + Hosting: link → confirm → sourcing (Tier A + C) → rules-only grades → INR totals, on 5 projects | Drop Tier B and the LLM judge from the MVP; keep rules-only grades |
| **G3 MVP freeze** | Mon 13 Oct | All Must features (M1–M15) working; full eval run; no P0 bugs | Cut the lowest-impact Must (M14 export, then M9 compile → diff only) |
| **G4 Submission** | Fri 17 Oct | Video < 3:00, deck PDF, public repo, live URL, theme, all submitted | 18 Oct is the hard deadline (time zone unstated) |

## 2. Day-by-day plan

Roles: **BE** = agent/backend (Anju), **FE** = frontend/UX, **KG** = data/KG + sourcing, **P** = pitch/QA. With only two people, BE+KG and FE+P combine.

| Day | Date | BE (agents/backend) | FE (frontend/UX) | KG (data/sourcing) | P (pitch/QA) |
|---|---|---|---|---|---|
| 1 | Wed 30 Sep (today) | Docs ✔. Email organisers about eligibility | – | – | Recruit teammates |
| 2 | Thu 1 Oct *(work day)* | Evening: new repo, GCP project, billing, AI Studio key, day-1 verification list (§4) | Vite + React skeleton, Firebase init | List 15 eval projects; start 5 gold BOMs | Register team on Hack2skill; join Discord; ask about credits |
| 3 | Fri 2 Oct | **Spike:** Interactions API agentic video → `VideoBom` on 5 videos; test ADK pass-through | Start screen, paste/share handling, job page shell | KG schema + loader; first 30 modules | User interviews (3 makers) |
| 4 | Sat 3 Oct | PageExtractor (URL context) + CodeExtractor (regex + KG map) | Watching screen: player, checklist, status line from Firestore | 30 more modules; datasheets → GCS + File Search store | Persona + problem slide drafts |
| 5 | Sun 4 Oct | **G0 check.** EvidenceFuser + conflicts; FastAPI `/v1/jobs`, Firestore sink | Confirm screen (edit/remove/have-it, conflict banner) | Shopify UCP/MCP adapter (Robocraze, Quartz) + products.json | Roster final ✔ |
| 6 | Mon 5 Oct *(work day)* | Evening: HumanConfirm node; **G1 check** | Sourcing live cards | Woo (Zbotic) + Magento (Probots) adapters | Gold BOMs 6–10 |
| 7 | Tue 6 Oct | PartResolver (KG → Flash-Lite), spec schemas | Desi BOM results layout (mobile cards) | Open SellerDiscoveryAgent (no allow-list) + Shopify Global Catalog + platform probe | – |
| 8 | Wed 7 Oct | ListingVerifier + cache; rules engine v1 (8 global rules) + unit tests from 13 cases | Grade/confidence/evidence chips; YouTube `seekTo` | DigiKey v4 + Mouser adapters (Tier B) | Gold substitutions for 10 projects |
| 9 | Thu 8 Oct *(work day)* | Evening: CompatibilityJudge (3.1 Pro + File Search) + ImpactReport | Row drawer: spec diff, wiring, citations | KG edges: footprint, lookalike, API_MAP | – |
| 10 | Fri 9 Oct | CostOptimizer (plans, thresholds, import baseline) | Totals footer, INR formatting, plan toggle | New-seller onboarding: Web Risk, RDAP, GSTIN checksum, policy reader, trust labels; verify INR/GST parsing | Deck skeleton (12 slides) |
| 11 | Sat 10 Oct | **G2:** deploy bs-api + Hosting; end-to-end on 5 projects | PWA manifest + **share_target**; test on 2 Android phones | Remaining KG to ~150 modules | First run of eval (8 projects) |
| 12 | Sun 11 Oct | CodeImpact + compile job (image build!) + repair loop | Code diff viewer, "✅ Compiles" badge | Judge checklist tuning with results | Record B-roll: phone share flow |
| 13 | Mon 12 Oct *(work day)* | Evening: judge ×3 consensus, confidence calibration | Accessibility pass (aria-live, contrast, targets) | Fix eval failures (canonicalisation) | Gold BOMs 11–15 |
| 14 | Tue 13 Oct | **G3 MVP freeze.** Full 15-project eval; perf (fan-out, caching) | Safety banner, sources footer (search_suggestions), export CSV/PDF | Pre-warm demo projects in library | Metrics table + reliability chart |
| 15 | Wed 14 Oct | **Stretch** (pick 2 max): S1 Indic TTS, S2 Maps markets, S3 parts-bin scan, S4 clip zoom | Stretch UI for chosen items; lite mode | Stretch data | Demo script rehearsal |
| 16 | Thu 15 Oct *(work day)* | Evening: min-instances=1; runbook; budget check | Bug bash on phones | Re-verify demo listings | **Record the demo video** (takes 1–2) |
| 17 | Fri 16 Oct | Bug fixes only; README + architecture diagram; `gitleaks` | Final polish, loading states | – | Edit video (2:45), captions; deck final |
| 18 | Sat 17 Oct | **Submit** (live URL, repo, video, deck, theme) | Incognito + phone smoke test | – | Submission checklist ✔ |
| — | Sun 18 Oct | Buffer. **Hard deadline** | | | |
| — | 19 Oct – 6 Nov | Keep warm; daily `/healthz` + one demo run; don't break prod | | | Social Choice Award: share the public link |

## 3. Scope guardrails

- **Nothing preview-only on the demo path.** Preview features (3.1 Pro, A2UI, Computer Use, Wokwi MCP) must sit behind a flag and have a working GA fallback.
- **No new Must features after G3.** Only stretch items that are finished by day 15; anything else gets cut.
- Work on **one stretch at a time**, in this order: S1 TTS → S2 Maps → S3 parts-bin → S4 clip zoom → S6 visual match → S7 A2UI → S8 Wokwi.
- If G2 slips by more than a day, drop Tier B and the compile job from the MVP. Show "diff (not compiled)" instead.

## 4. Day-1 verification list

These facts change often or were not fully confirmed in research. Check each on day 1–2 and update the docs.

| # | Check | How | Affects |
|---|---|---|---|
| V1 | Current model IDs and prices: `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview`, `gemini-embedding-2`, `gemini-3.8-flash-tts` | [models](https://ai.google.dev/gemini-api/docs/models), [pricing](https://ai.google.dev/gemini-api/docs/pricing) | config, cost doc |
| V2 | Search grounding works on our billed key; the free 5,000/month applies | Make one call; check the billing console | Open discovery |
| V3 | Whether ADK passes `processing: "agentic"` through, or a direct `client.interactions.create` call is needed | 20-minute spike | N2a |
| V4 | Whether setting `temperature` errors or is ignored | Test a call | all nodes |
| V5 | ADK `google_search` alongside other tools on 3.8 Flash (limitation claimed for ≤ v1.15) | Test | N6 |
| V6 | ADK 2.x graph syntax for parallel branches and human-input nodes | adk.dev/graphs | N3, N4 |
| V7 | Actual RPM/TPM per model on Tier 1 | AI Studio rate-limit page | concurrency settings |
| V8 | Robocraze UCP/MCP `search_catalog` with our agent profile; Shopify Global Catalog `ships_to=IN` coverage | curl + MCP client | Tier A |
| V9 | `url_context` success on robu.in, amazon.in, evelta.com, thingbits.in product pages | Test 5 URLs each | verifier fallbacks |
| V10 | Maps grounding availability for Indian locations | Test with a Bengaluru lat/lng | S2 |
| V11 | TTS quality in Hindi, Tamil and Malayalam, and pronunciation of part numbers | Listen | S1 |
| V12 | DigiKey v4 INR with locale headers; element14 India store id | API calls | Tier B |
| V13 | IGST rate currently applied to personal imports (heading 9804) after GST rationalisation | CBIC / customs pages | import baseline |
| V14 | Hackathon: roster lock date (4 vs 11 Oct), solo allowed?, submission time zone, credits | Discord / email | plan |
| V15 | PWA share_target from the YouTube Android app: does the link arrive in `text` or `url`? | Real phone | FE |
| V17 | Web Risk API enabled and `uris.search` works; RDAP for .in (`rdap.nixiregistry.in`) and gTLDs returns creation dates | API calls | trust scoring |
| V18 | Open discovery surfaces small/new shops: test 5 niche parts and count domains outside the seed list | Test | M6 |
| V16 | PlatformIO registry `header:` search reachable from Cloud Run | curl | N2c |

## 5. Definition of done (MVP)

- [ ] A public YouTube build link produces a Desi BOM in under 4 min on the deployed site
- [ ] Every shown product has a verified listing, and hallucinated URLs = 0 on the eval set
- [ ] Every substitute has a grade, a "what changes" note and ≥ 1 citation
- [ ] The MAINS project shows the safety banner (100% on the eval set)
- [ ] At least one compiled code diff is shown in the demo
- [ ] Share from the YouTube app works on a real Android phone
- [ ] Eval metrics table produced from `eval/out/metrics.json`
