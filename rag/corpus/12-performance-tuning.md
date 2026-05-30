---
title: Masking Performance Tuning for Large Tables
pii_categories:
  - GENERAL
---

# Masking Performance Tuning for Large Tables

## Throughput Strategy

For large tables, separate discovery from execution. Profile the schema once,
cache the masking plan, and then run the masking job in partitioned batches.
Avoid repeated live lookups for every row during transformation.

## Common Tuning Levers

- batch rows by table partition or primary-key range
- parallelize independent tables
- precompile masking rules before execution
- keep deterministic tokenization and formatting logic in-memory
- use preview sampling only on a subset of rows

## Operational Recommendation

If a customer schema contains thousands of columns, front-load column
classification and review before scanning the full dataset. Most time savings
come from avoiding repeated manual rule design rather than from row-level
micro-optimization alone.
