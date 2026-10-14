# Build guide (v0.40.0)

The build page shows a finished project (`status: "done"`) for the maker to follow: a
parts checklist and numbered build steps. The steps are **AI-inferred and not verified**
against the video or the physical build; the UI must say so. The backend puts that
sentence in `message` of a ready guide. Demo jobs get a labelled fixture guide
(`demo: true`, every title ends in "(demo)") without a model call.

## Parts checklist

`POST /v1/jobs/{job_id}/build-progress` with the job token (or account) of the owner:

```json
{ "line_id": "L02", "received": true }
```

Adds (`true`) or removes (`false`) the line id in `Job.build_received` (at most 100 ids)
and returns the updated `Job`. Idempotent: repeating a request changes nothing.
Errors: 404 `JOB_NOT_FOUND` (unknown job or token), 409 `INVALID_STATE` (job not `done`),
422 `INVALID_LINE` (no such line on the job). When a later confirm removes a line, its id
leaves `build_received`.

## Build steps

- `POST /v1/jobs/{job_id}/build-guide` (owner, `done` jobs; else 409 `INVALID_STATE`):
  returns the current guide when it is `ready` or `pending` within its lease; otherwise
  starts a new one and returns it `pending`. Only this request starts generation; nothing
  runs automatically when sourcing finishes.
- `GET /v1/jobs/{job_id}/build-guide`: the current guide; 404 `BUILD_GUIDE_NOT_FOUND`
  before the first POST. A `pending` guide whose lease (10 minutes) ran out is returned
  `failed` ("interrupted") and can be requested again.
- The same object is on `Job.build_guide`.

```text
BuildGuide { status: pending|ready|failed|stale, message, generated_at, items_hash,
             demo, steps: BuildStep[] (at most 20) }
BuildStep  { title (≤120), detail (≤600), line_ids: string[], timestamp: "MM:SS" or
             "H:MM:SS" | null, caution (≤200) | null, origin: "ai_inferred" }
```

`failed` and `stale` carry a `message`. A guide becomes `stale` when the parts list changes
(a confirm edit that adds, removes or changes lines); POST writes a new one.

## Generation

One Gemini call, site `build_guide` (low thinking; Vertex AI when enabled, else the API
key). Text only, no video. Input: the model's own project understanding (summary, power,
controller, interfaces, assumptions; owner-edited title and description are not sent), the
confirmed lines (id, name, count, whether the maker has it, up to four evidence
observations with their video timestamps), the overview wiring when the overview is
`ready` (from/to line and pin, signal, label), code-patch notes (applied changes and notes)
and the safety flags. The prompt asks for ordered steps a beginner can follow (prepare
parts, solder or connect, flash code, test, enclose) with the video timestamp where the
evidence shows that moment.

Validation in code (`build_guide.py`): text fields are cut to their limits; line ids not
on the job are dropped; a timestamp must equal one of the job's video evidence timestamps
(compared as seconds, returned in the stored form) or it becomes null; steps without a
title are dropped. An answer with fewer than 3 or more than 20 usable steps, invalid JSON,
or a finish reason other than `STOP` (for example `MAX_TOKENS`) fails; the call is retried
once, then the guide is stored `failed`.

## Cost and caching

About one call per guide (roughly $0.01 at current Flash prices; two on a retry), added to
`Job.cost_estimate` under `build_guide` without touching the sourcing run budget. Skipped
when the job's AI budget is reached. Results are cached in the shared cache (namespace
`build_guide`, 7 days) keyed by the parts list hash and a hash of the whole input, so only
a job with the same input reads a cached guide. `BS_BUILD_GUIDE_ENABLED=false` turns the
feature off (POST stores a `failed` guide saying so).
