# Frontend and UX

> **In one minute.** The frontend is a React + TypeScript PWA (Vite) on Firebase Hosting, mobile first. It has five screens: Start → Watching → Confirm → Sourcing → Desi BOM.
>
> Signature UX:
> - Share straight from the YouTube app (PWA `share_target`)
> - A live agent checklist
> - Timestamp evidence chips that seek the embedded player
> - Plain-language grade and confidence chips
> - INR with lakh grouping, "incl. GST", savings vs import
>
> It meets WCAG 2.2 AA and has a lite mode for low bandwidth. This work targets the 10% UX criterion and the separate **Best UI/UX** prize ($2,000).

---

## 1. Stack

| Concern | Choice |
|---|---|
| Framework | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS + a small token set (Material 3-inspired) |
| Data | Firebase JS SDK (Firestore `onSnapshot`, Auth, App Check); TanStack Query for REST calls |
| Video | YouTube IFrame Player API (`seekTo`, `getCurrentTime`) |
| Diff viewer | `react-diff-view` (or a small custom unified-diff renderer) |
| Charts | None needed. Totals are numbers, not charts |
| PWA | `vite-plugin-pwa` (manifest + service worker) |
| i18n | UI strings in English (submission rule). Content language toggle for summaries and voice |
| Optional | A2UI React renderer (S7); CopilotKit/AG-UI if we move to SSE |

Keep the bundle under about 150 KB gzipped for the first route. Load the diff viewer and player lazily.

## 2. Screens

### 2.1 Start
- A big paste box with a **"Paste link"** button (clipboard read needs a user gesture), plus PIN or city (optional, stored locally).
- A "What can I paste?" helper listing YouTube, Instructables, Hackster, Adafruit Learn, GitHub and blogs.
- A gallery of recent public Desi BOMs showing thumbnail, ₹ total and "% local".
- A tagline: *Watch it in America. Build it in India.*

### 2.2 Watching (extraction)
- Embedded YouTube player at the top.
- A **dynamic checklist** with 5 stages: ① Watching video ② Finding parts ③ Searching Indian stores ④ Checking compatibility ⑤ Costing.
- A **living status line** below it, e.g. "Reading the description… following 3 links… watching 04:10–05:30". This is fed by `events` where `kind=stage|tool_call`.
- A "What the agent is checking" expander that shows streamed thought summaries (sanitised).

### 2.3 Confirm parts (human-in-the-loop)
- A list of draft parts. Each row shows:
  - name and qty
  - a ▶ timestamp chip or 📄 quote chip or `</>` code chip
  - a confidence chip
- Row actions: **Edit**, **Remove**, **I already have this**.
- A conflict banner, e.g. "The description says BMP280 but the code uses a BME280 library. Which is it?", with quick-reply chips.
- Quick questions (escalation): "Motor voltage: 6 V / 12 V / Not sure".
- Primary button: **Looks right — find Indian parts**. In demo mode it auto-continues after 8 s.

### 2.4 Sourcing (live)
- One **card per part** that fills progressively: sellers checked (logos) → candidates → grade chip.
- A top bar shows parallelism: "14 agents working · 9 done".
- On partial failure the card says "Couldn't find in India yet — import options" rather than an error.

### 2.5 Desi BOM (results)
- **Header:** project title and creator, **₹ total incl. GST** (for example ₹3,480), **Saved ₹11,420 (77%) vs importing**, "12 of 14 parts sourced in India", and a "Cheapest / Fewest sellers" toggle.
- **Safety banner** (if any) above everything, e.g. "⚡ This project switches 230 V mains. Read before building."
- **Mobile layout:** cards with part name, qty, grade chip, chosen store (logo), unit ₹ / line ₹, stock, and a "2 more options ▾" control.
- **Desktop layout:** a table with columns Part · Qty · Original (USD, source) · India option · Store · Unit ₹ · Line ₹ · Match · Stock.
- **Row drawer ("What changes"):**
  - spec diff table (original vs substitute)
  - wiring changes (from → to, why)
  - code diff with "✅ Compiles for ESP32 Dev Module"
  - verify-on-arrival checklist
  - citations (datasheet page links)
  - evidence (timestamp, quote)
- **Sticky footer:** Parts ₹ · Shipping ₹ (per seller) · Total ₹ · buttons for **Export CSV/PDF** · **Share** · **🔊 Explain** (language picker) · **📍 Nearby markets**.
- **Sources footer:** Google `search_suggestions` (required by the ToS) and a list of sellers checked with "checked N min ago".

## 3. Chips and copy

### 3.1 Grade chip (text and icon, never colour alone)

| Grade | Chip text | Icon |
|---|---|---|
| A | Works as is | ✓ |
| B | Small setting change | ⟲ |
| C | Wiring changes needed | ⚠ |
| D | Different part, similar result | ≈ |
| X | Don't use | ⛔ |

### 3.2 Confidence chip (PAIR guidance: categories, not percentages)

| Bucket | Chip |
|---|---|
| Verified | ● Verified |
| Likely | ◐ Likely |
| Check manually | ○ Check. Tapping it shows N-best alternatives |

### 3.2b Seller trust badge (open discovery)

| Trust | Badge | Extra UI |
|---|---|---|
| Established | seller name only | – |
| Verified basics | "New seller · GSTIN verified" | Tap to open the seller card: domain age, GSTIN, policies, first seen by us |
| Unverified | "New & unverified — check before paying" (amber) | Prefer-COD hint; report button |
| Price anomaly | "Unusually cheap — check seller" | Shown alongside any badge |

- Each row shows **"Best deal"** and **"Best from an established seller"** when they differ.
- A global toggle, **"Trusted sellers only"**, is off by default.
- A trace line celebrates discovery: "🆕 Found 2 sellers we hadn't seen before".

### 3.3 Evidence chip
- ▶ 03:42 seeks the player and scrolls up.
- 📄 opens the quote in a popover with a link.
- `</>` shows `sketch.ino:14`.

### 3.4 Copy rules
- Use plain words, e.g. "Works with small changes" rather than "functionally equivalent".
- Every warning says what to do, not just what's wrong.
- Numbers always carry units: "3.3 V", "₹1,840", "2 A".

## 4. INR, GST and savings display

- Use `new Intl.NumberFormat('en-IN', {style: 'currency', currency: 'INR', maximumFractionDigits: 0})`, which gives lakh grouping (₹1,23,456).
- Show whole rupees in the UI and keep paise in exports. Large totals can use "₹1.2 L".
- Prices default to "incl. GST". Shipping is shown separately per seller, with the free-shipping threshold hint "Add ₹120 more for free shipping at Robocraze".
- The **import comparison** uses the *landed* cost: original price × FX + international shipping + duty. Assumptions go in a tooltip or footnote with the FX date and duty rates, so the saving is auditable.

## 5. Mobile-first entry: share from the YouTube app

```json
// manifest.webmanifest
"share_target": {
  "action": "/share-target/",
  "method": "GET",
  "params": {"title": "title", "text": "text", "url": "url"}
}
```

- Works on Android Chrome once the PWA is **installed**.
- Many apps put the link in `text`, not `url`, so parse both with a URL regex. ⚠️ Test on 2–3 real phones.
- The `/share-target/` route extracts the URL, calls `POST /v1/jobs` and routes to Watching.
- Film this flow on a real Android phone for the demo video.
- **Desktop fallback:** a bookmarklet `javascript:location='https://<site>/?u='+encodeURIComponent(location.href)`.

## 6. Low bandwidth and low-end devices

- All video processing happens server-side: "We watch it so you don't spend data."
- **Lite mode** has no thumbnails or product images and loads the player only on tap.
- Text renders first and images load lazily.
- Resumable: the job URL `/{jobId}` restores state from Firestore after a disconnect.
- Cached popular videos answer instantly.
- Service worker caches the app shell. The results page is readable offline once loaded.

## 7. Accessibility (WCAG 2.2 AA)

| Criterion | Implementation |
|---|---|
| 1.4.3 Contrast (min) | 4.5:1 for text. Check the amber and orange chips especially |
| 1.4.1 Use of colour | Chips always have text and an icon |
| 2.5.8 Target size (min) | ≥ 24×24 CSS px, with 48 dp preferred for touch |
| 4.1.3 Status messages | The checklist and status line use `role="status"` / `aria-live="polite"`, so screen readers hear progress. **Demo this.** |
| 2.1.1 Keyboard | Full keyboard flow, with visible focus and a skip link |
| 1.1.1 Non-text content | Alt text for thumbnails ("Frame at 03:42 showing a purple BME280 module") |
| Language | `lang` attribute is set on narrated or translated blocks |

## 8. Component inventory

`<PasteBox>`, `<ShareTargetHandler>`, `<YouTubePlayer>`, `<StageChecklist>`, `<StatusLine>`, `<ThinkingExpander>`, `<DraftPartRow>`, `<ConflictBanner>`, `<QuickQuestion>`, `<PartCard>`, `<GradeChip>`, `<ConfidenceChip>`, `<EvidenceChip>`, `<SellerLogo>`, `<SellerTrustBadge>`, `<SellerCard>`, `<TrustedOnlyToggle>`, `<ReportSellerButton>`, `<SpecDiffTable>`, `<WiringChanges>`, `<CodeDiff>`, `<VerifyChecklist>`, `<SafetyBanner>`, `<TotalsFooter>`, `<PlanToggle>`, `<ImportComparison>`, `<NarrateButton>`, `<MarketsSheet>` (with Maps attribution), `<SourcesFooter>` (search_suggestions), `<ExportMenu>`, `<LibraryGallery>`, `<VoteButtons>`.

## 9. Optional: generative UI (A2UI v0.9)

If there's time, the ReportComposer emits A2UI component JSON for three widgets (part card, spec diff, market card), rendered by the official React renderer. We keep our hand-built components as the fallback. The deck gets the line "UI generated by the agent with Google's A2UI". Pin the renderer version because v0.9 is still changing.

## 10. Usability test script (5 users, 15 min each)

1. "Here's a YouTube build you like. Find out what it would cost to make in India." (share flow)
2. "Is there anything you'd need to change?" (discovering the drawer)
3. "Which part are you least sure about, and why?" (understanding confidence)
4. "Tell a friend what this costs." (sharing)

Record time to first result, points of confusion, and quotes for the deck.
