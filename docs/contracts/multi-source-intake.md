# Multi-source intake, evidence fusion, look-alikes and confidence

Implemented behaviour (stream `intake`). All new fields are optional or have defaults, so
saved jobs and older clients keep working. Nothing here is a verified seller fact: code
hints, look-alike tables and confidence are deterministic rules over extracted evidence.

## 1. Supported sources

`POST /v1/jobs` still takes `url`. Accepted kinds (`source_reports[].kind`):

| Kind | URLs | What is read |
| --- | --- | --- |
| `video` | public YouTube watch, `youtu.be`, Shorts, embed | Gemini watches the video (unchanged) |
| `instructables` | `instructables.com/<slug>/` | project JSON the page loads (unchanged) |
| `hackster` | `hackster.io/<user>/<project>` | page HTML (Hackster blocks automated access; usually `SOURCE_UNAVAILABLE`) |
| `github` | `github.com/<owner>/<repo>` | README **plus code files** (section 2) |
| `adafruit` | `learn.adafruit.com/<guide>`, `/<guide>/<page>`, `/<guide>.md` | the whole guide as Markdown, `https://learn.adafruit.com/<guide>.md?view=all` |
| `blog` | an article path on a listed tutorial blog | the article's main content only |

**Adafruit Learn.** Images, link targets, HTML comments and the shop widgets repeated under
every product ("Buy Now", "In Stock", "Featured", "Related Guides to the Product") are
removed before the text goes to the model. Evidence cites the all-pages HTML view,
`https://learn.adafruit.com/<guide>?view=all`.

**Tutorial blogs.** Only these hosts are accepted (with or without `www.`):
randomnerdtutorials.com, dronebotworkshop.com, lastminuteengineers.com, circuitdigest.com,
howtomechatronics.com, makerguides.com, microcontrollerslab.com, eater.net,
circuitbasics.com, electronicshub.org. Text is taken from the first non-empty main-content
container, best first: an element with class `entry-content`, `post-content`,
`article-content`, `post-body` or `td-post-content`, then `<article>`, then `<main>`, else
the whole page. The existing chrome stripping still applies (nav, footer, aside, forms,
hidden elements, `#comments`, "Related posts"/"Comments" sections). Any other host returns
400 `UNSUPPORTED_URL` (the message lists the supported kinds).

All fetches go through `SafeFetcher` (HTTPS, public-address pinning, robots.txt, size
limits). Page quotes are still checked verbatim against the text the model saw; unverified
quotes are dropped.

## 2. Code evidence (GitHub)

After the README is read, up to **8** more files are fetched from the same public
`raw.githubusercontent.com/<owner>/<repo>/HEAD/...` endpoint (200 KB each, first 5000
lines), in this order: `platformio.ini`; up to 3 code files the README links to (relative
links or `github.com/<owner>/<repo>/blob/<ref>/<path>`; `..` and odd paths are rejected);
`src/main.cpp`, `<repo>.ino`, `<repo>/<repo>.ino`, `code.py`, `main.py`,
`requirements.txt`, `library.json`. Missing (404), robots-blocked, binary or oversized files
are skipped silently; code never fails a job. If the README itself is missing the job fails
as before and no code file is fetched.

Deterministic rules, no model call:

- C/C++ (`.ino .cpp .c .h .hpp`): `#include <X>` / `#include "X"` outside comments.
- Python: `import x`, `import a, b`, `from x import ...` (top-level module).
- `platformio.ini`: `board = <id>` and each `lib_deps` entry (version, owner and URL parts
  removed).
- `requirements.txt`: `adafruit-circuitpython-<x>` → `adafruit_<x>`, `micropython-<x>` → `<x>`.
- `library.json`: `dependencies` names.

Matches are mapped with the curated table `backend/src/bharat_sourcer/data/library_parts.json`
(28 parts, 23 PlatformIO boards; e.g. `Adafruit_BME280.h` → "BME280 sensor module",
`board = esp32dev` → "ESP32 development board"). Unknown headers are ignored. Each mapped part
becomes one BOM line with up to 5 evidence entries:

```json
{
  "source": "code",
  "file": "src/main.cpp",
  "line": 3,
  "quote": "#include <Adafruit_BME280.h>",
  "url": "https://github.com/<owner>/<repo>/blob/HEAD/src/main.cpp#L3",
  "observation": "src/main.cpp line 3 includes Adafruit_BME280.h; the curated library map links this to BME280 sensor module. Code shows the library, not the exact module.",
  "timestamp": null
}
```

Code never states a count: code-only lines get `qty: 1`, `qty_source: "inferred"` and a
`qty_reason`. `Evidence` now has `file` and `line` (always `null` for video and page
evidence) and `source` may be `"code"`.

## 3. Multi-source jobs

```http
POST /v1/jobs
{"url": "https://youtu.be/<id>", "sources": ["https://github.com/<owner>/<repo>"]}
```

- `sources`: optional list of up to **3** extra URLs, validated like `url`. Sources whose
  canonical URL repeats an earlier one are dropped. At most **one video** across `url` and
  `sources`, else 400 `UNSUPPORTED_SOURCES`; any unsupported URL returns 400
  `UNSUPPORTED_URL`. Demo mode ignores `sources`.
- The queued event says e.g. "Video queued with 1 more source."
- Each source is extracted with its existing extractor: one Gemini call per video or page
  source, none for code. A failing **extra** source does not fail the job; a single-source
  job fails exactly as before. A multi-source job fails only when no source yields parts
  (the first source's error is reported).
- `job.project` comes from the first source that produced one.
- `job.source_reports[]` (new, default `[]`) has one entry per distinct source:
  `url` (canonical), `kind`, `role` (`primary` | `additional`), `status` (`read` |
  `failed`), `item_count`, `code_item_count`, `error` (`{code, message}` when failed).

## 4. Fusion rules (M3)

Per-source BOMs are groups in URL order; a GitHub source contributes two groups (README
lines, then code lines). Lines are never merged within one group. For each later group,
candidate pairs with an existing line are scored, then assigned one-to-one, strongest first
(ties: earlier line, then earlier candidate):

| Score | Relation | Rule |
| --- | --- | --- |
| 5 | same | both names match the same member of a look-alike group (section 5) |
| 4 | same | they share a part-number-like word (letters + digits, 4+ characters, e.g. `l298n`, `esp32s3`, `hcsr04`; number+unit words such as `420mah` are specs, not part numbers) |
| 3 | same | equal normalised tokens (as in the evaluation harness) |
| 2 | same | one name's tokens are a subset of the other's, and they do not both carry different part numbers |
| 1 | identity conflict | the names match **different** members of one look-alike group (BMP280 vs BME280) |

Unmatched lines are appended. Merged lines keep the first source's name, except that a
generic name without a part number takes the more specific name when its tokens are a
subset of it ("Ultrasonic sensor" + "HC-SR04P ultrasonic sensor"). Evidence from all sources
is kept (deduplicated, at most 20); requirements and look-alikes are unioned. Quantity: a
stated count replaces an inferred one; two different stated counts keep the first and add a
conflict. Line ids are renumbered `L01...`; at most 100 lines.

### Conflicts

`items[].conflicts[]` (new, default `[]`):

```json
{
  "kind": "identity_mismatch",
  "message": "Sources name different parts: BMP280 sensor and BME280 sensor module. Check which one this build uses.",
  "values": [
    {"value": "BMP280 sensor", "source": "project_page", "url": "...", "locator": "BMP280 sensor"},
    {"value": "BME280 sensor module", "source": "code", "url": ".../src/main.cpp#L3", "locator": "src/main.cpp:3"}
  ]
}
```

`kind` is `identity_mismatch` or `qty_mismatch` (values are the two counts). `locator` is the
timestamp, `file:line` or page quote of that side's first evidence. The server never picks a
side for identity; the maker resolves it with the normal `update` edit at confirmation.

## 5. Look-alikes

`items[].lookalikes[]` (new, default `[]`, at most 10): `{name, note, origin}`.

- `origin: "table"`: from the curated `backend/src/bharat_sourcer/data/lookalikes.json`
  (BME280/BMP280, SSD1306/SH1106, AMS1117-3.3/5.0/ADJ, HC-SR04/HC-SR04P, DHT11/DHT22,
  ESP32/S2/S3/C3, A4988/DRV8825, WS2812B/WS2811/SK6812, MPU6050/6500/9250, 28BYJ-48
  5 V/12 V), applied after extraction and fusion. The line lists the group's other members
  with the group `note`; a name matching only the group (e.g. "AMS1117 regulator") lists all.
- `origin: "ai"`: the extraction prompts now ask the model for `lookalikes` (up to 5
  names, `note: null`). Names equal to the line's own name or part number are dropped.

Look-alikes are warnings, never suggested substitutes.

## 6. Confidence (M15)

`items[].confidence`: `"verified" | "likely" | "check" | null`, with a short
`confidence_reason`. Computed at extraction; first matching rule wins:

1. `check`: no evidence.
2. `check`: any conflict.
3. `check`: any look-alike, unless code evidence pins the line to exactly one member of
   each of its look-alike groups (e.g. `Adafruit_BME280.h` or `board = esp32dev`).
4. `verified`: code evidence (a mapped include, import, dependency or board).
5. `verified`: evidence from two or more distinct sources (video, each page URL, code).
6. `likely`: one source (a server-checked page quote, or model-reported video timestamps).

`null` means not assessed: lines added by the user, lines the user renamed at confirmation
(renaming clears the value, since the evidence was for the old name) and jobs saved before
this change. Quantity edits do not change confidence.

## 7. What the frontend should show

- **Confidence chip** on each BOM line: text plus icon, never colour alone, e.g.
  "✓ Verified", "◐ Likely", "⚠ Check". Put `confidence_reason` in the tooltip or
  expandable detail. Show no chip for `null`.
- **Conflict banner** at the confirmation step when any line has `conflicts`: "N lines
  have conflicting sources", linking to the lines. On the line, show each
  `values[]` entry with its source and locator (timestamp chip seeks the video; `file:line`
  and quotes link to `url`) and the `message`.
- **Look-alike warning** on lines with `lookalikes`: "Often confused with SH1106" plus the
  `note`; mark `origin: "ai"` entries as AI-suggested.
- **Code evidence** in the evidence strip as `file:line` linking to `url`, labelled "Code".
- **Sources**: list `source_reports` (kind, role, parts found); show failed extra sources
  with their `error.message` so the maker knows that source was skipped.
- **Create form**: optional "Add another source" inputs (max 3) sent as `sources`.
