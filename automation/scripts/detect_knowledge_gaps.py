#!/usr/bin/env python3
"""Knowledge gap detection: find cross-category bridges and under-researched areas.

Identifies:
1. Node pairs with moderate similarity across different categories (knowledge bridges)
2. Categories with fewer than 5 signals (under-researched)
3. Suggested research questions based on gap analysis

Usage:
    python3 detect_knowledge_gaps.py              # print to stdout
    python3 detect_knowledge_gaps.py --write-note  # write to Obsidian inbox
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from semantic_dedup import cosine_similarity

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_RESEARCH_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_RESEARCH_DIR / "registry.json"
INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"

BRIDGE_THRESHOLD = 0.40
UNDER_RESEARCHED_THRESHOLD = 5
TOP_BRIDGES = 20


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        return {"version": 1, "updated_at": "", "items": {}}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "updated_at": "", "items": {}}


def find_cross_category_bridges(
    items: dict[str, dict[str, Any]],
    threshold: float = BRIDGE_THRESHOLD,
    top_k: int = TOP_BRIDGES,
) -> list[dict[str, Any]]:
    """Find node pairs with moderate similarity across different categories."""
    # Build (id, vec, categories) tuples
    nodes: list[tuple[str, list[float], set[str]]] = []
    for item_id, item in items.items():
        vec = item.get("embedding")
        if not isinstance(vec, list) or not vec:
            continue
        cats = set(item.get("categories", ["general-research"]))
        nodes.append((item_id, vec, cats))

    bridges: list[dict[str, Any]] = []
    for i in range(len(nodes)):
        id_a, vec_a, cats_a = nodes[i]
        for j in range(i + 1, len(nodes)):
            id_b, vec_b, cats_b = nodes[j]
            # Skip if they share any category
            if cats_a & cats_b:
                continue
            sim = cosine_similarity(vec_a, vec_b)
            if sim > threshold:
                bridges.append({
                    "id_a": id_a,
                    "id_b": id_b,
                    "similarity": round(sim, 4),
                    "categories_a": sorted(cats_a),
                    "categories_b": sorted(cats_b),
                    "text_a": items[id_a].get("text", "")[:100],
                    "text_b": items[id_b].get("text", "")[:100],
                })

    bridges.sort(key=lambda x: -x["similarity"])
    return bridges[:top_k]


def find_under_researched_categories(
    items: dict[str, dict[str, Any]],
    threshold: int = UNDER_RESEARCHED_THRESHOLD,
) -> list[dict[str, Any]]:
    """Find categories with fewer than threshold signals."""
    cat_counts: dict[str, int] = defaultdict(int)
    for item in items.values():
        cats = item.get("categories", ["general-research"])
        if not isinstance(cats, list):
            cats = ["general-research"]
        for cat in cats:
            cat_counts[cat] += 1

    under: list[dict[str, Any]] = []
    for cat, count in sorted(cat_counts.items()):
        if count < threshold:
            under.append({"category": cat, "count": count, "deficit": threshold - count})

    under.sort(key=lambda x: x["count"])
    return under


def find_isolated_nodes(
    items: dict[str, dict[str, Any]],
    connectivity_threshold: float = 0.55,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Find nodes with fewest connections above the similarity threshold."""
    nodes: list[tuple[str, list[float]]] = []
    for item_id, item in items.items():
        vec = item.get("embedding")
        if isinstance(vec, list) and vec:
            nodes.append((item_id, vec))

    connection_counts: dict[str, int] = {}
    for i, (id_a, vec_a) in enumerate(nodes):
        count = 0
        for j, (id_b, vec_b) in enumerate(nodes):
            if i == j:
                continue
            if cosine_similarity(vec_a, vec_b) >= connectivity_threshold:
                count += 1
        connection_counts[id_a] = count

    sorted_by_connections = sorted(connection_counts.items(), key=lambda x: x[1])
    return [
        {
            "id": item_id,
            "connections": count,
            "text": items[item_id].get("text", "")[:100],
            "categories": items[item_id].get("categories", []),
        }
        for item_id, count in sorted_by_connections[:max_results]
    ]


def render_gaps_note(
    bridges: list[dict[str, Any]],
    under_researched: list[dict[str, Any]],
    isolated: list[dict[str, Any]],
    total_items: int,
) -> str:
    """Render the knowledge gaps report as an Obsidian note."""
    now = datetime.now(UTC).strftime("%Y-%m-%d")

    bridge_lines = []
    for b in bridges:
        bridge_lines.append(
            f"| [[{b['id_a']}]] | [[{b['id_b']}]] | {b['similarity']:.2f} | "
            f"{', '.join(b['categories_a'])} | {', '.join(b['categories_b'])} |"
        )

    under_lines = []
    for u in under_researched:
        under_lines.append(f"| `{u['category']}` | {u['count']} | {u['deficit']} more needed |")

    isolated_lines = []
    for iso in isolated:
        isolated_lines.append(
            f"| [[{iso['id']}]] | {iso['connections']} | {', '.join(iso['categories'])} |"
        )

    return f"""---
type: knowledge-gaps
source: gap-detection
created: {now}
---

# Knowledge Gap Analysis

> Auto-generated by `detect_knowledge_gaps.py` on {now}.
> Analyzed {total_items} research signals.

## Cross-Category Bridges

These signals connect different knowledge domains — potential for novel insights.

| Signal A | Signal B | Similarity | Categories A | Categories B |
|----------|----------|------------|--------------|--------------|
{chr(10).join(bridge_lines) if bridge_lines else "| - | - | - | - | - |"}

## Under-Researched Areas

Categories with fewer than {UNDER_RESEARCHED_THRESHOLD} signals.

| Category | Signals | Gap |
|----------|---------|-----|
{chr(10).join(under_lines) if under_lines else "| All categories well-covered | - | - |"}

## Most Isolated Nodes

Signals with fewest semantic connections (potential orphaned knowledge).

| Signal | Connections | Categories |
|--------|-------------|------------|
{chr(10).join(isolated_lines) if isolated_lines else "| All nodes well-connected | - | - |"}

## Suggested Research Directions

Based on gap analysis:
{"".join(f"{chr(10)}- Deepen research in `{u['category']}` (only {u['count']} signals)" for u in under_researched)}
{"".join(f"{chr(10)}- Explore connection between `{b['categories_a'][0]}` and `{b['categories_b'][0]}` (bridge similarity: {b['similarity']:.2f})" for b in bridges[:5])}

## Notes
- Bridge threshold: {BRIDGE_THRESHOLD} cosine similarity across different categories
- Under-researched threshold: < {UNDER_RESEARCHED_THRESHOLD} signals per category
- Run with `--write-note` to save to Obsidian inbox
"""


def run(write_note: bool) -> dict[str, Any]:
    registry = load_registry()
    items = registry.get("items", {})
    if not isinstance(items, dict):
        return {"ok": False, "error": "Invalid registry"}

    bridges = find_cross_category_bridges(items)
    under_researched = find_under_researched_categories(items)
    isolated = find_isolated_nodes(items)

    result: dict[str, Any] = {
        "ok": True,
        "total_items": len(items),
        "cross_category_bridges": len(bridges),
        "under_researched_categories": len(under_researched),
        "isolated_nodes": len(isolated),
    }

    note_content = render_gaps_note(bridges, under_researched, isolated, len(items))

    if write_note:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC).strftime("%Y-%m-%d")
        note_path = INBOX_DIR / f"knowledge-gaps-{now}.md"
        note_path.write_text(note_content, encoding="utf-8")
        result["note_path"] = str(note_path)
    else:
        print(note_content)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect knowledge gaps in research graph.")
    parser.add_argument("--write-note", action="store_true", help="Write gaps report to Obsidian inbox.")
    args = parser.parse_args()

    result = run(write_note=args.write_note)
    print(json.dumps({k: v for k, v in result.items() if k != "note_content"}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
