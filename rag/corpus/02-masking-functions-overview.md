---
title: Overview of Masking Functions and When to Use Each
pii_categories:
  - GENERAL
---

# Overview of Masking Functions and When to Use Each

## Direct Identifier Functions

Use `NAME_RANDOMIZE` for full names, `EMAIL_MASK` for email addresses,
`PHONE_MASK` for phone numbers, `SSN_MASK` for social security numbers, and
`NATIONAL_ID_MASK` for government-issued identity numbers. These functions are
intended for columns where the value itself is sensitive.

## Financial Functions

Use `CREDIT_CARD_MASK` for payment card numbers and `ACCOUNT_MASK` for bank or
customer account numbers. Both should preserve basic formatting when needed,
but they must not expose the original sequence.

## Location And Network Functions

Use `ADDRESS_RANDOMIZE` for street or mailing addresses and `IP_MASK` for IPv4
or IPv6 addresses. Address masking should keep locality realism where
possible. IP masking should preserve address family and optionally subnet
shape.

## Temporal Functions

Use `DATE_SHIFT` when the data must remain analytically useful but the exact
date must be hidden. Date shifting is often preferred for date of birth when
age banding or sequence analysis still matters.

## Selection Rule

Choose the function that matches the semantic category of the source column, not
just its format. A nine-digit numeric field could be an SSN, account number, or
national identifier, so schema context must be reviewed before finalizing the
masking rule.
