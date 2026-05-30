---
title: NAME_RANDOMIZE Usage, Parameters, and Examples
pii_categories:
  - FULL_NAME
---

# NAME_RANDOMIZE Usage, Parameters, and Examples

## Usage

`NAME_RANDOMIZE` replaces a personal name with a realistic substitute from an
approved name dictionary. Use it for columns such as `full_name`,
`customer_name`, `first_name`, or `last_name`.

## Parameters

- `locale`: optional locale code used to bias generated names
- `preserve_initial`: optional boolean to keep the first initial
- `allow_nulls`: optional boolean to leave null values unchanged

## Behavior

The function should preserve data type and length constraints where practical.
If the source system stores first and last name separately, each column should
be masked consistently with its semantic role.

## Example

Input `Aarav Mehta` might become `Karan Shah`. Input `Sophia Turner` might
become `Elena Brooks`.
