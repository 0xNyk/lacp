#!/usr/bin/env python3
"""Memory consolidation gate: cluster similar promoted research signals and
generate canonical synthesis notes via local Ollama LLM.

Inspired by Complementary Learning Systems (CLS) theory — fast episodic capture
(raw signals) gets consolidated into slow semantic memory (insight notes).

Usage:
    python3 consolidate_research.py --dry-run          # preview clusters
    python3 consolidate_research.py --apply            # generate synthesis notes
    python3 consolidate_research.py --apply --weekly-gate
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from semantic_dedup import cosine_similarity

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_RESEARCH_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_RESEARCH_DIR / "registry.json"
GRAPH_RESEARCH_DIR = KNOWLEDGE_ROOT / "graph" / "research"
SYNTHESIS_DIR = GRAPH_RESEARCH_DIR / "synthesis"
CONSOLIDATION_STATE_FILE = DATA_RESEARCH_DIR / "consolidation-state.json"

OLLAMA_HOST = "http://localhost:11434"
SUMMARIZE_MODEL = "llama3.1:8b"
CLUSTER_SIMILARITY_THRESHOLD = 0.70
MIN_CLUSTER_SIZE = 3


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        return {"version": 1, "updated_at": "", "items": {}}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "updated_at": "", "items": {}}


def load_consolidation_state() -> dict[str, Any]:
    if not CONSOLIDATION_STATE_FILE.exists():
        return {"version": 2, "consolidated_clusters": [], "last_run": "", "notes": {}}
    try:
        return json.loads(CONSOLIDATION_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 2, "consolidated_clusters": [], "last_run": "", "notes": {}}


def save_consolidation_state(state: dict[str, Any]) -> None:
    DATA_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONSOLIDATION_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(CONSOLIDATION_STATE_FILE)


def cluster_items_by_category(
    items: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Group item IDs by their primary category."""
    by_cat: dict[str, list[str]] = defaultdict(list)
    for item_id, item in items.items():
        cats = item.get("categories", ["general-research"])
        if not isinstance(cats, list) or not cats:
            cats = ["general-research"]
        by_cat[cats[0]].append(item_id)
    return dict(by_cat)


def load_promoted_items(items: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Use only promoted research nodes (materialized research-*.md files)."""
    if not GRAPH_RESEARCH_DIR.exists():
        return {}
    promoted_ids: set[str] = set()
    for path in GRAPH_RESEARCH_DIR.glob("research-*.md"):
        promoted_ids.add(path.stem)
    return {item_id: item for item_id, item in items.items() if item_id in promoted_ids}


def find_clusters_within_category(
    item_ids: list[str],
    items: dict[str, dict[str, Any]],
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> list[list[str]]:
    """Single-linkage clustering within a category using cosine similarity."""
    # Build adjacency list
    adjacency: dict[str, set[str]] = defaultdict(set)
    id_list = [iid for iid in item_ids if items.get(iid, {}).get("embedding")]

    for i, id_a in enumerate(id_list):
        vec_a = items[id_a]["embedding"]
        for j in range(i + 1, len(id_list)):
            id_b = id_list[j]
            vec_b = items[id_b]["embedding"]
            sim = cosine_similarity(vec_a, vec_b)
            if sim >= threshold:
                adjacency[id_a].add(id_b)
                adjacency[id_b].add(id_a)

    # Connected components via BFS
    visited: set[str] = set()
    clusters: list[list[str]] = []
    for node in id_list:
        if node in visited:
            continue
        component: list[str] = []
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(component) >= MIN_CLUSTER_SIZE:
            clusters.append(sorted(component))

    return clusters


def cluster_fingerprint(cluster: list[str]) -> str:
    """Deterministic fingerprint for a cluster to track consolidation state."""
    import hashlib
    joined = "|".join(sorted(cluster))
    return hashlib.sha1(joined.encode()).hexdigest()[:16]


def parse_iso_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def ollama_generate(prompt: str, model: str = SUMMARIZE_MODEL) -> str:
    """Generate text via local Ollama."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 512},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        obj = json.loads(raw)
        return obj.get("response", "").strip()
    except Exception as e:
        return f"[LLM error: {e}]"


def generate_insight(cluster_items: list[dict[str, Any]], category: str) -> str:
    """Generate a distilled insight from a cluster of related signals."""
    signal_texts = []
    for item in cluster_items[:10]:  # Cap at 10 to stay within context
        signal_texts.append(f"- {item.get('text', '')}")
    signals_block = "\n".join(signal_texts)

    prompt = f"""You are a research analyst distilling knowledge from multiple related research signals.

Category: {category}

Research signals in this cluster:
{signals_block}

Write a concise insight (3-5 sentences) that captures the key pattern or finding across these signals. Focus on:
1. What is the common theme?
2. What is the actionable takeaway?
3. What connections exist between these signals?

Write only the insight text, no preamble."""

    return ollama_generate(prompt)


def render_synthesis_note(
    cluster_ids: list[str],
    items: dict[str, dict[str, Any]],
    category: str,
    insight_text: str,
    fingerprint: str,
) -> str:
    """Render a canonical synthesis note in Obsidian format."""
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    source_links = [f"- [[{cid}]]" for cid in cluster_ids]
    topic = category.replace("-", " ")

    return f"""---
type: synthesis
source: consolidation
category: {category}
topic: {topic}
created: {now}
cluster_id: {fingerprint}
---

# Canonical Synthesis: {category}

## Insight
{insight_text}

## Source Signals
{chr(10).join(source_links)}

## Key Patterns
- Cluster size: {len(cluster_ids)} signals
- Category: `{category}`
- Generated: {now}

## Notes
- Auto-generated by `consolidate_research.py` from {len(cluster_ids)} semantically similar promoted research signals.
- This note represents consolidated semantic memory from episodic captures.
"""


def render_synthesis_index(records: list[dict[str, Any]], generated_at: str) -> str:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_category[str(rec.get("category", "general-research"))].append(rec)

    lines = [
        "---",
        "id: synthesis-index",
        "description: Index of canonical synthesis notes generated from clustered research signals.",
        "---",
        "",
        "# Research Synthesis Index",
        "",
        f"- generated_at: {generated_at}",
        f"- notes: {len(records)}",
        "",
        "## Categories",
    ]
    if not records:
        lines.append("- None")
        lines.append("")
        return "\n".join(lines)

    for category in sorted(by_category):
        lines.extend(["", f"### {category}"])
        cat_records = sorted(by_category[category], key=lambda r: int(r.get("size", 0)), reverse=True)
        for rec in cat_records:
            lines.append(
                f"- [[synthesis/{rec['note_stem']}]] "
                f"(size={rec.get('size', 0)}, cluster={str(rec.get('fingerprint', ''))[:8]})"
            )
    lines.append("")
    return "\n".join(lines)


def run(apply: bool, weekly_gate: bool = False, min_days_between_runs: int = 6) -> dict[str, Any]:
    registry = load_registry()
    items = registry.get("items", {})
    if not isinstance(items, dict):
        return {"ok": False, "error": "Invalid registry"}

    promoted_items = load_promoted_items(items)

    state = load_consolidation_state()
    already_done = set(state.get("consolidated_clusters", []))
    notes_state = state.get("notes", {})
    if not isinstance(notes_state, dict):
        notes_state = {}

    if weekly_gate:
        now = datetime.now(UTC)
        last_run = parse_iso_utc(str(state.get("last_run", "")))
        if last_run is not None and (now - last_run).days < min_days_between_runs:
            return {
                "ok": True,
                "mode": "skipped",
                "reason": "weekly-gate",
                "days_since_last_run": (now - last_run).days,
                "min_days_between_runs": min_days_between_runs,
                "promoted_items": len(promoted_items),
            }

    # Cluster within each category
    by_cat = cluster_items_by_category(promoted_items)
    all_clusters: list[dict[str, Any]] = []
    new_clusters: list[dict[str, Any]] = []

    for category, item_ids in sorted(by_cat.items()):
        clusters = find_clusters_within_category(item_ids, items)
        for cluster in clusters:
            fp = cluster_fingerprint(cluster)
            cluster_info = {
                "category": category,
                "item_ids": cluster,
                "size": len(cluster),
                "fingerprint": fp,
                "already_consolidated": fp in already_done,
            }
            all_clusters.append(cluster_info)
            if fp not in already_done:
                new_clusters.append(cluster_info)

    result: dict[str, Any] = {
        "ok": True,
        "total_items": len(items),
        "categories_with_clusters": len(set(c["category"] for c in all_clusters)),
        "total_clusters": len(all_clusters),
        "new_clusters": len(new_clusters),
        "already_consolidated": len(all_clusters) - len(new_clusters),
    }

    if not apply:
        # Dry run — show cluster analysis
        result["mode"] = "dry-run"
        result["cluster_preview"] = [
            {
                "category": c["category"],
                "size": c["size"],
                "fingerprint": c["fingerprint"],
                "sample_texts": [
                    promoted_items[iid].get("text", "")[:80] for iid in c["item_ids"][:3]
                ],
            }
            for c in new_clusters[:15]
        ]
        return result

    # Apply — generate synthesis notes and write graph index
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
    notes_created = 0
    consolidated_fps: list[str] = list(already_done)
    synthesis_records: list[dict[str, Any]] = []

    for cluster in new_clusters:
        category = cluster["category"]
        cluster_ids = cluster["item_ids"]
        fp = cluster["fingerprint"]

        cluster_items = [promoted_items[iid] for iid in cluster_ids if iid in promoted_items]
        insight_text = generate_insight(cluster_items, category)

        note_content = render_synthesis_note(
            cluster_ids, promoted_items, category, insight_text, fp,
        )

        note_filename = f"synthesis-{category}-{fp[:8]}.md"
        note_path = SYNTHESIS_DIR / note_filename
        note_path.write_text(note_content, encoding="utf-8")

        notes_state[fp] = {
            "category": category,
            "note_stem": note_path.stem,
            "size": len(cluster_ids),
            "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        synthesis_records.append(
            {
                "category": category,
                "fingerprint": fp,
                "note_stem": note_path.stem,
                "size": len(cluster_ids),
            }
        )
        consolidated_fps.append(fp)
        notes_created += 1

    # Include previously known notes in index even if no new clusters
    for fp, payload in notes_state.items():
        if not isinstance(payload, dict):
            continue
        note_stem = str(payload.get("note_stem", ""))
        if not note_stem:
            continue
        note_path = SYNTHESIS_DIR / f"{note_stem}.md"
        if not note_path.exists():
            continue
        synthesis_records.append(
            {
                "category": str(payload.get("category", "general-research")),
                "fingerprint": fp,
                "note_stem": note_stem,
                "size": int(payload.get("size", 0)),
            }
        )

    # De-duplicate records by note stem.
    unique_records: list[dict[str, Any]] = []
    seen_stems: set[str] = set()
    for rec in synthesis_records:
        stem = str(rec.get("note_stem", "")).strip()
        if not stem or stem in seen_stems:
            continue
        seen_stems.add(stem)
        unique_records.append(rec)

    index_path = SYNTHESIS_DIR / "index.md"
    index_path.write_text(
        render_synthesis_index(unique_records, datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")),
        encoding="utf-8",
    )

    # Update state
    state["consolidated_clusters"] = sorted(set(consolidated_fps))
    state["notes"] = notes_state
    state["last_run"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    save_consolidation_state(state)

    result["mode"] = "apply"
    result["notes_created"] = notes_created
    result["promoted_items"] = len(promoted_items)
    result["synthesis_dir"] = str(SYNTHESIS_DIR)
    result["index_path"] = str(index_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidate research signals into distilled insight notes."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview clusters without generating notes.")
    parser.add_argument("--apply", action="store_true", help="Generate insight notes for new clusters.")
    parser.add_argument("--weekly-gate", action="store_true", help="Skip apply if consolidation ran recently.")
    parser.add_argument("--min-days-between-runs", type=int, default=6, help="Minimum days between weekly gate runs.")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1

    result = run(
        apply=args.apply,
        weekly_gate=args.weekly_gate,
        min_days_between_runs=max(1, int(args.min_days_between_runs)),
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
