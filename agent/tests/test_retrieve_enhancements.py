"""Regression tests for deterministic query rewrite and hybrid reranking."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from rag.ingest import DocumentChunk
import rag.retrieve as retrieval


class _FakeEmbedModel:
    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        count = len(texts)
        return np.tile(np.array([[1.0, 0.0]], dtype="float32"), (count, 1))


def _chunk(chunk_id: str, text: str, source_file: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        title="Test Doc",
        source_file=source_file,
        section="Overview",
        text=text,
        pii_category="GENERAL",
        pii_categories=("GENERAL",),
        anchor="overview",
    )


def test_query_variants_expand_common_acronyms() -> None:
    variants = retrieval._build_query_variants("How to mask SSN and DOB under GDPR?")

    assert variants[0] == "How to mask SSN and DOB under GDPR?"
    assert len(variants) == 2
    expanded = variants[1].lower()
    assert "social security number" in expanded
    assert "date of birth" in expanded
    assert "general data protection regulation" in expanded


def test_hybrid_reranking_prefers_keyword_overlap_when_fusion_ties() -> None:
    chunk_by_id = {
        "chunk-a": _chunk(
            "chunk-a",
            "social security number masking keeps last 4 digits and format.",
            "a.md",
        ),
        "chunk-b": _chunk(
            "chunk-b",
            "name randomization replaces names with realistic alternatives.",
            "b.md",
        ),
    }
    fused_scores = {"chunk-a": 1.0, "chunk-b": 1.0}

    hybrid_scores, keyword_scores = retrieval._hybrid_rerank_scores(
        chunk_by_id,
        fused_scores,
        ["How should I mask SSN values?", "How should I mask SSN values? (social security number)"],
    )

    assert keyword_scores["chunk-a"] > keyword_scores["chunk-b"]
    assert hybrid_scores["chunk-a"] > hybrid_scores["chunk-b"]


def test_retrieve_uses_query_variants_and_hybrid_reranking(monkeypatch) -> None:
    candidates = [
        _chunk("chunk-a", "social security number masking and last four behavior", "a.md"),
        _chunk("chunk-b", "full name masking with random replacement", "b.md"),
    ]

    monkeypatch.setattr(retrieval, "load_corpus", lambda _: candidates)
    monkeypatch.setattr(
        retrieval,
        "_get_chunk_embeddings",
        lambda chunks: np.array([[1.0, 0.0], [1.0, 0.0]], dtype="float32"),
    )
    monkeypatch.setattr(retrieval, "_get_embed_model", lambda: _FakeEmbedModel())
    monkeypatch.setattr(retrieval, "_rrf_fuse", lambda *args, **kwargs: {"chunk-a": 1.0, "chunk-b": 1.0})

    results = retrieval.retrieve("How should I mask SSN values?", top_k=2)

    assert len(results) == 2
    assert results[0]["chunk_id"] == "chunk-a"
    assert results[0]["keyword_score"] > results[1]["keyword_score"]
    query_variants = results[0]["metadata"]["query_variants"]
    assert any("social security number" in variant.lower() for variant in query_variants)
