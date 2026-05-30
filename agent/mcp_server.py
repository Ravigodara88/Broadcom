"""MCP server exposing Schema Intelligence tools via the Model Context Protocol.

Run with:
    python agent/mcp_server.py            # stdio transport (default, for IDE/CLI clients)
    python agent/mcp_server.py --sse      # SSE transport on http://localhost:8000

The three tools exposed here are the same functions used by the conversational
agent internally, so any MCP-compatible client (Claude Desktop, VS Code Copilot,
Cursor, etc.) gains identical capabilities without re-implementing the logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap — allow running as a top-level script or as a module
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "pii-detector"))
sys.path.insert(0, str(ROOT_DIR / "masking-generator"))
sys.path.insert(0, str(ROOT_DIR))

from mcp.server.fastmcp import FastMCP

from detector import HybridPiiDetector
from generator import MaskingConfigGenerator
from rag.retrieve import retrieve

# ---------------------------------------------------------------------------
# Shared service instances (created once, reused across all tool calls)
# ---------------------------------------------------------------------------
_detector = HybridPiiDetector()
_generator = MaskingConfigGenerator()

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "Schema Intelligence Assistant",
    instructions=(
        "You are a Schema Intelligence Assistant for enterprise data masking. "
        "Use detect_pii_columns to identify PII in a database schema, "
        "generate_masking_config to produce a masking job configuration, and "
        "search_masking_docs to answer questions about masking functions and compliance. "
        "Only answer questions about PII detection and data masking. "
        "Always call search_masking_docs before answering documentation questions."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1 — PII detection
# ---------------------------------------------------------------------------
@mcp.tool()
def detect_pii_columns(schema: str) -> str:
    """Analyse a database schema and identify columns that likely contain PII.

    Args:
        schema: JSON string. Either a single column descriptor object OR a JSON
                array of column descriptors.  Each descriptor must have the fields:
                table_name, column_name, data_type, sample_values (list), nullable.

    Returns:
        JSON array of detection results.  Each result includes: is_pii, confidence,
        pii_category, recommended_masking_function, review_required, reasoning.
    """
    try:
        parsed: Any = json.loads(schema)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if isinstance(parsed, dict):
        results = [_detector.detect(parsed)]
    elif isinstance(parsed, list):
        results = _detector.detect_all(parsed)
    else:
        return json.dumps({"error": "schema must be a JSON object or array"})

    return json.dumps(results, indent=2)


# ---------------------------------------------------------------------------
# Tool 2 — Masking configuration generator
# ---------------------------------------------------------------------------
@mcp.tool()
def generate_masking_config(detections: str) -> str:
    """Generate a masking job configuration document from PII detection results.

    Args:
        detections: JSON string — the array returned by detect_pii_columns.

    Returns:
        JSON masking configuration with masking_rules (auto-configured columns)
        and review_queue (low-confidence columns requiring human review).
    """
    try:
        parsed: Any = json.loads(detections)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(parsed, list):
        return json.dumps({"error": "detections must be a JSON array"})

    config = _generator.generate(parsed)
    return json.dumps(config, indent=2)


# ---------------------------------------------------------------------------
# Tool 3 — Documentation RAG search
# ---------------------------------------------------------------------------
@mcp.tool()
def search_masking_docs(query: str, pii_category_filter: str = "") -> str:
    """Search the data masking documentation corpus using hybrid BM25 + vector retrieval.

    Args:
        query: Natural language question about data masking (e.g. "how to mask
               email addresses", "GDPR compliance requirements").
        pii_category_filter: Optional PII category to restrict results.
               Accepted values: FULL_NAME, EMAIL, PHONE, SSN, CREDIT_CARD,
               ACCOUNT_NUMBER, DATE_OF_BIRTH, ADDRESS, IP_ADDRESS, NATIONAL_ID.
               Leave empty to search across all categories.

    Returns:
        JSON array of the top-3 most relevant documentation chunks, each with
        fields: content, source, pii_category, score.
    """
    category = pii_category_filter.strip() or None
    chunks = retrieve(query=query, pii_category_filter=category, top_k=3)
    return json.dumps(chunks, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    transport = "sse" if "--sse" in sys.argv else "stdio"
    if transport == "sse":
        # SSE transport — useful for web-based MCP clients or local debugging
        mcp.run(transport="sse")
    else:
        # stdio transport — standard for Claude Desktop, VS Code, Cursor, etc.
        mcp.run(transport="stdio")
