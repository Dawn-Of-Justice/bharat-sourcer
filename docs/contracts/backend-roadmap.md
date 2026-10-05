# Backend delivery roadmap

This roadmap tracks decisions from implementation discussions. Architecture documents
describe a broader target; the API contract describes what actually works.

## Available in the integration backend (v0.16.1)

v0.16 is deployed: [general part research](part-research.md), arbitrary
categories, source quotes, AI suitability assessments, flexible requirements, and
reviewed selection of verified quotes. Frontend research controls need integration.

v0.16.1 adds a single automatic alternative-source search for empty research results
and fixes readable-document budget handling. The live API version and health are verified.

| Area | Implemented |
| --- | --- |
| Input | Public YouTube extraction; editable BOM with model-reported timestamp evidence |
| Review | Confirm quantities, ownership and specs; atomic confirmation |
| Conversation | Persistent job chat, saved-state questions, draft edit proposals with accept/reject |
| Live updates | SSE job snapshots and chat state; complete replies rather than token streaming |
| Sourcing | Grounded discovery, guarded seller fetches, explicit JSON-LD price/stock verification |
| Compatibility | General AI suitability assessments with cited facts and generic requirement checks; legacy A/B/X rules for four families |
| Costs | Explicit quote selection, parts subtotals, unknown tax/shipping |
| Revisions | Targeted seller refresh; post-report required-spec updates and reassessment |
| Design advice | Confirmed single-LED resistor calculation; contextual role questions |
| Recovery | Bounded HTTP retries, leases, checkpoint resume, tested resistor-selector fallback |
| Sourcing controls (v0.11) | Persisted pause intent, acknowledgement after the active sourcing batch is saved, resume saved work; chat stays available |
| Chat actions (v0.12) | Proposed scoped seller refresh with explicit approval, atomic queuing, stale-report checks and existing limits |
| Durable dispatch (v0.13) | Cloud Tasks HTTP execution, sourcing checkpoints, scheduled pending-state reconciliation and scale to zero |
| Project-only chat and search behavior (v0.14) | LLM scope gate with fail-closed handling; up to three concurrent part searches; verified same-product variant fetch; per-line no-offer diagnostics |
| Offer images (v0.15) | Optional HTTPS seller image URL extracted only from the matching verified Product JSON-LD |
| Storage | Firestore persistence and private per-job tokens |

## Agreed work still to implement

| Priority | Deliverable | Completion criteria / frontend impact |
| --- | --- | --- |
| 1 | End-to-end conversational UI integration | BOM beside chat; citation navigation; proposal diff and accept/reject; SSE reconnect; explicit confirmation; integration smoke test |
| 2 | User steering during sourcing | Pause/resume implemented in v0.11; reviewed edits to a paused sourcing plan and frontend controls remain |
| 3 | More agent search and report tools | Refresh proposals (v0.12), reviewed spec/requirement proposals (v0.17.9), deterministic refresh completion messages and a bounded per-action history implemented. Remaining: frontend display of completion messages and history; chat-proposed paused-plan edits |
| 4 | Broader seller-spec parsing | v0.17.7 reads spec tables and labelled JSON-LD properties with field-level evidence and reports contradictions. Remaining: evaluate against labelled real seller pages and extend labels only from that evidence |
| 5 | Circuit context and more design rules | Establish resistor roles, topology and source-backed inputs; support additional roles only with validated calculations; attach suggestions to a specific physical component |
| 6 | Permanent rule repair workflow | Capture bounded failure cases; generate candidate patch in isolation; regression/property tests; versioned release and rollback. Current runtime only quarantines and falls back; no automatic patch authoring/deployment |
| 7 | Queue operations hardening | Durable dispatch, per-user quotas (v0.17), bounded sweep, per-job failure isolation and queue-age log signals (v0.17.6) implemented. Remaining: provision a log-based alert policy and raise max instances when load requires |
| 8 | Public launch controls | v0.17.2 deploys opt-in account/guest authorization, transactional quotas and revoked/disabled-account checks; Google provider is enabled. Frontend integration, real-login staging tests and auth activation remain, alongside retention, operational alerts and access review. See [authentication rollout](authentication.md) |
| 9 | Extraction quality evaluation | Labelled real-video BOM set; measure omissions, quantities and evidence accuracy; avoid fixture-based accuracy claims |
| 10 | Project page/code evidence | Extract supported project pages and code; show provenance/conflicts alongside video evidence |
| 11 | Richer sourcing decisions | Seller trust checks, module-backed compatibility rules, delivery/tax/shipping inputs and final cost calculations |

## Discussed follow-ups requiring design

- Token-by-token answer streaming (current SSE delivers persisted complete replies).
- File/schematic uploads to supply missing circuit context.
- Broader substitutions and adaptations (C/D grades remain reserved).
- Autonomous permanent patch promotion: define permitted changes and release gates before enabling it.

## Current constraints to show in the UI

Unknown specifications block positive grades and selection. Advice is conditional on user
inputs, and does not establish whole-project safety. Many real seller listings lack enough
data for selection. The test video has two unspecified resistors; no actual resistor value
for that circuit has been established. Chat edits support drafts; report changes use existing
structured endpoints. No checkout, automatic purchase or verified final delivered total exists.

## Suggested implementation order

Integrate the v0.15 API including optional offer images, sourcing progress diagnostics
and reviewed refresh actions, then add reviewed specification changes. Develop seller
parsing and circuit-context work against real labelled examples. Add public-launch controls
before opening paid job creation to general users. Rule repairs must preserve failure
evidence and earn promotion through regression checks.
