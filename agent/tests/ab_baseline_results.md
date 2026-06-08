# A/B Baseline Results

Mode: `fallback_ablation`

No live multi-model configuration detected, so the artifact falls back to comparing the shipped submission against a retrieval-control variant. Set AGENT_AB_MODELS to two or more model names and provide LLM credentials to run a true model comparison.

Rubric: each query is scored from 0 to 5 using three dimensions: relevance (0-2), grounding (0-2), and policy discipline (0-1 or scenario-specific guardrail points).

| Variant | Query | Relevance | Grounding | Policy | Total | Notes |
|---|---|---:|---:|---:|---:|---|
| current_submission | What does DATE_SHIFT do and what parameters does it accept? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| control_no_category_filter | What does DATE_SHIFT do and what parameters does it accept? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| current_submission | What parameters does EMAIL_MASK accept? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| control_no_category_filter | What parameters does EMAIL_MASK accept? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| current_submission | How do I comply with GDPR when masking customer data? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| control_no_category_filter | How do I comply with GDPR when masking customer data? | 2 | 2 | 1 | 5 | Grounded and on-policy |
| current_submission | What is the weather in Hyderabad? | 0 | 2 | 3 | 5 | Grounded and on-policy |
| control_no_category_filter | What is the weather in Hyderabad? | 0 | 2 | 3 | 5 | Grounded and on-policy |
| current_submission | Mask this column | 2 | 1 | 2 | 5 | Grounded and on-policy |
| control_no_category_filter | Mask this column | 2 | 1 | 2 | 5 | Grounded and on-policy |

## Totals

| Variant | Total Score |
|---|---:|
| current_submission | 25 |
| control_no_category_filter | 25 |

## Interpretation

- Higher totals indicate better grounded behavior on the fixed baseline prompts.
- In `model_comparison` mode, future model or model-version changes should be compared against the current best-scoring model variant.
- In `fallback_ablation` mode, the report remains useful as a control baseline, but it is not yet a true multi-model comparison artifact.
