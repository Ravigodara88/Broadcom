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
from pii_patterns import REQUIRED_PII_CATEGORIES


detector = PiiDetector()
TEST_CASES_PATH = Path(__file__).with_name("schema_test_cases.json")


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


def test_non_english_email_column_detected() -> None:
    result = detector.detect(
        {
            "table_name": "CLIENTES",
            "column_name": "correo_electronico",
            "data_type": "VARCHAR(255)",
            "sample_values": ["maria.garcia@example.es"],
            "nullable": True,
        }
    )
    assert result["is_pii"] is True
    assert result["pii_category"] == "EMAIL"


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


def test_low_confidence_sets_review_required() -> None:
    result = detector.detect(
        {
            "table_name": "CONTACTS",
            "column_name": "secondary_phone",
            "data_type": "VARCHAR(20)",
            "sample_values": ["unknown", "null"],
            "nullable": True,
        }
    )
    assert result["is_pii"] is True
    assert result["review_required"] is True
    assert 0.60 <= result["confidence"] < 0.85


def test_schema_test_cases_file_is_valid_json() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    assert isinstance(cases, list)


def test_schema_test_cases_have_expected_balance_and_coverage() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    assert len(cases) == 30

    pii_cases = [case for case in cases if case["expected"]["is_pii"]]
    non_pii_cases = [case for case in cases if not case["expected"]["is_pii"]]
    categories = {case["expected"]["pii_category"] for case in pii_cases}

    assert len(pii_cases) == 15
    assert len(non_pii_cases) == 15
    assert set(REQUIRED_PII_CATEGORIES).issubset(categories)


def test_recall_on_golden_set() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    pii_cases = [case for case in cases if case["expected"]["is_pii"]]
    detected = sum(1 for case in pii_cases if detector.detect(case["input"])["is_pii"])
    recall = detected / len(pii_cases)
    assert recall >= 0.85, f"Recall {recall:.2f} below threshold"


def test_expected_categories_match_on_golden_set() -> None:
    cases = json.loads(TEST_CASES_PATH.read_text())
    mismatches = []
    for case in cases:
        expected = case["expected"]
        result = detector.detect(case["input"])
        if expected["is_pii"] != result["is_pii"]:
            mismatches.append((case["input"]["column_name"], expected, result))
            continue
        if expected["is_pii"] and expected["pii_category"] != result["pii_category"]:
            mismatches.append((case["input"]["column_name"], expected, result))
    assert not mismatches, f"Unexpected golden-set mismatches: {mismatches}"
