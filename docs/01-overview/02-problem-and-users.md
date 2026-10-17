# Problem and users

> **In one minute.** Indian makers copy projects from US/UK creators. Those parts lists point to stores and brands that don't serve India. Local equivalents exist, often at 5–15× lower prices, but finding them and knowing they'll work takes hours, and mistakes are expensive (or dangerous, with mains). Our users are students, hobbyists, lab mentors and small repair and prototyping shops.

---

## 1. The problem in detail

### 1.1 Where makers learn

Indian makers mostly learn from English-language channels and sites run outside India:

- Adafruit Learn, SparkFun and Random Nerd Tutorials
- DroneBot Workshop, GreatScott!, Andreas Spiess, Ben Eater
- Instructables and Hackster

Their parts lists link to Adafruit, SparkFun, Pololu, Digi-Key, Mouser and Amazon.com.

### 1.2 Why those parts lists fail in India

| Failure mode | Example | Source |
|---|---|---|
| **Price gap** (brand original vs Indian clone) | Pololu DRV8825 carrier **$15.95**; clone DRV8825 with heatsink on Zbotic **₹85 + GST = ₹100.30** (≈13× cheaper) | Team research, 30 Sep 2026 |
| **Not stocked / sold out** | Adafruit ESP32-S3 Reverse TFT Feather **sold out** at Thingbits (₹2,889.82). Teensy 4.1 listed at Zbotic ₹3,538.82 but **out of stock** | Team research, 30 Sep 2026 |
| **Brand ecosystems with few Indian equivalents** | Feather, Qwiic/STEMMA QT, Teensy, Pololu gearmotors. Substituting these needs *functional* reasoning (same chip, different form factor/connector) | Team research, 30 Sep 2026 |
| **Import cost** | Personal imports (CTH 9804): BCD cut **20% → 10% from 1 Apr 2026** + 10% social welfare surcharge on BCD + IGST (Mumbai Customs quotes 42.08% total at the old 28% IGST ⚠️ verify current IGST). Plus international courier, often more than the part itself | Team research, 30 Sep 2026 |
| **AliExpress blocked** | Blocked since 24 Nov 2020 (IT Act §69A). Forum users describe "local monopoly pricing" | Team research, 30 Sep 2026 |
| **Chip import paperwork** | LCSC shipments of chips to India need **CHIMS** registration + DHL KYC | Team research, 30 Sep 2026 |
| **Electrical standards** | US: **120 V / 60 Hz, plugs A/B**. India: **230 V / 50 Hz, plugs D (6 A) and M (16 A)**. A 60 Hz synchronous motor runs ≈17% slower at 50 Hz, and a 60 Hz transformer on 50 Hz sees ≈20% more core flux (saturation, overheating) | Team research, 30 Sep 2026 |
| **Look-alike / fake parts** | Cheap "BME280" modules are often BMP280s (no humidity). Chip-ID register 0xD0 reads 0x60 on a real BME280 and 0x58 on a BMP280 | Team research, 30 Sep 2026 |
| **Price display inconsistency** | Some stores show prices **ex-GST** (Evelta), others incl. GST. Free-shipping thresholds vary (₹499/₹999/₹2,000) | Team research, 30 Sep 2026 |
| **Store reliability varies** | TechEnclave users report problems with some budget stores (partial shipments, wrong quantities) | Team research, 30 Sep 2026 |

### 1.3 What people do today

1. Watch the video, pause and write down parts. Often the description has only affiliate links, and some parts appear only on screen.
2. Search each part on Robu, Robocraze, Amazon.in, ElectronicsComp and others, one by one.
3. For missing parts, ask on Quora, Reddit, TechEnclave, WhatsApp groups or an LLM chat. The answers are ungrounded.
4. Guess compatibility and discover problems when the parcel arrives: 5 V vs 3.3 V, different I2C address, different library, VCC/GND swapped on a 1.3" OLED.
5. Pay shipping on several small orders because nothing optimises the cart across free-shipping thresholds.

The TechEnclave thread (89 Indian retailer sites) confirms three pains:

- comparing prices across many sites by hand
- specialty items that are hard to find (e.g. "pancake NEMA17")
- unreliable stores

(Team research, 30 Sep 2026)

## 2. Size of the opportunity (impact slide numbers)

| Metric | Number | Source |
|---|---|---|
| Atal Tinkering Labs in schools (Oct 2025) | **10,000** | PIB, 5 Dec 2025 |
| Students engaged in ATLs | **> 1.1 crore** | PIB |
| Innovation projects from ATLs | **> 16 lakh** | PIB |
| ATL expansion target | **50,000** labs | PIB |
| Engineering (BE/BTech) enrolment per year (AICTE 2021-22) | **14.1 lakh** enrolled of 25.4 lakh seats | Careers360 / AICTE |
| India electronics imports FY25-26 | **$116.17 B** (record, +17.8%) | The Week, 16 Apr 2026 |
| E-waste generated FY24-25 | **13.97 lakh tonnes** | CPCB via Parliament |
| Maker event scale | MakerFest Vadodara 2026: 10,000+ visitors, 70+ makers | SSIP Gujarat |
| Retail signal | Quartz Components: 3 lakh+ orders to 18,000+ PIN codes | quartzcomponents.com |

Links for all rows: [../04-reference/03-citations-and-news.md](../04-reference/03-citations-and-news.md).

**Pitch framing (no invented numbers):**

> "10,000 Atal Tinkering Labs and 1.1 crore students today, going to 50,000 labs, plus ~14 lakh new engineering students a year. They all learn from US/UK tutorials whose parts lists don't match what they can buy."

We don't have a reliable market-size figure for Indian hobby electronics, so we don't claim one.

## 3. Users and personas

### Primary personas

| Persona | Context | Job to be done | What success looks like |
|---|---|---|---|
| **Ravi, 2nd-year ECE student, Coimbatore** | ₹2,000 budget, Android phone, patchy data, learns from YouTube, buys from Robu/Amazon.in | "Build this ESP32 weather station for my mini-project without overspending or frying anything" | A trustworthy list under budget, a clear "what to change" note, parts arriving in 3–5 days |
| **Priya, ATL mentor at a school in Kochi** | Runs a lab for 40 students, orders in bulk, needs safe projects, prefers Malayalam explanations for some students | "Turn this Adafruit Learn project into a lab kit I can order locally for 10 teams" | Qty × 10 BOM, one or two sellers, GST invoice, no mains parts, spoken explanation for students |
| **Arjun, hobbyist and working professional, Pune** | Owns a parts bin, 3D printer, likes genuine parts when it matters | "Replicate this GreatScott! build; tell me what I already have and where the genuine board is sold" | Exact-match options (Thingbits/Robu authorised) *and* cheap alternatives, with honest trade-offs |

### Secondary stakeholders

- **Indian retailers** (Robu, Robocraze, Quartz, Evelta…): receive qualified demand. There's an affiliate or partnership model (YouTube Shopping is a precedent).
- **Creators**: their videos become buildable in India, which is a reach story.
- **College clubs and repair shops**: bulk and repeat BOMs.

### Anti-personas (explicitly out of scope)

- Professional EEs designing new PCBs. Flux, Octopart and Circuit Mind already serve them.
- Anyone wanting automated purchasing. We never auto-checkout ([../02-architecture/10-safety-trust-and-compliance.md](../02-architecture/10-safety-trust-and-compliance.md)).

## 4. Problem statement (for the deck)

> Indian makers can watch any project in the world but can't build most of them as shown. Parts are missing, overpriced or electrically wrong for India. Adapting a single project takes hours of research, and wrong guesses waste money or create safety hazards. **Bharat Sourcer turns any maker video into a verified, costed, India-ready parts list in minutes.**

## 5. Assumptions to validate (cheaply, before the deck)

| Assumption | How to validate by Oct 12 |
|---|---|
| Most parts in popular US/UK builds have Indian equivalents | Run the 15-project eval set and report the "% parts sourced in India" metric |
| Local cost is much lower than import | Compute the landed import cost vs Desi BOM on the eval set and report the median saving |
| Users trust graded substitutes | 5 quick user tests with maker friends and classmates of teammates. Record quotes for the deck |
| Share-from-YouTube is the natural entry | Test the PWA share target on 2–3 Android phones |
