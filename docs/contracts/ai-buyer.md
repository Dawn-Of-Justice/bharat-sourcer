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

The buyer sees up to 16 fetched candidates, including rejected ones, and either picks
one or requests functional alternative searches. At most `BS_BUYER_SEARCH_ROUNDS`
extra rounds run, each with up to three seller queries and one query to enabled external
providers. New listings pass through the judge and then return to the buyer even if the
judge accepts them. Newly fetched alternatives take priority when the candidate cap is
exceeded. Known-URL refresh and follow-up grounded attempts skip this additional review.
The original buying specification is retained. Provider failures preserve existing
offers; an unsupported buyer pick cannot downgrade an accepted offer for the same URL.

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
| `model` | The model that decided |

Stages: `buyer_value` (value decided), `buyer` (a choice call), `buyer_search` (an extra
search). Calls count against the job's AI budget (site `buyer`).

Show these as AI suggestions for review, never as verified facts.
