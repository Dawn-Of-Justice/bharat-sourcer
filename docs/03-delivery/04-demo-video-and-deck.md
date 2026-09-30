# Demo video, deck and submission

> **In one minute.**
> - **Video:** 2:45, strictly under 3:00, English, captions burned in, filmed partly on a real Android phone.
> - **Structure:** hook → one-line premise → live happy path → two wow moments → under the hood (named agents, models, eval numbers) → impact and close.
> - **Deck:** 12 slides mapped to the judging criteria (use Hack2skill's template if the dashboard provides one).
> - **Submission:** everything goes in by 17 Oct.

Research: [research/05 §3](../../research/05-competition-ux-judging.md), [research/04 §6](../../research/04-frontier-wow-factors.md).

---

## 1. Demo projects (choose on day 12)

Pick three projects from the eval set, all pre-warmed in the library:

1. **Hero:** a popular YouTube build, e.g. an ESP32 weather station with a BME280 + OLED. It shows extraction from video, the SH1106 code diff, and the BME280 address note.
2. **Safety:** the Sous-viduino (mains). It shows the X grade and the MAINS banner.
3. **Savings:** a stepper-driver project (DroneBot). Pololu DRV8825 at $15.95 vs about ₹100 locally makes the savings dramatic.

## 2. Video script (target 2:45)

| Time | Shot | Voice-over (draft) | On screen |
|---|---|---|---|
| 0:00–0:12 | Screen: a US YouTube build; cut to a US cart total + shipping + customs | "Every maker in India knows this feeling. You find the perfect project… built in America." | "$142 + $60 shipping + customs" |
| 0:12–0:20 | Logo + tagline | "Bharat Sourcer turns any maker video into a parts list you can actually buy in India." | *Watch it in America. Build it in India.* |
| 0:20–0:45 | **Real Android phone:** YouTube app → Share → Bharat Sourcer | "I just share the video. Gemini watches it for me, using the new agentic video understanding, and reads the description, the blog and the code." | Checklist ticking; "Found 14 parts" |
| 0:45–1:00 | Confirm screen; tap ▶ 03:42 → player jumps to the part | "Every part comes with proof: here's exactly where it appears." | Evidence chip → video seek |
| 1:00–1:25 | Sourcing: 14 agent cards fanning out in parallel | "Now a team of agents searches Indian stores in parallel: Robocraze through Google and Shopify's Universal Commerce Protocol, distributors through their APIs, and everything else through Google Search grounding. Nothing is shown until it's verified." | Seller logos, "verified ✓" |
| 1:25–1:50 | **Wow 1:** the OLED row → drawer → SH1106 code diff → "✅ Compiles" | "The 1.3-inch OLED sold here uses a different chip. Bharat Sourcer catches it, rewrites the code, and proves it compiles." | Diff + badge |
| 1:50–2:05 | **Wow 2:** safety — the Sous-viduino MAINS banner, X grade, safe alternative | "It also knows India runs on 230 volts. This US mains switch would be dangerous here, so it says so and suggests a safe one." | Red banner |
| 2:05–2:15 | 🔊 Malayalam explanation (5 s of audio) + "Pick up today: SP Road, 2.1 km" | "And it explains the changes in your language." | Language chip, map card |
| 2:15–2:35 | Architecture animation + metrics table | "Under the hood: an ADK multi-agent workflow on Cloud Run: Gemini 3.8 Flash, Flash-Lite sub-agents, a Pro-model judge grounded in datasheets, deterministic safety rules. On 15 real projects: X% part recall, zero hallucinated links." | Diagram + numbers (real only) |
| 2:35–2:45 | Totals: ₹3,480 vs ₹14,900; impact line; close | "Median savings of Y%. For 1.1 crore Atal Tinkering Lab students and every maker in JAPAC. Bharat Sourcer." | URL, theme: Retail & Commerce |

**Production:**

- Record at 1080p (phone screen recording + OBS on desktop).
- Burn in captions, since judges may watch muted.
- No music with lyrics.
- Keep a pre-recorded fallback of every live step.
- Upload as a **public** YouTube video.
- Name the models and show one eval number. These tips come from past winners and judges' guidance.

## 3. Deck (12 slides, PDF)

| # | Slide | Content | Criterion |
|---|---|---|---|
| 1 | Title | Bharat Sourcer · tagline · team · **Theme: Retail & Commerce** | – |
| 2 | Problem | A real price comparison (DRV8825 $15.95 vs ₹100), import duty, 230 V vs 120 V, forum pain quotes | Impact |
| 3 | Who it's for | Ravi (student, Coimbatore), Priya (ATL mentor, Kochi), Arjun (hobbyist, Pune); retailers as a second stakeholder | Impact |
| 4 | Solution in one picture | Share → agents → Desi BOM | UX |
| 5 | Demo screenshots | 3 phone frames: evidence chip, live agents, results with a grade drawer | UX |
| 6 | **Architecture** | Diagram: ADK nodes, models, tools, Cloud Run, Firestore, UCP/MCP, grounding | Technical |
| 7 | **GenAI depth** | Agentic video; structured output + grounding; rules + LLM judge; File Search on datasheets; compile loop; research backing (PCEval, EmbedBench, IoT-SkillsBench, DRCY) | Technical |
| 8 | **Evaluation** | Metrics table + reliability plot + method | Technical |
| 9 | Why not Google Lens? / competitors | Condensed matrix | Innovation |
| 10 | Impact | ₹ and hours saved on the eval set; safety flags caught; ATL and engineering numbers; e-waste and imports context | Impact |
| 11 | Business model and scale | Affiliate links, retailer partnerships, ATL lab kits; "Build in JAPAC. Build for the world." (country adapters) | Impact / Innovation |
| 12 | Roadmap and ask | UPI agent payments (NPCI UAP), UCP checkout, A2A seller agents, WhatsApp, Gemma on-device | Innovation |

Design:

- Every slide carries one message, stated in its title.
- Architecture and metrics are large and legible.
- The screenshots are real, not mocked.

## 4. README (repo front page for judges)

- Tagline and a 2-line summary, the live URL, the video link
- Architecture diagram (the same one as the deck)
- "How it works": the 7 steps
- The Google services used, as a list with links
- Eval results table
- How to run locally (Firestore emulator, `.env.example`)
- A limitations section (honest)
- A licence (e.g. Apache-2.0; check the hackathon IP terms first)

## Submission checklist

- [ ] **Eligibility** confirmed; team registered before the roster lock (4 Oct)
- [ ] Live URL works in incognito on desktop and on an Android phone (from India)
- [ ] Cloud Run `min-instances=1` until 6 Nov; budget alert on
- [ ] Public GitHub repo; `gitleaks` clean; README complete; commit history shows work during the hackathon
- [ ] Video public on YouTube, **< 3:00** (2:45 target), captions, English
- [ ] Deck PDF (Hack2skill template if available), English
- [ ] Theme selected: **Retail & Commerce**
- [ ] All three demo projects pre-warmed and re-verified the day before submitting
- [ ] Screenshots of Cloud Trace and the monitoring dashboard in the deck
- [ ] Submitted on **17 Oct** and the confirmation email saved
