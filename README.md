Implementation: Python

# Schema Intelligence Assistant

Schema Intelligence Assistant is a standalone workflow for enterprise data
masking onboarding. It detects likely PII columns from schema metadata,
recommends masking functions, retrieves grounded masking documentation, and
generates a review-aware masking configuration.

## Architecture

```text
Schema JSON
   |
   v
+------------------+
| PiiDetector      |
| - name signals   |
| - sample checks  |
| - confidence     |
+------------------+
   |
   +----------------------------+
   |                            |
   v                            v
Detections                Review-required flags
   |                            |
   v                            |
+-------------------------+      |
| MaskingConfigGenerator  |<-----+
| - rules                 |
| - review queue          |
| - doc references        |
+-------------------------+
   |
   v
Masking Config JSON

User Question
   |
   v
+-------------------------+
| SchemaIntelligenceAgent |
| - route intent          |
| - call retrieval first  |
| - refuse out of scope   |
+-------------------------+
   |
   v
+-------------------------+
| Hybrid RAG              |
| TF-IDF + BM25 + RRF     |
| pii_category filtering  |
+-------------------------+
   |
   v
Grounded answer with citation
```

## Setup And Run

Preferred one-command setup:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Run the detector and generator tests:

```bash
./.venv/bin/python -m pytest -q pii-detector/tests masking-generator/tests
```

Run the Day 3 quality suite:

```bash
./.venv/bin/python -m pytest -q agent/tests/quality_tests.py
```

Generate the A/B baseline markdown:

```bash
./.venv/bin/python agent/tests/ab_comparison.py
```

Evaluate RAG Recall@3:

```bash
python3 -m rag.retrieve
```

## Design Decisions

- Chose Python over Spring AI because the task emphasizes rapid experimentation,
  test depth, and evaluation artifacts; Python keeps the detector, retrieval,
  and quality suite compact and easy to inspect.
- Used a deterministic detector instead of LLM-first classification because Day
  1 is recall- and QA-centric. That gives stable regression tests, zero per-row
  API cost, and explicit confidence routing.
- Kept the agent policy-driven rather than open-ended. The goal is reliable tool
  orchestration, not chatbot creativity, so documentation questions always go
  through retrieval before answering.
- Implemented hybrid retrieval with TF-IDF-style vector similarity, BM25, and
  Reciprocal Rank Fusion because the brief explicitly requires hybrid retrieval
  rather than pure semantic search.
- Routed low-confidence detections into a review queue instead of forcing
  automation. That reflects the risk asymmetry in masking workflows, where a
  false negative is more serious than extra review effort.

## What I Would Do Differently With More Time

- Add an optional LLM fallback for ambiguous columns behind a flag and measure
  whether it improves recall without destabilizing tests.
- Expand the golden set with more regional national IDs, multilingual aliases,
  and sparse-schema cases with missing sample values.
- Replace the simple answer synthesizer with a bounded LLM summarizer that still
  preserves grounding and source citation.
- Add a command-line entrypoint and example end-to-end run script for easier
  reviewer walkthroughs.
- Add CI automation that regenerates RAG evaluation results and the A/B baseline
  markdown on every change.

## Test Coverage Summary

Covered:

- detector behavior on direct PII, hard negatives, non-English aliases, and
  review-required edge cases
- golden-set recall regression and category mapping
- hybrid retrieval Recall@3 against a 10-query evaluation set
- masking configuration generation, documentation references, and integration
  with detector output
- agent grounding, out-of-scope refusal, schema-required prompting, detector
  regression, and masking-config completeness
- A/B baseline generation for future response-quality comparisons

Not covered:

- live external LLM integrations, because the current submission keeps the core
  workflow deterministic by default
- real database connectors and production execution, because the task is
  intentionally self-contained
- large-scale performance benchmarking, although the scalability write-up
  describes the production approach
