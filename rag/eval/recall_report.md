# RAG Recall Report

Initial evaluation completed against `masking_queries.json`.

## Current Metrics

- Retrieval strategy: TF-IDF vector similarity + BM25 + Reciprocal Rank Fusion
- Filter behavior: category-specific chunks are boosted when `pii_category_filter` is supplied
- Recall@3: `1.00` (`10/10`)

## Query Set Notes

- Total evaluation queries: `10`
- Category-filtered queries: `6`
- General operational and compliance queries: `4`

## Observations

- Function-specific questions such as `EMAIL_MASK`, `DATE_SHIFT`, and
  `ACCOUNT_MASK` are retrieved reliably when the category filter is present.
- General questions about GDPR, job configuration, and performance tuning rank
  the expected documents without requiring a filter.
- General overview documents still appear in some filtered result sets, but the
  exact category boost ensures the expected source stays inside the top-3 list.

## Residual Risks

- Queries that use unfamiliar synonyms not represented in the corpus may fall
  back to general overview documents.
- Multi-function documents can return multiple sections from the same file,
  which is acceptable for grounding but may reduce diversity in later agent
  prompts.
