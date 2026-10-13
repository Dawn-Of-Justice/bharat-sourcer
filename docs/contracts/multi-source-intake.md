# Multi-source intake, evidence fusion, look-alikes and confidence

Implemented behaviour (stream `intake`). All new fields are optional or have defaults, so
saved jobs and older clients keep working. Nothing here is a verified seller fact: code
hints, look-alike tables and confidence are deterministic rules over extracted evidence.

## 1. Supported sources

`POST /v1/jobs` still takes `url`. Accepted kinds (`source_reports[].kind`):

| Kind | URLs | What is read |
| --- | --- | --- |
| `video` | public YouTube watch, `youtu.be`, Shorts, embed | Gemini watches the video; with `BS_YOUTUBE_API_KEY` set, it also reads the description (section 8) |
| `instructables` | `instructables.com/<slug>/` | project JSON the page loads (unchanged) |
| `hackster` | `hackster.io/<user>/<project>` | page HTML (Hackster blocks automated access; usually `SOURCE_UNAVAILABLE`) |
| `github` | `github.com/<owner>/<repo>` | README **plus code files** (section 2) |
| `adafruit` | `learn.adafruit.com/<guide>`, `/<guide>/<page>`, `/<guide>.md` | the whole guide as Markdown, `https://learn.adafruit.com/<guide>.md?view=all` |
| `blog` | public personal blogs and project websites, plus the recognised tutorial blogs | readable article/main content, falling back to page text |

**Adafruit Learn.** Images, link targets, HTML comments and the shop widgets repeated under
every product ("Buy Now", "In Stock", "Featured", "Related Guides to the Product") are
removed before the text goes to the model. Evidence cites the all-pages HTML view,
`https://learn.adafruit.com/<guide>?view=all`.

**Tutorial blogs and personal websites.** These hosts have canonical URL handling (with or without `www.`):
randomnerdtutorials.com, dronebotworkshop.com, lastminuteengineers.com, circuitdigest.com,
howtomechatronics.com, makerguides.com, microcontrollerslab.com, eater.net,
circuitbasics.com, electronicshub.org. Text is taken from the first non-empty main-content
container, best first: an element with class `entry-content`, `post-content`,
`article-content`, `post-body` or `td-post-content`, then `<article>`, then `<main>`, else
the whole page. The existing chrome stripping still applies (nav, footer, aside, forms,
hidden elements, `#comments`, "Related posts"/"Comments" sections). Other public personal
blogs and project pages use the same text reader and are accepted both directly and as
extra sources. Query parameters are preserved for sites that identify posts by query.
HTTP links without an explicit port are upgraded to HTTPS. Known social, shop, affiliate
and shortener hosts are excluded, as are credentials, IP literals and local hostnames.
DNS and redirect destinations are checked by `SafeFetcher`; the final page must remain
on the requested host (with or without `www.`). This reads one page, without recursive
crawling or JavaScript rendering. Login-only or blocked pages may return `SOURCE_UNAVAILABLE`;
pages without quoted parts return `NO_BOM`.

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
are skipped silently; code never fails a job.

When none of those files is a code file (`.ino .cpp .c .h .hpp .py`), or the repository has
**no README** at all, the file list comes from the repository tree instead: one request to
`api.github.com/repos/<owner>/<repo>/git/trees/HEAD?recursive=1` through the same guarded
fetcher (robots, 1 MB limit). Build files come first, then `.ino` sketches, then other code
files, shallowest first; files over 200 KB and paths under `lib/`, `libraries/`, `.pio/`,
`examples/`, `test(s)/`, `docs/`, `build/` or `vendor/` are skipped; at most 8 are fetched.
If the tree cannot be read, the conventional names above are tried. A repository without a
README makes no page model call: its source report is `read` with `item_count: 0` and
`code_item_count` set, or the source fails with `SOURCE_UNAVAILABLE` ("no README and no code
files that name a known part library or board") when no code hint is found.

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
  `failed`), `item_count`, `code_item_count`, `error` (`{code, message}` when failed),
  `found_in` (`"youtube_description"` for a source taken from the video's description,
  else `null`). At most 5 entries: the video, its description and 3 extras.

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

**Generic suggested duplicates.** After merging, a line is folded into another (evidence,
requirements and look-alikes kept) when it is a *generic suggestion*: inferred quantity,
not user-edited, no conflict, and no part number or value in its name. It must fill a
single-part role (`battery` or `board`, from `buyable_spec.category`; a battery word such
as battery/LiPo/cell when there is no category) shared with exactly one other line. With two
or more other lines in that role (a coin cell and a LiPo) nothing is folded. Example:
"Rechargeable battery" (suggested qty) beside "3.7V 400mAh LiPo battery (602530)".

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

## 4a. Reconcile (v0.34.0)

Fusion only merges by name. After it, one Gemini call (site `reconcile`, `reconcile.py`)
reads the project and all lines (name, qty, specs, up to 4 short evidence notes) and
returns each line's function and connections plus:

- merges: lines that are one physical part (kept line, merged lines, reason). Applied with
  the fusion merge rules: evidence, requirements and look-alikes combined; names with
  different part numbers add an `identity_mismatch` conflict (confidence `check`).
- removals: `duplicate` (of `part_of`; applied as a merge), `built_in` (on another listed
  part; needs `part_of`), `tool`, `not_a_part`. Consumables and enclosures are kept.

Guards: unknown ids, overlapping merges and owned or user-edited lines are ignored; at most
a third of the lines can be removed; lines are renumbered L01, L02, ... Any failure keeps
the fused list. Every change is saved on `Job.reconciled` with its AI reason; the review
page lists them ("We checked the list as one build and combined 1 duplicate line").

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
3. `likely` ("Easily confused with X; confirm the exact variant."): any look-alike,
   unless code evidence pins the line to exactly one member of each of its look-alike
   groups (e.g. `Adafruit_BME280.h` or `board = esp32dev`). A look-alike is a variant
   warning, not doubt that the part is used, so it caps the line at `likely`.
4. `verified`: code evidence (a mapped include, import, dependency or board).
5. `verified`: evidence from two or more distinct sources (video, video description, each
   page URL, code).
6. `likely`: one source (a server-checked page or description quote, or model-reported
   video timestamps).

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

## 8. YouTube description intake

Implemented, optional. Enabled when `BS_YOUTUBE_API_KEY` is set (a YouTube Data API v3 key;
in Cloud Run it is the secret `bharat-sourcer-youtube`, see `backend/infra/README.md`).
When it is unset, nothing below happens and video extraction is unchanged.

**Fetch.** For each video source the extractor makes one
`GET https://www.googleapis.com/youtube/v3/videos?part=snippet&id=<video id>` call (1 quota
unit, 5 s timeout, one retry on a timeout, network error or 5xx). The key is sent in the
`x-goog-api-key` header, never in the URL, so it is absent from request logs, errors and
stored data. A failed or empty call is never fatal: the video is extracted as before and
the description report is `failed` with `DESCRIPTION_UNAVAILABLE`.

**Extraction (no extra Gemini call).** The title, channel and description go into the same
video `generateContent` call as a second, untrusted JSON text part. Each evidence entry the
model returns is either `source: "video"` (MM:SS timestamp) or `source: "youtube_description"`
with a quote copied verbatim from the description. The server keeps a description quote only
when its whitespace-normalised text appears in the description (`project_pages.quote_found`),
then cuts it to 300 characters. Entries that fail the check are dropped, and so are parts left
with no evidence.

```json
{
  "source": "youtube_description",
  "quote": "BME280 temperature, humidity and pressure sensor module",
  "url": "https://www.youtube.com/watch?v=<id>",
  "observation": "Listed in the description parts list.",
  "timestamp": null, "file": null, "line": null
}
```

Description evidence counts as its own source in fusion and confidence: a part shown in the
video and listed in the description is `verified` ("2 sources agree"); a description-only
line is `likely` ("One source: a quote checked in the video description."). In `conflicts`,
`values[].source` can be `"youtube_description"`.

**Links.** Up to 20 distinct `http(s)` links are read from the description and classified:

| `kind` | Rule | Followed? |
| --- | --- | --- |
| `project_source` | a recognised project page or public personal blog/project website, stored as its canonical URL | yes, as an extra source |
| `video` | another YouTube video | no (one video per job) |
| `store` | store or affiliate hosts (Amazon, amzn.to, Flipkart, robu.in, Robocraze, AliExpress, Adafruit shop and others) | no |
| `other` | anything else (social media, link shorteners) | no |

`project_source` links are appended in description order after the submitted sources,
with the usual dedupe by canonical URL and the limit of **3 extra sources** in total
(submitted ones first). They are extracted and fused like submitted sources, and their
`source_reports[]` entries have `found_in: "youtube_description"`. A failing link source is
reported and skipped.

Creator websites use `kind: "blog"` in source reports, so no new response fields are needed.
`video_meta.links[].followed` means the source was scheduled, not that it succeeded; check
the matching source report for its result. If video extraction yields no parts but returns
description project links, intake still tries those links before deciding there is no BOM.
URL discovery and classification are deterministic; page extraction uses the existing
model call and server-side quote checks. The three-extra-source cap includes creator sites.

**Reports and metadata.** `source_reports[]` gets an entry after the video with
`kind: "youtube_description"`, `role: "additional"`, the video URL, `status` and
`item_count` (lines with description evidence). `job.video_meta` is new, optional and
defaults to `null`:

```json
{
  "video_id": "abcdefghijk",
  "title": "...",
  "channel": "...",
  "published_at": "2026-09-14T12:30:00Z",
  "fetched_at": "2026-10-07T05:00:00Z",
  "links": [
    {"url": "https://github.com/<owner>/<repo>", "kind": "project_source", "followed": true},
    {"url": "https://amzn.to/...", "kind": "store", "followed": false}
  ],
  "expired": false
}
```

The full description is never stored; only `video_meta` and the short quotes are.

**Retention (YouTube API Services policy).** API data must be refreshed or deleted within
30 days. Every job read (`GET /v1/jobs/{id}`, the snapshot stream, share links and exports)
checks `video_meta.fetched_at`. When it is more than 30 days old, description evidence is
removed from `items[]` and report lines, description locators in conflicts are cleared, and
`video_meta` keeps only `video_id`, `fetched_at` and `expired: true`. Confidence values
computed with that evidence are not recomputed. The stored snapshot is not rewritten or
purged yet, and nothing is refreshed; a scheduled purge (or Firestore TTL) is a follow-up.

**Frontend.** Label description evidence "Description" and show its quote, linking to the
video. Show `video_meta.links`, marking store links as shop or affiliate links (not verified
sellers or prices) and project links as "Read as a source" when `followed`. When
`video_meta.expired` is true, say the description data expired under YouTube's 30-day policy.
