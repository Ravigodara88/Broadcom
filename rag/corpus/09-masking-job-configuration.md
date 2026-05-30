---
title: How To Configure and Run a Masking Job
pii_categories:
  - GENERAL
---

# How To Configure and Run a Masking Job

## Job Definition

A masking job typically includes a job name, source connection, target
connection, table selection, and a rule list mapping columns to masking
functions. High-confidence rules may be auto-configured, while ambiguous fields
should be routed to a review queue.

## Recommended Steps

1. Validate the schema profile and PII classification.
2. Confirm the masking function for each detected PII column.
3. Review low-confidence or ambiguous fields.
4. Run a dry-run preview against sample rows.
5. Execute the job and capture audit logs.

## Required Outputs

The final configuration should clearly show the table name, column name,
masking function, optional parameters, and whether manual approval was required.

## Operational Note

Never promote an auto-generated job directly to production without at least one
human sign-off for the review queue.
