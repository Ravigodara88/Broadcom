# Quality Criteria - Schema Intelligence Assistant (Day 1)

## 1) Detection Quality Targets

Given compliance risk asymmetry (false negatives are higher risk than false positives):

- Minimum Recall@PII (ship gate): `>= 0.85`
- Target Precision@PII (operational target): `>= 0.70`
- Maximum false-negative rate: `<= 0.15`

These thresholds prioritize catching sensitive columns while allowing manageable human review volume.

## 2) Confidence Routing Policy

- `confidence >= 0.85` -> auto-tag as PII and include masking recommendation
- `0.60 <= confidence < 0.85` -> `review_required = true`
- Deterministic routing rule: `confidence < 0.60` -> classify as non-PII unless strong conflicting pattern signals exist; if ambiguous, route to review

Hybrid fallback note:
- In hybrid mode, if blended rule+embedding confidence is low, an optional LLM fallback may still classify a column as PII.
- For LLM-classified PII, keep `review_required = true` whenever returned confidence is `< 0.85`.

Tie-break rule:
- If top-2 category scores differ by `< 0.10`, set `review_required = true` even when classified as PII.

## 3) Day-1 Labeled Test Data Plan

Dataset file:
- `pii-detector/tests/schema_test_cases.json`

Dataset size:
- `30` total labeled cases
- `15` PII + `15` non-PII

Per-case structure:
- `input`: `table_name`, `column_name`, `data_type`, `sample_values`, `nullable`
- `expected`: `is_pii`, `pii_category` (or `null` for non-PII)

Coverage requirement:
- Include all 10 required categories at least once:
  - `FULL_NAME`
  - `EMAIL`
  - `PHONE`
  - `SSN`
  - `CREDIT_CARD`
  - `ACCOUNT_NUMBER`
  - `DATE_OF_BIRTH`
  - `ADDRESS`
  - `IP_ADDRESS`
  - `NATIONAL_ID`

Required tricky/edge cases:
- Obfuscated names: e.g., `cust_fn`, `ph_no`, `nat_id`
- Non-English or localized names: e.g., `correo_electronico`, `apellido`, `fecha_nacimiento`
- Misleading identifiers: `transaction_id`, `session_id`, `order_ref` (non-PII)
- Numeric ambiguity: SSN vs account number vs national ID
- Partial/masked values and null-like strings
- Unusual naming variants: e.g., `national_insurance_number`

## 4) Category-to-Masking Mapping (Must Be Exact)

- `FULL_NAME` -> `NAME_RANDOMIZE`
- `EMAIL` -> `EMAIL_MASK`
- `PHONE` -> `PHONE_MASK`
- `SSN` -> `SSN_MASK`
- `CREDIT_CARD` -> `CREDIT_CARD_MASK`
- `ACCOUNT_NUMBER` -> `ACCOUNT_MASK`
- `DATE_OF_BIRTH` -> `DATE_SHIFT`
- `ADDRESS` -> `ADDRESS_RANDOMIZE`
- `IP_ADDRESS` -> `IP_MASK`
- `NATIONAL_ID` -> `NATIONAL_ID_MASK`

Any mismatch between detected category and recommended masking function is a test failure.

## 5) Day-1 Definition of Done

Day 1 is shippable only if all are true:

1. Detector unit tests pass.
2. Golden-set Recall@PII is `>= 0.85`.
3. Mapping correctness is 100% for detected PII categories.
4. Review queue logic behaves as defined by confidence policy.
5. Results are documented in `pii-detector/tests/eval_report.md`.

## 6) Execution Constraints (Chosen for Reliability)

- Implementation language: Python 3.10+
- Test framework: `pytest`
- Primary detector strategy: hybrid heuristic-first classifier with optional LLM fallback for low blended-confidence cases
- Unit tests must be deterministic (no live API dependency)
- Live-model checks, if any, run only behind an explicit flag (e.g., `RUN_LIVE_TESTS=1`)
