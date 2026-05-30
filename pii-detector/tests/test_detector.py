"""Detector tests for Day 1.

These tests start as a scaffold in Phase 1. The class and golden set are added
early so Phase 2 can focus on behavior rather than structure.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector import PiiDetector


detector = PiiDetector()
TEST_CASES_PATH = Path(__file__).with_name("schema_test_cases.json")


@pytest.mark.skip(reason="Detector behavior will be implemented in Phase 2.")
def test_email_column_detected() -> None:
    result = detector.detect(
        {
            "table_name": "USERS",
            "column_name": "email_address",
            "data_type": "VARCHAR(255)",
            "sample_values": ["user@example.com"],
            "nullable": True,
        }
    )
    assert result["is_pii"] is True
    assert result["pii_category"] == "EMAIL"
    assert result["recommended_masking_function"] == "EMAIL_MASK"


@pytest.mark.skip(reason="Detector behavior will be implemented in Phase 2.")
def test_non_pii_column_not_flagged() -> None:
    result = detector.detect(
        {
            "table_name": "ORDERS",
            "column_name": "transaction_id",
            "data_type": "BIGINT",
            "sample_values": ["100001", "100002"],
            "nullable": False,
        }
    )
    assert result["is_pii"] is False


@pytest.mark.skip(reason="Detector behavior will be implemented in Phase 2.")
def test_low_confidence_sets_review_required() -> None:
    result = detector.detect(
        {
            "table_name": "CONTRACTS",
            "column_name": "ref_code",
            "data_type": "VARCHAR(20)",
            "sample_values": ["C-2024-001"],
            "nullable": True,
        }
    )
    if result["confidence"] < 0.80:
        assert result["review_required"] is True


def test_schema_test_cases_file_is_valid_json() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    assert isinstance(cases, list)


@pytest.mark.skip(reason="Golden-set recall evaluation will be implemented in Phase 2.")
def test_recall_on_golden_set() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    pii_cases = [case for case in cases if case["expected"]["is_pii"]]
    detected = sum(1 for case in pii_cases if detector.detect(case["input"])["is_pii"])
    recall = detected / len(pii_cases)
    assert recall >= 0.85, f"Recall {recall:.2f} below threshold"
