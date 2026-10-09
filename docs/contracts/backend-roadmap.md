# Backend delivery roadmap

Reviewed against backend **v0.29.0**, 9 October 2026. The [API contract](README.md)
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
| Code | [Code patches and compile checks](code-adapt.md) (tiers 1–3) |
| Operations | [Firestore TTL, queue alerts, scaling and compile-runner runbook](../../backend/infra/README.md) |

Routing merged through PRs #46–#48. Free seller search continues after the paid budget
is exhausted. The [validation report](../../backend/infra/routing-evaluation.md)
records automated probe results and the remaining human relevance-review limitation.

## Remaining work and proposals

- **Code adaptation:** tiers 1–2 shipped in v0.28.0 and tier 3 (compile checks in
  isolated Cloud Run jobs) in v0.29.0 ([contract](code-adapt.md), [plan](../plans/code-adapt/PLAN.md));
  the frontend UI is not built. Hardware testing and PlatformIO builds are out of scope.
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
