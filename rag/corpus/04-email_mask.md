---
title: EMAIL_MASK Usage, Parameters, and Examples
pii_categories:
  - EMAIL
---

# EMAIL_MASK Usage, Parameters, and Examples

## Usage

`EMAIL_MASK` protects email addresses while preserving enough structure for
testing and validation. Use it for fields such as `email`, `email_address`, or
`correo_electronico`.

## Parameters

- `preserve_domain`: optional boolean to keep the original domain
- `replacement_domain`: optional domain used when domains should be normalized
- `keep_alias_length`: optional boolean to preserve the approximate local-part length

## Behavior

The function masks the local part and can either keep the domain or replace it
with a safe corporate test domain. Preserve the `@` separator and valid email
shape so downstream format validators continue to work.

## Example

`alex.chen@acme.com` could become `a***n@test.example` when preserving shape but
not identity.
