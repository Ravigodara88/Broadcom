"""Tool wrappers and tracking for the Schema Intelligence Agent."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any, Iterator

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "pii-detector"))
sys.path.insert(0, str(ROOT_DIR / "masking-generator"))
sys.path.insert(0, str(ROOT_DIR))

from detector import PiiDetector
from generator import MaskingConfigGenerator
from rag.retrieve import retrieve


_DETECTOR = PiiDetector()
_GENERATOR = MaskingConfigGenerator()
_TRACKERS: list["ToolCallTracker"] = []


@dataclass
class ToolCallTracker:
    """Collects tool invocations during a unit of agent work."""

    called_tools: list[str] = field(default_factory=list)


@contextmanager
def tool_call_tracker() -> Iterator[ToolCallTracker]:
    tracker = ToolCallTracker()
    _TRACKERS.append(tracker)
    try:
        yield tracker
    finally:
        _TRACKERS.remove(tracker)


def detect_pii_columns(schema: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Run the detector over a schema list or a single column descriptor."""

    _record_tool_call("detect_pii_columns")
    if isinstance(schema, dict):
        return [_DETECTOR.detect(schema)]
    return _DETECTOR.detect_all(schema)


def generate_masking_config(detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a masking configuration from detector output."""

    _record_tool_call("generate_masking_config")
    return _GENERATOR.generate(detections)


def search_masking_docs(query: str, pii_category_filter: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
    """Search the masking documentation corpus."""

    _record_tool_call("search_masking_docs")
    return retrieve(query=query, pii_category_filter=pii_category_filter, top_k=top_k)


def _record_tool_call(tool_name: str) -> None:
    for tracker in _TRACKERS:
        tracker.called_tools.append(tool_name)
