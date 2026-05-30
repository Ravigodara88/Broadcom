---
title: GDPR and CCPA Compliance in Data Masking Workflows
pii_categories:
  - GENERAL
---

# GDPR and CCPA Compliance in Data Masking Workflows

## GDPR Considerations

Under GDPR, masking supports data minimization, purpose limitation, and reduced
exposure in non-production use. Teams should document lawful purpose, access
controls, and the masking policy applied to direct identifiers such as name,
email, phone, national ID, and date of birth.

## CCPA Considerations

CCPA workflows should identify personal information categories, apply masking in
test and analytics environments, and retain an audit trail showing who approved
the transformation and when it was executed.

## Recommended Guardrails

- separate high-confidence automated rules from manual review items
- log every masking job run and approval event
- avoid exposing original values in previews or troubleshooting screens
- revalidate the policy when a new masking function is introduced

## Practical Outcome

Masking does not replace governance, but it materially lowers privacy risk and
helps prove that customer data is not broadly replicated in raw form.
