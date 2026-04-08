#!/usr/bin/env python3
"""Active Recall Probes — test actual retrievability of knowledge items.

Implements the TFC-SR pattern: instead of estimating decay with FSRS alone,
actively probe the RAG index to see if each important item can actually be found.
Items that are important but unretrievable get flagged as CRITICAL_RETRIEVAL_GAP
and boosted in the review queue.

Usage:
    python3 active_recall_probes.py                          # dry-run
    python3 active_recall_probes.py --apply                  # write results
    python3 active_recall_probes.py --threshold 0.3 --top-k 8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from memory_rag_lib import tokenize
from query_memory_rag import query_index
from sync_research_knowledge import (
    compute_importance_score,
    compute_retrieval_strength,
    compute_storage_strength,
)

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
REGISTRY_FILE = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"
INDEX_FILE = KNOWLEDGE_ROOT / "data" / "rag" / "hybrid-index.json"
OUTPUT_DIR = KNOWLEDGE_ROOT / "data" / "probes"

# Probe configuration
DEFAULT_TOP_K = 8
DEFAULT_IMPORTANCE_THRESHOLD = 0.3
DEFAULT_W_SPARSE = 0.45
DEFAULT_W_DENSE = 0.45
DEFAULT_W_LEXICAL = 0.10


def build_probe_query(item: dict[str, Any]) -> str:
    """Build a natural-language probe query from an item's text.

    Extracts the most distinctive tokens to form a query that should
    retrieve this item if the RAG index is working correctly.
    """
    text = item.get("text", "")
    if not text:
        return ""

    # Use normalized text if available, fall back to raw
    normalized = item.get("normalized", text)

    # Truncate to reasonable query length
    tokens = tokenize(normalized)
    if len(tokens) <= 8:
        return " ".join(tokens)

    # Take first 4 + last 4 tokens for diversity (captures topic + specifics)
    return " ".join(tokens[:4] + tokens[-4:])


def probe_item(
    item_id: str,
    item: dict[str, Any],
    payload: dict[str, Any],
    top_k: int,
    w_sparse: float,
    w_dense: float,
    w_lexical: float,
) -> dict[str, Any]:
    """Probe a single knowledge item against the RAG index.

    Returns probe result with retrievability score.
    """
    query = build_probe_query(item)
    if not query:
        return {
            "item_id": item_id,
            "status": "skip",
            "reason": "empty_query",
        }

    results, meta = query_index(
        query=query,
        payload=payload,
        top_k=top_k,
        w_sparse=w_sparse,
        w_dense=w_dense,
        w_lexical=w_lexical,
        ollama_host_override="",
        ollama_model_override="",
        ollama_timeout_s=20.0,
        allow_sparse_fallback=True,
        fusion_mode="rrf",
    )

    # Check if any result matches this item's expected paths
    # Items materialize as research-{id}.md files
    expected_stems = {item_id, f"research-{item_id}"}
    # Also check category MOCs that should reference this item
    categories = item.get("categories", [])
    for cat in categories:
        expected_stems.add(f"category-{cat}")

    hit_rank = None
    for rank, result in enumerate(results, start=1):
        result_path = result.get("path", "")
        result_stem = Path(result_path).stem
        # Check if result text contains substantial overlap with item text
        if result_stem in expected_stems:
            hit_rank = rank
            break
        # Also check text overlap — the item's text might be in a chunk
        item_tokens = set(tokenize(item.get("text", "")))
        result_tokens = set(tokenize(result.get("text", "")))
        if item_tokens and result_tokens:
            overlap = len(item_tokens & result_tokens) / len(item_tokens)
            if overlap >= 0.5:
                hit_rank = rank
                break

    retrievability = 1.0 if hit_rank is not None else 0.0
    # Partial credit for late hits
    if hit_rank is not None and hit_rank > 3:
        retrievability = 0.5

    if retrievability == 0.0:
        status = "CRITICAL_RETRIEVAL_GAP"
    elif retrievability < 1.0:
        status = "WEAK_RETRIEVAL"
    else:
        status = "OK"

    return {
        "item_id": item_id,
        "status": status,
        "query": query,
        "hit_rank": hit_rank,
        "retrievability": retrievability,
        "top_result_path": results[0]["path"] if results else "",
        "top_result_score": results[0]["score"] if results else 0.0,
    }


def run_probes(
    importance_threshold: float,
    top_k: int,
    w_sparse: float,
    w_dense: float,
    w_lexical: float,
    max_items: int,
    index_path: Path,
) -> dict[str, Any]:
    """Run active recall probes across all important knowledge items."""
    if not REGISTRY_FILE.exists():
        return {"ok": False, "error": f"Registry not found: {REGISTRY_FILE}"}
    if not index_path.exists():
        return {"ok": False, "error": f"Index not found: {index_path}"}

    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    items = registry.get("items", {})
    blocked = set(registry.get("blocked_ids", []))

    # Score all items and select those above importance threshold
    candidates: list[tuple[str, float, dict[str, Any]]] = []
    for item_id, item in items.items():
        if item_id in blocked:
            continue
        edge_count = len(item.get("edges", []))
        importance = compute_importance_score(item, edge_count=edge_count)
        if importance >= importance_threshold:
            candidates.append((item_id, importance, item))

    # Sort by importance descending — probe most important first
    candidates.sort(key=lambda x: x[1], reverse=True)
    if max_items > 0:
        candidates = candidates[:max_items]

    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    for item_id, importance, item in candidates:
        probe = probe_item(
            item_id=item_id,
            item=item,
            payload=payload,
            top_k=top_k,
            w_sparse=w_sparse,
            w_dense=w_dense,
            w_lexical=w_lexical,
        )
        probe["importance"] = round(importance, 4)
        probe["storage_strength"] = round(compute_storage_strength(item), 4)
        probe["retrieval_strength"] = round(
            compute_retrieval_strength(item, edge_count=len(item.get("edges", []))),
            4,
        )
        results.append(probe)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Aggregate
    probed = [r for r in results if r.get("status") != "skip"]
    critical = [r for r in probed if r["status"] == "CRITICAL_RETRIEVAL_GAP"]
    weak = [r for r in probed if r["status"] == "WEAK_RETRIEVAL"]
    ok = [r for r in probed if r["status"] == "OK"]

    success_rate = len(ok) / len(probed) if probed else 0.0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Category distribution of failures
    gap_by_category: dict[str, int] = {}
    for r in critical:
        item = items.get(r["item_id"], {})
        for cat in item.get("categories", ["uncategorized"]):
            gap_by_category[cat] = gap_by_category.get(cat, 0) + 1

    return {
        "ok": True,
        "timestamp": now,
        "elapsed_ms": round(elapsed_ms, 1),
        "total_registry_items": len(items),
        "items_above_threshold": len(candidates),
        "items_probed": len(probed),
        "items_skipped": len(results) - len(probed),
        "retrieval_ok": len(ok),
        "retrieval_weak": len(weak),
        "retrieval_critical": len(critical),
        "success_rate": round(success_rate, 4),
        "gap_by_category": gap_by_category,
        "critical_items": [
            {"id": r["item_id"], "importance": r["importance"], "query": r["query"]}
            for r in critical[:20]
        ],
        "probes": results,
    }


def write_results(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _self_test() -> None:
    """Minimal self-test."""
    item = {
        "text": "hybrid retrieval with BM25 and dense embeddings improves recall",
        "normalized": "hybrid retrieval bm25 dense embeddings improves recall",
        "count": 3,
        "last_seen": "2026-03-30",
        "categories": ["memory-knowledge"],
        "edges": [],
    }
    query = build_probe_query(item)
    assert len(query) > 0
    tokens = tokenize(query)
    assert len(tokens) >= 4

    # Test with empty item
    empty_probe = probe_item(
        "test-empty",
        {"text": ""},
        {"chunks": [], "idf": {}, "ollama": {"dense_enabled": False}},
        top_k=5,
        w_sparse=0.45,
        w_dense=0.45,
        w_lexical=0.10,
    )
    assert empty_probe["status"] == "skip"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Active Recall Probes — test actual retrievability of knowledge items."
    )
    parser.add_argument("--index", type=str, default=str(INDEX_FILE))
    parser.add_argument("--threshold", type=float, default=DEFAULT_IMPORTANCE_THRESHOLD)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--w-sparse", type=float, default=DEFAULT_W_SPARSE)
    parser.add_argument("--w-dense", type=float, default=DEFAULT_W_DENSE)
    parser.add_argument("--w-lexical", type=float, default=DEFAULT_W_LEXICAL)
    parser.add_argument("--apply", action="store_true", help="Write results to disk.")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    report = run_probes(
        importance_threshold=args.threshold,
        top_k=args.top_k,
        w_sparse=args.w_sparse,
        w_dense=args.w_dense,
        w_lexical=args.w_lexical,
        max_items=args.max_items,
        index_path=Path(args.index),
    )

    if args.apply and report.get("ok"):
        if args.output:
            out_path = Path(args.output)
        else:
            tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out_path = OUTPUT_DIR / f"probe-{tag}.json"
        write_results(report, out_path)
        report["output_file"] = str(out_path)

    # Print summary (without full probe list for readability)
    summary = {k: v for k, v in report.items() if k != "probes"}
    print(json.dumps(summary, indent=2))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
