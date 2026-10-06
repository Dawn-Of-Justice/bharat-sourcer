# Gemini extras: explain aloud, clip zoom, parts-bin scan

Three opt-in Gemini features (product features S1, S4 and S3). **All are off by default.**
None of them changes the BOM by itself: zoom and scan results become ordinary chat
proposals that the owner accepts or rejects with the existing
`POST /v1/jobs/{job_id}/messages/{message_id}/decision` endpoint
([conversation guide](conversation.md)). Everything the models say is labelled as AI
observation, never as verified seller, compatibility or identity data.

Code: `backend/src/bharat_sourcer/gemini_extras.py`. Tests:
`backend/tests/test_gemini_extras.py` (Gemini is mocked; no model is called).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BS_EXPLAIN_ENABLED` | `false` | Enables `POST /explain` |
| `BS_EXPLAIN_DAILY_LIMIT` | `10` | Uncached explanations per owner per UTC day |
| `BS_EXPLAIN_MAX_CHARS` | `900` | Max English script length (500–2000); safety notes always kept |
| `BS_TTS_MODEL` | `gemini-3.8-flash-tts` | Speech model (from the architecture docs; price unverified) |
| `BS_TTS_VOICE` | `Kore` | Prebuilt voice name |
| `BS_ZOOM_ENABLED` | `false` | Enables `POST /items/{line_id}/zoom` |
| `BS_ZOOM_DAILY_LIMIT` | `10` | Zoom calls per owner per UTC day |
| `BS_ZOOM_CLIP_S` | `15` | Clip length in seconds (10–20) |
| `BS_SCAN_ENABLED` | `false` | Enables `POST /scan` |
| `BS_SCAN_DAILY_LIMIT` | `5` | Scans per owner per UTC day |
| `BS_SCAN_MAX_BYTES` | `4000000` | Max decoded photo size (≤ 5 MB) |
| `BS_EXTRAS_GLOBAL_DAILY_LIMIT` | `200` | Per-feature cap across all owners per UTC day |

Text calls (translation, zoom, scan) use `BS_GEMINI_MODEL` (default `gemini-3.8-flash`).
A live job also needs `BS_GEMINI_API_KEY`; without it the endpoints return 503
`FEATURE_UNAVAILABLE`.

**Quotas.** "Owner" is the account or guest identity when authentication is on, otherwise
the job. Quotas use the same usage counters as the image fallback (`store.consume`); a
call is charged before Gemini is called, so a failed call still counts. Over the limit:
429 `FEATURE_QUOTA` with `Retry-After` (seconds to UTC midnight). With authentication
enabled these three endpoints still need identity, the CSRF header and job ownership, but
they do **not** spend the per-account project action budget (like `/image`); their own
quotas apply instead.

**Demo jobs** (`job.demo: true`) never call Gemini and consume no quota; each endpoint
returns a labelled sample (see below). The feature flag still applies.

## Feature status

`GET /v1/jobs/{job_id}/extras` (no quota, no Gemini call):

```json
{
  "demo": false,
  "explain": {"enabled": true, "daily_limit": 10, "remaining": 9},
  "zoom": {"enabled": true, "daily_limit": 10, "remaining": 10},
  "scan": {"enabled": false, "daily_limit": 5, "remaining": 5},
  "languages": ["hi", "ta", "ml", "bn", "te", "kn", "mr", "en"],
  "zoom_line_ids": ["L01"],
  "scan_max_bytes": 4000000,
  "scan_mime_types": ["image/jpeg", "image/png", "image/webp"]
}
```

`enabled` already accounts for the API key. `remaining` is the smaller of the owner's and
the global count. `zoom_line_ids` are the rows that deserve a "zoom in" button: only while
the BOM is `awaiting_confirmation`, not marked owned, with a video timestamp, and either
no part-number-like token (letters and digits, 4+ characters) in the name or an open
clarification. This is a deterministic hint, not a confidence score; the zoom endpoint
accepts any line with a video timestamp.

## S1: explain aloud

`POST /v1/jobs/{job_id}/explain` with `{"language": "ml"}` (one of `hi ta ml bn te kn mr
en`; default `en`). Allowed in any status once the job has parts (else 409
`NOTHING_TO_EXPLAIN`).

1. The server builds a short **deterministic English script** from saved data only:
   project title and summary, part count and parts still to buy, power, wiring changes
   from `changes_required` compatibility on the selected (or first assessed) offer,
   `incompatible` findings, one open clarification per part, then safety notes. Safety
   notes are always present: a generic power/voltage reminder, a lithium-cell note when
   the project mentions LiPo/Li-ion/18650, a mains note when it mentions mains or
   110–240 V, and a disclaimer that compatibility covers declared specs only and seller
   prices are not verified. Other sentences are dropped from the end to fit
   `BS_EXPLAIN_MAX_CHARS`.
2. For non-English languages the text model translates it, instructed to keep part names,
   part numbers, units, numbers and line IDs in English and not to drop safety notes.
3. The TTS model speaks the transcript. 16-bit PCM is wrapped as WAV.

Response:

```json
{
  "language": "ml",
  "transcript": "…translated text…",
  "source_script": "Project: … (English, deterministic)",
  "translated": true,
  "audio_mime": "audio/wav",
  "audio_base64": "UklGR…",
  "duration_s": 41.2,
  "cached": false,
  "demo": false,
  "model": "gemini-3.8-flash-tts",
  "label": "AI-generated narration of saved project data (machine-translated); not verified advice."
}
```

**Cache.** Keyed by owner scope, the English script (so any change to the saved job that
changes the script is a new "revision"), language, TTS model, voice and translation
model. A cache hit returns `cached: true`, costs nothing and does not consume quota.
Audio is stored as PCM in memory (32 entries) or in the Firestore `<collection>_audio`
collection, split into ≤ 900 KB chunk documents, with an `expires_at` field 30 days out
(a Firestore TTL policy on that field must be configured to actually delete them).
Speech output above 8 MB of PCM (~166 s) is rejected.

Demo: the transcript is the real deterministic script (untranslated, `translated:
false`), the audio is one second of silence, label "Demo sample: silent placeholder
audio…".

## S4: clip zoom re-read

`POST /v1/jobs/{job_id}/items/{line_id}/zoom` with `{}` or `{"timestamp": "03:12"}`.
`line_id` is the BOM item's `line_id`. The timestamp must be one of that item's own video
evidence timestamps (422 `INVALID_TIMESTAMP`); it defaults to the first.

- Only while `status == "awaiting_confirmation"` (409 `INVALID_STATE`), only for YouTube
  jobs (409 `NOT_A_VIDEO`) and items with a video timestamp (409 `NO_TIMESTAMP`).
- The clip is `BS_ZOOM_CLIP_S` seconds starting a third of that before the timestamp
  (03:12 → 03:07–03:22). Gemini gets the YouTube URL with `videoMetadata.startOffset` /
  `endOffset`, `fps: 2` and `mediaResolution: MEDIA_RESOLUTION_HIGH`, plus the current
  name and earlier observations, and is told to report markings only if it can read them.
- If the model returns a readable marking and a different name, the server appends an
  assistant chat message with a pending **draft proposal** (`update` `raw_name`). Nothing
  is renamed until the owner accepts it. An unreadable clip still adds a message (without
  a proposal) so the attempt is visible in chat.

Response:

```json
{
  "line_id": "L01",
  "clip": {"start": "03:07", "end": "03:22"},
  "readable": true,
  "marking": "ATMEGA328P",
  "suggested_name": "ATmega328P microcontroller",
  "observation": "The chip top reads ATMEGA328P.",
  "evidence": {"source": "video", "timestamp": "03:15",
               "observation": "Zoomed 03:07–03:22: The chip top reads ATMEGA328P."},
  "message_id": "…",
  "demo": false,
  "model": "gemini-3.8-flash",
  "label": "AI observation of a video clip; review before accepting."
}
```

`evidence.timestamp` is the model's `seen_at` when it falls inside the clip, else the clip
start. The evidence is returned for display; it is not written into `items[].evidence`.
Demo: a fixed "Demo sample: no video was read" observation, no message, no proposal.

## S3: parts-bin scan

`POST /v1/jobs/{job_id}/scan` with `{"image_base64": "<base64 or data:image/...;base64,...>"}`.
JSON/base64 is used because the backend has no multipart dependency.

- Only while `status == "awaiting_confirmation"` (409 `INVALID_STATE`).
- Decoded size ≤ `BS_SCAN_MAX_BYTES` (413 `IMAGE_TOO_LARGE`); magic bytes must be JPEG,
  PNG or WebP (415 `UNSUPPORTED_IMAGE`); undecodable input 422 `INVALID_IMAGE`; more than
  40 megapixels 413.
- The photo is processed **in memory only**: EXIF-rotated, downscaled to ≤ 1536 px,
  re-encoded as JPEG (dropping metadata) and sent inline to Gemini. It is never stored or
  logged.
- Gemini object detection returns one entry per BOM line. Unknown or duplicate line IDs are
  dropped; invalid boxes become `null`.
- Lines that are `likely_present` and not already owned become one pending **draft
  proposal** of `have_it` edits in a new assistant chat message. Accepting it marks them
  owned (owned parts are not sourced); rejecting changes nothing.

Response:

```json
{
  "suggestions": [
    {"line_id": "L02", "likely_present": true, "box_2d": [100, 120, 400, 520],
     "observation": "Blue ESP32 board", "already_marked": false},
    {"line_id": "L01", "likely_present": false, "box_2d": null,
     "observation": "Not seen", "already_marked": false}
  ],
  "message_id": "…",
  "demo": false,
  "model": "gemini-3.8-flash",
  "label": "AI suggestions from your photo; the photo was not stored."
}
```

`box_2d` is `[ymin, xmin, ymax, xmax]` normalised to 0–1000 on the photo as the browser
displays it (EXIF orientation applied). `message_id` is null when nothing new looks
present. Demo: the photo is still validated; the first line is returned as a sample
suggestion labelled "Demo sample" with a sample proposal message.

## Cost per call (estimates, not measurements)

Based on `gemini-3.8-flash` at $0.75 input / $3.75 output per 1M tokens until 2026-12-31
(doubling on 2027-01-01) from [the cost research](../../backend/infra/gemini-cost-research-2026-10-05.md).
Usage is logged as `GEMINI_USAGE` with sites `explain_translate`, `explain_tts`,
`clip_zoom` and `parts_scan`; replace these estimates with `scripts/usage_report.py`
numbers once there is traffic.

| Site | Estimated tokens | Estimated cost |
| --- | --- | --- |
| `explain_translate` (non-English only) | ~0.5K in, ~1–1.5K out incl. thinking | ~$0.005 |
| `explain_tts` | ~0.4K text in, ~25 audio tokens/s out | **unverified**: `gemini-3.8-flash-tts` pricing is not in our cost docs. At earlier Flash-TTS list prices ($0.50 in / $10 out per 1M) a 60 s clip is ~$0.015 |
| `clip_zoom` | 15 s × 2 fps × 280 (high res) ≈ 8.4K + audio ≈ 0.4K in; ~0.7K out | ~$0.009 |
| `parts_scan` | ~1–1.5K image + ~0.5K text in; ~1–2K out | ~$0.006–0.009 |

Cache hits for explain cost nothing. With default quotas the worst case per owner per day
is about 10 × $0.02 + 10 × $0.009 + 5 × $0.009 ≈ $0.34, and the global caps bound each
feature at 200 calls/day.

## Frontend needs (not built; frontend teammate)

Call `GET /v1/jobs/{job_id}/extras` once per job view and hide disabled features.

- **Explain:** a 🔊 button with a language picker (`languages`), a spinner (calls can take
  tens of seconds), then an `<audio controls>` player with
  `src = "data:audio/wav;base64," + audio_base64` and the `transcript` shown below it with
  the `label`. Show "Demo sample" prominently when `demo` is true. Show `remaining` and
  handle 429 `FEATURE_QUOTA`.
- **Zoom:** a "zoom in" button on rows listed in `zoom_line_ids` (optionally any row with a
  video timestamp). Show the result as "We zoomed into 03:07–03:22: …" with the label;
  when `message_id` is set, the existing chat proposal card (Approve/Reject) handles the
  rename. Link the timestamp to the video if the UI already does that for evidence.
- **Scan:** a "Scan my parts bin" upload (camera/file input, JPEG/PNG/WebP, client-side
  check against `scan_max_bytes`; downscale in the browser if larger). Read the file as
  base64 and post it. Overlay `box_2d` boxes on the local preview for `likely_present`
  rows, list the observations, and point the user to the proposal card to mark parts
  "✔ You have this". Say that the photo is not stored.
