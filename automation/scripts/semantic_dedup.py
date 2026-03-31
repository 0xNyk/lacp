#!/usr/bin/env python3
"""Semantic dedup helper for research signals.

Uses local Ollama embeddings to detect semantically similar research signals
that text-based SHA-1 dedup would miss. Sits on top of the existing fast-path
dedup — only invoked for signals that pass the text fingerprint check.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Reuse the existing Ollama embedding infrastructure
sys.path.insert(0, str(Path(__file__).parent))
from memory_rag_lib import dot_dense, ollama_embed  # noqa: E402

OLLAMA_HOST = "http://localhost:11434"
EMBED_MODEL = "mxbai-embed-large"


def compute_embedding(text: str) -> list[float]:
    """Compute a dense embedding vector for a single text string.

    Returns an empty list if Ollama is unreachable or errors out.
    """
    if not text.strip():
        return []
    try:
        vectors = ollama_embed([text], host=OLLAMA_HOST, model=EMBED_MODEL, timeout_s=15.0)
        if vectors and len(vectors) == 1:
            return vectors[0]
    except Exception:
        return []
    return []


def compute_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Compute embeddings for multiple texts in batches.

    Returns list of vectors (empty list for any text that fails).
    """
    results: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_clean = [t if t.strip() else "empty" for t in batch]
        try:
            vectors = ollama_embed(batch_clean, host=OLLAMA_HOST, model=EMBED_MODEL, timeout_s=30.0)
            if vectors and len(vectors) == len(batch_clean):
                results.extend(vectors)
            else:
                results.extend([] for _ in batch_clean)
        except Exception:
            results.extend([] for _ in batch_clean)
    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors.

    Since ollama_embed returns L2-normalized vectors, this is just a dot product.
    Returns 0.0 if either vector is empty.
    """
    if not a or not b:
        return 0.0
    return dot_dense(a, b)


def find_semantic_duplicates(
    new_text: str,
    existing_items: dict[str, dict[str, Any]],
    threshold: float = 0.85,
    top_k: int = 3,
) -> list[tuple[str, float]]:
    """Find existing registry items semantically similar to new_text.

    Args:
        new_text: The normalized text of the new signal.
        existing_items: Registry items dict (item_id -> item data).
        threshold: Minimum cosine similarity to consider a match.
        top_k: Maximum number of matches to return.

    Returns:
        List of (item_id, similarity_score) tuples, sorted by score descending.
        Returns empty list if Ollama is unreachable (graceful fallback).
    """
    new_vec = compute_embedding(new_text)
    if not new_vec:
        return []

    scored: list[tuple[str, float]] = []
    for item_id, item in existing_items.items():
        if not isinstance(item, dict):
            continue
        cached_vec = item.get("embedding")
        if not isinstance(cached_vec, list) or not cached_vec:
            continue
        sim = cosine_similarity(new_vec, cached_vec)
        if sim >= threshold:
            scored.append((item_id, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _self_test() -> None:
    """Quick inline validation."""
    # Test cosine_similarity
    assert cosine_similarity([], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-6

    # Test compute_embedding (requires Ollama running)
    vec = compute_embedding("optimize claude context window")
    if vec:
        assert len(vec) > 0, "Expected non-empty vector"
        # Two semantically similar texts should have high similarity
        vec2 = compute_embedding("claude context optimization best practices")
        if vec2:
            sim = cosine_similarity(vec, vec2)
            assert sim > 0.5, f"Expected similar texts to have sim > 0.5, got {sim}"
            print(f"  semantic similarity (same topic): {sim:.4f}")

        # Two unrelated texts should have lower similarity
        vec3 = compute_embedding("cooking pasta recipe italian food")
        if vec3:
            sim_unrelated = cosine_similarity(vec, vec3)
            print(f"  semantic similarity (unrelated):  {sim_unrelated:.4f}")
            assert sim_unrelated < sim, "Unrelated text should be less similar"

    # Test find_semantic_duplicates with empty items
    matches = find_semantic_duplicates("test text", {})
    assert matches == []

    print("self-test passed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Semantic dedup helper for research signals.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        raise SystemExit(0)
