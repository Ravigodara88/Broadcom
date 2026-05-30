---
title: PHONE_MASK and SSN_MASK Usage, Parameters, and Examples
pii_categories:
  - PHONE
  - SSN
---

# PHONE_MASK and SSN_MASK Usage, Parameters, and Examples

## PHONE_MASK

### Usage

Use `PHONE_MASK` for direct phone contact values such as `phone_number`,
`mobile_number`, `telefono`, or `ph_no`.

### Parameters

- `preserve_country_code`: optional boolean
- `masking_style`: `full`, `partial`, or `tokenized`
- `keep_formatting`: optional boolean to preserve punctuation

### Example

`+1 415-555-0199` could become `+1 415-***-****`.

## SSN_MASK

### Usage

Use `SSN_MASK` for United States social security numbers or fields explicitly
documented as `ssn` or `social_security_number`.

### Parameters

- `show_last4`: optional boolean
- `preserve_dashes`: optional boolean
- `fallback_token`: optional replacement for invalid input

### Example

`123-45-6789` could become `***-**-6789`.
