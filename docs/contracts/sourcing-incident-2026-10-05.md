# Parts-search failure investigation — 5 October 2026

Affected job: `d2ecdff5-0800-48c2-a420-2ea0d4bd28b9`.

The job completed extraction and sourcing checkpoints, but most lines returned
`DISCOVERY_FAILED` before seller fetching. One resistor line reached research and
returned no retained evidence. The Cloud Tasks HTTP 503 responses at batch boundaries
were the existing continuation mechanism (`complete=false`), not proof of a crash.

A live `33k resistor` discovery reproduced HTTP 200 with `finishReason=MAX_TOKENS`
and nine grounded source chunks. The old parser rejected every non-STOP response,
discarding those sources. Historical per-line finish reasons were not logged, so
this reproduction does not establish the cause of every failed line in the job.

v0.17.3 accepts grounded source URLs on STOP or MAX_TOKENS. It still rejects truncated
responses without grounded sources and safety-blocked responses. Generated prose
URLs are never accepted. Source fetching, quote verification, and compatibility
evidence checks remain required. New logs record safe error categories, HTTP status,
finish reason and source count without API keys or raw model output.

Verification: 269 tests passed, two emulator tests skipped. A second live discovery
returned MAX_TOKENS with 13 source chunks; the fixed parser accepted five source URLs
within the configured limit. This verifies discovery, not seller availability or
end-to-end evidence quality. Existing saved results are not automatically rerun.

The pulled GitHub workflow targets GKE, but the deployed frontend BACKEND_BASE_URL
still points to the Cloud Run integration service. The immediate fix targets that
Cloud Run service. Coordinate deployment targets before relying on GitHub rollout.

Frontend: keep distinguishing `DISCOVERY_FAILED` from `NO_VERIFIED_OFFERS`; show
research diagnostics even when no verified offer exists. Users can explicitly
refresh selected lines after deployment without re-extracting the video.
