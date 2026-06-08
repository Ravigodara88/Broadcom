"""Policy-driven conversational agent for schema intelligence workflows."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

try:
    from .tools import detect_pii_columns, generate_masking_config, search_masking_docs
except ImportError:  # pragma: no cover - script execution fallback
    sys.path.insert(0, str(ROOT_DIR / "agent"))
    from tools import detect_pii_columns, generate_masking_config, search_masking_docs


logger = logging.getLogger(__name__)


FUNCTION_TO_CATEGORY = {
    "NAME_RANDOMIZE": "FULL_NAME",
    "EMAIL_MASK": "EMAIL",
    "PHONE_MASK": "PHONE",
    "SSN_MASK": "SSN",
    "CREDIT_CARD_MASK": "CREDIT_CARD",
    "ACCOUNT_MASK": "ACCOUNT_NUMBER",
    "DATE_SHIFT": "DATE_OF_BIRTH",
    "ADDRESS_RANDOMIZE": "ADDRESS",
    "IP_MASK": "IP_ADDRESS",
    "NATIONAL_ID_MASK": "NATIONAL_ID",
}

KEYWORD_TO_CATEGORY = {
    "full name": "FULL_NAME",
    "name randomize": "FULL_NAME",
    "email": "EMAIL",
    "phone": "PHONE",
    "mobile": "PHONE",
    "ssn": "SSN",
    "social security": "SSN",
    "credit card": "CREDIT_CARD",
    "account number": "ACCOUNT_NUMBER",
    "account mask": "ACCOUNT_NUMBER",
    "date_shift": "DATE_OF_BIRTH",
    "date shift": "DATE_OF_BIRTH",
    "date of birth": "DATE_OF_BIRTH",
    "address": "ADDRESS",
    "ip": "IP_ADDRESS",
    "national id": "NATIONAL_ID",
    "passport": "NATIONAL_ID",
    "aadhaar": "NATIONAL_ID",
}


class SchemaIntelligenceAgent:
    """Deterministic agent that orchestrates detector, generator, and RAG tools."""

    def __init__(self, use_category_filters: bool = True, use_tool_calling: bool | None = None) -> None:
        self.use_category_filters = use_category_filters
        if use_tool_calling is None:
            env_value = os.getenv("AGENT_USE_TOOL_CALLING", "")
            self.use_tool_calling = env_value.strip().lower() in {"1", "true", "yes", "on"}
        else:
            self.use_tool_calling = use_tool_calling

    def chat(
        self,
        user_message: str,
        *,
        schema: list[dict[str, Any]] | dict[str, Any] | None = None,
        detections: list[dict[str, Any]] | None = None,
    ) -> str:
        message = user_message.strip()
        lowered = message.lower()

        if self._is_out_of_scope(lowered):
            return (
                "That request is out of scope for this assistant. I can help with "
                "PII detection, masking configuration, and masking documentation only."
            )

        if self.use_tool_calling:
            tool_response = self._tool_calling_chat(message, schema=schema, detections=detections)
            if tool_response:
                return tool_response

        if self._is_config_request(lowered):
            payload = detections or self._extract_json_payload(message)
            if not payload:
                return (
                    "I can generate a masking configuration, but I need detector results "
                    "or a structured detection payload first."
                )
            config = generate_masking_config(payload)
            return self._render_json_response("Generated masking configuration.", config)

        if self._is_schema_analysis_request(lowered):
            payload = schema or self._extract_json_payload(message)
            if not payload:
                return (
                    "Please provide the schema JSON so I can analyse it for PII and "
                    "return confidence-scored results."
                )
            detections_result = detect_pii_columns(payload)
            summary = self._summarize_detection_results(detections_result)
            return self._render_json_response(summary, detections_result)

        if self._is_single_column_question(message):
            descriptor = self._build_single_column_descriptor(message)
            detection = detect_pii_columns(descriptor)[0]
            if detection["is_pii"]:
                return (
                    f"Column `{detection['column_name']}` in table `{detection['table_name']}` "
                    f"is likely PII ({detection['pii_category']}) with confidence "
                    f"{detection['confidence']:.2f}. {detection['reasoning']}"
                )
            return (
                f"Column `{detection['column_name']}` in table `{detection['table_name']}` "
                f"is not strongly classified as PII (confidence {detection['confidence']:.2f}). "
                f"{detection['reasoning']}"
            )

        if self._looks_like_column_mask_request(lowered):
            return (
                "I need the column schema before I can suggest masking. Please provide "
                "at least the table name, column name, data type, and sample values."
            )

        if self._is_doc_question(lowered):
            return self._answer_doc_question(message)

        # Keep any remaining in-scope informational requests grounded via retrieval.
        return self._answer_doc_question(message)

    def _answer_doc_question(self, query: str) -> str:
        pii_category_filter = self._infer_pii_category_filter(query) if self.use_category_filters else None
        results = search_masking_docs(query, pii_category_filter=pii_category_filter)
        if not results:
            return "I could not find relevant masking documentation for that question."

        snippets = self._build_doc_snippets(query, results)
        citations = "; ".join(self._unique_sources(results))
        answer = " ".join(snippets)
        return f"{answer} [Source: {citations}]"

    def _build_doc_snippets(self, query: str, results: list[dict[str, Any]]) -> list[str]:
        lowered = query.lower()
        snippets: list[str] = []

        preferred_sections: list[str] = []
        if "parameter" in lowered:
            preferred_sections.append("Parameters")
        if any(token in lowered for token in ("what does", "usage", "how does", "do")):
            preferred_sections.extend(["Usage", "Behavior", "Purpose", "GDPR Considerations", "Recommended Steps"])
        if "comply" in lowered or "gdpr" in lowered or "ccpa" in lowered:
            preferred_sections.extend(["GDPR Considerations", "CCPA Considerations", "Recommended Guardrails"])

        ordered_results = sorted(
            results,
            key=lambda item: (item["section"] in preferred_sections, item["score"]),
            reverse=True,
        )

        for result in ordered_results[:3]:
            content = self._strip_heading_lines(result["text"])
            if result["section"] == "Parameters":
                params = self._extract_bullet_items(content)
                if params:
                    snippets.append(
                        "Key parameters include " + ", ".join(f"`{param}`" for param in params[:4]) + "."
                    )
                    continue
            sentence = self._first_sentence(content)
            if sentence:
                snippets.append(sentence)

        deduped: list[str] = []
        for snippet in snippets:
            if snippet not in deduped:
                deduped.append(snippet)
        return deduped[:3]

    def _summarize_detection_results(self, detections: list[dict[str, Any]]) -> str:
        pii_count = sum(1 for detection in detections if detection["is_pii"])
        review_count = sum(1 for detection in detections if detection["review_required"])
        return (
            f"Analysed {len(detections)} columns. Detected {pii_count} likely PII columns "
            f"with {review_count} requiring review."
        )

    def _render_json_response(self, preamble: str, payload: Any) -> str:
        json_text = json.dumps(payload, indent=2)
        return f"{preamble}\n```json\n{json_text}\n```"

    def _extract_json_payload(self, message: str) -> Any | None:
        for pattern in (r"(\[[\s\S]+\])", r"(\{[\s\S]+\})"):
            match = re.search(pattern, message)
            if not match:
                continue
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
        return None

    def _infer_pii_category_filter(self, query: str) -> str | None:
        upper_query = query.upper()
        for function_name, category in FUNCTION_TO_CATEGORY.items():
            if function_name in upper_query:
                return category

        lowered = query.lower()
        for keyword, category in KEYWORD_TO_CATEGORY.items():
            if keyword in lowered:
                return category
        return None

    def _unique_sources(self, results: list[dict[str, Any]]) -> list[str]:
        seen: list[str] = []
        for result in results:
            source = result["metadata"]["source"]
            if source not in seen:
                seen.append(source)
        return seen

    def _strip_heading_lines(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) >= 3:
            return "\n".join(lines[2:])
        return "\n".join(lines)

    def _extract_bullet_items(self, text: str) -> list[str]:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- `") and "`:" not in line:
                items.append(line.split("`")[1])
        return items

    def _first_sentence(self, text: str) -> str:
        normalized = " ".join(text.split())
        match = re.match(r"(.+?[.!?])(?:\s|$)", normalized)
        return match.group(1) if match else normalized

    def _is_out_of_scope(self, lowered: str) -> bool:
        phrase_terms = (
            "data masking",
            "masking rule",
            "masking rules",
            "masking function",
            "masking functions",
            "social security",
            "credit card",
            "account number",
            "date of birth",
            "ip address",
            "national id",
            "full name",
            "phone number",
            "email address",
            "review queue",
            "masking job",
        )
        token_terms = {
            "pii",
            "schema",
            "column",
            "table",
            "mask",
            "masking",
            "masked",
            "detect",
            "detection",
            "gdpr",
            "ccpa",
            "compliance",
            "comply",
            "function",
            "functions",
            "configure",
            "configuration",
            "troubleshoot",
            "troubleshooting",
            "performance",
            "review",
            "confidence",
            "anonymize",
            "anonymized",
            "anonymization",
            "email",
            "phone",
            "ssn",
            "dob",
            "aadhaar",
            "passport",
        }
        function_tokens = {function.lower() for function in FUNCTION_TO_CATEGORY}
        tokens = set(re.findall(r"[a-z0-9_]+", lowered))

        if any(phrase in lowered for phrase in phrase_terms):
            return False
        if tokens & token_terms:
            return False
        if tokens & function_tokens:
            return False
        return True

    def _is_doc_question(self, lowered: str) -> bool:
        doc_terms = (
            "what does",
            "what parameters",
            "gdpr",
            "ccpa",
            "configure",
            "masking job",
            "troubleshooting",
            "performance",
        )
        if any(term in lowered for term in doc_terms):
            return True
        return any(function.lower() in lowered for function in FUNCTION_TO_CATEGORY)

    def _is_schema_analysis_request(self, lowered: str) -> bool:
        return "analyse this schema" in lowered or "analyze this schema" in lowered

    def _is_config_request(self, lowered: str) -> bool:
        return "generate a masking configuration" in lowered or "generate masking configuration" in lowered

    def _looks_like_column_mask_request(self, lowered: str) -> bool:
        return "mask this column" in lowered

    def _is_single_column_question(self, message: str) -> bool:
        return bool(re.search(r"is column\s+\S+\s+in table\s+\S+\s+pii\??", message, flags=re.IGNORECASE))

    def _tool_calling_chat(
        self,
        message: str,
        *,
        schema: list[dict[str, Any]] | dict[str, Any] | None,
        detections: list[dict[str, Any]] | None,
    ) -> str | None:
        """Optional raw tool-calling path backed by an OpenAI-compatible chat model."""
        api_key = (os.getenv("CI_TOKEN") or os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return None
        try:
            client = self._build_openai_client(api_key)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Tool-calling client unavailable: %s", exc)
            return None

        context_lines = []
        if schema is not None:
            context_lines.append("Schema context:\n" + json.dumps(schema, indent=2))
        if detections is not None:
            context_lines.append("Detection context:\n" + json.dumps(detections, indent=2))
        user_content = message if not context_lines else f"{message}\n\n" + "\n\n".join(context_lines)

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a Schema Intelligence Assistant for enterprise data masking. "
                    "Only answer questions about PII detection, masking configuration, and masking documentation. "
                    "Use the provided tools whenever they are relevant. "
                    "For documentation questions, call search_masking_docs before answering. "
                    "If the request asks to generate a masking configuration, call generate_masking_config. "
                    "If the request asks to analyse a schema or a single column, call detect_pii_columns."
                ),
            },
            {"role": "user", "content": user_content},
        ]

        tools = self._tool_specs()
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini").strip()
        for _ in range(3):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0,
                    max_tokens=700,
                )
            except Exception as exc:  # pragma: no cover - network/runtime fallback
                logger.warning("Tool-calling request failed: %s", exc)
                return None

            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                content = (assistant_message.content or "").strip()
                return content or None

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                tool_result = self._dispatch_tool_call(tool_call.function.name, tool_call.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, indent=2),
                    }
                )

        return None

    def _build_openai_client(self, api_key: str):
        import openai  # noqa: PLC0415

        base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
        header_name = os.getenv("LLM_APP_HEADER_NAME", "").strip()
        header_value = os.getenv("LLM_APP_HEADER_VALUE", "").strip()
        default_headers = {header_name: header_value} if (header_name and header_value) else None
        return openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )

    def _tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "detect_pii_columns",
                    "description": "Analyse a schema or single column descriptor and return PII detection results.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "schema": {
                                "description": "A single column descriptor object or a list of column descriptors.",
                                "oneOf": [{"type": "object"}, {"type": "array"}],
                            }
                        },
                        "required": ["schema"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_masking_config",
                    "description": "Generate a masking configuration from PII detection results.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "detections": {
                                "type": "array",
                                "description": "Detection result objects returned by detect_pii_columns.",
                            }
                        },
                        "required": ["detections"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_masking_docs",
                    "description": "Retrieve masking documentation chunks. Must be used before answering documentation questions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "pii_category_filter": {"type": "string"},
                            "top_k": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    def _dispatch_tool_call(self, tool_name: str, raw_arguments: str) -> Any:
        arguments = json.loads(raw_arguments or "{}")
        if tool_name == "detect_pii_columns":
            return detect_pii_columns(arguments["schema"])
        if tool_name == "generate_masking_config":
            return generate_masking_config(arguments["detections"])
        if tool_name == "search_masking_docs":
            return search_masking_docs(
                arguments["query"],
                pii_category_filter=arguments.get("pii_category_filter") or None,
                top_k=int(arguments.get("top_k", 3)),
            )
        raise ValueError(f"Unsupported tool call: {tool_name}")

    def _build_single_column_descriptor(self, message: str) -> dict[str, Any]:
        match = re.search(
            r"is column\s+(?P<column>[A-Za-z0-9_]+)\s+in table\s+(?P<table>[A-Za-z0-9_]+)\s+pii\??",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError("Could not parse single-column question.")
        return {
            "table_name": match.group("table"),
            "column_name": match.group("column"),
            "data_type": "VARCHAR(255)",
            "sample_values": [],
            "nullable": True,
        }
