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


@dataclass(frozen=True)
class Variant:
    name: str
    agent: SchemaIntelligenceAgent


CASES = [
    BaselineCase("What does DATE_SHIFT do and what parameters does it accept?", "doc"),
    BaselineCase("What parameters does EMAIL_MASK accept?", "doc"),
    BaselineCase("How do I comply with GDPR when masking customer data?", "doc"),
    BaselineCase("What is the weather in Hyderabad?", "scope"),
    BaselineCase("Mask this column", "missing_schema"),
]


def score_response(case: BaselineCase, response: str) -> tuple[int, int, int]:
    relevance = 0
    grounding = 0
    policy = 0
    lowered = response.lower()

    if case.kind == "doc":
        if any(token in lowered for token in ["mask", "date", "parameter", "gdpr", "ccpa", "offset"]):
            relevance = 2
        if "[source:" in lowered:
            grounding = 2
        if "out of scope" not in lowered:
            policy = 1
    elif case.kind == "scope":
        if "out of scope" in lowered or "masking" in lowered:
            policy = 3
        if "hyderabad" not in lowered:
            grounding = 2
    elif case.kind == "missing_schema":
        if "provide" in lowered and ("schema" in lowered or "table name" in lowered):
            relevance = 2
            policy = 2
        if "[source:" not in lowered:
            grounding = 1

    return relevance, grounding, policy


def generate_baseline_results() -> str:
    schema = json.loads(SCHEMA_PATH.read_text())
    variants = [
        Variant("current_submission", SchemaIntelligenceAgent(use_category_filters=True)),
        Variant("control_no_category_filter", SchemaIntelligenceAgent(use_category_filters=False)),
    ]

    lines = [
        "# A/B Baseline Results",
        "",
        "Rubric: each query is scored from 0 to 5 using three dimensions: relevance (0-2), grounding (0-2), and policy discipline (0-1 or scenario-specific guardrail points).",
        "",
        "| Variant | Query | Relevance | Grounding | Policy | Total | Notes |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    totals = {variant.name: 0 for variant in variants}

    for case in CASES:
        for variant in variants:
            if case.prompt == "Analyse this schema for PII":
                response = variant.agent.chat(case.prompt, schema=schema)
            else:
                response = variant.agent.chat(case.prompt)
            relevance, grounding, policy = score_response(case, response)
            total = relevance + grounding + policy
            totals[variant.name] += total
            note = "Grounded and on-policy" if total >= 4 else "Needs follow-up tuning"
            lines.append(
                f"| {variant.name} | {case.prompt} | {relevance} | {grounding} | {policy} | {total} | {note} |"
            )

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
            "- `current_submission` is the preferred baseline because it uses category-aware retrieval and represents the intended shipped behavior.",
            "- `control_no_category_filter` is an ablation baseline; future prompt or model revisions should outperform or at least match `current_submission` on this rubric.",
        ]
    )
    markdown = "\n".join(lines) + "\n"
    OUTPUT_PATH.write_text(markdown)
    return markdown


if __name__ == "__main__":
    print(generate_baseline_results())
