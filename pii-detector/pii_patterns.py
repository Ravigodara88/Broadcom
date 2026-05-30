"""PII pattern library and masking-function mappings.

Phase 1 captures the required taxonomy and exact category-to-mask mapping from
the candidate task. Matching logic will be added in Phase 2.
"""

from __future__ import annotations

PII_CATEGORY_TO_MASKING_FUNCTION = {
    "FULL_NAME": "NAME_RANDOMIZE",
    "EMAIL": "EMAIL_MASK",
    "PHONE": "PHONE_MASK",
    "SSN": "SSN_MASK",
    "CREDIT_CARD": "CREDIT_CARD_MASK",
    "ACCOUNT_NUMBER": "ACCOUNT_MASK",
    "DATE_OF_BIRTH": "DATE_SHIFT",
    "ADDRESS": "ADDRESS_RANDOMIZE",
    "IP_ADDRESS": "IP_MASK",
    "NATIONAL_ID": "NATIONAL_ID_MASK",
}


REQUIRED_PII_CATEGORIES = tuple(PII_CATEGORY_TO_MASKING_FUNCTION.keys())
