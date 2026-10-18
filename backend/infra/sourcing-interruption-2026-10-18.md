# Sourcing interruption repair — 2026-10-18

Job a344cc82-d0ee-408b-a74d-eaf87fd1bd4b stopped after 14 saved lines.

- Cloud Run logged an out-of-memory termination at 08:26:53 UTC (512 MiB limit).
- The recovered snapshot reached 795,096 serialized bytes, near the 800,000-byte
  application storage cap. Another report line could no longer be checkpointed.
- The lease then expired after its recovery allowance was consumed.

Large reports now use lossless zlib/base64 storage in report_zlib_b64. Query fields,
ownership, retention timestamps, and transaction semantics remain unchanged.
All reads hydrate the original report; public API schemas are unchanged.
Legacy documents remain readable. Small reports remain directly stored.
Expanded reports are bounded at 16 MB and persisted documents at 800 KB.
The existing saved report round-tripped exactly and persisted at 259,316 bytes.

Deployment memory is 2 GiB. Do not roll back to code predating compressed-report
support once large documents have been rewritten; deploy a forward fix instead.
No completed seller evidence is removed to make room.

Validation: synthetic 37-line/20-offer round-trip, legacy documents, corrupt and
oversized compressed reports, storage and edit-after-sourcing tests; mypy and ruff.
