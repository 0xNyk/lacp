#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from memory_rag_lib import (
    build_sparse_query_vector,
    dot_dense,
    dot_sparse,
    lexical_overlap_score,
    normalize_weights,
    ollama_embed,
    reciprocal_rank_fusion,
    tokenize,
)


INDEX_FILE = Path.home() / "control" / "knowledge" / "knowledge-memory" / "data" / "rag" / "hybrid-index.json"


def query_index(
    query: str,
    payload: dict[str, Any],
    top_k: int,
    w_sparse: float,
    w_dense: float,
    w_lexical: float,
    ollama_host_override: str,
    ollama_model_override: str,
    ollama_timeout_s: float,
    allow_sparse_fallback: bool,
    fusion_mode: str = "rrf",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks: list[dict[str, Any]] = payload.get("chunks", [])
    idf: dict[str, float] = payload.get("idf", {})
    query_tokens = set(tokenize(query))
    sparse_query_vector = build_sparse_query_vector(query, idf)

    weights = normalize_weights({"sparse": w_sparse, "dense": w_dense, "lexical": w_lexical})

    metadata = payload.get("ollama", {}) if isinstance(payload.get("ollama"), dict) else {}
    dense_enabled = bool(metadata.get("dense_enabled")) and any("dense_vector" in c for c in chunks)
    dense_query_vector: list[float] | None = None
    dense_warning = ""

    if not dense_enabled and weights["dense"] > 0:
        weights = normalize_weights({"sparse": weights["sparse"], "dense": 0.0, "lexical": weights["lexical"]})

    if dense_enabled and weights["dense"] > 0:
        ollama_host = ollama_host_override or str(metadata.get("host") or "http://127.0.0.1:11434")
        ollama_model = ollama_model_override or str(metadata.get("model") or "nomic-embed-text:latest")
        try:
            dense_query_vector = ollama_embed([query], host=ollama_host, model=ollama_model, timeout_s=ollama_timeout_s)[0]
        except Exception as exc:
            if not allow_sparse_fallback:
                raise
            dense_warning = str(exc)
            weights = normalize_weights({"sparse": weights["sparse"], "dense": 0.0, "lexical": weights["lexical"]})

    # Score every chunk on each signal independently
    per_chunk_scores: list[dict[str, float]] = []
    for chunk in chunks:
        sparse_score = 0.0
        dense_score = 0.0
        lexical_score = lexical_overlap_score(query_tokens, chunk.get("text", ""))

        sparse_vector = chunk.get("sparse_vector", chunk.get("vector", {}))
        if weights["sparse"] > 0 and isinstance(sparse_vector, dict) and sparse_query_vector:
            sparse_score = dot_sparse(sparse_query_vector, sparse_vector)

        if weights["dense"] > 0 and dense_query_vector is not None:
            dense_vector = chunk.get("dense_vector")
            if isinstance(dense_vector, list):
                dense_score = dot_dense(dense_query_vector, [float(x) for x in dense_vector if isinstance(x, (int, float))])

        per_chunk_scores.append({
            "sparse": sparse_score,
            "dense": dense_score,
            "lexical": lexical_score,
        })

    if fusion_mode == "rrf":
        # Build ranked lists per signal (only chunks with score > 0)
        ranked_lists: dict[str, list[tuple[int, float]]] = {}
        for signal in ("sparse", "dense", "lexical"):
            if weights.get(signal, 0.0) <= 0:
                continue
            signal_ranked = [
                (i, scores[signal])
                for i, scores in enumerate(per_chunk_scores)
                if scores[signal] > 0
            ]
            signal_ranked.sort(key=lambda x: x[1], reverse=True)
            ranked_lists[signal] = signal_ranked

        fused_scores = reciprocal_rank_fusion(ranked_lists, weights)

        # RRF selects candidates; re-score top candidates with linear interpolation
        # for final ranking (combines rank-based diversity with score-based precision)
        rrf_top = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:top_k * 4]

        ranked: list[dict[str, Any]] = []
        for chunk_idx, rrf_score in rrf_top:
            scores = per_chunk_scores[chunk_idx]
            # Final score: blend RRF rank contribution with linear score
            linear_score = (
                weights["sparse"] * scores["sparse"]
                + weights["dense"] * scores["dense"]
                + weights["lexical"] * scores["lexical"]
            )
            # RRF contribution normalized to ~[0, 1] range (max RRF ~ 0.016)
            combined = 0.5 * linear_score + 0.5 * (rrf_score * 60)
            chunk = chunks[chunk_idx]
            ranked.append({
                "score": round(combined, 6),
                "rrf_score": round(rrf_score, 6),
                "sparse_score": round(scores["sparse"], 6),
                "dense_score": round(scores["dense"], 6),
                "lexical_score": round(scores["lexical"], 6),
                "path": chunk.get("path", ""),
                "heading": chunk.get("heading", ""),
                "text": chunk.get("text", ""),
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)
    else:
        # Legacy linear interpolation
        ranked = []
        for i, chunk in enumerate(chunks):
            scores = per_chunk_scores[i]
            score = (
                weights["sparse"] * scores["sparse"]
                + weights["dense"] * scores["dense"]
                + weights["lexical"] * scores["lexical"]
            )
            if score <= 0:
                continue
            ranked.append({
                "score": round(score, 6),
                "sparse_score": round(scores["sparse"], 6),
                "dense_score": round(scores["dense"], 6),
                "lexical_score": round(scores["lexical"], 6),
                "path": chunk.get("path", ""),
                "heading": chunk.get("heading", ""),
                "text": chunk.get("text", ""),
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)

    return ranked[:top_k], {"weights": weights, "dense_warning": dense_warning, "dense_enabled": dense_enabled, "fusion_mode": fusion_mode}


def _self_test() -> None:
    payload = {
        "idf": {"memory": 1.0, "task": 1.0, "other": 1.0},
        "chunks": [
            {
                "path": "control/knowledge/knowledge-memory/memory/MEMORY.md",
                "heading": "root",
                "text": "memory task context",
                "sparse_vector": {"memory": 0.8, "task": 0.6},
            },
            {
                "path": "control/knowledge/knowledge-memory/memory/OTHER.md",
                "heading": "root",
                "text": "other topic unrelated",
                "sparse_vector": {"other": 0.9},
            },
        ],
        "ollama": {"dense_enabled": False},
    }
    # Test RRF mode (default)
    results, meta = query_index(
        query="memory task",
        payload=payload,
        top_k=3,
        w_sparse=0.8,
        w_dense=0.0,
        w_lexical=0.2,
        ollama_host_override="",
        ollama_model_override="",
        ollama_timeout_s=5.0,
        allow_sparse_fallback=True,
        fusion_mode="rrf",
    )
    assert len(results) >= 1
    assert results[0]["path"].endswith("MEMORY.md")
    assert meta["weights"]["dense"] == 0.0
    assert meta["fusion_mode"] == "rrf"

    # Test linear mode (legacy)
    results_linear, meta_linear = query_index(
        query="memory task",
        payload=payload,
        top_k=3,
        w_sparse=0.8,
        w_dense=0.0,
        w_lexical=0.2,
        ollama_host_override="",
        ollama_model_override="",
        ollama_timeout_s=5.0,
        allow_sparse_fallback=True,
        fusion_mode="linear",
    )
    assert len(results_linear) >= 1
    assert results_linear[0]["path"].endswith("MEMORY.md")
    assert meta_linear["fusion_mode"] == "linear"


def main() -> int:
    parser = argparse.ArgumentParser(description="Query local hybrid memory RAG index.")
    parser.add_argument("query", type=str, nargs="?", default="")
    parser.add_argument("--index", type=str, default=str(INDEX_FILE))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--w-sparse", type=float, default=0.45)
    parser.add_argument("--w-dense", type=float, default=0.45)
    parser.add_argument("--w-lexical", type=float, default=0.10)
    parser.add_argument("--ollama-host", type=str, default="")
    parser.add_argument("--ollama-model", type=str, default="")
    parser.add_argument("--ollama-timeout", type=float, default=20.0)
    parser.add_argument("--strict-dense", action="store_true", help="Fail query if dense embedding lookup fails.")
    parser.add_argument("--fusion-mode", choices=["rrf", "linear"], default="rrf", help="Score fusion strategy (default: rrf).")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if not args.query.strip():
        raise SystemExit("query is required")

    index_path = Path(args.index)
    if not index_path.exists():
        raise SystemExit(f"index file not found: {index_path}")
    payload = json.loads(index_path.read_text())

    results, meta = query_index(
        query=args.query,
        payload=payload,
        top_k=args.top_k,
        w_sparse=args.w_sparse,
        w_dense=args.w_dense,
        w_lexical=args.w_lexical,
        ollama_host_override=args.ollama_host,
        ollama_model_override=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout,
        allow_sparse_fallback=not args.strict_dense,
        fusion_mode=args.fusion_mode,
    )

    if meta.get("dense_warning"):
        print(f"[warning] dense fallback applied: {meta['dense_warning']}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "weights": meta["weights"],
                    "dense_enabled": meta.get("dense_enabled"),
                    "results": results,
                },
                indent=2,
            )
        )
        return 0

    print(f"# Query: {args.query}\n")
    print(
        f"Weights: sparse={meta['weights']['sparse']:.2f} dense={meta['weights']['dense']:.2f} lexical={meta['weights']['lexical']:.2f}\n"
    )
    if not results:
        print("No matches.")
        return 0

    for idx, item in enumerate(results, start=1):
        path = item["path"] or "-"
        heading = item["heading"] or "root"
        text = item["text"].replace("\n", " ")
        if len(text) > 260:
            text = text[:259] + "…"
        print(
            f"{idx}. `{path}` [{heading}] score={item['score']} "
            f"(sparse={item['sparse_score']}, dense={item['dense_score']}, lexical={item['lexical_score']})"
        )
        print(f"   {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
