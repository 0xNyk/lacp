#!/usr/bin/env python3
"""Generate an FSRS-based review queue of decaying knowledge nodes.

Loads the research registry, computes importance scores via FSRS-inspired
decay, and writes a review queue note to Obsidian _generated/.

Usage:
    python3 generate_review_queue.py                    # defaults
    python3 generate_review_queue.py --threshold 0.25   # stricter
    python3 generate_review_queue.py --max-items 100    # more items
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from sync_research_knowledge import (
    compute_importance_score,
    compute_retrieval_strength,
    compute_storage_strength,
)

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_RESEARCH_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_RESEARCH_DIR / "registry.json"
OUTPUT_DIR = Path.home() / "obsidian" / "nyk" / "_generated"
OUTPUT_FILE = OUTPUT_DIR / "review-queue.md"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        return {"version": 1, "updated_at": "", "items": {}}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "updated_at": "", "items": {}}


def generate_queue(threshold: float, max_items: int) -> dict[str, Any]:
    registry = load_registry()
    items = registry.get("items", {})
    blocked = set(registry.get("blocked_ids", []))

    if not isinstance(items, dict):
        return {"ok": False, "error": "Invalid registry"}

    scored: list[tuple[str, float, float, float, dict[str, Any]]] = []
    total_score = 0.0

    for item_id, item in items.items():
        if item_id in blocked:
            continue
        s = compute_storage_strength(item)
        r = compute_retrieval_strength(item, edge_count=0)
        score = compute_importance_score(item, edge_count=0)
        total_score += score
        if score < threshold:
            scored.append((item_id, score, s, r, item))

    # Sort by retrieval strength ascending — low R + high S = best review candidates
    scored.sort(key=lambda x: (x[3], x[1]))
    decaying = scored[:max_items]

    active_count = len(items) - len(blocked)
    avg_score = total_score / active_count if active_count else 0.0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[str] = []
    for item_id, score, s, r, item in decaying:
        last_seen = item.get("last_seen", "unknown")
        categories = ", ".join(item.get("categories", ["uncategorized"]))
        edge_count = len(item.get("edges", []))
        tip = " *" if s > 0.5 and r < 0.2 else ""
        rows.append(f"| [[{item_id}]] | {score:.4f} | S={s:.2f} | R={r:.4f} | {last_seen} | {edge_count} | {categories} |{tip}")

    note = f"""---
id: review-queue
description: FSRS-based review queue - nodes with decaying retrievability.
tags: [review, fsrs, maintenance]
---

# Review Queue

- generated_at: {now}
- total_items: {active_count}
- items_below_threshold: {len(decaying)}
- avg_retrievability: {avg_score:.4f}
- threshold: {threshold:.2f}
- tip_of_tongue: items marked * have high S but low R (best review candidates)

## Decaying Nodes

| Node | Score | Storage | Retrieval | Last Seen | Edges | Categories |
|------|-------|---------|-----------|-----------|-------|------------|
{chr(10).join(rows) if rows else "| (none) | - | - | - | - | - | - |"}
"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(note, encoding="utf-8")

    result = {
        "ok": True,
        "generated_at": now,
        "total_items": active_count,
        "items_below_threshold": len(decaying),
        "avg_retrievability": round(avg_score, 4),
        "threshold": threshold,
        "output_file": str(OUTPUT_FILE),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate FSRS-based review queue for decaying knowledge nodes.")
    parser.add_argument("--threshold", type=float, default=0.3, help="Score threshold for inclusion (default: 0.3)")
    parser.add_argument("--max-items", type=int, default=50, help="Maximum items in queue (default: 50)")
    args = parser.parse_args()

    result = generate_queue(threshold=args.threshold, max_items=args.max_items)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
