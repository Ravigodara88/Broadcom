"""Integration tests between the detector and masking configuration generator."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pii-detector"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector import PiiDetector
from generator import MaskingConfigGenerator


detector = PiiDetector()
generator = MaskingConfigGenerator()


def test_high_confidence_email_becomes_masking_rule() -> None:
    detections = detector.detect_all(
        [
            {
                "table_name": "USERS",
                "column_name": "email_address",
                "data_type": "VARCHAR(255)",
                "sample_values": ["user@example.com"],
                "nullable": True,
            },
            {
                "table_name": "ORDERS",
                "column_name": "transaction_id",
                "data_type": "BIGINT",
                "sample_values": ["100001", "100002"],
                "nullable": False,
            },
        ]
    )

    config = generator.generate(detections)
    configured_columns = {rule["column"] for rule in config["masking_rules"]}

    assert "email_address" in configured_columns
    assert "transaction_id" not in configured_columns


def test_review_required_detection_stays_out_of_masking_rules() -> None:
    detections = detector.detect_all(
        [
            {
                "table_name": "CONTACTS",
                "column_name": "secondary_phone",
                "data_type": "VARCHAR(20)",
                "sample_values": ["unknown", "null"],
                "nullable": True,
            }
        ]
    )

    config = generator.generate(detections)

    assert config["masking_rules"] == []
    assert any(item["column"] == "secondary_phone" for item in config["review_queue"])
