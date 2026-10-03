# Backend delivery roadmap

This roadmap tracks decisions from implementation discussions. Architecture documents
describe a broader target; the API contract describes what actually works.

## Available in the integration backend (v0.11)

| Area | Implemented |
| --- | --- |
| Input | Public YouTube extraction; editable BOM with model-reported timestamp evidence |
| Review | Confirm quantities, ownership and specs; atomic confirmation |
| Conversation | Persistent job chat, saved-state questions, draft edit proposals with accept/reject |
| Live updates | SSE job snapshots and chat state; complete replies rather than token streaming |
| Sourcing | Grounded discovery, guarded seller fetches, explicit JSON-LD price/stock verification |
| Compatibility | Declared-spec A/B/X/unknown rules for four supported families |
| Costs | Explicit quote selection, parts subtotals, unknown tax/shipping |
| Revisions | Targeted seller refresh; post-report required-spec updates and reassessment |
| Design advice | Confirmed single-LED resistor calculation; contextual role questions |
| Recovery | Bounded HTTP retries, leases, checkpoint resume, tested resistor-selector fallback |
| Sourcing controls (v0.11) | Persisted pause intent, part-boundary acknowledgement, resume saved work; chat stays available |
| Storage | Firestore persistence and private per-job tokens |

## Agreed work still to implement

| Priority | Deliverable | Completion criteria / frontend impact |
| --- | --- | --- |
| 1 | End-to-end conversational UI integration | BOM beside chat; citation navigation; proposal diff and accept/reject; SSE reconnect; explicit confirmation; integration smoke test |
| 2 | User steering during sourcing | Pause/resume implemented in v0.11; reviewed edits to a paused sourcing plan and frontend controls remain |
| 3 | Agent-triggered search and report tools | Agent proposes scoped refresh/spec changes; user authorizes cost-bearing work; tool progress and results visible in chat; preserve limits and stale-edit checks |
| 4 | Broader seller-spec parsing | Read supported specification tables with field-level evidence; detect contradictions; unknown stays unknown; evaluate real sellers |
| 5 | Circuit context and more design rules | Establish resistor roles, topology and source-backed inputs; support additional roles only with validated calculations; attach suggestions to a specific physical component |
| 6 | Permanent rule repair workflow | Capture bounded failure cases; generate candidate patch in isolation; regression/property tests; versioned release and rollback. Current runtime only quarantines and falls back; no automatic patch authoring/deployment |
| 7 | Durable task dispatch | Move work out of API background tasks to a queue/worker; idempotent claims and bounded retries; recovery without an always-running API sweeper |
| 8 | Public launch controls | User authentication/authorization, durable quotas/rate limits, retention, operational alerts and access review. Shared integration key is temporary team access only |
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

Integrate the deployed v0.11 API including pause/resume, then add reviewed agent tools.
Develop seller parsing and circuit-context work against real labelled examples. Add queueing
and public-launch controls before opening paid job creation to general users. Rule repairs
must preserve failure evidence and earn promotion through regression checks.
