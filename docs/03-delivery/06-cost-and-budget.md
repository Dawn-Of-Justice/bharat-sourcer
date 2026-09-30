# Cost and budget

> **In one minute.**
> - **Per analysis:** about **$0.40–0.60** with caching and Flash-Lite fan-out. About $0.95 without caching (inside the free 5,000 grounding queries a month), and about $1.65 once past that.
> - **Hackathon total:** under about **$200**, protected by a spend cap, a budget alert, caching and App Check.
> - **Import baseline:** the "savings vs import" number uses a transparent landed-cost formula with dated assumptions.

All prices were checked on 30 Sep 2026 ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). ⚠️ Verify on day 1.

---

## 1. Unit prices used

| Item | Price |
|---|---|
| `gemini-3.8-flash` | $0.75 in / $3.75 out per 1M tokens (intro until 31 Dec 2026) |
| `gemini-3.5-flash-lite` | $0.30 in / $2.50 out |
| `gemini-3.1-pro-preview` | $2.00 in / $12.00 out (≤ 200k ctx), no free tier |
| Grounding with Google Search (Gemini 3) | 5,000 free queries/month (paid tier, shared), then **$14 / 1,000 queries** (billed per query executed) |
| Grounding with Google Maps | 5,000 free/month, then $14 / 1,000 |
| Video tokens (static) | ~100 tokens/s default, ~300 high resolution; agentic mode uses fewer tokens (up to 88% fewer on long videos, per Google) |
| Cloud Run (instance-based) | Free 240k vCPU-s + 450k GiB-s/month; $0.000018/vCPU-s after |
| Firestore | Free 50k reads, 20k writes/day, 1 GiB |
| File Search | Indexing at embedding rates; storage free |

## 2. Cost of one analysis (15-min video, ~25 parts)

| Step | Units | Cost (USD) |
|---|---|---|
| Video extraction (static estimate: 90k in / 10k out) | 3.8 Flash | ≈ 0.11 (agentic: likely less) |
| 3 clip re-reads (high resolution) | 3.8 Flash | ≈ 0.02 |
| Spec resolution, 25 parts | Flash-Lite, 60k in / 20k out | ≈ 0.07 |
| Grounded sourcing: ~50 queries | Search grounding | 0 within 5k/month; **0.70** after |
| Grounded turn tokens | 3.8 Flash, 25 × (8k in / 1.5k out) | ≈ 0.29 |
| URL context reads (~20 pages × 15k) | 3.8 Flash input | ≈ 0.23 |
| Compatibility judge (all parts, one call) | 3.1 Pro, 40k in / 10k out | ≈ 0.20 |
| Report + narration text | 3.8 Flash | ≈ 0.03 |
| Cloud Run | ~180 vCPU-s | ≈ 0.004 (free tier) |
| **Total** | | **≈ $0.95** (free grounding) / **≈ $1.65** (paid grounding) |

With the cost levers below, the total comes to **≈ $0.40–0.60**. A cached library hit costs almost nothing, since only the price re-verification runs.

Source: [research/01 §8](../../research/01-google-stack.md).

## 3. Cost levers (in order of effect)

1. **Library cache by video id.** Repeat videos cost almost nothing.
2. **Parts cache** (`part_offers`, 24 h). Common parts (ESP32, SG90, DHT22) never hit grounding twice a day.
3. **Skip Tier C** when Tiers A + B already give ≥ 3 verified candidates.
4. **One grounded call per part**, covering the original and its candidate substitutes together.
5. **Flash-Lite** for fan-out; Pro only for the judge, in one batched call per job.
6. **Implicit caching:** put the stable prompt prefix first.
7. **Agentic video mode** (fewer tokens on long videos).
8. **Flex / Batch** (50% off) for the nightly re-pricing of library BOMs.

## 4. Hackathon budget

| Bucket | Estimate |
|---|---|
| Development runs (~200 jobs, many partly cached) | ~$60–100 tokens |
| Grounding beyond 5k/month (≈ 5k extra queries) | ~$70 |
| Eval runs (15 projects × ~6 full runs) | ~$40 |
| Judging period (19 Oct – 6 Nov) | ~$10–30 (mostly cached) |
| Cloud Run min-instance (1 × 2 vCPU for ~3 weeks) | ⚠️ could exceed the free tier. Consider `--cpu=1` for the warm instance, or scale to 2 vCPU only when load rises |
| Firestore, Storage, Hosting | ~$0–5 |
| **Total** | **≈ $150–250** |

Guards:

- AI Studio **project spend cap** ($150 to start)
- Cloud Billing **budget alerts** at 50/80/100%
- App Check and per-IP limits on job creation
- Kill switches in `config/runtime`

Ask on the hackathon Discord whether Google Cloud credits are available. None are published.

## 5. Import-baseline formula (used for "savings vs import")

```
landed_inr = (Σ original_price_foreign × qty) × fx_rate
           + intl_shipping_inr
           + duty
duty       = assessable × (BCD + BCD × SWS) + (assessable + BCD_amt + SWS_amt) × IGST
assessable = goods_inr + intl_shipping_inr          (CIF approximation)
```

Defaults (all configurable, shown in the UI footnote with dates):

| Parameter | Default | Note |
|---|---|---|
| BCD (personal imports, CTH 9804) | 10% | Cut from 20% on 1 Apr 2026 (Budget 2026-27) |
| SWS | 10% of BCD | Social Welfare Surcharge |
| IGST | ⚠️ verify (Mumbai Customs FAQ shows 28%, possibly pre-rationalisation) | V13 in the day-1 list |
| International shipping | Flat estimate per origin (e.g. US small parcel) ⚠️ calibrate with 2–3 real quotes | Shown as an assumption |
| FX | Daily reference rate, dated | e.g. RBI reference rate |
| Duty-free threshold | Postal CIF ≤ ₹1,000 per Mumbai Customs FAQ | Applied when relevant |

We always show the formula and assumptions next to the savings figure. It's an estimate and is labelled as one.
