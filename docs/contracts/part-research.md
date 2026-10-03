# General part research — v0.16.1

The research path accepts arbitrary components, materials and part categories. It
uses grounded search to find supplier pages and manufacturer documentation, reads
them through the existing guarded fetcher, and asks Gemini to extract source-backed
facts and assess the candidates against the saved project. There is no category
allow-list for research. `PartSpecs.family` also accepts arbitrary strings; the
older typed fields and four-family deterministic compatibility checks remain available.

## Frontend integration

Render `report.lines[].research` independently of `offers` and `sourcing_status`.
`no_verified_offers` means no verified INR quote: a line can still have useful
research candidates and specification evidence. The existing frontend only renders
verified offers, so it needs a research section to display these new results.
Saved project chat already receives the new research results.

Use [the labelled UI fixture](fixtures/part-research.json) to build the empty-offers
case with a useful research candidate. All URLs and facts in that file are synthetic.

Research statuses are `ready`, `no_evidence`, `failed`, and `stale`. Null means an
older snapshot, skipped line, failed discovery, or research disabled. Each result has
`summary`, `checked_at`, `model`, `questions`, `sources`, and `candidates`.

Each source records its URL, fetch status (`read` or `unavailable`), sanitized reason
when unavailable, and `reviewed` indicating that its text entered the research call.
A fetched source can be outside the review budget. A failed call can have reviewed
sources but no completed assessment. Show unavailable source links as unverified.

Each candidate contains:

- `url`, `title`, free-form `category`, and `kind` (`seller`, `manufacturer`, `reference`).
- `match`: `exact` or `possible`, a model assessment of part identity.
- `identity_quote` and `facts`: free-form name/value/unit entries with source quotes.
- `assessment`: `status`, `explanation`, `conditions`, `questions`, and `checks`.
- `evidence_method: llm_extraction_quote_checked`.

Assessment statuses are `potential_match`, `needs_information`, `not_suitable`, or
`stale`. Label this **AI assessment**, show conditions and questions, and link the
source. `potential_match` is a candidate for human review, not an electrical safety
certification or a deterministic A/B grade. Quote matching validates that the text
exists in that source; it does not independently prove the model's interpretation,
the source's accuracy, or the completeness of project requirements.

Do not present a price inside `facts` as a verified per-piece offer. Keep its quote,
currency and package context visible. Only `offers` enter the existing costing flow.
When research matches a verified offer URL, that offer also exposes
`research_assessment`. Show the AI assessment alongside any deterministic checks;
the old compatibility field alone no longer describes all available analysis.

## Flexible project requirements and interaction

Every BOM item has a `requirements` list, defaulting to empty. Each entry has
`name`, `value`, optional `unit`, and `operator`: `equals`, `at_least`, or `at_most`.
Values are strings to preserve exact decimal values and textual requirements.
Example (synthetic, not a recommendation for a real project):

```json
{
  "name": "bore diameter",
  "value": "8",
  "unit": "mm",
  "operator": "equals"
}
```

Draft confirmation and chat edit proposals support `requirements` on `add` and
`update`. An omitted list preserves requirements; a supplied list replaces it;
`[]` clears it. Existing chat proposal approval applies before changes are saved.
Ask the user to supply missing requirements rather than silently accepting the
model's suggested requirements as project facts.

After completion, `POST /v1/jobs/{id}/specs` accepts either legacy `specs`, generic
`requirements`, or both:

```json
{"updates":[{"line_id":"L01","requirements":[
  {"name":"bore diameter","value":"8","unit":"mm","operator":"equals"}
]}]}
```

All updates are atomic. A change marks the project's AI assessments stale because
they used the shared BOM context, and clears selections based on AI assessments.
Source facts remain saved; numeric checks are recomputed without model calls.
Refresh affected lines using the existing approved refresh flow to reassess.
The existing limit of two refresh batches per job still applies. The completed-job
chat currently cannot apply requirements directly: the frontend uses `/specs`.

Checks compare exact normalized property names and compatible units. Decimal
arithmetic handles equals/minimum/maximum and supported SI conversions for voltage,
current, power, length, resistance, frequency and mass. Case-sensitive SI prefixes
are preserved. Missing, conflicting, unmatched properties, unsupported conversions,
or non-numeric ranges produce `unknown`. Units not in the conversion table can
still be compared when identical. Text equality uses case-insensitive exact values.
These checks are independent of the open-ended AI suitability explanation.

## Reviewed selection

A verified, in-stock, fresh quote with an AI `potential_match` can be selected with
`accept_research_assessment: true` if deterministic compatibility is unresolved.
Its research must be current; declared generic requirements must all pass. Known
deterministic incompatibility still blocks selection. The report records
`research_accepted: true` and leaves `grade: null`; show that the user approved an
AI assessment. This creates a quoted subtotal, not a purchase. Research-only
candidates without verified quotes cannot be selected into costs.

```json
{"selections":[{"line_id":"L01","offer_url":"https://seller.example/fixture",
"accept_research_assessment":true}]}
```

The example URL is a dummy fixture. Existing A/B selection rules remain, but new
generic requirements must also have evidence; `REQUIREMENTS_UNRESOLVED` identifies
missing or failing checks. Unsupported families no longer produce a request to
choose one of four categories.

## Execution, limits and failures

Sourcing still runs parts in parallel and checkpoints each complete line. Research
adds one Gemini request per part with readable documents, with existing bounded
transient retries; it increases model usage and per-line completion latency. It
does not stream partial research tokens.

v0.16.1 attempts one follow-up discovery if the first round has neither a verified
offer nor usable research evidence. It asks for alternative accessible sources while
preserving the original identity and requirements. It skips previously attempted URLs
and merges source diagnostics and search attribution. Redirect aliases can still incur
a fetch before their duplicate destination is recognized. Provider failures do not
trigger an extra search; failed follow-ups preserve the original results. A successful
verified quote survives even if its research call fails. The follow-up does not consume
one of the user's two refresh batches.

This allows at most two discovery requests and two research requests per sourced part
(each still subject to bounded transient retries). Each round retains the existing
candidate and readable-document budgets. Sources are capped at 32 across both rounds.
Unreadable documents no longer consume the readable-document review budget. Search
coverage may still vary between runs; sources can remain blocked or lack useful text.

- `BS_RESEARCH_ENABLED=true` enables research in live mode.
- `BS_RESEARCH_FOLLOWUP_ENABLED=true` enables the single automatic follow-up.
- `BS_RESEARCH_PAGES_PER_PART=3` limits reviewed documents (1–5).
- `BS_RESEARCH_PAGE_CHARS=12000` caps text per document (2,000–20,000).
- Existing discovery and per-job sourcing budgets still apply.
- HTML, plain text, JSON-LD, and text PDFs are supported. PDFs run in a subprocess
  with a 12-second timeout, first 10 pages, 2 MB input and 20,000-character output
  limits. Linux deployments also cap parser memory at 96 MB. Scanned PDFs have no OCR.
- Robots rules, public HTTPS enforcement, pinned DNS, redirects, fetch size limits,
  and timeouts remain in effect. JavaScript-only or blocked pages may be unreadable.
- A source quote or identity that cannot be matched is rejected. Rejected facts are
  omitted and the candidate becomes `needs_information`; other usable candidates survive.
- Provider failure preserves verified offers and returns a sanitized research failure.

This is category-independent research, not a guarantee of internet completeness.
Part identity, document availability, bounded search, missing project context and
model interpretation still limit results. Research has no automatic rule-writing
or code-patching capability.

Schema generation follows the existing [Gemini structured-output adapter](https://ai.google.dev/gemini-api/docs/structured-output).
PDF text extraction uses [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
