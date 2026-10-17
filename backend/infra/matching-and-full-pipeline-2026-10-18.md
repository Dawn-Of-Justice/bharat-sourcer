# Matching safeguards and full-pipeline pilot — 18 October 2026

## Implementation

Commit `8ebab9d` on `feat/robust-seller-discovery` (pushed; not deployed).
- Reject accessory-only mismatches even if the AI judge accepts them.
- Keep other Uno generations returned by the judge as partial adaptation candidates,
  with an explicit MCU/voltage/pinout/library review note. Do not silently treat them as exact.
- Preserve sparse-description partial candidates and existing AI compatibility/adaptation paths.
- Remove Shopify `_gsid` tracking IDs; normalize fetch-deduplication keys while retaining
  genuine variant parameters. Base URLs and variant URLs are not blindly merged.
- Existing quantity-aware bulk-waste flags and selection safeguards remain in place.

## ESP32 diagnosis

The exact DOIT product URL at techiesms returned HTTP 200 but its structured offer title
was only “ESP32 Development Board – Best Price India”. The title-only query therefore
could not confirm DOIT DevKit V1. The AI-judged pilot found usable candidates without
relaxing that exact-model title check. This is a verification-evidence gap, not proof
that the requested board cannot be purchased.

## Validation

Full suite before the final adaptation adjustment: 1,695 passed, 3 skipped.
After the adjustment: 74 targeted matching/sourcing/buyer tests passed; mypy checked
75 source files; lint/format and OpenAPI checks passed. Production was not changed.

## Pilot limitations

Three core components, one from each prior project; three provider configurations.
Actual app sourcing factory with AI spec writing, judge, recovery, grounding, buyer and
research enabled according to local settings; in-memory storage and independent caches.
Rotated arm order; one run per arm. Maximum Gemini budget $0.30 per arm (not a hard
network spend cap; in-flight calls may overshoot). API subscription costs are excluded.
Names and minimal project contexts are held fixed, but AI specs are regenerated per arm;
therefore model variance and live seller variability confound causal attribution.
This is a small diagnostic pilot, not a statistically controlled A/B or complete-BOM study.
The process loaded the initial safeguards before the later Uno adaptation adjustment;
none of these three pilot queries request Uno, so that change does not affect its cases.
The final query-order deduplication change was added after the process started and is
covered by regression tests, not by these pilot timings.

Counts distinguish AI-judged in-stock exact/compatible offers from partial candidates.
Neither category is independently hardware-tested; partial can be the right component
with missing evidence or an alternative needing adaptation. No code changes to a user's
project or hardware compatibility certification were performed.

## Completed nine-run results

In-stock exact/compatible offers judged by the AI, deduplicated by observed product path
for reporting only (variant identities remain intact in application logic):

| Component | Baseline | Brave | Brave + Shopify |
|---|---:|---:|---:|
| ESP32 DOIT DevKit V1 | 1 | 1 | 3 |
| HC-SR04 | 5 | 7 | 8 |
| 28BYJ-48 5V motor | 7 | Inconclusive | 9 |

In-stock partial candidates remained visible: ESP32 5/4/4 across the respective arms;
HC-SR04 0/0/1. Partial does not mean wrong: evidence may be incomplete, or a change may
be needed. The report does not count partial as drop-in verified compatibility.

The Brave-only motor run took 203 seconds and returned one unjudged offer. It is not a
valid comparison of judged coverage. Error logs were suppressed to protect credentials,
so the underlying judge/research failure was not captured; diagnose with sanitized
structured error telemetry before rerunning. All runs reported offers_found, which alone
is therefore insufficient as a success metric.

Baseline versus both providers: ESP32 66.7 vs 83.9 seconds; HC-SR04 37.0 vs 62.4;
stepper 47.6 vs 72.8. This is roughly 17–25 seconds extra in these single runs.

The both-provider arm contains bundles and model ambiguities retained by the AI,
including an HC-SR04 title with HY-SRF05 URL and a motor+driver bundle. Its counts are
AI judgments, not independently validated compatible purchases. Sparse project context
and independently generated AI specs limit comparisons. No arm needed grounded fallback
on the successful judged runs; it was configured but not exercised.

## Recommendation

Keep Brave and Shopify available while measuring the full flow. The earlier title-only
sample did not show Shopify's benefit, but this pilot did; do not disable it based on that
sample. Preserve partial candidates, state what evidence is missing versus what actually
conflicts, and require a concrete compatibility/adaptation plan before recommending a
changed board as a replacement. Existing code-adaptation features were not extended or
hardware-validated in this change.

Before wider rollout: repeat with frozen buying specs and a richer shared project
context, capture sanitized failure reasons, and distinguish exact/compatible, partial,
unjudged, out-of-stock and duplicate results in telemetry. Evidence-backed base/variant
alias merging remains a separate improvement; this change only safely removes tracking
and normalizes equivalent URL keys.

Final implementation commits: 8ebab9d, ddecf9e, 0b0872c (pushed). The surface-mount
refinement added one more regression test: 19 matching tests pass. No deployment occurred.

Estimated recorded Gemini cost across the pilot: $0.1401 (provider fees excluded).
