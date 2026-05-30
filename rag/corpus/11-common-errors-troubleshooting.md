---
title: Common Masking Errors and Troubleshooting
pii_categories:
  - GENERAL
---

# Common Masking Errors and Troubleshooting

## Frequent Errors

Common failures include choosing the wrong masking function, preserving too much
of the original identifier, breaking downstream validation rules, or masking a
reference column that should have been left untouched.

## Troubleshooting Flow

If a masking job fails, first confirm that the column category is correct. A
nine-digit field may have been misclassified as SSN when it is really an
account number or national identifier. Next, inspect parameter choices such as
`show_last4`, date shift range, and formatting preservation.

## Retrieval-Friendly Hints

Questions about why email addresses still look valid usually map to
`EMAIL_MASK`. Questions about maintaining date format after de-identification
usually map to `DATE_SHIFT`. Questions about compliance justification usually
map to the GDPR and CCPA policy guidance.

## Safe Recovery

When in doubt, move the column into the review queue, rerun a preview, and log
the reason for the override.
