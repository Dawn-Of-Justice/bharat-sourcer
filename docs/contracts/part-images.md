# Part images

Images are presentation assets. They do not establish identity, price, stock,
specifications, pin layout, or compatibility.

## Response fields and routes

- `offers[].image_url`: optional seller photo from the checked product page.
- `report.lines[].image_candidates`: optional page reference images, including
  parts without a verified offer.
- `GET /v1/jobs/{job_id}/parts/{line_id}/image`: returns `PartImages` without
  starting generation.
- `POST` to the same path with `{"failed_urls": [...]}` excludes up to 10 failed
  photo URLs and may generate an illustration when enabled and within quota.

Both routes use normal job access credentials. Image requests do not consume the
project action quota.

`PartImages` contains ordered `candidates`, an always-present `fallback`, and
`generation_status`. Each image has `url`, `kind`, `label`, and nullable `source_url`.
Kinds are `seller`, `source`, `category`, `generated`, and `placeholder`.

The fallback is a URL-encoded `data:image/svg+xml,` image with a visible illustration
label. Generated images are cached JPEG data URLs. Generation is synchronous in the
POST and can take about 75 seconds; it does not change the sourcing report.

| Generation status | Meaning |
| --- | --- |
| `not_needed` | A candidate or category illustration is available |
| `not_requested` | Generation was not requested or is disabled/unavailable for this job |
| `ready` | A generated illustration is available |
| `pending` | Another request holds the generation lease |
| `unavailable` | Generation failed or exceeded quota; the backend can retry after an hour |

## Display behavior

The frontend tries seller photos, then page references, then the endpoint's fallback.
It reports exhausted photo URLs once per mounted part card. When no photo or category
art is available, it requests the optional generated illustration while keeping the
placeholder visible. A failed image request leaves the report usable.

The visible label follows the image actually displayed. Category and placeholder art
are marked as illustrations, and generated images keep the backend's generated-image
label. A pending or unavailable generation keeps the fallback; the frontend does not
automatically repeat generation POSTs. Older snapshots without image fields remain valid.
