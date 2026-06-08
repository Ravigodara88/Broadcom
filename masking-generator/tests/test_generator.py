"""Unit tests for masking configuration generation."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generator import DetectionResult, MaskingConfigGenerator


generator = MaskingConfigGenerator()


def sample_detections() -> list[DetectionResult]:
    return [
        DetectionResult(
            table="CUSTOMERS",
            column="email_address",
            is_pii=True,
            confidence=0.94,
            pii_category="EMAIL",
            recommended_masking_function="EMAIL_MASK",
            review_required=False,
            reasoning="Column name and sample values match email format",
        ),
        DetectionResult(
            table="ORDERS",
            column="ref_code",
            is_pii=True,
            confidence=0.62,
            pii_category="ACCOUNT_NUMBER",
            recommended_masking_function="ACCOUNT_MASK",
            review_required=True,
            reasoning="Column name is ambiguous",
        ),
        DetectionResult(
            table="ORDERS",
            column="transaction_id",
            is_pii=False,
            confidence=0.23,
            pii_category=None,
            recommended_masking_function=None,
            review_required=False,
            reasoning="Identifier looks operational rather than personal",
        ),
    ]


def test_low_confidence_goes_to_review_queue() -> None:
    detections = [
        DetectionResult(
            table="ORDERS",
            column="ref_code",
            is_pii=True,
            confidence=0.62,
            pii_category="ACCOUNT_NUMBER",
            recommended_masking_function="ACCOUNT_MASK",
            review_required=True,
            reasoning="Column name is ambiguous",
        )
    ]
    config = generator.generate(detections)
    assert any(item["column"] == "ref_code" for item in config["review_queue"])
    assert not any(item["column"] == "ref_code" for item in config["masking_rules"])


def test_documentation_references_exist() -> None:
    config = generator.generate(sample_detections())
    corpus_files = {file_path.name for file_path in Path("rag/corpus").glob("*.md")}
    for rule in config["masking_rules"]:
        doc_file = rule["documentation_reference"].split("#")[0]
        assert doc_file in corpus_files


def test_documentation_reference_comes_from_retrieval_context() -> None:
    retriever_calls: list[tuple[str, str | None, int]] = []

    def fake_retriever(query: str, pii_category_filter: str | None, top_k: int) -> list[dict[str, object]]:
        retriever_calls.append((query, pii_category_filter, top_k))
        return [
            {
                "metadata": {
                    "source": "04-email_mask.md#behavior",
                }
            }
        ]

    config = MaskingConfigGenerator(doc_retriever=fake_retriever).generate(sample_detections())

    assert retriever_calls == [
        ("What does EMAIL_MASK do and what parameters does it accept?", "EMAIL", 1)
    ]
    assert config["masking_rules"][0]["documentation_reference"] == "04-email_mask.md#behavior"


def test_confidence_summary_counts_are_correct() -> None:
    config = generator.generate(sample_detections())
    assert config["confidence_summary"] == {
        "auto_configured": 1,
        "requires_review": 1,
        "not_pii": 1,
    }
