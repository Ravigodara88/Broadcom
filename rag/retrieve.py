"""Hybrid retrieval for masking documentation using sentence-transformers FAISS, rank_bm25, and RRF."""

from __future__ import annotations

from collections import defaultdict
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

try:
    from .ingest import DEFAULT_CORPUS_DIR, DocumentChunk, load_corpus
except ImportError:  # pragma: no cover - script execution fallback
    from ingest import DEFAULT_CORPUS_DIR, DocumentChunk, load_corpus


_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model: SentenceTransformer | None = None
logger = logging.getLogger(__name__)

# Per-chunk embedding cache: chunk_id -> L2-normalised float32 embedding
_emb_cache: dict[str, np.ndarray] = {}

TOKEN_RE = re.compile(r"[a-z0-9]+")
DEFAULT_EVAL_PATH = Path(__file__).with_name("eval").joinpath("masking_queries.json")

# Deterministic query rewrite hints to improve lexical matching without LLM calls.
QUERY_TERM_EXPANSIONS: dict[str, str] = {
    "ssn": "social security number",
    "dob": "date of birth",
    "pii": "personally identifiable information",
    "gdpr": "general data protection regulation",
    "ccpa": "california consumer privacy act",
    "ip": "internet protocol",
    "ipv4": "internet protocol version 4",
    "ipv6": "internet protocol version 6",
    "acct": "account number",
}

RERANK_FUSION_WEIGHT = 0.7
RERANK_KEYWORD_WEIGHT = 0.3


def _get_embed_model() -> SentenceTransformer:
    """Lazy-load the sentence-transformer model (cached at module level).

    Loading strategy for reliability:
    1) Try local cache first (no network), which works with corporate SSL limits.
    2) If local cache is missing and HF_HUB_OFFLINE is not enabled, try online.
    """
    global _embed_model
    if _embed_model is None:
        offline = _is_truthy_env(os.getenv("HF_HUB_OFFLINE", ""))

        # Suppress transformers' safetensors auto-conversion probe that can
        # trigger unnecessary HF Hub network calls in restricted environments.
        try:
            import transformers.modeling_utils as _mu  # noqa: PLC0415

            _orig_auto_conversion = _mu.auto_conversion
            _mu.auto_conversion = lambda *a, **kw: None
            _modeling_utils = _mu
        except Exception:
            _orig_auto_conversion = None
            _modeling_utils = None

        try:
            try:
                _embed_model = SentenceTransformer(_EMBED_MODEL_NAME, local_files_only=True)
                logger.info("Loaded sentence-transformer model from local cache: %s", _EMBED_MODEL_NAME)
            except Exception as local_exc:
                if offline:
                    raise RuntimeError(
                        f"Sentence-transformer model not found in local cache: {_EMBED_MODEL_NAME!r}.\n"
                        "HF_HUB_OFFLINE is enabled, so online download is disabled.\n"
                        "To cache once on a network-enabled machine, run:\n"
                        "  python -c \"from sentence_transformers import SentenceTransformer; "
                        "SentenceTransformer('all-MiniLM-L6-v2')\""
                    ) from local_exc
                logger.warning(
                    "Local model cache unavailable (%s). Falling back to online load for %s.",
                    local_exc,
                    _EMBED_MODEL_NAME,
                )
                _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
        finally:
            if _modeling_utils is not None and _orig_auto_conversion is not None:
                _modeling_utils.auto_conversion = _orig_auto_conversion
    return _embed_model


def _is_truthy_env(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_chunk_embeddings(chunks: list[DocumentChunk]) -> np.ndarray:
    """Return L2-normalised float32 embeddings for chunks, caching per chunk_id."""
    model = _get_embed_model()
    missing = [c for c in chunks if c.chunk_id not in _emb_cache]
    if missing:
        texts = [c.text for c in missing]
        new_embs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype("float32")
        for chunk, emb in zip(missing, new_embs):
            _emb_cache[chunk.chunk_id] = emb
    return np.stack([_emb_cache[c.chunk_id] for c in chunks])


def _normalize_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def _build_query_variants(query: str) -> list[str]:
    """Build deterministic query variants using acronym expansion (no LLM call)."""
    normalized = _normalize_query_text(query)
    if not normalized:
        return []

    expansions: list[str] = []
    for token in _tokenize(normalized):
        expansion = QUERY_TERM_EXPANSIONS.get(token)
        if expansion and expansion not in expansions:
            expansions.append(expansion)

    variants = [normalized]
    if expansions:
        variants.append(f"{normalized} ({'; '.join(expansions)})")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in variants:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _vector_scores_for_queries(
    query_variants: list[str],
    candidates: list[DocumentChunk],
    corpus_embeddings: np.ndarray,
) -> dict[str, float]:
    model = _get_embed_model()
    query_embeddings = model.encode(query_variants, convert_to_numpy=True, normalize_embeddings=True).astype("float32")

    dim = corpus_embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(corpus_embeddings)
    scores_arr, idx_arr = index.search(query_embeddings, len(candidates))

    vector_scores: dict[str, float] = {}
    for row_scores, row_indices in zip(scores_arr, idx_arr):
        for score, idx in zip(row_scores, row_indices):
            if idx < 0:
                continue
            chunk_id = candidates[idx].chunk_id
            current = vector_scores.get(chunk_id)
            if current is None or float(score) > current:
                vector_scores[chunk_id] = float(score)
    return vector_scores


def _bm25_scores_for_queries(query_variants: list[str], candidates: list[DocumentChunk]) -> dict[str, float]:
    tokenized_docs = [_tokenize(chunk.text) for chunk in candidates]
    bm25 = BM25Okapi(tokenized_docs)

    bm25_scores: dict[str, float] = {chunk.chunk_id: float("-inf") for chunk in candidates}
    for query_variant in query_variants:
        query_tokens = _tokenize(query_variant)
        variant_scores = bm25.get_scores(query_tokens)
        for chunk, score in zip(candidates, variant_scores):
            current = bm25_scores[chunk.chunk_id]
            if float(score) > current:
                bm25_scores[chunk.chunk_id] = float(score)
    return bm25_scores


def _keyword_overlap_score(query_tokens: set[str], text_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    overlap_count = len(query_tokens.intersection(text_tokens))
    return overlap_count / len(query_tokens)


def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    min_score = min(scores.values())
    max_score = max(scores.values())
    if max_score - min_score <= 1e-12:
        return {key: 1.0 for key in scores}
    return {key: (value - min_score) / (max_score - min_score) for key, value in scores.items()}


def _hybrid_rerank_scores(
    chunk_by_id: dict[str, DocumentChunk],
    fused_scores: dict[str, float],
    query_variants: list[str],
    *,
    fusion_weight: float = RERANK_FUSION_WEIGHT,
    keyword_weight: float = RERANK_KEYWORD_WEIGHT,
) -> tuple[dict[str, float], dict[str, float]]:
    query_tokens: set[str] = set()
    for query_variant in query_variants:
        query_tokens.update(_tokenize(query_variant))

    keyword_scores: dict[str, float] = {}
    for chunk_id, chunk in chunk_by_id.items():
        keyword_scores[chunk_id] = _keyword_overlap_score(query_tokens, set(_tokenize(chunk.text)))

    normalized_fused = _min_max_normalize(fused_scores)
    normalized_keyword = _min_max_normalize(keyword_scores)

    hybrid_scores: dict[str, float] = {}
    for chunk_id in chunk_by_id:
        hybrid_scores[chunk_id] = (
            fusion_weight * normalized_fused.get(chunk_id, 0.0)
            + keyword_weight * normalized_keyword.get(chunk_id, 0.0)
        )

    return hybrid_scores, keyword_scores


def retrieve(
    query: str,
    pii_category_filter: str | None = None,
    top_k: int = 3,
    corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks using deterministic rewrite, FAISS, BM25, RRF, and hybrid reranking."""

    query_variants = _build_query_variants(query)
    if not query_variants:
        return []

    chunks = load_corpus(corpus_dir)
    candidates = _filter_chunks(chunks, pii_category_filter)
    if not candidates:
        return []

    # --- Vector search over one or more deterministic query variants ---
    corpus_embeddings = _get_chunk_embeddings(candidates)  # (N, dim), cosine-ready
    vector_scores = _vector_scores_for_queries(query_variants, candidates, corpus_embeddings)

    # --- BM25 search across the same query variants ---
    bm25_scores = _bm25_scores_for_queries(query_variants, candidates)

    # --- RRF fusion ---
    vector_rank = _sorted_ids(vector_scores)
    bm25_rank = _sorted_ids(bm25_scores)
    fused_scores = _rrf_fuse(vector_rank, bm25_rank)

    if pii_category_filter:
        normalized_filter = pii_category_filter.upper()
        for chunk in candidates:
            if normalized_filter in chunk.pii_categories or chunk.pii_category == normalized_filter:
                fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 0.02

    chunk_by_id = {chunk.chunk_id: chunk for chunk in candidates}
    hybrid_scores, keyword_scores = _hybrid_rerank_scores(chunk_by_id, fused_scores, query_variants)

    ordered_ids = sorted(
        hybrid_scores,
        key=lambda chunk_id: (
            hybrid_scores[chunk_id],
            fused_scores.get(chunk_id, 0.0),
            vector_scores.get(chunk_id, 0.0),
            bm25_scores.get(chunk_id, 0.0),
            keyword_scores.get(chunk_id, 0.0),
        ),
        reverse=True,
    )

    # Deduplicate: return at most one chunk per source document
    seen_sources: set[str] = set()
    deduped_ids: list[str] = []
    for chunk_id in ordered_ids:
        source = chunk_by_id[chunk_id].source_file
        if source not in seen_sources:
            seen_sources.add(source)
            deduped_ids.append(chunk_id)

    results = []
    for chunk_id in deduped_ids[:top_k]:
        chunk = chunk_by_id[chunk_id]
        results.append(
            {
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "source_file": chunk.source_file,
                "section": chunk.section,
                "text": chunk.text,
                "score": round(hybrid_scores[chunk_id], 6),
                "fusion_score": round(fused_scores.get(chunk_id, 0.0), 6),
                "vector_score": round(vector_scores.get(chunk_id, 0.0), 6),
                "bm25_score": round(bm25_scores.get(chunk_id, 0.0), 6),
                "keyword_score": round(keyword_scores.get(chunk_id, 0.0), 6),
                "metadata": {
                    "pii_category": chunk.pii_category,
                    "pii_categories": list(chunk.pii_categories),
                    "anchor": chunk.anchor,
                    "source": f"{chunk.source_file}#{chunk.anchor}",
                    "query_variants": query_variants,
                },
            }
        )
    return results


def evaluate_recall_at_k(
    eval_path: Path | str = DEFAULT_EVAL_PATH,
    top_k: int = 3,
    corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
) -> dict[str, Any]:
    """Evaluate Recall@K using the configured retrieval pipeline."""

    cases = json.loads(Path(eval_path).read_text())
    hits = 0
    details = []
    for case in cases:
        results = retrieve(
            query=case["query"],
            pii_category_filter=case.get("pii_category_filter"),
            top_k=top_k,
            corpus_dir=corpus_dir,
        )
        titles = [result["title"] for result in results]
        hit = case["expected_title"] in titles
        hits += int(hit)
        details.append(
            {
                "query": case["query"],
                "pii_category_filter": case.get("pii_category_filter"),
                "expected_title": case["expected_title"],
                "returned_titles": titles,
                "hit": hit,
            }
        )

    recall = hits / len(cases) if cases else 0.0
    return {"recall_at_k": recall, "top_k": top_k, "cases": details}


def _filter_chunks(chunks: list[DocumentChunk], pii_category_filter: str | None) -> list[DocumentChunk]:
    if not pii_category_filter:
        return chunks

    normalized = pii_category_filter.upper()
    filtered = []
    for chunk in chunks:
        categories = set(chunk.pii_categories)
        if normalized in categories or chunk.pii_category == normalized or "GENERAL" in categories:
            filtered.append(chunk)
    return filtered


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _rrf_fuse(*rankings: list[str], rrf_k: int = 60) -> dict[str, float]:
    fused: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] += 1.0 / (rrf_k + position)
    return dict(fused)


def _sorted_ids(scores: dict[str, float]) -> list[str]:
    return [chunk_id for chunk_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


if __name__ == "__main__":
    report = evaluate_recall_at_k()
    print(json.dumps(report, indent=2))
