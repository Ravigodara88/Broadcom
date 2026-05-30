"""PII detection engine for the Schema Intelligence Assistant.

Phase 1 provides the contract and scaffold. The classifier implementation
arrives in Phase 2.
"""

from __future__ import annotations

from typing import Any


class PiiDetector:
    """Detect likely PII columns from schema descriptors."""

    def detect(self, column: dict[str, Any]) -> dict[str, Any]:
        """Classify a single column descriptor.

        Expected input:
        {
            "table_name": "CUSTOMERS",
            "column_name": "cust_acct_no",
            "data_type": "VARCHAR(20)",
            "sample_values": ["****1234", "ACC-98765", "null"],
            "nullable": true
        }
        """

        raise NotImplementedError("PiiDetector.detect will be implemented in Phase 2.")

    def detect_all(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Classify a list of schema column descriptors."""

        return [self.detect(column) for column in columns]
