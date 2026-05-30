"""A/B baseline comparison for agent response quality."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from agent.agent import SchemaIntelligenceAgent


OUTPUT_PATH = Path(__file__).with_name("ab_baseline_results.md")
SCHEMA_PATH = Path(__file__).with_name("10_column_schema.json")


@dataclass
class BaselineCase:
    prompt: str
    kind: str


CASES = [
    BaselineCase("What does DATE_SHIFT do and what parameters does it accept?", "doc"),
    BaselineCase("What parameters does EMAIL_MASK accept?", "doc"),
    BaselineCase("How do I comply with GDPR when masking customer data?", "doc"),
    BaselineCase("What is the weather in Hyderabad?", "scope"),
    BaselineCase("Mask this column", "missing_schema"),
]


def score_response(case: BaselineCase, response: str) -> int:
    score = 0
    lowered = response.lower()

    if case.kind == "doc":
        if any(token in lowered for token in ["mask", "date", "parameter", "gdpr", "ccpa", "offset"]):
            score += 2
        if "[source:" in lowered:
            score += 2
        if "out of scope" not in lowered:
            score += 1
    elif case.kind == "scope":
        if "out of scope" in lowered or "masking" in lowered:
            score += 3
        if "hyderabad" not in lowered:
            score += 2
    elif case.kind == "missing_schema":
        if "provide" in lowered and ("schema" in lowered or "table name" in lowered):
            score += 4
        if "[source:" not in lowered:
            score += 1

    return score


def generate_baseline_results() -> str:
    schema = json.loads(SCHEMA_PATH.read_text())
    variants = {
        "category_aware": SchemaIntelligenceAgent(use_category_filters=True),
        "broad_retrieval": SchemaIntelligenceAgent(use_category_filters=False),
    }

    lines = [
        "# A/B Baseline Results",
        "",
        "Rubric: each query is scored from 0 to 5 on relevance, grounding, and scope discipline.",
        "",
        "| Variant | Query | Score | Notes |",
        "|---|---|---:|---|",
    ]

    totals = {name: 0 for name in variants}

    for case in CASES:
        for variant_name, agent in variants.items():
            if case.prompt == "Analyse this schema for PII":
                response = agent.chat(case.prompt, schema=schema)
            else:
                response = agent.chat(case.prompt)
            score = score_response(case, response)
            totals[variant_name] += score
            note = "Grounded and on-policy" if score >= 4 else "Needs follow-up tuning"
            lines.append(f"| {variant_name} | {case.prompt} | {score} | {note} |")

    lines.extend(
        [
            "",
            "## Totals",
            "",
            "| Variant | Total Score |",
            "|---|---:|",
        ]
    )
    for variant_name, total in totals.items():
        lines.append(f"| {variant_name} | {total} |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `category_aware` is the preferred baseline because it applies category filtering before retrieval.",
            "- `broad_retrieval` provides a weaker comparison point for future prompt or model revisions.",
        ]
    )
    markdown = "\n".join(lines) + "\n"
    OUTPUT_PATH.write_text(markdown)
    return markdown


if __name__ == "__main__":
    print(generate_baseline_results())
