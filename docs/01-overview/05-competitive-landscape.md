# Competitive landscape

> **In one minute.** Every existing tool does one slice of the job:
> - Octopart and PartGenie need part numbers and ignore Indian maker stores.
> - Kitspace's cart-filler is archived.
> - Google Lens finds one look-alike item at a time.
> - YouTube Shopping only covers what the creator tagged.
> - Indian price comparators don't understand components.
>
> We found **no tool that turns a maker video into a localised, compatibility-checked, costed BOM**. We say "no known tool", not "nobody".

Source: [research/05 §2](../../research/05-competition-ux-judging.md). All links were opened on 30 Sep 2026.

---

## 1. Matrix

| Product | What it does | Input | India / INR | Video / blog input | Compatibility reasoning | Gap we fill |
|---|---|---|---|---|---|---|
| [Octopart BOM Tool](https://octopart.com/bom-tool) | Matches BOM rows, alternates, prices across "670+ distributors", one-click cart | XLSX/CSV with MPNs | Global distributors only | ✗ | Parametric alternates | Needs a BOM with part numbers. No Robu, Robocraze or Amazon.in. Not built for makers |
| [Kitspace](https://kitspace.org/) + [1clickBOM](https://github.com/kitspace/1clickBOM) | Fills carts at Digikey, Mouser, Farnell, RS, LCSC | Kitspace-format repo | No Indian stores | ✗ | ✗ | **Archived 3 Jan 2025** |
| Hackster "Things used" / Instructables "Supplies" | Author-entered parts with US links | Manual | US/EU vendors | Only if filled | ✗ | These are *our input sources*, not competitors |
| [PartGenie Alternative Finder](https://www.partgenie.ai/alternative-finder) | Exact / pin-compatible / functional / partial alternatives; "56M+ parts" | MPN or description | No regional focus | ✗ | ✓ (tiers) | No video, no Indian stores, no maker modules; 3 free searches/month. **We borrowed its tier idea** |
| [Parter.ai](https://parter.ai/alternatives) | Datasheet-spec alternates, live distributor stock | MPN | ✗ | ✗ | ✓ | Engineer-grade and MPN-only |
| [Flux](https://www.flux.ai/) | AI PCB copilot that reads datasheets | Your own design | Global | ✗ | ✓ while designing | For designing new boards, not rebuilding projects |
| [Circuit Mind](https://www.circuitmind.io/) | Architecture → schematic + BOM | Spec | Enterprise | ✗ | ✓ | Enterprise (defence, instruments) |
| [Cofactr](https://www.cofactr.com/) | Component intelligence + procurement | BOM | US B2B | ✗ | – | Pitch line: "Cofactr for makers" |
| [Buyhatke](https://buyhatke.com/) | Price history across "1 Lakh+ stores" | Product link | ✓ (Amazon, Flipkart…) | ✗ | ✗ | Identical consumer SKUs only; no components, no BOM |
| [MySmartPrice](https://www.mysmartprice.com/) | Gadget price comparison | – | ✓ | ✗ | ✗ | Phones and appliances; no components |
| [Google Lens / Circle to Search](https://blog.google/products/shopping/visual-search-lens-shopping/) | Circle an item in a video or image → shopping results across retailers | One object | ✓ (Hindi follow-ups in India) | One frame, one item | ✗ | **Main objection.** See §2 |
| [YouTube Shopping (India)](https://yourstory.com/2024/10/youtube-expands-shopping-programme-india) | Creator-tagged products (Flipkart, Myntra) since Oct 2024 | Creator tags | ✓ | ✓, but only tagged items | ✗ | US/UK maker videos aren't tagged for Indian stores. **We auto-tag any video for India** |
| ExtractCode (Gemini competition entry) | YouTube → on-screen code | YouTube | – | ✓ | ✗ | Shows that extraction alone doesn't win |

## 2. "Why not just use Google Lens / ask Gemini?"

Put this on a slide. Lens and a plain chat each fail at least one of these:

| Need | Google Lens | Plain LLM chat | Bharat Sourcer |
|---|---|---|---|
| Complete BOM with quantities, including parts only mentioned in narration, code or linked pages | ✗ one object per circle | Partial, ungrounded | ✓ evidence fusion across video, description, code and pages |
| Parts you can't *see* (resistor values, library-implied chips, screw sizes) | ✗ | Sometimes | ✓ code + narration + description |
| Indian maker stores (Robu, Robocraze, Quartz, Evelta, Thingbits) with INR incl. GST | Partial (big marketplaces) | Hallucinated links | ✓ verified listings only |
| Compatibility (3.3 V vs 5 V, I2C address, SH1106 vs SSD1306, 120 V vs 230 V) | ✗ | Unreliable (benchmarks: PCEval, EmbedBench) | ✓ rules + datasheet-grounded judge |
| Code changes that compile | ✗ | Untested | ✓ diff + `arduino-cli compile` |
| Total cost vs import, seller split, shipping thresholds | ✗ | ✗ | ✓ |
| Evidence for every claim | Image match only | ✗ | ✓ timestamps, quotes, URLs, datasheet pages |

## 3. Our moat, honestly

1. **The curated compatibility graph + rules.** Research shows expert-curated hardware knowledge beats LLM-generated knowledge (IoT-SkillsBench: 42/42 with human skills). It grows with every BOM and every 👍/👎 vote.
2. **The India seller adapter layer**: UCP/MCP, store APIs, grounding, verification. It's tedious to build and valuable once built.
3. **The public Desi BOM library**, a data flywheel: popular videos resolve instantly and cheaply.
4. **Trust UX**: evidence on every row, conservative safety rules.

What's *not* a moat: calling Gemini on a YouTube URL. Anyone can do that, so we never pitch it as the product. It's step 1 of 7.

## 4. Business model (one slide, optional)

- Affiliate links to Indian sellers (Flipkart Affiliate API exists; Amazon Creators API needs qualifying sales). YouTube Shopping is a precedent.
- Retailer partnerships: qualified demand, "Buildable in India with Robu" badges.
- Institutional plan: ATL / college lab kits (qty × N, GST invoice).
- Creator partnerships: "Build this in India" links under videos.
