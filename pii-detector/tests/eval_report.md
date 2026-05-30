# PII Detector Evaluation Report

Initial evaluation completed against `schema_test_cases.json`.

## Current Metrics

- Recall@PII: `1.00` (`15/15`)
- Precision@PII: `1.00` (`15/15`)
- False-negative count: `0`
- False-positive count: `0`
- Review-required behavior: covered by unit tests for low-confidence named columns
- Category mismatches: `0`

## Coverage Notes

- Golden set size: `30`
- Balance: `15` PII and `15` non-PII
- Required category coverage: all `10` required PII categories are present
- Tricky cases included:
  - obfuscated names such as `ph_no` and `cust_acct_no`
  - non-English names such as `correo_electronico`, `fecha_nacimiento`, and `apellido`
  - misleading non-PII names such as `email_opt_in`, `dob_verified`, `account_status`, and `customer_name_score`

## Current Failure Analysis

No golden-set failures on the initial deterministic rule set.

Residual risks remain outside this synthetic set:

- unusual organization-specific abbreviations not represented in the dataset
- identifier collisions where sample values are missing or heavily masked
- partial addresses or single-token names with weak context
- region-specific national identifiers not yet represented in the rules
