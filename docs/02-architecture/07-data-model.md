# Data model

> **In one minute.** Firestore (Native mode, `asia-south1`) stores four groups of data:
> - **per-job data:** `jobs` with `events` and `parts` subcollections
> - **shared caches:** `listings`, `part_offers`
> - **the knowledge graph:** `kg_*`
> - **the public library:** `bom_library`
>
> Large blobs go to Cloud Storage. The frontend reads jobs and the library directly through security rules, and only the backend writes.

---

## 1. Collections

```
jobs/{jobId}
  ├── events/{seq}
  ├── parts/{lineId}
  └── (fields: status, source, counters, costing, report_ref …)
listings/{listingId}
part_offers/{moduleId_country}
kg_chips/{chipId}
kg_modules/{moduleId}          (+ vector field "embedding")
kg_libraries/{libraryId}
kg_boards/{boardId}
kg_ecosystems/{ecosystemId}
kg_edges/{edgeId}
bom_library/{sourceKey}
  └── votes/{uid_lineId}
users/{uid}                     (optional, Firebase Auth)
config/runtime                  (feature flags, model ids, seller thresholds)
```

## 2. Document shapes

### `jobs/{jobId}`

```json
{
  "status": "sourcing",                       // queued|ingesting|extracting|awaiting_confirmation|resolving|sourcing|judging|costing|done|partial|failed
  "created_at": "…", "updated_at": "…",
  "input": {"url": "https://www.youtube.com/watch?v=…", "pin": "682011", "lang": "ml", "user_level": "beginner"},
  "source_key": "yt:dQw4w9WgXcQ",
  "project": {"title": "ESP32 Weather Station", "creator": "…", "thumbnail": "…"},
  "counters": {"parts": 14, "resolved": 14, "sourced": 9, "graded": 6},
  "costing": { /* Costing (cheapest) summary */ },
  "report_ref": "gs://bs-artifacts/jobs/<id>/report.json",
  "error": null,
  "model_versions": {"video": "gemini-3.8-flash", "judge": "gemini-3.1-pro-preview", "prompts": "v3"},
  "visibility": "unlisted",                   // unlisted|public
  "owner_uid": null
}
```

### `jobs/{jobId}/events/{seq}`

See [03-agent-pipeline.md §5](03-agent-pipeline.md#5-trace-events-what-judges-see). `seq` is a zero-padded integer for ordering.

### `jobs/{jobId}/parts/{lineId}`

```json
{
  "line_id": "L07",
  "stage": "graded",                          // extracted|confirmed|resolved|sourcing|candidates|graded|failed
  "item": { /* BomItem */ },
  "spec": { /* PartSpec */ },
  "candidates": ["lst_ab12…", "lst_cd34…"],
  "chosen_listing_id": "lst_ab12…",
  "impacts": [ /* ImpactReport, top 3 */ ],
  "updated_at": "…"
}
```

### `listings/{listingId}`

`Listing` schema ([04-prompts-and-schemas.md §1.2](04-prompts-and-schemas.md#12-offers-and-listings)) + `price_history: [{inr, at}]` (last 10).

### `kg_modules/{moduleId}`

```json
{
  "id": "gy-bme280-3v3",
  "aliases": ["GY-BME280-3.3", "BME280 3.3V module", "purple BME280"],
  "chip_id": "bme280",
  "category": "sensor",
  "vin": {"min": 3.0, "max": 3.6, "unit": "V", "citation": "…"},
  "has_regulator": false, "has_level_shift": false, "logic_v": 3.3,
  "connector": "header-4", "ecosystem": "none",
  "pinout": [{"label": "VIN"}, {"label": "GND"}, {"label": "SCL", "function": "I2C_SCL"}, {"label": "SDA", "function": "I2C_SDA"}],
  "i2c_default": "0x76",
  "common_in_india": true,
  "lookalikes": ["gy-bmp280"],
  "embedding": [/* 768 floats, gemini-embedding-2 */],
  "sources": ["https://…datasheet#page=2"],
  "curated_by": "anju", "curated_at": "2026-10-03"
}
```

### `kg_edges/{edgeId}`

```json
{"from": "a4988-pololu", "to": "drv8825-pololu", "type": "FOOTPRINT_COMPATIBLE",
 "grade": "B", "notes": ["current limit = VREF × 2", "A4988 VDD pin position is FAULT on DRV8825", "min STEP pulse 1.9 µs"],
 "citations": ["https://www.pololu.com/product/2133"]}
```

### `bom_library/{sourceKey}`

```json
{
  "source_key": "yt:abc123", "title": "…", "creator": "…",
  "latest_job_id": "…", "runs": 7,
  "summary": {"parts": 14, "local_share_pct": 86, "total_inr": 1840, "savings_pct": 71},
  "votes_up": 12, "votes_down": 1,
  "public": true, "embedding": [/* title+summary, for dedupe */]
}
```

## 3. Indexes

| Collection | Index | Purpose |
|---|---|---|
| `jobs/*/events` | `seq` asc | ordered trace |
| `listings` | `module_id` asc, `fetched_at` desc | cache lookup |
| `listings` | `seller` asc, `module_id` asc | seller split |
| `kg_modules` | **vector** on `embedding` (768, COSINE), prefilter `category` | canonicalisation and candidate search |
| `bom_library` | `public` asc, `runs` desc | gallery |

Vector index creation (example):

```bash
gcloud firestore indexes composite create --collection-group=kg_modules \
  --query-scope=COLLECTION --field-config=field-path=category,order=ASCENDING \
  --field-config='field-path=embedding,vector-config={"dimension":"768","flat":"{}"}'
```

## 4. Cloud Storage layout (`gs://bs-artifacts-<project>`)

```
jobs/{jobId}/report.json
jobs/{jobId}/export.csv | export.pdf
jobs/{jobId}/frames/{lineId}_{mmss}.jpg     (uploaded videos / blog images only)
jobs/{jobId}/compile/{lineId}.log
jobs/{jobId}/audio/{lang}.wav
datasheets/{chipId}.pdf                     (also imported into File Search store)
```

Lifecycle: delete `jobs/**` after 30 days unless the BOM is public.

## 5. Security rules (sketch)

```js
rules_version = '2';
service cloud.firestore {
  match /databases/{db}/documents {
    match /jobs/{jobId} {
      allow read: if true;                  // job ids are unguessable (uuid4); treated like unlisted links
      allow write: if false;                // backend only (Admin SDK)
      match /{sub=**} { allow read: if true; allow write: if false; }
    }
    match /bom_library/{k} {
      allow read: if resource.data.public == true;
      match /votes/{v} {
        allow create, update: if request.auth != null && v.split('_')[0] == request.auth.uid;
        allow read: if true;
      }
    }
    match /{document=**} { allow read, write: if false; }  // kg_*, listings, config: backend only
  }
}
```

## 6. Write budget (free tier: 20k writes/day)

A typical job makes about 60 events + 14 parts × ~6 stage updates + ~10 job updates ≈ **160 writes**. That's about 120 full jobs per day inside the free tier, which is enough for development. The judging period may exceed it slightly, costing cents.
