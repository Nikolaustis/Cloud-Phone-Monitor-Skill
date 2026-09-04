# AI Evaluation Strategy

Evaluation starts before the production LLM is selected.

## Layer A — routing

Does the question select the correct deterministic capability?

## Layer B — data correctness

Numeric exact match, entity resolution, duration/filter accuracy and What-if calculations.

## Layer C — grounding

Evidence coverage, evidence precision and unsupported-claim rate.

## Layer D — answer behavior

Correct abstention, relevance, completeness, P50/P95 latency and cost.

The checked-in `evals/demo_report.json` measures only the synthetic deterministic tool layer. Production LLM metrics require a separate safe real-data benchmark and recorded provider/model + data revision.
