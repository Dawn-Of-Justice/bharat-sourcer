# Cost controls: shared cache, research rules, refresh, budget and cost accounting

Released in v0.21.0; budget and cache behavior updated for v0.27.0. Gemini prices, measurements and
estimates are in [`backend/infra/gemini-cost.md`](../../backend/infra/gemini-cost.md).
All dollar figures are **estimates** computed from logged token counts and a dated price
table, not Google invoices.

## API additions (additive)

### `job.cost_estimate` (optional)

Present once a job has made at least one attributed Gemini call or cache hit.

```json
{
  "method": "estimated_from_token_counts",
  "total_usd": 0.0412,
  "run_usd": 0.0187,
  "budget_usd": 0.25,
  "budget_reached": false,
  "calls": 5,
  "search_queries": 3,
  "calls_by_site": {"extraction_video": 1, "discovery": 2, "research": 2},
  "usd_by_site": {"extraction_video": 0.0123, "discovery": 0.0241, "research": 0.0048},
  "cache_hits": {"discovery": 1, "research": 1},
  "prices_checked": "2026-10-05",
  "updated_at": "2026-10-07T10:00:00Z"
}
```

- `total_usd` covers the whole job (extraction and every sourcing run).
- `run_usd` covers the current sourcing run (the first run or one refresh); the budget
  applies to it. Extraction is counted in `total_usd` but not limited.
- Grounding queries are priced at $14 per 1,000 as if the monthly free tier were used up,
  so search cost is an upper bound.
- Chat calls (`chat_scope`, `chat_reply`) and opt-in extras are not attributed to a job yet;
  they still appear in `GEMINI_USAGE` logs.

Frontend: optional. If shown, label it "Estimated AI cost" and never as a charge.

### Research status `skipped`

`line.research.status` may now be `"skipped"`: no Gemini document review ran. `summary`
says why:

- a verified, in-stock offer with compatible declared specs (grade A/B or unknown grade)
  already exists, so the review was unnecessary; or
- the job budget was reached.

Treat it like a line without research candidates. `sources` still lists fetched pages.

### Line error `JOB_BUDGET_REACHED`

Older snapshots can contain `sourcing_status: "not_run"` and
`sourcing_error.code: "JOB_BUDGET_REACHED"`. In v0.27.0, reaching the budget skips
paid stages while free catalogue search, known-URL verification and cache reuse continue.
The report summary notes skipped paid search. A refresh starts a fresh run budget;
the existing refresh limits still apply.

## Behaviour

### Shared cache (`sourcing/cache.py`)

Cross-job, cross-owner cache for paid results. `get(key) -> dict | None`,
`set(key, value, ttl_s)`. Keys are `<namespace>-<sha256 prefix>` from
`cache_key(namespace, *parts)`; part names go through `normalise_part` (case-folded,
units normalised, whitespace collapsed), so `33kΩ resistor`, `33K resistor` and
`33 k ohm resistor` share one entry while `1MΩ` and `1mΩ` never collide.

| Namespace | Key | Value | TTL |
| --- | --- | --- | --- |
| `discovery` | normalised part query | grounded candidate URLs | 7 days |
| `judge` | spec hash + URL + content hash | verdict | 7 days |
| `page` | URL | fetched response, parsed again before use | min(8 h, `BS_SELLER_PAGE_CACHE_S`), default 15 min |
| `seller_search` | seller host + exact request URL | successfully parsed search response | min(6 h, `BS_SELLER_SEARCH_CACHE_S`); empty results at most 10 min |
| `research` | normalised part + specs/requirements + document URLs | quote-checked candidates | 7 days |
| `spec` | normalised item name + qty + requirements + project-context hash | guarded buyable spec (derived from that project, so only the same item in the same project reads it) | 7 days |

Backends: in memory (local and tests, LRU of 2,048 entries) and Firestore collection
`<BS_FIRESTORE_COLLECTION>_cache`, one document per key with `expires_at`; values over
900 KB are chunked into `<key>-<n>` documents. Lookups are by document id only, so no
index is needed. Expired entries are ignored on read. Cache failures are misses.

Values are shared across owners, so they hold only public evidence: never project text,
assessments written for a project, tokens or identities. Cached offers and evidence are
always re-verified against the pages fetched for the current job before they are shown.

Each hit logs `GEMINI_CACHE_HIT {"namespace", "job_id", "line_id"}` and counts in
`cost_estimate.cache_hits`. `BS_CACHE_ENABLED=false` disables the cache.

### Research (`sourcing/research.py`)

1. The document review is skipped when the line already has a verified, in-stock,
   compatible offer (research is for when offers fail).
2. Document text is capped at `BS_RESEARCH_PAGES_PER_PART` (3) documents,
   `BS_RESEARCH_PAGE_CHARS` (12,000) per document and `BS_RESEARCH_TOTAL_CHARS` (24,000)
   in total.
3. A `research` cache hit reuses quote-checked candidates (title, identity quote, facts)
   only after re-checking every quote against the current page text. Requirement checks
   are recomputed; the AI's project-suitability text is not reused, so cached candidates
   read "Suitability for this project was not re-assessed by AI" and are at most
   `potential_match` when every declared requirement is met.
4. The alternative-source follow-up search runs only when the line has no offer **and** no
   research candidate, and the budget allows it.
5. Prompt order is stable instructions, then the job's project context, then the line's
   part and documents, so lines of one job share a prefix for implicit caching.

### Refresh without rediscovery

`POST /v1/jobs/{id}/refresh` remembers each requested line's previous offer URLs. The
refresh re-fetches and re-verifies those pages (no Gemini search) and keeps the line when
at least one offer is not out of stock. Grounded discovery runs only when every known
page is gone, no longer verifies or is out of stock. A refreshed line's
`attribution.search_queries` is empty. Lines that had no offers search as before.

### Budget guard

`BS_JOB_GEMINI_BUDGET_USD` (default `0.25`) caps the estimated Gemini spend of each
sourcing run. Once reached, remaining lines skip paid stages;
free catalogue searches, known-URL refreshes and cache hits still run. Judge failures or
budget exhaustion preserve available deterministic and cached results. It is a soft ceiling:
lines already in flight (up to `BS_SOURCING_PARALLELISM`) finish their current call.
`0` disables paid sourcing entirely; use a large value (max 10) to effectively disable the
guard.

### Per-call-site model and thinking

| Setting | Default | Meaning |
| --- | --- | --- |
| `BS_GEMINI_SITE_MODELS` | `{}` | JSON map of call site to model; unset sites use `BS_GEMINI_MODEL` |
| `BS_GEMINI_SITE_THINKING` | `{"chat_scope": "low", "discovery": "low", "judge": "low", "spec": "low"}` | JSON map of call site to `thinkingLevel` (`low`/`medium`/`high`); setting it replaces the whole map; unlisted sites use the model default (medium on 3.8 Flash) |

Paid call sites use per-site configuration, including the spec judge.
New paid call sites should use `config.site_model(settings, site)` and merge
`config.site_generation(settings, site)` into `generationConfig`.

## Guidance for other call sites

- Put the fixed instructions in `systemInstruction`, then data shared by the job, then the
  per-line data last. Implicit caching needs a matching prefix of at least 4,096 tokens on
  Gemini 3.x Flash; keep JSON key order and serialisation deterministic.
- Check `usage.paid_allowed()` before any paid stage and return the budget diagnostic
  instead of calling Gemini when it is false.
- Run Gemini calls inside the worker that `JobService` wraps with `usage.attribute`; a new
  thread pool inside a stage must re-enter `attribute(current_ledger(), line_id)`.
- Read the shared cache before paid calls and write only project-independent values.
