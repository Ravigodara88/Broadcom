# Future Enhancements Roadmap

This document lists high-value enhancements that are intentionally out of scope for the current submission, but recommended for the next iterations.

## Prioritized Backlog

| Priority | Enhancement | Why It Matters | Success Signal |
|---|---|---|---|
| P0 | CI pipeline for quality gates | Prevents regressions in detector, agent behavior, and retrieval quality | All PRs run unit tests + Recall@3 gate before merge |
| P0 | Better out-of-scope intent classifier | Reduces accidental in-domain answers for unrelated prompts | Out-of-scope precision > 95% on a curated prompt set |
| P0 | Model warm-up utility command | Improves first-run reliability in restricted/offline environments | Zero startup failures due to missing embedding model cache |
| P1 | Active learning from review queue | Improves PII recall/precision using analyst feedback loops | Recall improves over baseline while review volume decreases |
| P1 | Optional LLM answer synthesizer with strict citations | Produces cleaner explanations while preserving grounding | User-rated answer clarity improves with citation compliance at 100% |
| P1 | Reranker weight tuning + ablation harness | Calibrates fusion vs keyword weighting for different query types | Best weight profile selected from reproducible benchmark runs |
| P2 | Database connectors (Snowflake/Postgres/MySQL) | Enables direct schema ingestion from customer systems | Time from connection to first draft config is reduced |
| P2 | Multi-tenant service mode with auth and quotas | Supports production deployment across multiple customers | Stable latency/SLO under concurrent workloads |
| P2 | Observability dashboard for drift and quality | Enables proactive operations and issue triage | Alert MTTR and false-alarm rate improve month over month |

## Delivery Plan

1. Ship P0 items first to harden reliability and release safety.
2. Implement P1 items to improve model quality and end-user response quality.
3. Build P2 items for production scale, tenancy, and operations.

## Notes

- Current project scope remains deterministic-first and test-first.
- Any LLM expansion should remain behind flags and quality gates.
- Every new feature should include measurable acceptance criteria before release.
