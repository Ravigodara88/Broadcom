---
title: CREDIT_CARD_MASK and ACCOUNT_MASK Usage, Parameters, and Examples
pii_categories:
  - CREDIT_CARD
  - ACCOUNT_NUMBER
---

# CREDIT_CARD_MASK and ACCOUNT_MASK Usage, Parameters, and Examples

## CREDIT_CARD_MASK

### Usage

Use `CREDIT_CARD_MASK` for payment card primary account numbers. Typical source
columns include `credit_card_number`, `card_number`, or `payment_card`.

### Parameters

- `show_last4`: optional boolean
- `preserve_bin`: optional boolean for first six digits in controlled flows
- `keep_separators`: optional boolean to preserve spaces or dashes

### Example

`4111 1111 1111 1111` could become `411111******1111`.

## ACCOUNT_MASK

### Usage

Use `ACCOUNT_MASK` for bank account numbers, customer account numbers, and IBAN
style identifiers where the value is not a payment card.

### Parameters

- `show_last4`: optional boolean
- `preserve_prefix`: optional boolean for account family prefixes
- `normalize_format`: optional boolean to emit a standard masked pattern

### Example

`ACC-9876543` could become `ACC-***6543`.
