"""Masking configuration generator based on PII detection output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from typing import Any


AUTO_CONFIGURE_THRESHOLD = 0.85

DOCUMENTATION_REFERENCES = {
    "FULL_NAME": "03-name_randomize.md#usage",
    "EMAIL": "04-email_mask.md#usage",
    "PHONE": "05-phone_ssn_mask.md#phone-mask",
    "SSN": "05-phone_ssn_mask.md#ssn-mask",
    "CREDIT_CARD": "06-credit_card_account_mask.md#credit-card-mask",
    "ACCOUNT_NUMBER": "06-credit_card_account_mask.md#account-mask",
    "DATE_OF_BIRTH": "07-date_shift.md#usage",
    "ADDRESS": "08-address_ip_national_id_mask.md#address-randomize",
    "IP_ADDRESS": "08-address_ip_national_id_mask.md#ip-mask",
    "NATIONAL_ID": "08-address_ip_national_id_mask.md#national-id-mask",
}

ALTERNATIVE_FUNCTIONS = {
    "FULL_NAME": ["EMAIL_MASK", "ADDRESS_RANDOMIZE"],
    "EMAIL": ["PHONE_MASK", "NAME_RANDOMIZE"],
    "PHONE": ["EMAIL_MASK", "NATIONAL_ID_MASK"],
    "SSN": ["ACCOUNT_MASK", "NATIONAL_ID_MASK"],
    "CREDIT_CARD": ["ACCOUNT_MASK", "NATIONAL_ID_MASK"],
    "ACCOUNT_NUMBER": ["SSN_MASK", "NATIONAL_ID_MASK"],
    "DATE_OF_BIRTH": ["NAME_RANDOMIZE", "ADDRESS_RANDOMIZE"],
    "ADDRESS": ["IP_MASK", "NAME_RANDOMIZE"],
    "IP_ADDRESS": ["ADDRESS_RANDOMIZE", "NATIONAL_ID_MASK"],
    "NATIONAL_ID": ["SSN_MASK", "ACCOUNT_MASK"],
}


@dataclass
class DetectionResult:
    """Optional typed helper for generator tests and integrations."""

    table: str
    column: str
    is_pii: bool
    confidence: float
    pii_category: str | None
    recommended_masking_function: str | None
    review_required: bool
    reasoning: str = ""


class MaskingConfigGenerator:
    """Convert detector output into a masking configuration document."""

    def generate(self, detections: list[Any]) -> dict[str, Any]:
        normalized_detections = [self._normalize_detection(detection) for detection in detections]

        masking_rules: list[dict[str, Any]] = []
        review_queue: list[dict[str, Any]] = []
        not_pii_count = 0

        for detection in normalized_detections:
            if not detection["is_pii"]:
                not_pii_count += 1
                continue

            if detection["review_required"] or detection["confidence"] < AUTO_CONFIGURE_THRESHOLD:
                review_queue.append(self._build_review_item(detection))
                continue

            masking_rules.append(self._build_masking_rule(detection))

        return {
            "masking_job_name": f"AUTO_GENERATED_{date.today().isoformat()}",
            "generated_by": "SchemaIntelligenceAssistant",
            "confidence_summary": {
                "auto_configured": len(masking_rules),
                "requires_review": len(review_queue),
                "not_pii": not_pii_count,
            },
            "masking_rules": masking_rules,
            "review_queue": review_queue,
        }

    def _normalize_detection(self, detection: Any) -> dict[str, Any]:
        if isinstance(detection, dict):
            payload = dict(detection)
        elif is_dataclass(detection):
            payload = asdict(detection)
        else:
            raise TypeError(f"Unsupported detection type: {type(detection)!r}")

        if "table" not in payload:
            payload["table"] = payload.get("table_name")
        if "column" not in payload:
            payload["column"] = payload.get("column_name")
        return payload

    def _build_masking_rule(self, detection: dict[str, Any]) -> dict[str, Any]:
        category = detection["pii_category"]
        return {
            "table": detection["table"],
            "column": detection["column"],
            "masking_function": detection["recommended_masking_function"],
            "parameters": {},
            "confidence": round(float(detection["confidence"]), 2),
            "requires_review": False,
            "documentation_reference": DOCUMENTATION_REFERENCES[category],
        }

    def _build_review_item(self, detection: dict[str, Any]) -> dict[str, Any]:
        category = detection.get("pii_category")
        alternatives = ALTERNATIVE_FUNCTIONS.get(category or "", [])
        confidence = round(float(detection["confidence"]), 2)

        if detection["review_required"]:
            reason = f"Low confidence ({confidence:.2f}) - column classification requires human review"
        else:
            reason = f"Confidence below auto-configure threshold ({confidence:.2f})"

        if detection.get("reasoning"):
            reason = f"{reason}. {detection['reasoning']}"

        return {
            "table": detection["table"],
            "column": detection["column"],
            "reason": reason,
            "suggested_function": detection.get("recommended_masking_function"),
            "alternatives": alternatives,
        }
