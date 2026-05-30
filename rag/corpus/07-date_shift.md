---
title: DATE_SHIFT Usage, Parameters, and Examples
pii_categories:
  - DATE_OF_BIRTH
---

# DATE_SHIFT Usage, Parameters, and Examples

## Usage

`DATE_SHIFT` offsets a date by a controlled amount instead of replacing it with
an unrelated value. Use it when analysts still need seasonal patterns, age
bands, or event ordering. It is commonly applied to `date_of_birth`,
`birth_date`, and other regulated date fields.

## Parameters

- `shift_days_min`: minimum day offset
- `shift_days_max`: maximum day offset
- `preserve_month`: optional boolean to keep the calendar month fixed
- `consistent_per_subject`: optional boolean to apply the same offset across a person record

## Behavior

The function preserves data type and date format while shifting the underlying
value. Teams often use a narrow offset for event timelines and a broader offset
for date of birth.

## Example

If the shift range is plus or minus 30 days, `1989-04-12` might become
`1989-05-01`. The exact date is hidden, but the value remains a valid date in
the same general period.
