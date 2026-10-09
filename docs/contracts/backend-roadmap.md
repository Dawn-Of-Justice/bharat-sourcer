# Backend delivery roadmap

Reviewed against backend **v0.27.0**, 9 October 2026. The [API contract](README.md)
and [backend README](../../backend/README.md) describe implemented behavior.
Architecture documents describe the broader target.

## Delivered

| Area | Implemented contract |
| --- | --- |
| Intake | [Multiple sources and code evidence](multi-source-intake.md), [project context](project-understanding.md) |
| Conversation | [Chat actions](chat-actions.md), [pause/resume](pause-resume.md), [durable dispatch](queued-dispatch.md) |
| Sourcing | [Seller routing](seller-search.md), [spec matching](part-matching.md), [research](part-research.md), [seller trust](seller-trust.md) |
| Decisions | [Compatibility grades](compatibility-rules.md), [recommendations](recommendations.md), [costing](costing.md), [AI budgets](cost-controls.md) |
| Access | [Account/guest authorization and deletion](authentication.md), [PDF/HTML export, sharing and copying](export-and-share.md) |
| Location | [Country settings](countries.md), [nearby markets by city](nearby-markets.md) |
| Operations | [Firestore TTL, queue alerts and scaling runbook](../../backend/infra/README.md) |

Routing merged through PRs #46–#48. Free seller search continues after the paid budget
is exhausted. The [validation report](../../backend/infra/routing-evaluation.md)
records automated probe results and the remaining human relevance-review limitation.

## Remaining work and proposals

- **Code adaptation:** [draft plan](../plans/code-adapt/PLAN.md), not implemented or
  approved. The routing prerequisite is complete; owner decisions remain open.
- **Evaluation:** curate real labelled extraction examples and manually review seller
  relevance before claiming accuracy. The [gold set](evaluation-gold-set.md) is a draft.
- **Circuit context:** extend role-specific design rules only with supported inputs
  and validated calculations. Compatibility does not establish whole-project safety.
- **Conversation:** token-level answer streaming and reviewed edits to paused sourcing
  plans remain follow-ups; current SSE sends persisted snapshots and complete replies.
- **Infrastructure and broader features:** see the dated [proposal register](../../roadmap.md).

Check client integration against the current frontend and [quickstart](frontend-quickstart.md).
Obsolete release handoffs have been removed. There is no checkout, automatic purchase,
or verified final delivered total.

## Proposed, awaiting owner approval: code-adapt tier 3 compile runner

Compile curated/AI code patches with `arduino-cli` in an isolated Cloud Run **Job** (pinned
cores, no secrets, egress limited to GitHub and the Arduino index, compile only, never
upload), writing results to an inbox the API processes idempotently; at most two
compiler-error repair rounds. New infrastructure (job, images, service account, egress
policy), so it is not built. Details: `docs/plans/code-adapt/PLAN.md` §6. Tiers 1–2 shipped
in v0.28.0 with `check: not_checked`.
