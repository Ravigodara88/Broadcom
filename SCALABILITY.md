# Scalability

For a schema with 5,000 columns, the detection path should stay under 30
seconds by keeping the classifier local, vector-free, and batch-oriented. This
submission already uses deterministic scoring over column name, table context,
sample values, and data type, so throughput scales linearly and parallelization
is straightforward. In production, I would process columns in batches, cache
tokenized pattern features, and only send ambiguous cases to an optional
secondary review model. The practical target is at least ~167 columns/second
(5,000 columns / 30 seconds), with headroom from multi-core batch execution.

RAG freshness should be handled as a content pipeline, not a manual task. When
the product team adds or changes a masking function, the documentation source
should trigger an ingestion job that re-chunks the affected docs, refreshes
metadata such as `pii_category`, reruns Recall@3 evaluation, and only publishes
the updated index if the retrieval quality gate still passes.

At 500 customers running schema analysis weekly, the core detector cost is
effectively zero in LLM spend because it is deterministic. If an optional LLM
fallback were enabled for, say, 5% of ambiguous columns and a typical weekly
run sent 250 columns to a small model at low token volume, the monthly cost
would still be manageable. A concrete estimate is roughly $150-$300/month at
this scale (about 0.5M fallback calls/month with very small prompt/response
payloads and aggressive caching). The first optimization should be to reduce LLM
use through better rules, caching, and review-queue thresholds rather than to
scale model traffic blindly.

In production I would alert on recall proxy drift, review-queue growth,
retrieval Recall@3 degradation, and config-generation coverage. Example
thresholds: review queue above 25% of detected PII columns, Recall@3 below
0.70, detector golden-set recall below 0.85 in CI, or a sudden drop in
auto-configured high-confidence columns for a stable customer schema. Those
signals would tell us whether quality, freshness, or ambiguity has started to
drift.
