# Project chat and parallel sourcing (v0.14)

## Project-only chat

Live chat first classifies whether the latest request relates to the saved project,
using its BOM and recent conversation. Unrelated or mixed-purpose requests receive
a fixed project-only reply, with no BOM edits or refresh proposal. Failed scope
checks are retried first (five backed-off HTTP attempts per check, two checks); only
when all fail is a retry message returned, without running answer generation. The answer prompt
also enforces the same scope. A short follow-up is allowed when its project context
is clear. Existing 20-turn and one-active-reply limits still apply.

This is an LLM classifier, not a guaranteed abuse barrier. It adds one small Gemini
call per turn. Public account quotas and rate limits are still needed to bound
abuse across newly created jobs; rejected questions still incur classification
usage and count toward the job's turn limit.

## Parallel sourcing

`BS_SOURCING_PARALLELISM` defaults to 3 and accepts 1–4. Each worker processes a
batch of that many BOM lines concurrently. Individual results are saved as they
finish and displayed in BOM order. One Cloud Tasks delivery processes one batch;
the existing sourcing budget is reserved before starting calls, so parallelism
does not raise the maximum number of searched parts.

Pause waits for all already-started parts in the batch to finish and be saved.
It starts no further batch. Resume skips saved lines. Update pause UI wording to
“Pausing after active parts finish”. An active provider request is not cancelled.

## Seller verification fixes and diagnostics

Some sellers publish a single Product/Offer on a base page with an explicit
`?variant=...` offer URL. The backend now follows one such URL on the same HTTPS
host and product path, fetches it through the existing safeguards and verifies
the offer again. It never accepts an unfetched variant price. Multiple variants,
wrong parts, blocked pages and unsupported offers remain unverified.

Conservative plural normalization covers resistors, LEDs and wires. Searches with
no verified offer now include `sourcing_error.code = NO_VERIFIED_OFFERS` and an
explanation with candidate/fetch/rejection counts. The frontend should display
that message. `no_verified_offers` does not mean no sellers exist.

Observed failures included HTTP 403, robots restrictions, category pages,
oversized pages, mismatched ESP32 listings and unfetched variant URLs. A live
Quartz Components red LED variant was verified after the fix. Seller restrictions
are not bypassed and generated search text is never treated as verified pricing.
