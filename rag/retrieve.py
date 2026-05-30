"""Hybrid retrieval for masking documentation using TF-IDF, BM25, and RRF."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
from typing import Any

try:
    from .ingest import DEFAULT_CORPUS_DIR, DocumentChunk, load_corpus
except ImportError:  # pragma: no cover - script execution fallback
    from ingest import DEFAULT_CORPUS_DIR, DocumentChunk, load_corpus


TOKEN_RE = re.compile(r"[a-z0-9]+")
DEFAULT_EVAL_PATH = Path(__file__).with_name("eval").joinpath("masking_queries.json")


def retrieve(
    query: str,
    pii_category_filter: str | None = None,
    top_k: int = 3,
    corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks using vector similarity, BM25, and RRF."""

    chunks = load_corpus(corpus_dir)
    candidates = _filter_chunks(chunks, pii_category_filter)
    if not candidates:
        return []

    query_tokens = _tokenize(query)
    vector_scores = _vector_scores(query_tokens, candidates)
    bm25_scores = _bm25_scores(query_tokens, candidates)

    vector_rank = _sorted_ids(vector_scores)
    bm25_rank = _sorted_ids(bm25_scores)
    fused_scores = _rrf_fuse(vector_rank, bm25_rank)
    if pii_category_filter:
        normalized_filter = pii_category_filter.upper()
        for chunk in candidates:
            if normalized_filter in chunk.pii_categories or chunk.pii_category == normalized_filter:
                fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 0.02

    chunk_by_id = {chunk.chunk_id: chunk for chunk in candidates}
    ordered_ids = sorted(
        fused_scores,
        key=lambda chunk_id: (
            fused_scores[chunk_id],
            vector_scores.get(chunk_id, 0.0),
            bm25_scores.get(chunk_id, 0.0),
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
                "score": round(fused_scores[chunk_id], 6),
                "vector_score": round(vector_scores.get(chunk_id, 0.0), 6),
                "bm25_score": round(bm25_scores.get(chunk_id, 0.0), 6),
                "metadata": {
                    "pii_category": chunk.pii_category,
                    "pii_categories": list(chunk.pii_categories),
                    "anchor": chunk.anchor,
                    "source": f"{chunk.source_file}#{chunk.anchor}",
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


def _vector_scores(query_tokens: list[str], chunks: list[DocumentChunk]) -> dict[str, float]:
    doc_tokens = [_tokenize(chunk.text) for chunk in chunks]
    doc_freq: Counter[str] = Counter()
    for tokens in doc_tokens:
        doc_freq.update(set(tokens))

    total_docs = len(chunks)
    idf = {
        token: math.log((1 + total_docs) / (1 + frequency)) + 1.0
        for token, frequency in doc_freq.items()
    }

    query_vector = _tfidf_vector(query_tokens, idf)
    query_norm = _vector_norm(query_vector)

    scores: dict[str, float] = {}
    for chunk, tokens in zip(chunks, doc_tokens):
        doc_vector = _tfidf_vector(tokens, idf)
        denominator = query_norm * _vector_norm(doc_vector)
        if denominator == 0:
            scores[chunk.chunk_id] = 0.0
            continue
        scores[chunk.chunk_id] = _dot_product(query_vector, doc_vector) / denominator
    return scores


def _bm25_scores(query_tokens: list[str], chunks: list[DocumentChunk]) -> dict[str, float]:
    tokenized_docs = [_tokenize(chunk.text) for chunk in chunks]
    avg_doc_len = sum(len(tokens) for tokens in tokenized_docs) / max(1, len(tokenized_docs))
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        doc_freq.update(set(tokens))

    total_docs = len(chunks)
    k1 = 1.5
    b = 0.75
    scores: dict[str, float] = {}

    for chunk, tokens in zip(chunks, tokenized_docs):
        tf = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0
        for token in query_tokens:
            if token not in tf:
                continue
            df = doc_freq[token]
            idf = math.log(((total_docs - df + 0.5) / (df + 0.5)) + 1.0)
            numerator = tf[token] * (k1 + 1)
            denominator = tf[token] + k1 * (1 - b + b * (doc_len / avg_doc_len))
            score += idf * (numerator / denominator)
        scores[chunk.chunk_id] = score
    return scores


def _rrf_fuse(*rankings: list[str], rrf_k: int = 60) -> dict[str, float]:
    fused: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] += 1.0 / (rrf_k + position)
    return dict(fused)


def _sorted_ids(scores: dict[str, float]) -> list[str]:
    return [chunk_id for chunk_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {token: (count / total) * idf.get(token, 0.0) for token, count in counts.items()}


def _vector_norm(vector: dict[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def _dot_product(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


if __name__ == "__main__":
    report = evaluate_recall_at_k()
    print(json.dumps(report, indent=2))
