# Export and share (M14)

Owners can download a project's BOM as CSV, open a printable HTML report (print to PDF
from the browser), and create a revocable, read-only share link. Code:
`backend/src/bharat_sourcer/export.py` (redaction and rendering) and `sharing.py` (routes).

## Endpoints

All paths are under `/v1/`, so the integration key (when configured) is still required;
the frontend proxy adds it as for every other call.

| Method and path | Auth | Result |
| --- | --- | --- |
| `GET /v1/jobs/{job_id}/export.csv` | Same as `GET /v1/jobs/{job_id}` | `text/csv`, `Content-Disposition: attachment` |
| `GET /v1/jobs/{job_id}/export.html` | Same as `GET /v1/jobs/{job_id}` | Self-contained HTML, `Content-Disposition: inline` |
| `GET /v1/jobs/{job_id}/share` | Owner | `{"active": bool, "created_at": datetime \| null}` |
| `POST /v1/jobs/{job_id}/share` | Owner (+ CSRF header when auth is on) | 201 `{"share_token", "path", "created_at"}` |
| `DELETE /v1/jobs/{job_id}/share` | Owner (+ CSRF header when auth is on) | 204 |
| `GET /v1/shared/{share_token}` | None (no session or job token) | Redacted `SharedProject` JSON |
| `GET /v1/shared/{share_token}/export.csv` | None | Same CSV as the owner export |
| `GET /v1/shared/{share_token}/export.html` | None | Same HTML as the owner export |

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

### Redacted view (`SharedProject`)

Fields: `shared` (always `true`), `demo`, `status`, `source_url`, `project`
(AI-inferred `ProjectContext`), `created_at`, `updated_at`, `items`, `report`, `notice`.

Excluded: job id, job token and its hash, owner identity, PIN code, `lang`/`user_level`,
chat `messages`, `chat_state`/`chat_error`, `events`, `actions`, `resistor_advice`,
extraction model and recovery counters, and each line's grounded-search `attribution`
(search queries and suggestion HTML). Offers, research and evidence are kept.

## CSV

- UTF-8 with BOM (opens correctly in Excel), CRLF rows, stdlib `csv`.
- Leading comment rows start with `#`: a `DEMO JOB` row for demo jobs, the price-snapshot
  notice, project title, source URL and export time. Then the header row and one row per
  report line (or per draft BOM item before a report exists), then a subtotal and the
  unselected line ids.
- Columns: `data_label` (`demo_sample` | `seller_published_snapshot` |
  `no_selected_offer`), `line_id`, `part_name`, `qty`, `qty_unit`, `qty_source`,
  `qty_reason`, `owned` (`yes`/`no`), `sourcing_status`, `requirements`
  (`name op value unit`, `; `-joined, `(inferred)` marked), `offer_count`,
  `selected_seller`, `selected_offer_title`, `selected_offer_url`, `price_inr`,
  `subtotal_inr`, `stock`, `checked_at`, `compatibility_status`, `compatibility_grade`,
  `selection_grade`, `evidence` (`mm:ss observation` or `"quote" (url)`, ` | `-joined).
- Offer columns describe the **selected** offer only; unselected lines show the count.
- Removed lines are not in the export: confirmation deletes them from the BOM.
- Formula injection: any cell starting with `=`, `+`, `-`, `@`, tab or CR is prefixed
  with `'`.

## HTML report

Inline CSS with a print stylesheet (A4 landscape, repeated table header, rows not split),
no scripts, images or external assets. Every value is HTML-escaped; links are the stored
http(s) URLs with `rel="noopener noreferrer nofollow"`. Response headers:
`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; ...` and
`X-Content-Type-Options: nosniff`. Demo jobs show a red `DEMO JOB` banner; every report
shows the snapshot notice and states the subtotal excludes tax and shipping.

## Frontend to do

- Report page: "Download CSV" and "Print / PDF" (open `export.html` in a new tab) buttons.
  Fetch through the proxy so credentials are attached, then save the blob.
- Share control: show `GET .../share` state; "Create link" calls `POST` and shows a copy
  box for a frontend URL that embeds `share_token` (the token is shown only once; warn
  that creating again replaces the old link); "Revoke" calls `DELETE`.
- Public share page: a route reachable without sign-in that calls
  `GET /v1/shared/{share_token}` through the proxy and renders a read-only report (no
  chat, edit, select, refresh or image-generation controls). Show `notice` prominently,
  and the demo label when `demo` is true. Handle 404 (revoked) and 429.
- The CORS allow-list now includes `DELETE`.
