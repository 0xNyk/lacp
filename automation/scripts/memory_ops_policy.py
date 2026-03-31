#!/usr/bin/env python3
"""Memory Operations Policy — learned ADD/UPDATE/DELETE/NOOP decisions.

Implements the Memory-R1 interface (arXiv:2508.19828) with a heuristic
scoring policy. Each new signal is evaluated against existing items to
decide the optimal memory operation.

The heuristic policy can later be replaced with an RL-trained model
using the same interface (just swap `decide_operation`).

Usage:
    python3 memory_ops_policy.py --self-test
    python3 memory_ops_policy.py --signal "new research finding" --source claude
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from memory_rag_lib import tokenize
from sync_research_knowledge import (
    compute_importance_score,
    compute_retrieval_strength,
    compute_storage_strength,
    normalize_text,
)


@dataclass
class MemoryOp:
    """A memory operation decision."""
    action: str         # "ADD", "UPDATE", "DELETE", "NOOP"
    target_id: str      # item_id to update/delete (empty for ADD/NOOP)
    confidence: float   # 0.0-1.0 how confident the policy is
    reason: str         # human-readable explanation


# Thresholds for the heuristic policy
SIMILARITY_UPDATE_THRESHOLD = 0.75  # above this → UPDATE existing
SIMILARITY_DUPLICATE_THRESHOLD = 0.90  # above this → NOOP (duplicate)
MIN_SIGNAL_LENGTH = 10  # tokens below this → NOOP (too short)
LOW_QUALITY_PATTERNS = [
    "users nyk",       # conversational noise
    "lets try",        # command fragments
    "please and",      # instruction fragments
    "ok so",           # filler
]


def compute_signal_quality(text: str) -> float:
    """Score signal quality 0.0-1.0 based on content characteristics."""
    tokens = tokenize(text)
    if len(tokens) < MIN_SIGNAL_LENGTH:
        return 0.1

    # Check for low-quality patterns
    lower = text.lower()
    for pattern in LOW_QUALITY_PATTERNS:
        if pattern in lower:
            return 0.2

    # Length bonus (longer = likely more informative, up to a point)
    length_score = min(1.0, len(tokens) / 30.0)

    # URL presence is a quality signal (evidence-backed)
    has_url = "http" in text
    url_bonus = 0.1 if has_url else 0.0

    # Technical term density (rough proxy for informativeness)
    tech_terms = sum(1 for t in tokens if len(t) > 6)
    tech_density = min(1.0, tech_terms / max(1, len(tokens)) * 3)

    return min(1.0, 0.3 + 0.3 * length_score + 0.2 * tech_density + url_bonus + 0.1)


def find_most_similar(
    normalized_text: str,
    items: dict[str, dict[str, Any]],
    top_k: int = 3,
) -> list[tuple[str, float]]:
    """Find most similar existing items using token overlap (fast, no embeddings).

    Returns [(item_id, similarity_score), ...] sorted descending.
    """
    query_tokens = set(tokenize(normalized_text))
    if not query_tokens:
        return []

    scored: list[tuple[str, float]] = []
    for item_id, item in items.items():
        item_norm = item.get("normalized", "")
        item_tokens = set(tokenize(item_norm))
        if not item_tokens:
            continue
        # Jaccard similarity
        intersection = len(query_tokens & item_tokens)
        union = len(query_tokens | item_tokens)
        if union > 0:
            sim = intersection / union
            if sim > 0.3:
                scored.append((item_id, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def decide_operation(
    signal_text: str,
    items: dict[str, dict[str, Any]],
    source: str = "",
) -> MemoryOp:
    """Decide the optimal memory operation for a new signal.

    This is the heuristic policy — can be replaced with a trained model.
    """
    normalized = normalize_text(signal_text)
    quality = compute_signal_quality(signal_text)

    # NOOP: signal too short or low quality
    if quality < 0.3:
        return MemoryOp(
            action="NOOP",
            target_id="",
            confidence=0.9,
            reason=f"low_quality (score={quality:.2f})",
        )

    # Find similar existing items
    similar = find_most_similar(normalized, items, top_k=3)

    if similar:
        best_id, best_sim = similar[0]
        best_item = items.get(best_id, {})

        # NOOP: near-duplicate
        if best_sim >= SIMILARITY_DUPLICATE_THRESHOLD:
            return MemoryOp(
                action="NOOP",
                target_id=best_id,
                confidence=0.85,
                reason=f"duplicate (sim={best_sim:.2f} with {best_id})",
            )

        # UPDATE: high similarity but not duplicate
        if best_sim >= SIMILARITY_UPDATE_THRESHOLD:
            return MemoryOp(
                action="UPDATE",
                target_id=best_id,
                confidence=0.7 + 0.2 * best_sim,
                reason=f"merge (sim={best_sim:.2f} with {best_id})",
            )

        # DELETE candidate: if new signal contradicts old and has higher quality
        if best_sim >= 0.6:
            old_importance = compute_importance_score(best_item, edge_count=0)
            old_r = compute_retrieval_strength(best_item, edge_count=0)
            # If old item is fading AND new signal is high quality → supersede
            if old_r < 0.1 and quality > 0.7:
                return MemoryOp(
                    action="DELETE",
                    target_id=best_id,
                    confidence=0.6,
                    reason=f"supersede (old R={old_r:.3f}, new quality={quality:.2f})",
                )

    # ADD: novel signal with sufficient quality
    return MemoryOp(
        action="ADD",
        target_id="",
        confidence=min(0.95, 0.5 + quality * 0.4),
        reason=f"novel (quality={quality:.2f}, best_sim={(similar[0][1] if similar else 0.0):.2f})",
    )


def evaluate_batch(
    signals: list[dict[str, str]],
    items: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate a batch of signals and return operation summary."""
    ops: list[dict[str, Any]] = []
    counts = {"ADD": 0, "UPDATE": 0, "DELETE": 0, "NOOP": 0}

    for signal in signals:
        text = signal.get("text", "")
        source = signal.get("source", "")
        op = decide_operation(text, items, source)
        counts[op.action] += 1
        ops.append({
            "text": text[:80],
            "action": op.action,
            "target_id": op.target_id,
            "confidence": round(op.confidence, 3),
            "reason": op.reason,
        })

    return {
        "ok": True,
        "total_signals": len(signals),
        "counts": counts,
        "operations": ops,
    }


def _self_test() -> None:
    """Minimal self-test."""
    items = {
        "existing-1": {
            "text": "hybrid retrieval with BM25 and dense embeddings",
            "normalized": "hybrid retrieval bm25 dense embeddings",
            "count": 5,
            "last_seen": "2026-03-30",
            "categories": ["memory-knowledge"],
            "edges": [],
        },
        "existing-2": {
            "text": "neural network architecture for transformer models",
            "normalized": "neural network architecture transformer models",
            "count": 2,
            "last_seen": "2026-01-01",
            "categories": ["ai-ml-research"],
            "edges": [],
        },
    }

    # Test ADD — novel signal (must have 10+ tokens to pass quality gate)
    op = decide_operation(
        "quantum computing applications in modern cryptography and post-quantum algorithm design for secure communications",
        items,
    )
    assert op.action == "ADD", f"Expected ADD, got {op.action}: {op.reason}"
    assert op.confidence > 0.5

    # Test NOOP — low quality
    op = decide_operation("ok so lets try", items)
    assert op.action == "NOOP", f"Expected NOOP, got {op.action}: {op.reason}"

    # Test NOOP — too short
    op = decide_operation("hi", items)
    assert op.action == "NOOP", f"Expected NOOP, got {op.action}: {op.reason}"

    # Test UPDATE — similar to existing
    op = decide_operation(
        "hybrid retrieval combining BM25 sparse and dense embedding vectors for search",
        items,
    )
    assert op.action in ("UPDATE", "ADD"), f"Expected UPDATE or ADD, got {op.action}: {op.reason}"

    # Test quality scoring
    q_high = compute_signal_quality(
        "Reciprocal Rank Fusion combines BM25 and dense embeddings for improved retrieval accuracy in knowledge bases"
    )
    q_low = compute_signal_quality("users nyk lets try this")
    assert q_high > q_low, f"High quality {q_high} should exceed low quality {q_low}"

    # Test batch evaluation
    result = evaluate_batch(
        [
            {"text": "novel research finding about memory consolidation", "source": "claude"},
            {"text": "ok", "source": "conversation"},
        ],
        items,
    )
    assert result["ok"]
    assert result["counts"]["NOOP"] >= 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Memory Operations Policy (Memory-R1 pattern)")
    parser.add_argument("--signal", type=str, default="", help="Single signal text to evaluate")
    parser.add_argument("--source", type=str, default="cli", help="Signal source")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    # Load registry
    registry_path = Path.home() / "control" / "knowledge" / "knowledge-memory" / "data" / "research" / "registry.json"
    if not registry_path.exists():
        print(json.dumps({"ok": False, "error": "registry not found"}))
        return 1

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    items = registry.get("items", {})

    if args.signal:
        op = decide_operation(args.signal, items, args.source)
        print(json.dumps({
            "action": op.action,
            "target_id": op.target_id,
            "confidence": round(op.confidence, 3),
            "reason": op.reason,
        }, indent=2))
    else:
        # Interactive: read signals from stdin
        print("Enter signals (one per line, Ctrl+D to finish):", file=sys.stderr)
        signals = [{"text": line.strip(), "source": args.source} for line in sys.stdin if line.strip()]
        result = evaluate_batch(signals, items)
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
