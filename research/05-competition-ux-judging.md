# Bharat Sourcer: Competition rules, competitors, winning patterns, UX and naming

*Research date: 2026-09-30. Every URL cited was opened during this research unless marked "(search result only)". Quotes come from pages as fetched on this date.*

---

## 0. Read this first: eligibility and deadline risks

These come before everything else because they can disqualify the entry however good the build is.

| # | Risk | What the source says | Why it matters for Anju |
|---|---|---|---|
| 1 | **Region: JAPAC only** | FAQ: *"Can someone based outside the JAPAC region join? No, all team members must be based out of JAPAC region itself."* ([FAQ](https://aibuildercup.com/Faqs.html)). T&C: *"All participants must be physically based in and legal residents of countries within the JAPAC (Japan & Asia-Pacific) region."* ([T&C](https://docs.google.com/document/d/e/2PACX-1vRm7ChZ6Ij9fG7uFDkxzUMpwgVeBmnQ6cMDnAIEEX84AiLBOOQ9cYbl3S5OzFBbcVb8TF55s-eVpiXb/pub)) | **The profile says Anju lives in London.** Read literally, a UK-based person cannot compete, and the T&C allow checks: *"The Organizer/Company reserves the right to verify government IDs, employment credentials, and age at any point."* **Confirm eligibility with support+aibuildercup@hack2skill.com before investing more time.** If a UK-based member is ruled out, the only options are a team made entirely of JAPAC-based members, or not entering. |
| 2 | **No solo entries (site) vs. 1–4 members (T&C)** | Site: *"2-4 Team Member, 21+ Age only, JAPAC Region"*. FAQ: *"You cannot participate solo."* The T&C say teams range from 1–4 members. | The two sources disagree. Plan on having at least one teammate. |
| 3 | **Roster lock may be Oct 4, not Oct 11** | Site timeline: Registration & Team Formation *Sept 1 – Oct 11, 2026*. T&C: *"No team roster changes are allowed after October 4."* One aggregator also lists Oct 4 as the application deadline ([opportunitiescorners](https://opportunitiescorners.com/google-cloud-ai-builder-cup-2026-in-singapore/)). | Today is Sep 30. **Treat Oct 4 as the real deadline for registration and team formation.** |
| 4 | **Working professionals only; no students** | *"This edition is open to working professionals only. Students are not eligible to participate."* T&C: *"If any single member of a team is found to be a student, the entire team will be immediately disqualified, even if discovered after shortlisting."* | Every teammate must be employed or running a startup and aged 21+. |
| 5 | **Fresh code only** | T&C: *"Submissions must consist exclusively of fresh code and original assets created during the official hackathon timeline. Pre-existing products, ongoing projects, or code developed prior to the official launch will be disqualified."* | Nothing can be copied from Kanakku Booku, AI Resume Analyser or other existing repos. Start a new repo and commit early and often so the history proves the work was new. |
| 6 | **IP: right of first refusal** | T&C: the organisers hold *"a right of first refusal for the acquisition of any exclusive license for all materials including software, source code, documentation, data, and concepts... for a period of 6 months following the conclusion of the Hackathon."* | Worth knowing if Bharat Sourcer might become a startup later. |
| 7 | **Public GitHub repo required** | FAQ: *"a working deployed link of your prototype, a video demo under 3 minutes, the public GitHub repository of your prototype and a deck explaining your solution in detail."* | Keep secrets out of the repo from the first commit. Add a README with an architecture diagram. |
| 8 | **Third-party rights** | T&C: submissions must not infringe *"upon any copyright or upon any other third party rights."* | Scraping Indian retailer sites or showing YouTube thumbnails and transcripts needs care. See §2.5. |

---

## 1. AI Builder Cup 2026: full details

### 1.1 Organisers and positioning
- **Organiser:** Hack2skill. **Sponsor:** Google Cloud. The site reads *"Powered by Hack2skill"* and *"organized by Hack2skill and sponsored by Google Cloud."* ([index](https://aibuildercup.com/index.html))
- **Hero headline:** *"Build in JAPAC. Build for the world."*
- **Framing text:** *"Start with a problem you understand, build a solution on Google Cloud, and show that something built for a local need can scale to a global one."*
  - Bharat Sourcer fits this framing unusually well. It solves a local Indian problem (import cost, parts that aren't available locally), and the same pattern works for any country: "localise a maker BOM for Indonesia, Vietnam or the Philippines". **Put "local need → global scale" on the deck's final slide.**
- **Registration portal:** `https://hack2skill.com/event/aibuildercup2026/` (the page is rendered in JavaScript and couldn't be read. The link comes from [Metropolis Japan](https://metropolisjapan.com/events/ai-builder-cup-2026/).) **Entry is free.**
- **Support:** online sessions *"covering the overall program and the problem statements will be hosted"* ([FAQ](https://aibuildercup.com/Faqs.html)). There is also a Discord at `discord.gg/x5GRzJbKpa`.

### 1.2 Timeline (from [aibuildercup.com](https://aibuildercup.com/index.html))

| Stage | Dates |
|---|---|
| Registration & team formation | Sept 1 – Oct 11, 2026 (**T&C: roster frozen after Oct 4**) |
| Prototype building & submission | Sept 7 – Oct 18, 2026 |
| **Prototype submission deadline** | **Oct 18, 2026** (verified). The time zone is not stated, so assume IST end of day or earlier and submit by Oct 17. |
| Evaluation phase | Oct 19 – Nov 6, 2026 |
| Finalists announced | Nov 7, 2026 |
| Grand Finale / Demo Day | **Dec 4, 2026, Singapore** (in person) |

The FAQ says there is *"a scoring round before the grand finale which will release the list of shortlisted teams who will eventually travel to Singapore."* In practice this is two rounds: an online scoring round, then a live demo in Singapore.

### 1.3 Prizes ([rewards](https://aibuildercup.com/rewards.html))

| Prize | USD |
|---|---|
| Winner | 10,000 |
| First runner-up | 7,000 |
| Second runner-up | 5,000 |
| Best use of Google Cloud AI tools | 2,000 |
| Most Impactful Solution | 2,000 |
| Social Choice Award | 2,000 |
| **Best UI/UX** | 2,000 |
| **Total** | 31,000 (marketing says "$30,000"; the page's counter shows "USD 0", which is a site bug) |

- Finalists get *"Fully sponsored travel and stay in Singapore"* for up to **2 members**: *"flight tickets, accommodation and meals on the day of the Grand Finale."* Visas are the team's responsibility. A 3rd or 4th member cannot attend, even at their own cost.
- T&C: *"The cash rewards will be paid within 60 days... will see a deduction of TDS as per the government rules."* TDS is Indian tax withholding, which suggests an Indian payer.
- **No Google Cloud credit amount is published** on any page opened. Plan to use the free tier plus the $300 new-account trial, and ask on Discord whether credits are available.
- Bharat Sourcer can compete for **Best UI/UX** and **Most Impactful**, not only the top three places. A polished mobile flow is worth designing deliberately.

### 1.4 Themes ([themes](https://aibuildercup.com/themes.html))
There are six themes, and each team submits **one solution under one theme** only.

| Theme | Fit for Bharat Sourcer |
|---|---|
| **2. Retail & Commerce**: *"Build an AI-powered solution that transforms how businesses understand, engage, and serve customers while improving operational efficiency across physical and digital commerce."* Scope listed: discovery, personalization, **conversational shopping**, inventory, fraud. | **Best fit.** This is AI product discovery plus cross-store price comparison. Ties to Robu/Evelta-style stores work as a "retailer" story. |
| 6. Sustainability & Social Impact: resource efficiency, **accessibility**, community support, informed decision-making. | Second choice. The angle would be "democratising making" and cutting import waste and cost. It's weaker because judges will read it as commerce. |
| 3. Manufacturing | Weak fit. It's about operations data. |
| 4. Media, Content & Digital Experiences: *"content ... understanding"* | Plausible angle: "turn how-to video into actionable content". It's a secondary pitch line, not the theme to submit under. |

**Recommendation:** submit under **Retail & Commerce**. Frame it as *"video-to-cart commerce for India's maker economy"*.

### 1.5 Submission requirements (combined from themes, FAQ and T&C)
1. **Deck / proposal, as a PDF.** *"Submit a compelling vision for your AI solution, highlighting its positive impact and alignment with one of the problem statements in a deck/PPT converted into a PDF."*
2. **Functional prototype.** *"Build a working prototype using Google Cloud's AI tools & deployed on Cloud Run/GCP/Firebase."* Named platforms: **Gemini, Gemma, Agent Platform, Antigravity, AI Studio**. FAQ: *"Solutions built primarily on other cloud platforms will not be eligible."* A prototype is enough, but it *"should demonstrate your idea functioning end-to-end."*
3. **Video.** *"Include a link to a public YouTube or Vimeo video or public Google drive link (3 minutes)."* The T&C tighten this to **"strictly under three (3) minutes"**, so aim for 2:45.
4. **Public GitHub repository.**
5. **Live deployed URL.** The judges need to be able to open it during the Oct 19 – Nov 6 evaluation window, so keep Cloud Run min-instances at 1 or pre-warm it.
6. Everything must be in **English**.

### 1.6 Judging (same for every theme)

| Criterion | Weight | Official description | What earns points for Bharat Sourcer |
|---|---|---|---|
| Technical Merit & GenAI Implementation | **40%** | "Meaningful Gen AI use, technical soundness, scalability potential" | Multimodal Gemini working directly on YouTube video. A multi-agent ADK pipeline (extractor → spec normaliser → India sourcer → compatibility checker → costing). Grounded search with citations. Structured output. Evals. Deployed on Cloud Run. |
| Problem Alignment & Impact | 25% | "Effective problem addressing, clear stakeholder value demonstration" | Rupee savings per project. Import duty and shipping avoided. Time saved. Named user personas (student maker, college robotics club, repair shop). Retailers as a second stakeholder. |
| Innovation & Creativity | 25% | "Fresh perspective, creative Gen AI application beyond basic implementation" | "Video → costed Indian BOM" appears to be new: no existing tool combined found (§2). Compatibility reasoning such as 5V vs 3.3V logic, or the US 120V vs India 230V mains trap. |
| User Experience & Solution Design | 10% | *"Is the solution intuitive, user-friendly, and reasonably accessible to its intended users?"* | Android share-sheet entry from the YouTube app. INR formatting. A visible agent trace. Confidence chips. Also counts toward the Best UI/UX prize. |

**Implication:** 40% technical plus 25% innovation means **65% of the score rewards visible GenAI sophistication**. Show the agents working in the UI and in the video; don't hide them behind a single spinner.

### 1.7 Useful Gemini capability facts for the build ([video understanding docs](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding))
- Gemini accepts **YouTube URLs directly**, but *"You can only upload public videos (not private or unlisted videos)."* The free tier allows at most **8 hours of YouTube video per day**. Gemini 2.5+ accepts up to **10 videos per request**.
- Prompts and outputs can reference timestamps in `MM:SS` format. **Use this in the UI:** each BOM row links back to the moment in the video where the part appears. This is strong for both citations and the demo.
- Clip the video with `videoMetadata.start_offset / end_offset`. Sampling defaults to 1 FPS and is adjustable. Cost is roughly 100 tokens/sec at low resolution and 300 at high.
- **Grounding with Google Search** returns inline citation annotations with start and end indices, plus a `search_suggestions` HTML snippet that the Terms of Service require you to render. It can be combined with the **URL context tool** to ground on specific retailer URLs ([grounding docs](https://ai.google.dev/gemini-api/docs/google-search)).
- **ADK** (now at [adk.dev](https://adk.dev/)) supports Python, TypeScript, Go, Java and Kotlin. It has sequential, parallel and loop workflow agents, **graph workflows (ADK 2.0)**, deployment to Cloud Run, Agent Runtime or GKE, and a built-in evaluation framework plus visual builder. A ParallelAgent that queries several Indian stores at once makes a good architecture-slide moment.

---

## 2. Competitive landscape and prior art

### 2.1 Summary matrix

| Product | What it does | Input | India / INR | Video or blog input | Compatibility reasoning | Gap that Bharat Sourcer fills |
|---|---|---|---|---|---|---|
| [Octopart BOM Tool](https://octopart.com/bom-tool) | Upload XLSX/CSV/JSON BOM, auto-match parts, suggest alternates, price across *"670+ Distributors worldwide"*, one-click cart | Structured BOM with part numbers | Not stated. Focus is on global distributors (Digi-Key, Mouser, etc.) | No | Parametric alternates | Needs a BOM with part numbers already. Doesn't cover Robu, Robocraze or Amazon.in. Not built for hobbyists. |
| [Kitspace](https://kitspace.org/) + [1clickBOM](https://github.com/kitspace/1clickBOM) | Shares open-hardware designs. The extension *"fills your shopping carts for you on sites like Digikey and Mouser"* | Project repo BOM | Retailers: Digikey, Mouser, Farnell, Newark, RS, LCSC. **No Indian stores.** | No | No | **Archived Jan 3 2025**, so there is no active competitor here. Covers only projects authored with Kitspace-format BOMs. |
| [Hackster.io "Things used in this project"](https://www.hackster.io/glowascii/basic-hardware-components-77182f) | Structured components list with buy links (Newark, SparkFun) | Author-entered | US/EU vendors | Only if the author filled it in | No | Links go to US stores, and a hobbyist in India pays import costs. Good **input source**: parse this list first when present. |
| Instructables "Supplies" | Free-text supplies section | Author-entered | Usually Amazon.com links | – | – | Unstructured free text. Also a good input source. |
| [PartGenie Alternative Finder](https://www.partgenie.ai/alternative-finder) | AI finds *"exact matches, pin-compatible replacements, and functional alternatives"* from MPN, BOM row or plain-language description; *"56M+ Parts"* | MPN or description | No regional focus | No | **Yes.** Pin and functional tiers, voltage, package | This is the closest analogue for the compatibility tiers. **Borrow its 4-tier model** (exact / pin-compatible / functional / partial). Missing: Indian stores, INR, video input, maker modules (e.g., "HC-SR04 clone"). Free tier is 3 searches/month. |
| [Parter.ai alternatives](https://parter.ai/alternatives) | Reads datasheet specs, *"live stock availability across distributors,"* lifecycle and RoHS | MPN | No India info | No | Yes, spec-based | Engineer-grade and MPN-only. Doesn't cover Arduino-ecosystem modules. |
| [Flux](https://www.flux.ai/) | AI PCB design copilot that *"grounds its decisions in the actual parts by reading datasheets"*, shows costs and lead times | Your own design | Global | No | Yes, while designing | Aimed at designing new boards, not rebuilding someone else's project. |
| [Circuit Mind](https://www.circuitmind.io/) | Generates schematics and a BOM from an architecture, optimising *"size, cost, power, and availability"* | Architecture spec | Enterprise | No | Yes | Enterprise tool (NI, BAE). Not for makers. |
| [Cofactr](https://www.cofactr.com/) | *"AI-powered component intelligence, procurement execution, and ITAR-registered warehousing"* | BOM | US defence/manufacturing | No | – | B2B supply chain. Irrelevant to hobbyists, but a useful comparison point: "Cofactr for makers". |
| [Buyhatke](https://buyhatke.com/) | Indian price comparison and history across *"1 Lakh+ stores"*, extension, AI deal scanner | Product link | **Yes**: Amazon, Flipkart, Myntra, Meesho | No | No | Compares *identical* consumer SKUs. Doesn't understand components or BOMs, and doesn't cover Robu or Evelta. |
| [MySmartPrice](https://www.mysmartprice.com/) | Gadget and appliance prices and reviews | – | Yes | No | No | Covers phones, laptops, TVs and appliances only. **No components.** |
| [Google Lens / Circle to Search](https://blog.google/products/shopping/visual-search-lens-shopping/) | Circle products in *"videos, websites, or social media"*; shows *"price across retailers"* | Screenshot or frame | Rolled out in India with Hindi follow-ups via Gemini app and AI Mode ([Outlook Business](https://www.outlookbusiness.com/ampstories/deeptech/google-rolls-out-ai-shopping-tools-in-india-heres-how-it-works)) | One object at a time | No | **Main "why not just use Google?" objection.** Lens finds one visually similar item. It can't produce a complete BOM with quantities, spot the hidden parts (resistor values, screw sizes, firmware-dependent modules), check compatibility or total the cost. Answer this directly in the deck. |
| [YouTube Shopping (India)](https://yourstory.com/2024/10/youtube-expands-shopping-programme-india) | Creators tag products. Launched in India Oct 25 2024 with Flipkart and Myntra | Creator-tagged | Yes | Yes, but only products the creator tagged | No | US/UK maker videos aren't tagged for Indian stores. Robu and Evelta aren't partners. Bharat Sourcer effectively **auto-tags any video for India**. There's a possible affiliate business model here. |

### 2.2 The Indian supply side (the stores to target)
From [Zbotic's 2026 list](https://zbotic.in/best-online-electronics-stores-india-2026/) (note that Zbotic ranks itself first) and the [TechEnclave maker thread](https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-to-shop-for-tools-and-components/271822?page=2):

| Store | Notes (as stated) |
|---|---|
| Robu.in (Pune) | 5,000+ products; robotics, Arduino, Raspberry Pi; free shipping over ₹999 |
| Evelta (Mumbai) | 15,000+ components; ST/TI partnerships; 24-hour shipping; B2B/RFQ |
| Probots (Bangalore) | 110,000+ products, the largest catalogue |
| Robocraze (Bangalore) | Authorised Raspberry Pi seller; cash on delivery. Forum user: *"ordered at least thrice... no issues"* |
| Thingbits (Mumbai) | Authorised Adafruit/SparkFun/Arduino distributor, so the **exact same SKU** as US videos. High-value match. |
| ThinkRobotics (Delhi) | Authorised Raspberry Pi distributor |
| ElectronicsComp (Bangalore) | Budget pricing. The forum reports *"scamming behavior starting 2023"* (partial shipments, wrong quantities). **Worth a store-reputation signal.** |
| Zbotic, SunRobotics, FlyRobo, Hubtronics | Drones, 3D printing, fast shipping |
| OnlyScrews / Omrook | Fasteners. Forum: OnlyScrews *"10-15% expensive"* vs Bhagirath Palace, Delhi. Fasteners and mechanical parts are a gap that pure electronics tools ignore. |

**User pain points confirmed by the forum thread:** people compare prices across many sites by hand, specialty items such as a *"pancake NEMA17 stepper"* are hard to find, and store reliability varies. These are the three things Bharat Sourcer automates.

### 2.3 Prior art in AI competitions
- **ExtractCode** (Gemini API Developer Competition entry, Senegal): takes a YouTube URL and extracts on-screen code ([page](https://ai.google.dev/competition/projects/extractcode)). It didn't win. The lesson is that "extract X from a video" alone isn't enough. Winning requires the **downstream action**: sourcing, pricing and compatibility.
- **GKE Turns 10 Hackathon grand prize: "cart-to-kitchen AI assistant"**, which analyses a grocery cart and recommends recipes (Gemini + ADK + A2A). The **APAC winner, V-Commerce Studio**, and **EMEA winner Cartmate** (*"six specialized AI agents"*) are also commerce agents ([Google Cloud blog](https://cloud.google.com/blog/topics/developers-practitioners/winners-and-highlights-from-gke-hackathon/)). Google Cloud judges have repeatedly rewarded **multi-agent commerce assistants tied to a concrete everyday task**. Bharat Sourcer is the mirror image of cart-to-kitchen: project-to-cart.
- **Honourable mention: "CO2-Aware Shopping Assistant"** (same source). A sustainability metric on a shopping agent was enough to stand out. A "kg CO₂ / import miles saved" line is a cheap addition.

### 2.4 Things not found
Searches for a "localise a project BOM to India" startup, a "YouTube DIY video → parts list" AI tool, or an electronics-component price comparator across Robu, Evelta and Robocraze found **no direct competitor**. The closest are Taskade's generic "YouTube video to project/to-do list" converters (search results only) and an [EEVblog user's replacement-part AI](https://www.eevblog.com/forum/projects/i-created-an-ai-to-find-replacement-parts/) (search result only). Say "no known tool does video → localised costed BOM", not "nobody has ever done this".

### 2.5 Legal and data cautions for sourcing
- **YouTube:** Gemini ingests a public YouTube URL natively, so there's no need to download or re-host video. Show the thumbnail through the official embed.
- **Retailer data:** prefer Google Search grounding and the URL context tool for store pages, which is also the best Google-native story for technical merit. If scraping, respect robots.txt and cache lightly. The T&C bar third-party rights infringement.
- **Price display:** India's Legal Metrology (Packaged Commodities) Amendment Rules 2017 (effective Jan 1 2018), Rule 6(10), require e-commerce entities to display *"the maximum retail price inclusive of all taxes"* and the country of origin ([LKS law firm](https://www.lkslaw.com/insights/articles/aiming-greater-transparency-on-sale-of-packaged-commodity-online)). Bharat Sourcer is a comparator, not a seller, so this doesn't bind it directly. Still, it means **Indian store prices are normally shown GST-inclusive**. Show "incl. GST" and "+ shipping" separately. Showing **country of origin** from the listing is a nice extra.

---

## 3. Winning patterns

### 3.1 What recent Google-sponsored winners had in common

| Competition | Winners (examples) | Common thread | Source |
|---|---|---|---|
| Gemini API Developer Competition | Jayu (Best Overall: on-device assistant with visual understanding); Vite Vere (Most Impactful + People's Choice: cognitive-disability support); Gaze Link (ALS eye communication); ViddyScribe (Best Web: audio descriptions for video) | **Multimodality** plus a **clearly named beneficiary**. Google's write-up stresses *"ability to interpret visual information"* and solutions for *"people who are blind or visually impaired"* | [ai.google.dev/competition](https://ai.google.dev/competition), [Developers Blog](https://developers.googleblog.com/en/announcing-the-winners-of-the-gemini-api-developer-competition/) |
| ADK Hackathon (10,400+ participants, 477 submissions) | Grand prize SalesShortcut (multi-agent SDR); APAC: GreenOps (agents auditing cloud sustainability); Edu.AI (Brazil-specific education) | **Several specialised agents with clear roles**. Regional specificity (the Brazil example) was rewarded. Judging: Technical 50%, Innovation 30%, Demo & docs 20%, with an **architecture diagram required** | [ADK results blog](https://cloud.google.com/blog/products/ai-machine-learning/adk-hackathon-results-winners-and-highlights), [Devpost](https://googlecloudmultiagents.devpost.com/) |
| GKE Turns 10 | Cart-to-kitchen (grand prize), V-Commerce Studio (APAC), Cartmate (EMEA) | Judges valued *"Creative problem-solving using agentic AI architecture"*, *"Effective use of Google's ecosystem (Gemini, ADK, A2A protocols)"*, *"Real-world impact"* | [GKE winners blog](https://cloud.google.com/blog/topics/developers-practitioners/winners-and-highlights-from-gke-hackathon/) |
| **Gen AI Exchange Hackathon 2025 (Google Cloud × Hack2skill, India; same organiser)** | 10 winners, including **ArtisanGully** (AI marketplace listings for local artisans), Parallax (explainable deepfake detection), Cement Operations Optimizer (autonomous agents), Legal SahAI (RAG) | 270,000 developers; top 100 pitched to a 30-member jury. Judges valued *"domain-specific, production-ready tooling"* that could *"provide auditability, and scale"*; a *"shift away from prototype-style demos towards agentic systems and explainable models"* | [Hack2skill blog](https://blog.hack2skill.com/gen-ai-exchange-hackathon-finale), [Outlook Business](https://www.outlookbusiness.com/deeptech/artificial-intelligence/google-cloud-gen-ai-hackathon-2025-winners-use-cases-and-what-270000-developers-built) |

**Takeaways for Bharat Sourcer:**
1. **Agents with visible, distinct roles** (ADK, GKE and Gen AI Exchange all point this way). Name the agents in the UI and on the architecture slide.
2. **Explainability and auditability.** The Hack2skill jury explicitly valued this. Every INR price should cite a store URL, and every part should cite a video timestamp.
3. **Multimodal input** (Gemini competition). Accepting video directly is the most visible multimodal feature.
4. **A local, named beneficiary** (Edu.AI for Brazil, ArtisanGully for Indian artisans). For example: "Ravi, a second-year engineering student in Coimbatore with a ₹2,000 budget". Check the profession rule first: since only professionals can enter, the persona can still be a student user, but the team can't include one.
5. **Production signals**: Cloud Run, evals, caching, cost per query. The Gen AI Exchange jury looked for "production-ready".

### 3.2 A 3-minute demo video plan (2:45 target)
Synthesised from [Terence Eden](https://shkspr.mobi/blog/2019/11/how-to-present-at-a-hack-day/) (*"A good demo won't bombard them with slides"*, *"Spend just 10 seconds explaining the premise"*, *"Focus on the happy-path"*), [AngelHack](https://angelhack.com/blog/10-tips-to-help-you-rock-your-next-hackathon-demo/) (*"Focus on storytelling"*, *"Name your model and how you evaluated it"*, *"Share more than what's already on screen"*, *"Make it fun and memorable"*), [hackathon.com](https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know) (*"immediately demonstrat[e] your project"*) and [DEV](https://dev.to/jacklyn/how-to-make-your-devpost-submissions-not-suck-37i0) (judges spend *"only five minutes per project"*).

| Time | Segment | Content |
|---|---|---|
| 0:00–0:15 | Hook | Screen recording of a popular US YouTube build (e.g., a robot arm). Cut to the Amazon.com cart: "$142 + $60 shipping + customs. In India?" |
| 0:15–0:25 | Premise | One line: "Bharat Sourcer turns any maker video into a costed Indian parts list." |
| 0:25–1:35 | **Live happy path on a phone** | YouTube app → Share → Bharat Sourcer. The agent trace streams: Watching video → found 14 parts (with timestamps) → searching Robu / Evelta / Robocraze / Amazon.in in parallel → compatibility check flags a US 12V 2A adapter with a 2-pin plug and suggests an Indian 5A/6A plug SMPS → total ₹3,480 vs ₹14,900 imported. |
| 1:35–2:05 | **"Wow" moment** | Tap a BOM row: the video jumps to 04:12 where the part appears. Or: "No exact match for the pancake NEMA17. Here are 2 functional alternatives, medium confidence, and why." |
| 2:05–2:30 | Under the hood | Architecture animation: Gemini 2.5 video understanding → ADK SequentialAgent with ParallelAgent → Search grounding → Cloud Run. Name the models and show an eval figure, e.g., "BOM extraction recall 91% on 30 labelled videos". |
| 2:30–2:45 | Impact + close | "X lakh Indian engineering students; ~70% saving on our test set; works for any country." Logo, URL, theme. |

Production tips: record at 1080p, add burned-in captions (it's English-only and judges may watch muted), include no music with lyrics, and keep a pre-recorded fallback. Upload as a **public** YouTube video, not unlisted. The rules accept either, but public avoids access problems.

### 3.3 Deck structure (PDF)
Hack2skill usually provides its own PPT template in the participant dashboard. **Check the dashboard first and use theirs if it exists.** Its exact headings couldn't be verified: the SlideShare copy didn't load. Otherwise, use about 12 slides mapped to the rubric:

1. Title: name, tagline, team, **theme: Retail & Commerce**
2. Problem: the maker cost gap, with a real price comparison and the forum pain quotes (§2.2)
3. Who it's for: 2 personas plus a secondary stakeholder (Indian retailers get demand)
4. Solution in one picture: share → agents → costed BOM
5. Demo screenshots (3 mobile frames)
6. **Architecture diagram**: ADK agents, Gemini models, tools, Cloud Run, Firestore cache *(Technical 40%)*
7. **GenAI depth**: video grounding with timestamps, structured output schema, 4-tier compatibility reasoning, grounding citations, evals *(Technical 40%)*
8. Competitive landscape: the §2.1 matrix condensed, plus the "Why not Google Lens?" answer *(Innovation 25%)*
9. Impact and metrics: ₹ saved per project, time saved, test-set results *(Impact 25%)*
10. UX and accessibility: share-sheet, INR/GST, low-data mode, WCAG *(UX 10%)*
11. Business model and scale: affiliate links (YouTube Shopping precedent), retailer partnerships, expansion across JAPAC
12. Roadmap and asks

---

## 4. UX patterns for Bharat Sourcer

### 4.1 Showing agent reasoning (transparency)
Draws on Smashing Magazine's [AI transparency patterns](https://smashingmagazine.com/2026/05/practical-interface-patterns-ai-transparency/) and [agentic UX patterns](https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/):

| Pattern | Source quote | Bharat Sourcer implementation |
|---|---|---|
| **Dynamic Checklist** | *"completed steps, current progress, and pending actions"* | A vertical stepper: ① Watching video ② Extracting parts (14) ③ Searching 5 stores ④ Checking compatibility ⑤ Costing. Stream it over SSE from Cloud Run. |
| **Living Breadcrumb** | subtle status that *"smoothly transitions between task updates"* | A one-line status under the header on mobile ("Checking Robu for 'TB6612FNG'…"). |
| **Thinking Toggle** | *"expand friendly summaries into sanitized raw logic logs"* | A "Why this part?" expander on each row showing the agent's rationale and the sources checked. |
| **Audit Trail / "Show Work"** | persistent record *"to review decision logic"* | Save each run as a shareable URL with all citations, which also helps the Social Choice Award (shareable links spread). |
| **Intent Preview** | *"User reviews and approves the agent's plan before any action"* | After extraction: "I found 14 parts. Edit or remove any before I search?" This keeps the human in the loop and catches extraction errors cheaply. |
| **Confidence Signal** | *"communicates its own certainty"* | Chips per row. See §4.2. |
| **Escalation Pathway** | *"requests clarification... when facing ambiguous situations"* | "The video doesn't show the motor's voltage. Is it 6V or 12V?" as a quick-reply chip. |
| Partial success | *"design for when the AI is mostly successful"*; *"clearly show what worked and what didn't"* | "12 of 14 parts sourced in India · 2 need import". Never a single pass/fail. |

### 4.2 Confidence and compatibility display (Google PAIR)
From the [PAIR Guidebook, Explainability + Trust](https://pair.withgoogle.com/chapter/explainability-trust/):
- *"categorize confidence values into buckets, such as High / Medium / Low and show the category rather than the numerical value."*
- **N-best alternatives** are *"especially useful in low-confidence situations"*.
- Numeric percentages are *"risky because they presume your users have a good baseline understanding of probability."*
- Goal: users should *"trust it in some situations, but to double-check it when needed."*

Combining that with PartGenie's tiers gives a **4-level compatibility chip**:

| Chip | Meaning | Colour + icon (never colour alone) |
|---|---|---|
| ✅ Exact | Same SKU or MPN (e.g., the genuine Adafruit board from Thingbits) | Green + check |
| 🔁 Drop-in | Different brand, same pinout and spec (e.g., HC-SR04 clone) | Teal + swap icon |
| ⚠️ Works with changes | Functional alternative that needs a wiring or code change (e.g., 3.3V logic, level shifter needed) | Amber + warning, with a mandatory "What changes" note |
| ❓ Check | Low confidence. Show the top 2–3 alternatives (N-best) | Grey + question |

From [PAIR Errors + Graceful Failure](https://pair.withgoogle.com/chapter/errors-failing/): make **"context errors"** visible, i.e. explain *why* a substitute was chosen. **"Return control"**: every row has "Change part" and "I already have this". **"Solicit feedback"**: a thumbs-down on a row asks "What was wrong? wrong part / wrong price / out of stock", which also gives you eval data.

### 4.3 Citations
- Each price shows the store name, a favicon, "checked 2 min ago", and an outbound link.
- Each part links to its **video timestamp** (Gemini `MM:SS`) and, for blogs, the quoted sentence.
- If you use Google Search grounding, you must **render the `search_suggestions` snippet** per the ToS ([grounding docs](https://ai.google.dev/gemini-api/docs/google-search)). Put it in a collapsible "Sources" footer.

### 4.4 Comparison table and BOM layout
- **Mobile:** use cards, not a wide table. Each card shows part name, qty, chosen store and price, a chip, and "2 more options ▾".
- **Desktop:** a table with columns for Part · Qty · Original (USD, source store) · Best India option · Store · Unit ₹ · Line ₹ · Match chip · Stock.
- **Sticky footer:** a total ₹ with a breakdown (Parts / Shipping per store / Estimated GST included) and "Saved ₹X vs importing".
- **Cart optimisation toggle:** "Cheapest overall" vs "Fewest stores". Free-shipping thresholds (e.g., ₹999 at Robu/Zbotic) change the best split. This is also a small optimisation agent that impresses judges.

### 4.5 INR formatting and GST
- Use `new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR'})`. MDN confirms en-IN lakh grouping: `new Intl.NumberFormat("en-IN").format(123456.789)` → `1,23,456.789` ([MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat)). Display ₹1,23,456 rather than ₹123,456, and consider "₹1.2 L" for large totals.
- Round to whole rupees in the UI and keep paise in the export.
- Label prices "incl. GST" by default. MRP display rules make GST-inclusive the norm (§2.5). Show shipping separately, since it varies by store and threshold.
- Show the original USD/GBP **and the landed import cost**: item + international shipping + customs duty estimate. The honest comparison is "India ₹3,480 vs import ₹14,900 landed", not an exchange-rate conversion. State the assumed duty rate and FX date as a footnote so the numbers can be audited.

### 4.6 Mobile-first entry: share from the YouTube app
- **PWA route (fastest to build):** add a `share_target` to the manifest ([Chrome docs](https://developer.chrome.com/docs/capabilities/web-apis/web-share-target)):
  ```json
  "share_target": { "action": "/share-target/", "method": "GET",
    "params": { "title": "title", "text": "text", "url": "url" } }
  ```
  This is supported on Chrome 76+ on Android. **The PWA must be installed first** (*"This prevents sites from randomly adding themselves to the share chooser"*). Practical note: many Android apps, YouTube likely among them, put the link in `text` rather than `url`. Parse both with a URL regex. Test on a real device.
- **Native route (optional):** an Android `ACTION_SEND` intent filter with `text/plain`, then read `Intent.EXTRA_TEXT` ([Android docs](https://developer.android.com/training/sharing/receive)). A Trusted Web Activity wrapper around the PWA can add this, but it's probably not worth it before Oct 18.
- **Fallbacks:** a paste box that auto-detects a link on the clipboard (with a "Paste link" button, since clipboard read needs a user gesture) and a **bookmarklet or Chrome extension** for desktop YouTube.
- For the demo video, **film the share-sheet flow on a real Android phone**. It's the most relatable moment for Indian judges and users.

### 4.7 Low-bandwidth and low-end devices
Google Design's [Connectivity, Culture and Credit](https://design.google/library/connectivity-culture-and-credit): *"Products in emerging markets have to be able to perform over slow or intermittent connectivity"*. Some users afford only about 250 MB a month: *"People will turn off their phones at night to save data."* It also notes that *"less than 2 percent of Indians have credit cards"*, which argues for linking to stores that support UPI and COD (e.g., Robocraze offers COD).

What that means here:
- **All video processing happens server-side** in Gemini, so the user never downloads the video. Make this explicit: "We watch it so you don't spend data."
- Keep the JS bundle under about 150 KB. Show text first with lazy-loaded thumbnails, and add a "Lite mode" with no product images.
- Make runs **resumable**. Store job state in Firestore keyed by run ID, so a dropped connection resumes instead of restarting a 60-second agent run. Send a push or "we'll text you the link" for long runs.
- Cache results per video ID. A second user sharing the same popular video gets an instant answer and costs no extra tokens, which is also a scalability point for technical merit.

### 4.8 Accessibility (WCAG 2.2 AA; [W3C quickref](https://www.w3.org/WAI/WCAG22/quickref/))
- **1.4.3 Contrast (Minimum):** 4.5:1 for text. Check the amber "Works with changes" chip in particular.
- **2.5.8 Target Size (Minimum):** at least 24×24 CSS px. Material recommends 48 dp for touch.
- **4.1.3 Status Messages:** the streaming agent steps must use `role="status"` / `aria-live="polite"` so screen-reader users hear the progress. This is a concrete, demonstrable accessibility feature.
- Chips carry text plus an icon, never colour alone.
- Nice extra for the Impact score: Hindi and regional-language output (Gemini supports it). The **submission must be in English**, but the app can offer हिन्दी / தமிழ் toggles. The Gemini app already takes Hindi shopping follow-ups ([Outlook Business](https://www.outlookbusiness.com/ampstories/deeptech/google-rolls-out-ai-shopping-tools-in-india-heres-how-it-works)).
- Material 3 content guidance: *"UI text should be understandable by anyone, anywhere"* ([M3 UX writing](https://m3.material.io/foundations/content-design/style-guide/ux-writing-best-practices); the page renders in JS, so only the meta description could be read). Use plain words such as "Works with small changes" rather than "functionally equivalent".

---

## 5. Naming and branding

### 5.1 Is "Bharat Sourcer" a good name?
**Strengths**
- Immediately says India ("Bharat") and the job ("sourcing"). For an India-rooted JAPAC entry, the local identity is on-brief ("Build in JAPAC. Build for the world.").
- "Bharat" is widely used by private brands (e.g., BharatPe, Bharat Biotech). The [Emblems and Names (Prevention of Improper Use) Act, 1950](https://bnblegal.com/bareact/emblems-names-act-1950/) Schedule doesn't list "Bharat" or "India". It only prohibits *"Any name which may suggest or be calculated to suggest — (i) the patronage of the Government of India"* (Item 7). **Avoid visual cues that look governmental**: the Ashoka emblem, tricolour-as-seal, "Official", ".gov"-like styling.

**Weaknesses**
- **"Sourcer" collides with recruiting.** A search for the exact phrase returned no product named "Bharat Sourcer", but "Sourcer" results were all talent-acquisition jobs and HR software: G2 lists at least two products called "Sourcer" (search results only: [g2.com Sourcer](https://www.g2.com/products/sourcer-sourcer/reviews), [alternativeto](https://alternativeto.net/software/sourcer/about/)). "Sourcer" reads as recruiter jargon to many people, so SEO and first impressions suffer.
- It's awkward to say ("sor-ser") and easily misspelt as "Sourcerer" or "Source-r".
- It doesn't mention making, parts or video, so judges get the "India" but not the "what".
- Outside India, "Bharat" may need explaining, but the Singapore/JAPAC judges will likely know it.

**Conflict checks done:** a web search for "Bharat Sourcer" / "BharatSourcer" found **no existing product or company**. The domain check on bharatsourcer.com timed out (the fetch needed permission), so **check .com/.in/.app availability yourself**. The Indian trademark register (IP India public search) wasn't checked. For a hackathon this is low risk; do it before any commercial use.

**Verdict:** fine for a hackathon and memorable to Indian judges, but not the strongest option. Rename only if a better option is clearly available by domain. Otherwise keep it and let a strong tagline carry the meaning.

### 5.2 Alternative names (not trademark-checked)

| Name | Rationale |
|---|---|
| **Desi BOM** | Short and maker-literate ("BOM" is what makers call it); playful |
| **PartsBharat** / **BharatParts** | Clearer than "Sourcer"; generic, so it may be taken |
| **JugaadKart** | "Jugaad" (frugal ingenuity) plus a cart. Very Indian and memorable. Note that "jugaad" can imply hacky or low quality. |
| **Swadeshi Parts** | Self-reliance framing (Atmanirbhar), but politically loaded |
| **BuildLocal** / **Local BOM** | Works globally for the JAPAC scale-up story ("BuildLocal India, BuildLocal Indonesia") |
| **Kit Kaise?** (Hinglish: "How do I get the kit?") | Fun as a sub-brand or feature name |

A hybrid option: keep **Bharat Sourcer** as the product name and use **"Desi BOM"** as the name of the output artifact ("Your Desi BOM is ready").

### 5.3 Tagline options
1. **"Watch it in America. Build it in India."** (strongest; gives the pitch's before/after in six words)
2. "Any maker video → a costed Indian parts list."
3. "From YouTube to your doorstep, in rupees."
4. "Same build. Indian parts. Half the price." (only if your test set supports "half")
5. "Stop importing. Start building."
6. For the JAPAC and global slide: "Any build, sourced locally."

---

## 6. Actionable checklist (by date)

| By | Action |
|---|---|
| **Now** | **Email support+aibuildercup@hack2skill.com about UK residency eligibility.** Decide whether to continue. |
| **Oct 4** | Register on Hack2skill; finalise a 2–4 person team of JAPAC-based, 21+, non-student professionals (T&C roster lock). Join Discord. Ask whether Google Cloud credits are available. |
| Oct 4–6 | New public repo. Skeleton: ADK agents on Cloud Run, Gemini video → BOM JSON, one Indian store via grounding plus URL context. |
| Oct 7–12 | Parallel store search, 4-tier compatibility agent, INR costing with a landed-import comparison, PWA share target, streaming trace UI. |
| Oct 13–14 | Eval set of about 30 videos with hand-labelled BOMs. Measure extraction recall and precision and the sourcing hit-rate. These numbers go in the deck and video. |
| Oct 15–16 | Accessibility pass (contrast, aria-live, targets), caching, min-instances, error states. |
| Oct 16–17 | Record video (under 3:00, captions, real phone), build deck PDF, write README with architecture diagram. **Submit by Oct 17** as a buffer. |
| Oct 19 – Nov 6 | Keep the deployment up and warm during judging. |

---

## Sources opened

**Competition:** https://aibuildercup.com/index.html · https://aibuildercup.com/themes.html · https://aibuildercup.com/rewards.html · https://aibuildercup.com/Faqs.html · T&C: https://docs.google.com/document/d/e/2PACX-1vRm7ChZ6Ij9fG7uFDkxzUMpwgVeBmnQ6cMDnAIEEX84AiLBOOQ9cYbl3S5OzFBbcVb8TF55s-eVpiXb/pub · https://metropolisjapan.com/events/ai-builder-cup-2026/ · https://opportunitiescorners.com/google-cloud-ai-builder-cup-2026-in-singapore/ · (hack2skill.com/event/aibuildercup2026 loaded as a blank JS page)

**Google tech:** https://ai.google.dev/gemini-api/docs/generate-content/video-understanding · https://ai.google.dev/gemini-api/docs/google-search · https://adk.dev/

**Competitors:** https://octopart.com/bom-tool · https://kitspace.org/ · https://github.com/kitspace/1clickBOM · https://www.hackster.io/glowascii/basic-hardware-components-77182f · https://www.partgenie.ai/alternative-finder · https://parter.ai/alternatives · https://www.flux.ai/ · https://www.circuitmind.io/ · https://www.cofactr.com/ · https://buyhatke.com/ · https://www.mysmartprice.com/ · https://blog.google/products/shopping/visual-search-lens-shopping/ · https://www.outlookbusiness.com/ampstories/deeptech/google-rolls-out-ai-shopping-tools-in-india-heres-how-it-works · https://yourstory.com/2024/10/youtube-expands-shopping-programme-india · https://zbotic.in/best-online-electronics-stores-india-2026/ · https://techenclave.com/t/indian-sites-for-electronics-diy-tinkerers-makers-to-shop-for-tools-and-components/271822?page=2 · https://ai.google.dev/competition/projects/extractcode

**Winners and pitching:** https://ai.google.dev/competition · https://developers.googleblog.com/en/announcing-the-winners-of-the-gemini-api-developer-competition/ · https://cloud.google.com/blog/products/ai-machine-learning/adk-hackathon-results-winners-and-highlights · https://googlecloudmultiagents.devpost.com/ · https://cloud.google.com/blog/topics/developers-practitioners/winners-and-highlights-from-gke-hackathon/ · https://blog.hack2skill.com/gen-ai-exchange-hackathon-finale · https://www.outlookbusiness.com/deeptech/artificial-intelligence/google-cloud-gen-ai-hackathon-2025-winners-use-cases-and-what-270000-developers-built · https://shkspr.mobi/blog/2019/11/how-to-present-at-a-hack-day/ · https://angelhack.com/blog/10-tips-to-help-you-rock-your-next-hackathon-demo/ · https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know · https://dev.to/jacklyn/how-to-make-your-devpost-submissions-not-suck-37i0 · https://forum.trondao.org/t/tron-grand-hackathon-improving-your-devpost-judge-score/9393

**UX:** https://pair.withgoogle.com/chapter/explainability-trust/ · https://pair.withgoogle.com/chapter/errors-failing/ · https://smashingmagazine.com/2026/05/practical-interface-patterns-ai-transparency/ · https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/ · https://developer.chrome.com/docs/capabilities/web-apis/web-share-target · https://developer.android.com/training/sharing/receive · https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat · https://design.google/library/connectivity-culture-and-credit · https://www.w3.org/WAI/WCAG22/quickref/ · https://m3.material.io/foundations/content-design/style-guide/ux-writing-best-practices · https://www.lkslaw.com/insights/articles/aiming-greater-transparency-on-sale-of-packaged-commodity-online

**Naming:** https://bnblegal.com/bareact/emblems-names-act-1950/ · (search results only: g2.com/alternativeto "Sourcer" listings)

**Tried but couldn't read:** the Devpost demo-video blog, bharatsourcer.com, indiacode.nic.in (permission timeouts); the Hack2skill SlideShare template (JavaScript wall); pair.withgoogle.com/guidebook/chapters (JS-only).
