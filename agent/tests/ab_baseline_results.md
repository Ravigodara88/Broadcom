# A/B Baseline Results

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

- `current_submission` is the preferred baseline because it uses category-aware retrieval and represents the intended shipped behavior.
- `control_no_category_filter` is an ablation baseline; future prompt or model revisions should outperform or at least match `current_submission` on this rubric.
