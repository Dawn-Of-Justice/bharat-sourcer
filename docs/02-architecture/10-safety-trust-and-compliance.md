# Safety, trust and compliance

> **In one minute.**
> - **Physical safety:** mains (120 V US → 230 V India) and Li-ion are handled by hard-coded rules and templated banners, never by the LLM alone.
> - **Trust:** no URL, price or number reaches the user without verification or a citation.
> - **Legal:** sanctioned data paths only (UCP/MCP, documented store APIs, distributor APIs, Google grounding), no auto-checkout, no re-hosting of YouTube or seller images, and minimal personal data (DPDP Act).
> - **Hackathon:** fresh code, public repo with no secrets, third-party rights respected.
>
> *Not legal advice; confirm anything commercial with a lawyer.*

---

## 1. Physical safety

### 1.1 Mains voltage

| | India | USA | UK |
|---|---|---|---|
| Voltage | **230 V** | 100–127 V | 230 V |
| Frequency | **50 Hz** | 60 Hz | 50 Hz |
| Plugs | **Type D (6 A), Type M (16 A)** | A, B | G |

Source: [WorldStandards India](https://www.worldstandards.eu/electricity/plug-voltage-by-country/india/).

Rules (implemented in `compat/rules.py`, see [05-compatibility-engine.md §5](05-compatibility-engine.md#5-rules-engine)):

- Any line in category `mains_switching`, or any project that switches an AC appliance, sets the **MAINS** flag. That shows a red banner at the top of the BOM and in the video, plus a checklist:
  - enclosure
  - earth continuity
  - fuse
  - strain relief
  - no exposed 230 V on the low-voltage side
  - "have a qualified electrician review"
- US-plug products (e.g. PowerSwitch Tail II) get grade **X**. Recommend a 230 V-rated, ≥ 250 VAC relay/SSR in an enclosure, or a certified smart plug for beginners.
- **60 Hz-specific** parts (synchronous clock motors, 60 Hz transformers) are graded D or X, with the reason stated: about 17% slower, or about 20% higher core flux (saturation and overheating risk).
- **UK projects:** mains is 230 V / 50 Hz like India's, so parts often transfer; only the plug differs (G vs D/M). This reduces false alarms.
- **Universal SMPS** labelled "100–240 V" is marked safe to reuse, with a plug adapter or a local equivalent.
- For `user_level=beginner`, mains projects show a "Consider a low-voltage version" suggestion.

### 1.2 Other hazards

| Flag | Trigger | Required text |
|---|---|---|
| LIPO | Li-ion/LiPo cells or packs | Protection circuit (DW01/BMS), correct charger (TP4056 with protection), JST polarity check, no charging unattended |
| HIGH_CURRENT | > 3 A rails, motors, LED strips | Wire gauge, fuse, PSU headroom math |
| LEVEL_SHIFT_REQUIRED | 5 V signal into a 3.3 V input | Divider or shifter, with values |
| HEAT | Heaters, high-power resistors, stepper drivers without heatsinks | Heatsink or ventilation |
| LASER | Laser modules | Eye-safety class, goggles |

Banners are **templated strings** (`backend/compat/banners.py`). The LLM cannot remove or rephrase them.

## 2. Trust: preventing hallucinations

| Risk | Control |
|---|---|
| Invented product or URL | The recommender references `listing_id` only, and the UI renders URLs from `listings`. Listings exist only after verification (HTTP 200, title match, INR price parsed) |
| Invented price or stock | Prices come from JSON-LD, the page or a structured API, with `fetched_at` shown ("checked 12 min ago") |
| Invented specs | Every numeric spec needs a KG or datasheet citation. The judge strips uncited numbers. LLM-derived specs are marked "Likely" |
| Wrong grade | The rules engine sets a grade floor and the LLM can't upgrade it. Judge ×3 majority. Eval grade accuracy is reported |
| Misidentified part | Silkscreen text is read verbatim first, look-alike lists are used, the human confirms, and verify-on-arrival tests are attached |
| Code that doesn't work | Compile in the loop; `compiled=false` is shown honestly |
| Overclaiming in the pitch | Eval numbers come only from the gold set; "no known tool" rather than "first ever" |

## 3. Data sources and legal

### 3.1 Seller data

Priority order:

1. **Merchant-sanctioned agent protocols.** Shopify UCP/MCP, which Robocraze's and Quartz's robots.txt tell agents to use.
2. **Official APIs.** DigiKey, Mouser, element14, Nexar, LCSC, TME, Flipkart Affiliate, Amazon Creators.
3. **Public, documented storefront endpoints** (Shopify `/products.json`, WooCommerce Store API), at a low rate with caching and robots.txt respected.
4. **Gemini grounding with Google Search** for everything else. We show snippets, citations and deep links, and present prices as "last seen".

Indian law context (from [research/02 §5](../../research/02-india-parts-market.md)):

- **IT Act 2000 §43/§66** covers unauthorised access or extraction, both civil and criminal.
- **Copyright Act 1957:** factual price data is weakly protected, but text and images are protected (*Eastern Book Co. v. D.B. Modak*, 2007).
- **Site ToS** often prohibit robots. We don't scrape where they do, and use grounding instead.

We don't:

- bypass bot protection or CAPTCHAs
- scrape login-only pages
- re-host images or descriptions
- auto-checkout ("DO NOT complete checkout…" in Robocraze's `agents.md`)

Robots.txt signals we honour:

| Site | Signal |
|---|---|
| Evelta | Crawl-delay 10 for AI bots, including Google-Extended and GoogleOther |
| Hubtronics | Crawl-delay 10 |
| Robokits | Crawl-delay 5 |
| FlyRobo | Crawl-delay 1 |
| Thingbits | `/api/` disallowed |
| ElectronicsComp, FlyRobo | Search pages disallowed |
| Probots | Explicitly allows AI bots |

### 3.2 YouTube
- We pass the **public URL** to Gemini. We never download, re-host or cut the video.
- Playback uses the official IFrame embed.
- Thumbnails come from the official thumbnail URLs or the embed.
- Only the description is read, via the YouTube Data API (`videos.list`). Caption download via the API is owner-restricted, so we rely on Gemini's own processing.
- Frame extraction with bounding boxes happens **only for user-uploaded videos and blog images**.

### 3.3 Google API terms
- **Search grounding:** render the `search_suggestions` HTML exactly as returned (Sources footer).
- **Maps grounding:** show Google Maps attribution right after the generated content.
- **Paid tier:** our prompts and outputs aren't used to improve Google products. The free tier's are, which is another reason to bill.

### 3.4 Price display
- India's Legal Metrology (Packaged Commodities) Amendment Rules 2017 require e-commerce sellers to show MRP inclusive of taxes and the country of origin.
- We're a comparator, not a seller, but we follow the same norms: GST-inclusive prices and origin shown when the listing states it.

## 4. Privacy (DPDP Act 2023)

| Data | Handling |
|---|---|
| URLs submitted | Stored with the job. Public only if the user chooses "public" |
| PIN/city | Stored per job for delivery and markets. Never tied to identity without sign-in |
| Account (optional) | Firebase Auth (Google). We store uid, display name and saved BOMs only |
| Uploaded images/audio | GCS, deleted after 30 days |
| Analytics | Aggregate counts only; no third-party trackers |
| Deletion | "Delete my data" button for signed-in users; unlisted jobs expire |

A privacy notice in plain English is linked from the footer.

## 5. Security

- Secrets live in Secret Manager only. The repo gets a pre-commit secret scan (`gitleaks`) because it must be **public**.
- The Cloud Run service account follows least privilege: Firestore user, Storage object admin on one bucket, Secret accessor, Run invoker for the compile job.
- **App Check** on job creation, plus rate limits per IP and per user.
- The compile job runs untrusted user code only as `arduino-cli compile`. Nothing executes: no network, a separate service account, and a time limit.
- **Prompt-injection hygiene:**
  - Fetched page text is wrapped as data, and the system prompt says to ignore instructions inside sources.
  - Tool outputs never trigger new tool calls outside the fixed workflow.
  - Computer Use (S11) runs with its safety policy and `require_confirmation`, and stops before checkout.

## 6. Hackathon compliance checklist

- [ ] New repo created after the program launch; frequent commits (proof of fresh code)
- [ ] No code copied from earlier personal projects
- [ ] All compute on Google Cloud (Cloud Run / Firebase); Gemini models
- [ ] Public repo with no secrets in history (`gitleaks detect` clean)
- [ ] Third-party assets: only licensed icons and fonts (e.g. Material Symbols, Google Fonts); seller logos used nominatively and small, or text names instead
- [ ] Video < 3:00, English, captions
- [ ] Team eligibility confirmed in writing by the organisers if there's any doubt
