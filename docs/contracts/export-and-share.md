# Export and share (M14)

Owners can download a project's BOM as CSV, open a printable HTML report (print to PDF
from the browser), and create a revocable, read-only share link. Code:
`backend/src/bharat_sourcer/export.py` (redaction and rendering) and `sharing.py` (routes).

## Endpoints

All paths are under `/v1/`, so the integration key (when configured) is still required;
the frontend proxy adds it as for every other call.

| Method and path | Auth | Result |
| --- | --- | --- |
| `GET /v1/jobs/{job_id}/export.pdf` | Same as `GET /v1/jobs/{job_id}` | `application/pdf`, `Content-Disposition: attachment` (A4 order plan) |
| `GET /v1/jobs/{job_id}/export.html` | Same as `GET /v1/jobs/{job_id}` | Self-contained HTML, `Content-Disposition: inline` |
| `GET /v1/jobs/{job_id}/share` | Owner | `{"active": bool, "created_at": datetime \| null}` |
| `POST /v1/jobs/{job_id}/share` | Owner (+ CSRF header when auth is on) | 201 `{"share_token", "path", "created_at"}` |
| `DELETE /v1/jobs/{job_id}/share` | Owner (+ CSRF header when auth is on) | 204 |
| `GET /v1/shared/{share_token}` | None (no session or job token) | Redacted `SharedProject` JSON |
| `GET /v1/shared/{share_token}/export.pdf` | None | Same PDF as the owner export |
| `GET /v1/shared/{share_token}/export.html` | None | Same HTML as the owner export |
| `POST /v1/shared/{share_token}/copy` | Account or guest session, `X-Requested-With: BharatSourcer` | 201 `CopiedProject` (`job_id`, `job_token`, `status`); see [Copy to my projects](#copy-to-my-projects) |

Owner auth means an account/guest session when auth is enabled, otherwise `X-Job-Token`.
Wrong owners get 404 `JOB_NOT_FOUND`, as elsewhere. Exports and share-link changes do not
consume the action quota and never start extraction or sourcing.

## Share links

- `POST .../share` returns the token once. The server stores only its SHA-256 hash on the
  job document (`share_token_hash`, `shared_at`), so the token cannot be shown again; call
  `POST` again to get a new link. **Creating again rotates the link**: the old one stops
  working.
- Token format is `<job_id>.<random>` (`secrets.token_urlsafe(32)`, 256 bits). The job id
  lets the server read one document by id: no new Firestore query, index or collection.
  The job id alone grants nothing.
- `DELETE .../share` revokes immediately. Unknown, malformed, rotated and revoked tokens
  all return 404 `SHARE_NOT_FOUND`.
- Shared reads are bounded per client IP (hashed, like the existing quota keys): 30 per
  minute and 300 per day across all shared links, returning 429 `USAGE_LIMIT`. They never
  touch the owner's quotas.
- Shared responses send `Referrer-Policy: no-referrer`, and the HTML report sets a
  `no-referrer` meta tag, so seller sites do not receive the share URL.

### Copy to my projects

v0.25. `POST /v1/shared/{share_token}/copy` creates a new project owned by the caller from
what the share link shows. No AI runs.

- **Copied:** the input (source URL, extra sources, country), `project`, `items`, `report`
  (offers, research, order plan), `safety_flags`, `source_reports`, `video_meta` (YouTube
  quote retention keeps counting from the original fetch). Each line's grounded-search
  `attribution` is dropped, as in the shared view.
- **Not copied:** chat, events (the copy starts with one "Copied from a shared project"
  event), actions, `resistor_advice`, `cost_estimate`, the share link.
- **Owned parts:** every `user_has_it` is reset to false; lines that were `already_owned`
  become `not_run` (refresh to find offers).
- **Selections:** the sharer's own choices stay selected with `selection_source: "user"`
  and `copied_choice: true` ("Copied choice"). Choosing or clearing an offer through
  `/selections` sets `copied_choice` to false. Recommendations are unchanged.
- `job.copied_from` holds `copied_at` and `source_updated_at` (prices are from then or
  earlier). It does not identify the source project.
- **Which projects:** only `awaiting_confirmation` (a draft parts list) and `done`; others
  return 409 `SHARE_NOT_READY`.
- **Limits:** counts as a new project (daily project quota and action budget; 429
  `USAGE_LIMIT`). Guests get 422 `PART_LIMIT` when the project has more parts than the
  guest limit, rather than a cut-down copy. Revoked or unknown links return 404
  `SHARE_NOT_FOUND`. A copy is independent: revoking the link does not affect it.

### Redacted view (`SharedProject`)

Fields: `shared` (always `true`), `demo`, `status`, `source_url`, `project`
(AI-inferred `ProjectContext`), `created_at`, `updated_at`, `items`, `report`, `notice`.

Excluded: job id, job token and its hash, owner identity, `lang`/`user_level`,
chat `messages`, `chat_state`/`chat_error`, `events`, `actions`, `resistor_advice`,
extraction model and recovery counters, and each line's grounded-search `attribution`
(search queries and suggestion HTML). Offers, research and evidence are kept.

## PDF and HTML report

v0.26.0: the order plan as a downloadable A4 PDF (`export.pdf`), rendered by WeasyPrint from
the same HTML as `export.html`. CSV export was removed. The PDF needs Pango and a font with
the rupee sign on the server (installed in `backend/Dockerfile`); without them the PDF
routes return 503 `PDF_UNAVAILABLE`. Rendering never fetches external resources.

Sections, in order:

1. Branded header with the title, description, source ("YouTube video" or the site name),
   part count and status in plain words.
2. When the report has an `order_plan`: a summary (estimated total, parts, sellers, parts
   still to source), then one section per seller with need, buy (pack rounding and spares),
   unit and line price, the pick label (Recommended, Your choice, Copied choice, or the
   reason it is not selected), the seller's parts, GST, shipping and total with their
   estimated or unknown status, the free-shipping gap and the dated shipping policy.
   Then "Still to source" with each line's message and next steps.
   Reports without an order plan (demo or older) show the selected offer per line and the
   selected subtotal, which excludes tax and shipping. Drafts show the parts list only.
3. Parts the user already has, the full parts list (requirements and status in plain
   words), "Where each part came from" (evidence), and AI-inferred project notes.
4. A footer with the snapshot, plan and costing disclaimers and "This is not an invoice".

Amounts use Indian digit grouping (₹1,23,456.50). Links show short text ("open listing",
the source name) with the stored http(s) URL as `href`. Inline CSS only: no scripts,
images or external assets. Every value is HTML-escaped; links use
`rel="noopener noreferrer nofollow"`. Response headers:
`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; ...` and
`X-Content-Type-Options: nosniff`. Demo jobs show a red `DEMO JOB` banner.

## Frontend to do

- Report page: a "Download PDF" button (`export.pdf`), fetched through the proxy so
  credentials are attached, then saved as `<project>.pdf`.
- Share control: show `GET .../share` state; "Create link" calls `POST` and shows a copy
  box for a frontend URL that embeds `share_token` (the token is shown only once; warn
  that creating again replaces the old link); "Revoke" calls `DELETE`.
- Public share page: a route reachable without sign-in that calls
  `GET /v1/shared/{share_token}` through the proxy and renders a read-only report (no
  chat, edit, select, refresh or image-generation controls). Show `notice` prominently,
  and the demo label when `demo` is true. Handle 404 (revoked) and 429.
- The CORS allow-list now includes `DELETE`.
