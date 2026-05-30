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

from detector import PiiDetector, HybridPiiDetector
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


# ---------------------------------------------------------------------------
# HybridPiiDetector tests
# ---------------------------------------------------------------------------

_REQUIRED_OUTPUT_KEYS = {
    "is_pii",
    "confidence",
    "pii_category",
    "recommended_masking_function",
    "review_required",
    "reasoning",
}


def test_hybrid_output_contract_clear_pii() -> None:
    """HybridPiiDetector must return all JD-required keys for a clear PII column."""
    hybrid = HybridPiiDetector()
    result = hybrid.detect(
        {
            "table_name": "CUSTOMERS",
            "column_name": "email_address",
            "data_type": "VARCHAR(255)",
            "sample_values": ["alice@example.com", "bob@corp.org"],
            "description": "Customer email address",
        }
    )
    missing = _REQUIRED_OUTPUT_KEYS - result.keys()
    assert not missing, f"Output missing required keys: {missing}"
    assert result["is_pii"] is True
    assert result["pii_category"] == "EMAIL"
    assert result["recommended_masking_function"] is not None
    assert "masking_function" not in result, "Old key 'masking_function' must not appear"


def test_hybrid_output_contract_non_pii() -> None:
    """HybridPiiDetector must return all JD-required keys for a non-PII column."""
    hybrid = HybridPiiDetector()
    result = hybrid.detect(
        {
            "table_name": "PRODUCTS",
            "column_name": "product_id",
            "data_type": "INTEGER",
            "sample_values": ["1001", "1002", "1003"],
            "description": "Internal product identifier",
        }
    )
    missing = _REQUIRED_OUTPUT_KEYS - result.keys()
    assert not missing, f"Output missing required keys: {missing}"
    assert result["is_pii"] is False
    assert "masking_function" not in result, "Old key 'masking_function' must not appear"


def test_hybrid_llm_path_uses_correct_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM tier result must use 'recommended_masking_function', not 'masking_function'."""
    import detector as det_module

    # Force LLM path by stubbing the lower tiers
    fake_llm_response = {
        "table_name": "T",
        "column_name": "ssn",
        "is_pii": True,
        "pii_category": "SSN",
        "confidence": 0.95,
        "recommended_masking_function": "mask_ssn",
        "review_required": False,
        "reasoning": "LLM says SSN",
        "detection_method": "llm",
    }

    hybrid = HybridPiiDetector()
    monkeypatch.setattr(hybrid, "_llm_classify", lambda col, txt: fake_llm_response)
    # Lower rule confidence so Tier 1 fast-path is not taken
    monkeypatch.setattr(det_module.PiiDetector, "detect", lambda self, col: {
        "table_name": col.get("table_name", ""),
        "column_name": col.get("column_name", ""),
        "is_pii": False,
        "pii_category": None,
        "confidence": 0.1,
        "recommended_masking_function": None,
        "review_required": True,
        "reasoning": "low rule confidence",
    })

    result = hybrid.detect(
        {
            "table_name": "T",
            "column_name": "ssn",
            "data_type": "CHAR(11)",
            "sample_values": ["078-05-1120"],
            "description": "Social security number",
        }
    )
    assert "recommended_masking_function" in result
    assert "masking_function" not in result


def test_hybrid_build_ai_result_includes_table_column() -> None:
    """_build_ai_result must echo table_name and column_name from the input column."""
    hybrid = HybridPiiDetector()
    result = hybrid._build_ai_result(
        column={"table_name": "HR", "column_name": "dob"},
        category="DATE_OF_BIRTH",
        confidence=0.90,
        reasoning="test",
    )
    assert result["table_name"] == "HR"
    assert result["column_name"] == "dob"
    assert "recommended_masking_function" in result
    assert "masking_function" not in result
