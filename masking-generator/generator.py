"""Masking configuration generator based on PII detection output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from typing import Any, Callable

try:
    from rag.retrieve import retrieve as rag_retrieve
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    ROOT_DIR = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT_DIR))
    from rag.retrieve import retrieve as rag_retrieve


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

RetrieverFn = Callable[[str, str | None, int], list[dict[str, Any]]]


def _default_doc_retriever(query: str, pii_category_filter: str | None, top_k: int = 1) -> list[dict[str, Any]]:
    return rag_retrieve(query=query, pii_category_filter=pii_category_filter, top_k=top_k)


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

    def __init__(self, doc_retriever: RetrieverFn | None = None) -> None:
        self._doc_retriever = doc_retriever or _default_doc_retriever

    def generate(self, detections: list[Any]) -> dict[str, Any]:
        normalized_detections = [self._normalize_detection(detection) for detection in detections]
        doc_reference_cache: dict[tuple[str | None, str | None], str] = {}

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

            doc_reference = self._resolve_doc_reference(detection, doc_reference_cache)
            masking_rules.append(self._build_masking_rule(detection, doc_reference))

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

    def _build_masking_rule(self, detection: dict[str, Any], doc_reference: str) -> dict[str, Any]:
        category = detection["pii_category"]
        return {
            "table": detection["table"],
            "column": detection["column"],
            "masking_function": detection["recommended_masking_function"],
            "parameters": {},
            "confidence": round(float(detection["confidence"]), 2),
            "requires_review": False,
            "documentation_reference": doc_reference or DOCUMENTATION_REFERENCES[category],
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

    def _resolve_doc_reference(
        self,
        detection: dict[str, Any],
        cache: dict[tuple[str | None, str | None], str],
    ) -> str:
        category = detection.get("pii_category")
        function_name = detection.get("recommended_masking_function")
        cache_key = (category, function_name)
        if cache_key in cache:
            return cache[cache_key]

        fallback = DOCUMENTATION_REFERENCES.get(category, "")
        if not category or not function_name:
            cache[cache_key] = fallback
            return fallback

        query = f"What does {function_name} do and what parameters does it accept?"
        try:
            results = self._doc_retriever(query, category, 1)
        except Exception:
            results = []

        if results:
            reference = str(results[0].get("metadata", {}).get("source", "")).strip()
            if reference:
                cache[cache_key] = reference
                return reference

        cache[cache_key] = fallback
        return fallback
