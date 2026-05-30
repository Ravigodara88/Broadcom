---
title: ADDRESS_RANDOMIZE, IP_MASK, and NATIONAL_ID_MASK Usage and Examples
pii_categories:
  - ADDRESS
  - IP_ADDRESS
  - NATIONAL_ID
---

# ADDRESS_RANDOMIZE, IP_MASK, and NATIONAL_ID_MASK Usage and Examples

## ADDRESS_RANDOMIZE

Use `ADDRESS_RANDOMIZE` for street, mailing, billing, or shipping addresses.
The function should generate realistic substitutes while preserving broad shape
such as city, state, or postal-code compatibility when required.

## IP_MASK

Use `IP_MASK` for `ip_address`, `client_ip`, `source_ip`, IPv4, and IPv6
fields. Preserve address family and, if needed, subnet prefix behavior for
network analytics without exposing the exact host.

## NATIONAL_ID_MASK

Use `NATIONAL_ID_MASK` for government-issued identifiers such as national ID,
passport number, Aadhaar, or national insurance number. These values should be
fully protected even when they are alphanumeric.

## Example Patterns

- `221B Baker Street` could become `410 Market Lane`
- `192.168.1.10` could become `192.168.1.200`
- `QQ123456C` could become `ZZ******7`
