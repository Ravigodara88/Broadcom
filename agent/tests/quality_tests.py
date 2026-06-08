"""Day 3 quality tests for the Schema Intelligence Agent."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "pii-detector"))
sys.path.insert(0, str(ROOT_DIR / "masking-generator"))

from agent.agent import SchemaIntelligenceAgent
from agent.tools import detect_pii_columns, generate_masking_config, tool_call_tracker


agent = SchemaIntelligenceAgent()
GOLDEN_SET_PATH = ROOT_DIR / "pii-detector" / "tests" / "schema_test_cases.json"
TEN_COLUMN_SCHEMA_PATH = Path(__file__).with_name("10_column_schema.json")


def response_cites_source(response: str) -> bool:
    return "[Source:" in response and "#" in response


def assert_no_hallucination(response: str) -> None:
    assert "paris" not in response.lower()
    assert "hyderabad" not in response.lower()


def run_detector_on_golden_set() -> list[dict[str, object]]:
    cases = json.loads(GOLDEN_SET_PATH.read_text())
    results = []
    for case in cases:
        detection = detect_pii_columns(case["input"])[0]
        results.append({"expected": case["expected"], "actual": detection})
    return results


def compute_recall(results: list[dict[str, object]]) -> float:
    positives = [result for result in results if result["expected"]["is_pii"]]  # type: ignore[index]
    detected = sum(1 for result in positives if result["actual"]["is_pii"])  # type: ignore[index]
    return detected / len(positives)


def load_test_schema(filename: str) -> list[dict[str, object]]:
    return json.loads((Path(__file__).with_name(filename)).read_text())


def test_date_shift_answer_is_grounded() -> None:
    response = agent.chat("What does DATE_SHIFT do and what parameters does it accept?")
    assert any(keyword in response.lower() for keyword in ["shift", "offset", "date", "preserve", "parameter"])
    assert response_cites_source(response)


def test_ssn_acronym_question_is_grounded() -> None:
    response = agent.chat("How should I mask SSN values while keeping only the last four digits?")
    assert any(keyword in response.lower() for keyword in ["ssn", "social security", "last four", "mask"])
    assert response_cites_source(response)


def test_doc_question_triggers_retrieval() -> None:
    with tool_call_tracker() as tracker:
        agent.chat("What parameters does EMAIL_MASK accept?")
    assert "search_masking_docs" in tracker.called_tools


def test_generic_doc_question_triggers_retrieval_and_citation() -> None:
    with tool_call_tracker() as tracker:
        response = agent.chat("What masking functions are available?")
    assert "search_masking_docs" in tracker.called_tools
    assert response_cites_source(response)


def test_out_of_scope_query_rejected() -> None:
    response = agent.chat("What is the capital of France?")
    assert_no_hallucination(response)
    assert any(phrase in response.lower() for phrase in ["out of scope", "masking", "data"])


def test_personal_prompt_rejected_without_tool_call() -> None:
    with tool_call_tracker() as tracker:
        response = agent.chat("What is your name?")
    assert tracker.called_tools == []
    assert "out of scope" in response.lower()


def test_pii_detector_recall_regression() -> None:
    recall = compute_recall(run_detector_on_golden_set())
    assert recall >= 0.85, f"PII recall regression: {recall:.2f} < 0.85"


def test_masking_config_covers_high_confidence_detections() -> None:
    schema = load_test_schema("10_column_schema.json")
    detections = detect_pii_columns(schema)
    config = generate_masking_config(detections)
    high_conf = [detection for detection in detections if detection["confidence"] >= 0.80 and detection["is_pii"]]
    configured = {rule["column"] for rule in config["masking_rules"]}
    for detection in high_conf:
        assert detection["column_name"] in configured


def test_missing_schema_prompts_for_required_input() -> None:
    response = agent.chat("Mask this column")
    assert "provide" in response.lower()
    assert "schema" in response.lower() or "table name" in response.lower()


def test_schema_analysis_returns_confidence_scored_results() -> None:
    schema = load_test_schema("10_column_schema.json")
    response = agent.chat("Analyse this schema for PII", schema=schema)
    assert "confidence" in response.lower()
    assert "email_address" in response


def test_single_column_question_returns_reasoning() -> None:
    response = agent.chat("Is column ref_code in table ORDERS PII?")
    assert "confidence" in response.lower()
    assert "reason" in response.lower() or "classified" in response.lower()


def test_gdpr_compliance_answer_is_grounded() -> None:
    response = agent.chat("How do I comply with GDPR when masking customer data?")
    assert any(keyword in response.lower() for keyword in ["gdpr", "compliance", "mask", "pii", "personal"])
    assert_no_hallucination(response)
    assert response_cites_source(response)


def test_masking_config_generated_via_agent_chat() -> None:
    schema = load_test_schema("10_column_schema.json")
    detections = detect_pii_columns(schema)
    with tool_call_tracker() as tracker:
        response = agent.chat("Generate a masking configuration for these results", detections=detections)
    assert "generate_masking_config" in tracker.called_tools
    assert "masking_rules" in response


def test_tool_calling_agent_uses_doc_search(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeToolCall:
        def __init__(self, name: str, arguments: str, call_id: str = "call-1") -> None:
            self.id = call_id
            self.function = type("Function", (), {"name": name, "arguments": arguments})()

    first_message = type(
        "Message",
        (),
        {
            "content": "",
            "tool_calls": [FakeToolCall("search_masking_docs", json.dumps({"query": "What parameters does EMAIL_MASK accept?", "pii_category_filter": "EMAIL", "top_k": 1}))],
        },
    )()
    second_message = type("Message", (), {"content": "EMAIL docs answer [Source: 04-email_mask.md#parameters]", "tool_calls": []})()
    responses = [
        type("Response", (), {"choices": [type("Choice", (), {"message": first_message})()]})(),
        type("Response", (), {"choices": [type("Choice", (), {"message": second_message})()]})(),
    ]

    class FakeCompletions:
        def __init__(self, queued_responses: list[object]) -> None:
            self._queued_responses = queued_responses

        def create(self, **_kwargs):
            return self._queued_responses.pop(0)

    fake_client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions(responses)})()})()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    tool_agent = SchemaIntelligenceAgent(use_tool_calling=True)
    monkeypatch.setattr(tool_agent, "_build_openai_client", lambda _api_key: fake_client)

    with tool_call_tracker() as tracker:
        response = tool_agent.chat("What parameters does EMAIL_MASK accept?")

    assert "search_masking_docs" in tracker.called_tools
    assert response == "EMAIL docs answer [Source: 04-email_mask.md#parameters]"
