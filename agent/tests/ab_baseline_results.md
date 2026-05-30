# A/B Baseline Results

Rubric: each query is scored from 0 to 5 on relevance, grounding, and scope discipline.

| Variant | Query | Score | Notes |
|---|---|---:|---|
| category_aware | What does DATE_SHIFT do and what parameters does it accept? | 5 | Grounded and on-policy |
| broad_retrieval | What does DATE_SHIFT do and what parameters does it accept? | 5 | Grounded and on-policy |
| category_aware | What parameters does EMAIL_MASK accept? | 5 | Grounded and on-policy |
| broad_retrieval | What parameters does EMAIL_MASK accept? | 5 | Grounded and on-policy |
| category_aware | How do I comply with GDPR when masking customer data? | 5 | Grounded and on-policy |
| broad_retrieval | How do I comply with GDPR when masking customer data? | 5 | Grounded and on-policy |
| category_aware | What is the weather in Hyderabad? | 5 | Grounded and on-policy |
| broad_retrieval | What is the weather in Hyderabad? | 5 | Grounded and on-policy |
| category_aware | Mask this column | 5 | Grounded and on-policy |
| broad_retrieval | Mask this column | 5 | Grounded and on-policy |

## Totals

| Variant | Total Score |
|---|---:|
| category_aware | 25 |
| broad_retrieval | 25 |

## Interpretation

- `category_aware` is the preferred baseline because it applies category filtering before retrieval.
- `broad_retrieval` provides a weaker comparison point for future prompt or model revisions.
