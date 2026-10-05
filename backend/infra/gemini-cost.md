# Gemini cost: call sites, measurements and findings

Running log for reducing Gemini spend. Add a dated entry for every finding, measurement or
decision; never delete history, mark superseded entries instead. Prices change: always
record the source URL and the date you read it.

## Call sites (as of v0.19.2)

| Site (`GEMINI_USAGE` `site`) | Code | Calls per job | Input | Tools |
| --- | --- | --- | --- | --- |
| `extraction_video` | `extraction.py` `_extract_video` | 1 | YouTube video (`fileData`) + prompt | none |
| `extraction_project_page` | `extraction.py` `_extract_page` | 1 | up to `BS_PROJECT_PAGE_CHARS` (60k) chars of page text | none |
| `discovery` | `sourcing/service.py` `GeminiDiscovery` | 1 per sourced part, +1 for an alternative search | short part query | `google_search` grounding |
| `research` | `sourcing/research.py` | 1 per sourced part (2 with follow-up) | fetched page text, up to 16 sources | none |
| `chat_scope` | `conversation.py` `in_scope` | 1 per chat message | last messages + project context | none |
| `chat_reply` | `conversation.py` `reply` | 1 per allowed chat message | saved job context (items, report, 12 messages) | none |
| `image` | `images.py` | 0 unless generation enabled (≤10/owner/day) | short prompt | image output |

A 10-part live job is roughly 1 extraction + 10 discovery + 10–20 research calls
(21–31 calls), plus 2 per chat message. All text calls use `BS_GEMINI_MODEL`
(default `gemini-3.8-flash`).

## Measuring

Since v0.19.2 every call logs one line:

```text
GEMINI_USAGE {"site": "research", "model": "...", "prompt": 5123, "output": 410,
"thoughts": 96, "cached": 0, "tool_prompt": 0, "total": 5629, "grounded": false,
"by_modality": {"TEXT": 5123}}
```

`python scripts/usage_report.py --days 7` (from `backend/`, with Cloud Logging read
access) prints calls, grounded calls, average input/output/thinking tokens and cached
share per site. Multiply by current prices to get cost; record results below.

## Findings log

### 2026-10-05: baseline audit (no measurements yet)

- Token usage was not recorded anywhere; `usageMetadata` was discarded. Fixed in
  v0.19.2 (`usage.py`). Decision: measure for a few days of real traffic before
  changing models or prompts.
- Likely largest costs, to confirm with measurements: `research` (large page-text
  input on every sourced part), `discovery` (one grounded search request per part),
  `extraction_video` (video tokens scale with duration).
- `chat_scope` is a yes/no classifier using the same model as replies: a candidate for
  a cheaper model if quality holds.
- Research findings on URL context, Batch API and context caching: pending (being
  researched; entries will be added below with sources).
