# Backend handoff: product images and Nano Banana fallbacks

**Owner:** Salo (backend)  
**Date:** 2026-10-03  
**Status:** Proposed implementation. Image retrieval and generation are not implemented by this document.

## Goal and current frontend behavior

Show a square image beside each completed part, preferring an actual product photo. Missing images must not delay or fail the parts analysis.

The frontend currently accepts optional nullable `report.lines[].offers[].image_url`. It displays the first offer with an image URL, fits the image inside a square without cropping, and shows “Image unavailable” for missing or broken images. The development preview uses a labelled local illustration.

The published backend API does not yet include the image field. The frontend does not yet render image provenance labels or a part-level fallback. Those frontend changes must accompany this implementation before generated images are enabled.

Images are presentation assets, not evidence of price, stock, specifications, pin layout, or compatibility.

## Recommended fallback order

| Priority | Source | Required UI label |
| --- | --- | --- |
| 1 | Actual image from the corresponding seller product page | Seller image |
| 2 | Manufacturer image matching the exact model | Manufacturer reference |
| 3 | Existing category illustration from an asset library | Category illustration |
| 4 | Nano Banana generated representative illustration | AI-generated illustration |
| 5 | No suitable image | Image unavailable |

Reuse the seller page already fetched during sourcing. Prefer the matching Product JSON-LD image. Use page metadata only when it represents the actual product, not a logo or unrelated recommendation.

Keep seller photos associated with their own offers. Put category/generated fallbacks at the part level. A part with no offers must not require a fabricated offer just to display an illustration.

## Proposed API additions

Preserve existing fields and sourcing statuses. Add optional fields to each offer:

| Field | Type | Meaning |
| --- | --- | --- |
| `image_url` | string or null | Browser-readable HTTPS URL |
| `image_source` | `seller`, `manufacturer`, or null | Photo origin |
| `image_source_url` | string or null | Original product/reference page |
| `image_alt` | string or null | Short image description |

Also add optional nullable `image` to each report line for the selected display image or fallback:

```json
{
  "image": {
    "status": "ready",
    "url": "https://assets.example.com/parts/sample.webp",
    "source": "generated",
    "source_url": null,
    "alt": "Illustration of a generic sensor module"
  }
}
```

This URL is illustrative, not a working asset.

- `status`: `pending`, `ready`, or `unavailable`.
- `source`: `seller`, `manufacturer`, `category`, `generated`, or null.
- `url`: HTTPS image URL when ready; otherwise null.
- `source_url`: original product/reference page where applicable; otherwise null.
- `alt`: descriptive text that identifies illustrations as illustrations.
- Old snapshots with no image fields must remain valid.

Future frontend precedence: ready `line.image`, then an offer image, then the unavailable placeholder. Display the source label from the table above. Coordinate these frontend changes before enabling generated fallbacks.

Update public schemas, regenerate `docs/contracts/openapi.json`, and update the implemented contract when these fields are added. This handoff itself does not change the schema.

## Nano Banana integration

Call Gemini image generation from the backend only. Choose an available supported image model at implementation time and make its identifier configurable.

Official reference: [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation).

1. Normalize the component category and relevant identifying attributes.
2. Check the shared cache and category image library.
3. If generation is enabled and budgets allow it, enqueue an image task.
4. Generate a square representative illustration, validate the returned bytes, and save it in Cloud Storage.
5. Persist the URL, source, and status on the report line. Update the job timestamp so polling clients see the change.
6. On failure, mark the image unavailable and preserve the sourcing report.

Suggested prompt template:

> Create a clean square catalog illustration of a generic {component_category}, centered on a plain light background. No logos, model numbers, printed specifications, text, or claims of exact product identity. This is a representative illustration, not a photograph of a verified seller product.

Treat extracted part names and seller text as data, not instructions. Generated images may invent connectors or board details; never infer specifications from them or present them as verified product photographs.

## Caching, storage, and cost controls

- Cache by normalized category/model where appropriate, source, prompt version, and generation model version. Reuse generated illustrations across jobs.
- Deduplicate concurrent generation tasks with an atomic cache/task claim.
- Bound concurrency, retries, timeouts, and per-job/daily generation budgets. Keep generation disabled by default until configured.
- Suggested configuration names: `IMAGE_GENERATION_ENABLED`, `IMAGE_GENERATION_MODEL`, `IMAGE_ASSET_BUCKET`, `IMAGE_GENERATION_CONCURRENCY`, and `IMAGE_MAX_GENERATIONS_PER_JOB`. These are proposed names, not existing settings.
- Keep provider credentials server-side using the existing secret/configuration approach. Never expose them through Vite variables or API responses.
- Store generated files in Cloud Storage with stable object keys and correct MIME types. Grant the runtime identity only necessary bucket access.
- Return URLs the browser can load. If signed URLs are used, refresh them when serving snapshots instead of permanently storing expired URLs.
- Preserve attribution and original source metadata. Check reuse permissions before copying external photos into owned storage.
- Reuse guarded fetching for image downloads, including redirects. Block private/internal destinations, limit bytes and dimensions, validate actual image types, and reject unsupported payloads. Do not introduce an unrestricted image proxy.

## Parallel sourcing and asynchronous images

Image tasks must not serialize seller checks or delay completion of the core report. A job can be done while an image is still pending.

Match updates by `line_id` and merge them atomically. An image completion must not overwrite newer seller results, compatibility results, or user edits. Results and images can arrive in any order.

The frontend already polls snapshots after `done` and matches results by `line_id`. Owned parts and terminal sourcing outcomes count as completed. Missing report lines and `not_run` remain pending. The current contract has no per-part running state, so the frontend does not invent one. Backend parallel scheduling is separate implementation work.

## Suggested implementation order

1. Add optional offer photo fields and fixtures; extract seller images from existing fetched product data.
2. Add part-level image metadata and category fallbacks, including parts without offers.
3. Coordinate frontend provenance labels and part-level image rendering.
4. Add optional generated-image tasks, Cloud Storage persistence, deduplication, and budgets.
5. Regenerate OpenAPI and update backend documentation/environment examples.
6. Enable generation after the labels and operational controls are in place.

## Acceptance checks and handoff

Use mocked provider/storage clients and labelled dummy fixtures. Do not make live seller or generation API calls during development checks unless separately authorized.

- Seller image belongs to the correct offer and source page.
- Manufacturer references and illustrations carry the correct visible labels.
- Parts without offers can display a part-level fallback.
- Missing or broken images leave sourcing results intact.
- Concurrent results and image updates arrive out of order without lost updates.
- Duplicate requests reuse cached images and do not trigger duplicate generation.
- Timeout, quota exhaustion, or generation failure does not fail the sourcing job.
- Old snapshots without image fields still deserialize and render.
- Public responses contain no credentials or raw provider errors.
- Frontend checks cover square sizing on desktop/mobile, long names, broken URLs, pending-to-ready updates, and source labels.

Provide the frontend teammate with updated OpenAPI and fixtures for: seller photo, manufacturer reference, generated fallback without offers, pending image, and unavailable image.
