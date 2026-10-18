# AI buyer (v0.30.0–v0.30.3)

Hard parts are decided the way a maker buying parts in India would: from the whole project
(what it builds, its power supply, every other part and this part's role), not from keyword
rules. Implemented in `backend/src/bharat_sourcer/sourcing/buyer.py`; enabled by default
(`BS_BUYER_ENABLED`, `BS_BUYER_SEARCH_ROUNDS`, default 2).

## Unstated values

When a part's value is not in the source (an unmarked resistor), the buyer works one out
from the circuit before searching: one standard value, the reasoning and a confidence
(`high`, `medium`, `low`), plus store searches for it. The line's `buyable_spec` gets the
value as an `equals` param whose `reason` starts "Decided by the AI buyer from the
circuit", and `needs_value` becomes false, so normal selection rules apply. The user can
change the value through the spec (`POST …/specs`) and refresh.

## Choosing what to buy

During normal sourcing the buyer reviews candidates even when the spec judge accepted
an exact listing. It evaluates the component's function against the project description,
interfaces, power, other parts, requirements and source evidence. The named model is a
starting point; explicit must-use constraints remain binding. Firmware, library, pinout
and wiring changes can justify a substitute when supported by listing evidence.

Before choosing a purchase, the buyer explicitly plans functional alternative searches,
even when an exact listing exists. It may abstain when substitutions are forbidden,
the function cannot be inferred, or there is no defensible new query; the explanation
is returned as `exploration_reason`. One exploration round consumes one of the existing
`BS_BUYER_SEARCH_ROUNDS` (default two), with up to three unique seller queries and one
query to enabled external providers. A zero round limit disables exploration.

Purchase selection sees up to 16 candidates. Independently, every fetched candidate is
reviewed in batches of six, including partial and rejected listings, without that
16-candidate cap. Each receives `usable_directly`, `usable_with_changes`, `incompatible`,
or `insufficient_evidence`, plus its reason, quotes, missing facts and required changes.
Usable verdicts update offer matching and compatibility (grade A or B). Explicit
negative/uncertain verdicts become mismatch/partial and cannot be automatically selected.
All supplied supporting quotes must be found in the listing; positive verdicts cannot
have critical missing facts, and changes-required verdicts must have a concrete plan.
Accessory guardrails remain enforced. Unresolved variant groups require more evidence.

Missing/duplicate verdict IDs, model failure or exhausted model budget produce an
insufficient-evidence assessment without destroying prior offer evidence. An individual
assessment can therefore say the functional review is unavailable while an earlier
strict match remains accepted. Fabricated IDs cannot introduce listings. Every model
call uses the existing paid budget. This adds a planning call and approximately one
assessment call per six fetched candidates, in addition to purchase selection.

Known-URL refresh and follow-up grounded attempts skip this additional review. The
original buying specification is retained. Provider failures preserve existing offers.

A pick sets the offer's `match.method` to `llm_buyer`, with:

| fit | match.status | Selection |
| --- | --- | --- |
| `exact` | `exact` | automatic when quotes verify |
| `kit` | `compatible` | automatic when quotes verify |
| `substitute` | `compatible` | grade B: `compatibility.changes` lists what the maker must do; acknowledge before ordering |

Claims keep only quotes found verbatim in the listing; a pick with no verified quote is
`partial` and is not selected automatically. The buyer can only pick a listing it was shown;
prices and stock always come from the seller's page.

## `report.lines[].buyer` (`BuyerDecision`)

| Field | Meaning |
| --- | --- |
| `value`, `value_reason`, `value_confidence` | The decided value, e.g. `resistance: 1k`, and why |
| `fit`, `offer_url`, `reason`, `changes` | The listing it chose and why; changes for a substitute |
| `searched` | Extra store searches it ran |
| `exploration_reason` | Why functional alternatives were searched or exploration abstained |
| `assessments` | Per-listing URL, verdict, reason, changes, missing facts, verified quotes and model |
| `model` | The model that decided |

Stages: `buyer_value` (value decided), `buyer` (a choice call), `buyer_search` (an extra
search). Calls count against the job's AI budget (site `buyer`).

Show these as AI suggestions for review, never as verified facts.
