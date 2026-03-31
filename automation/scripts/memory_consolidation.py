#!/usr/bin/env python3
"""Sleep-cycle memory consolidation: prune weak signals and merge redundant clusters.

Extends consolidate_research.py with pruning (forget gate) and merge detection.
Weak, disconnected signals are archived; tight clusters are flagged for merging.

Includes mycelium-inspired exploratory tendril protection: frontier nodes in
active categories are shielded from pruning to preserve exploration pathways.

Usage:
    python3 memory_consolidation.py --dry-run
    python3 memory_consolidation.py --apply
    python3 memory_consolidation.py --apply --config /path/to/config.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from consolidate_research import (
    GRAPH_RESEARCH_DIR,
    SYNTHESIS_DIR,
    cluster_fingerprint,
    cluster_items_by_category,
    find_clusters_within_category,
    load_consolidation_state,
    load_registry,
    save_consolidation_state,
)
from semantic_dedup import cosine_similarity
from sync_research_knowledge import (
    compute_importance_score,
    compute_related_signals,
    compute_retrieval_strength,
    compute_storage_strength,
    find_articulation_points,
)

import os

DEFAULT_CONFIG_PATH = Path.home() / "control" / "frameworks" / "lacp" / "config" / "consolidation.json"
ARCHIVE_DIR = Path(os.environ.get("LACP_OBSIDIAN_VAULT", str(Path.home() / "obsidian" / "vault"))) / "inbox" / "archive"
PROBE_DIR = Path.home() / "control" / "knowledge" / "knowledge-memory" / "data" / "probes"

DEFAULT_CONFIG: dict[str, Any] = {
    "cluster_threshold": 0.75,
    "merge_threshold": 0.80,
    "min_cluster_size": 3,
    "prune_r_threshold": 0.1,
    "prune_s_threshold": 0.3,
    "prune_edge_threshold": 0.5,
    "max_prune_per_run": 50,
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load consolidation config with fallback defaults."""
    path = config_path or DEFAULT_CONFIG_PATH
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def load_latest_probe_results() -> dict[str, dict[str, Any]]:
    """Load most recent active recall probe results, keyed by item_id."""
    if not PROBE_DIR.exists():
        return {}
    probe_files = sorted(PROBE_DIR.glob("probe-*.json"), reverse=True)
    if not probe_files:
        return {}
    try:
        data = json.loads(probe_files[0].read_text(encoding="utf-8"))
        return {p["item_id"]: p for p in data.get("probes", []) if isinstance(p, dict) and "item_id" in p}
    except (json.JSONDecodeError, KeyError):
        return {}


def detect_conflicts(
    items: dict[str, dict[str, Any]],
    related_map: dict[str, list[tuple[str, float, str]]],
    similarity_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Detect conflicting items — high similarity but potentially contradictory.

    SleepGate pattern: items with cosine > threshold that have different
    sources or different event times may represent conflicting information.
    Returns pairs with resolution recommendation.
    """
    conflicts: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for item_id, related in related_map.items():
        item = items.get(item_id, {})
        for rel_id, sim, _edge_type in related:
            if sim < similarity_threshold:
                continue
            pair_key = tuple(sorted([item_id, rel_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            rel_item = items.get(rel_id, {})
            # Check for temporal or source divergence
            item_event = item.get("event_time", item.get("first_seen", ""))
            rel_event = rel_item.get("event_time", rel_item.get("first_seen", ""))
            item_conf = (item.get("provenance") or {}).get("confidence", 0.7)
            rel_conf = (rel_item.get("provenance") or {}).get("confidence", 0.7)

            # Resolve: newer event_time wins when confidence is similar;
            # higher confidence wins when event times are similar
            if item_event > rel_event:
                winner, loser = item_id, rel_id
                reason = "newer_event"
            elif rel_event > item_event:
                winner, loser = rel_id, item_id
                reason = "newer_event"
            elif item_conf > rel_conf:
                winner, loser = item_id, rel_id
                reason = "higher_confidence"
            elif rel_conf > item_conf:
                winner, loser = rel_id, item_id
                reason = "higher_confidence"
            else:
                winner, loser = item_id, rel_id
                reason = "tie_keep_first"

            conflicts.append({
                "winner": winner,
                "loser": loser,
                "similarity": round(sim, 4),
                "reason": reason,
                "winner_event": item_event if winner == item_id else rel_event,
                "loser_event": rel_event if winner == item_id else item_event,
            })

    return conflicts


def apply_forgetting_gate(
    items: dict[str, dict[str, Any]],
    prune_candidates: list[str],
    probe_results: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Enhanced forgetting gate using Active Recall Probe results.

    Items that are both low-importance AND unretrievable are strong
    candidates for archival. Items that are unretrievable but important
    get protected (they need index rebuild, not pruning).
    """
    probe_accelerated: list[str] = []  # unretrievable + low importance → fast-track prune
    probe_protected: list[str] = []     # unretrievable + high importance → protect

    remaining = []
    for item_id in prune_candidates:
        probe = probe_results.get(item_id, {})
        if probe.get("status") == "CRITICAL_RETRIEVAL_GAP":
            importance = probe.get("importance", 0)
            if importance < 0.4:
                probe_accelerated.append(item_id)
            else:
                probe_protected.append(item_id)
                continue
        remaining.append(item_id)

    # Accelerated items go to the front of the prune list
    return probe_accelerated + remaining, probe_protected


def run_consolidation(apply: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Run sleep-cycle memory consolidation.

    Steps:
      1. Cluster items by category using existing infrastructure
      2. Identify merge candidates (tight clusters >merge_threshold)
      3. Identify prune candidates (low importance, no strong edges)
      4. Archive pruned items
      5. Return summary
    """
    registry = load_registry()
    items = registry.get("items", {})
    if not isinstance(items, dict):
        return {"ok": False, "error": "Invalid registry"}

    cluster_threshold = float(config.get("cluster_threshold", 0.75))
    merge_threshold = float(config.get("merge_threshold", 0.80))
    min_cluster_size = int(config.get("min_cluster_size", 3))
    prune_r_threshold = float(config.get("prune_r_threshold", 0.1))
    prune_s_threshold = float(config.get("prune_s_threshold", 0.3))
    prune_edge_threshold = float(config.get("prune_edge_threshold", 0.5))
    max_prune_per_run = int(config.get("max_prune_per_run", 50))

    # Step 1: Cluster items by category
    by_cat = cluster_items_by_category(items)

    # Compute related signals and edge counts for importance scoring
    _related, edge_counts = compute_related_signals(items)

    all_clusters: list[dict[str, Any]] = []
    merge_candidates: list[dict[str, Any]] = []

    for category, item_ids in sorted(by_cat.items()):
        clusters = find_clusters_within_category(item_ids, items, threshold=cluster_threshold)
        for cluster in clusters:
            if len(cluster) < min_cluster_size:
                continue
            fp = cluster_fingerprint(cluster)
            cluster_info = {
                "category": category,
                "item_ids": cluster,
                "size": len(cluster),
                "fingerprint": fp,
            }
            all_clusters.append(cluster_info)

            # Step 2: Merge candidates — clusters with 3+ nodes >merge_threshold
            tight_clusters = find_clusters_within_category(
                cluster, items, threshold=merge_threshold,
            )
            for tight in tight_clusters:
                if len(tight) >= min_cluster_size:
                    merge_candidates.append({
                        "category": category,
                        "item_ids": tight,
                        "size": len(tight),
                        "fingerprint": cluster_fingerprint(tight),
                    })

    # Step 3: Prune candidates — low importance, no strong incoming edges
    prune_candidates: list[str] = []
    items_with_embeddings = {
        iid: item for iid, item in items.items()
        if isinstance(item.get("embedding"), list) and item["embedding"]
    }

    for item_id, item in items_with_embeddings.items():
        ec = edge_counts.get(item_id, 0)
        importance = compute_importance_score(item, edge_count=ec)

        # Check if any strong incoming edges exist
        has_strong_edge = False
        related_list = _related.get(item_id, [])
        for _rel_id, sim, _edge_type in related_list:
            if sim > prune_edge_threshold:
                has_strong_edge = True
                break

        if has_strong_edge:
            continue

        # Dual-strength model check
        storage_strength = compute_storage_strength(item)
        retrieval_strength = compute_retrieval_strength(item, edge_count=ec)

        if (
            storage_strength < prune_s_threshold
            and retrieval_strength < prune_r_threshold
        ):
            prune_candidates.append(item_id)

    # Dreaming consolidation: detect conflicts (SleepGate pattern)
    conflicts = detect_conflicts(items, _related, similarity_threshold=merge_threshold)

    # Dreaming consolidation: forgetting gate with probe results
    probe_results = load_latest_probe_results()
    prune_candidates, probe_protected = apply_forgetting_gate(
        items, prune_candidates, probe_results,
    )

    # Mark conflict losers as superseded (don't prune, but mark)
    superseded_ids: list[str] = []
    if apply and conflicts:
        for conflict in conflicts:
            loser_id = conflict["loser"]
            if loser_id in items:
                items[loser_id]["supersedes"] = conflict["winner"]
                superseded_ids.append(loser_id)

    # Respect max_prune_per_run
    prune_candidates = prune_candidates[:max_prune_per_run]

    # Bridge protection: prevent pruning articulation points
    articulation_points = find_articulation_points(items)
    bridge_protected: list[str] = []
    non_bridge_prune: list[str] = []
    for item_id in prune_candidates:
        if item_id in articulation_points:
            bridge_protected.append(item_id)
        else:
            non_bridge_prune.append(item_id)
    prune_candidates = non_bridge_prune

    # Mycelium-inspired exploratory tendril protection:
    # Frontier nodes (few edges) in active categories get a grace period.
    category_activity: dict[str, int] = {}
    for item in items.values():
        for cat in (item.get("categories") or []):
            category_activity[cat] = category_activity.get(cat, 0) + int(item.get("count", 0))
    activity_values = sorted(category_activity.values()) if category_activity else [0]
    median_activity = activity_values[len(activity_values) // 2]

    active_categories = {cat for cat, act in category_activity.items() if act > median_activity}

    protected_tendrils: list[str] = []
    surviving_prune: list[str] = []
    for item_id in prune_candidates:
        ec = edge_counts.get(item_id, 0)
        item_cats = set(items.get(item_id, {}).get("categories") or [])
        if ec <= 2 and item_cats & active_categories:
            protected_tendrils.append(item_id)
        else:
            surviving_prune.append(item_id)
    prune_candidates = surviving_prune

    pruned_ids: set[str] = set()
    archived_files: list[str] = []

    if apply and prune_candidates:
        # Step 4: Archive pruned items
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        for item_id in prune_candidates:
            source = GRAPH_RESEARCH_DIR / f"{item_id}.md"
            if source.exists():
                dest = ARCHIVE_DIR / f"{item_id}.md"
                shutil.move(str(source), str(dest))
                archived_files.append(str(dest))
            pruned_ids.add(item_id)

        # Update consolidation state with prune record
        state = load_consolidation_state()
        prune_record = {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "pruned_ids": sorted(pruned_ids),
            "count": len(pruned_ids),
        }
        prune_history = state.get("prune_history", [])
        if not isinstance(prune_history, list):
            prune_history = []
        prune_history.append(prune_record)
        state["prune_history"] = prune_history
        state["last_prune"] = prune_record["timestamp"]
        save_consolidation_state(state)

    # Step 5: Return summary
    result: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "total_items": len(items),
        "total_clusters": len(all_clusters),
        "merge_candidates": len(merge_candidates),
        "prune_candidates": len(prune_candidates),
        "pruned": len(pruned_ids),
        "archived_files": len(archived_files),
        "protected_tendrils": len(protected_tendrils),
        "bridge_protected": len(bridge_protected),
        # Dreaming consolidation metrics
        "conflicts_detected": len(conflicts),
        "superseded": len(superseded_ids),
        "probe_protected": len(probe_protected),
        "probe_coverage": len(probe_results),
    }

    if not apply:
        result["merge_preview"] = [
            {
                "category": m["category"],
                "size": m["size"],
                "fingerprint": m["fingerprint"],
                "sample_ids": m["item_ids"][:3],
            }
            for m in merge_candidates[:10]
        ]
        result["prune_preview"] = [
            {
                "item_id": iid,
                "text": items.get(iid, {}).get("text", "")[:80],
            }
            for iid in prune_candidates[:15]
        ]
        result["bridge_preview"] = [
            {
                "item_id": iid,
                "text": items.get(iid, {}).get("text", "")[:80],
            }
            for iid in bridge_protected[:10]
        ]
        result["tendril_preview"] = [
            {
                "item_id": iid,
                "text": items.get(iid, {}).get("text", "")[:80],
                "categories": items.get(iid, {}).get("categories", []),
            }
            for iid in protected_tendrils[:10]
        ]
        result["conflict_preview"] = [
            {
                "winner": c["winner"],
                "loser": c["loser"],
                "similarity": c["similarity"],
                "reason": c["reason"],
            }
            for c in conflicts[:10]
        ]
        if probe_protected:
            result["probe_protected_preview"] = [
                {
                    "item_id": iid,
                    "text": items.get(iid, {}).get("text", "")[:80],
                }
                for iid in probe_protected[:10]
            ]

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sleep-cycle memory consolidation: prune and merge research signals.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview prune/merge candidates without changes.")
    parser.add_argument("--apply", action="store_true", help="Archive pruned items and record state.")
    parser.add_argument("--config", type=str, default=None, help="Path to consolidation config JSON.")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    result = run_consolidation(apply=args.apply, config=config)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
