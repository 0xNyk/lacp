#!/usr/bin/env python3
"""Obsidian vault optimization engine.

Reads vault metrics (node count, registry size, orphan ratio, taxonomy categories)
and computes optimal plugin settings based on size-aware profiles.

Usage:
    python3 optimize_obsidian_config.py --dry-run
    python3 optimize_obsidian_config.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


VAULT_ROOT = Path(os.environ.get("LACP_OBSIDIAN_VAULT", Path.home() / "obsidian" / "nyk"))
KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_RESEARCH_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_RESEARCH_DIR / "registry.json"
TAXONOMY_FILE = DATA_RESEARCH_DIR / "taxonomy.json"

CONFIG_DIR = Path.home() / "control" / "frameworks" / "lacp" / "config" / "obsidian"
PROFILES_FILE = CONFIG_DIR / "optimization-profiles.json"
PLUGIN_SETTINGS_FILE = CONFIG_DIR / "plugin-settings.json"

PLUGINS_DIR = VAULT_ROOT / ".obsidian" / "plugins"
GRAPH_JSON = VAULT_ROOT / ".obsidian" / "graph.json"

# Graph filter: paths to exclude from the graph view
GRAPH_SEARCH_EXCLUDES = [
    "-path:knowledge/data/sandbox-runs",
    "-path:knowledge/data/benchmarks",
    "-path:knowledge/data/quality",
    "-path:knowledge/data/swarms",
    "-path:knowledge/data/remote-smoke",
    "-path:.smart-env",
    "-path:_generated/extractions",
    "-path:_generated/sessions",
]

# Predefined color palette for taxonomy categories (hex -> rgb int)
CATEGORY_COLORS: dict[str, int] = {
    "memory-knowledge": 0x9B59B6,
    "agent-orchestration": 0xE74C3C,
    "claude-codex-optimization": 0x3498DB,
    "security-governance": 0xE57373,
    "product-market-competitors": 0xFFD54F,
    "infra-performance": 0x81C784,
    "solana-defi-trading": 0x55EFC4,
    "web3-blockchain": 0x6C5CE7,
    "ai-ml-research": 0xBA68C8,
    "frontend-design": 0xFF7043,
    "devtools-workflow": 0x64B5F6,
    "content-writing": 0x8D6E63,
    "startup-business": 0xFFB300,
    "marketing-outreach": 0xAED581,
    "quantitative-finance": 0x4DB6AC,
    "data-engineering": 0x607D8B,
    "automation-ops": 0x78909C,
    "prediction-markets": 0x26A69A,
    "privacy-identity": 0x7986CB,
    "general-research": 0x90A4AE,
}


def load_json(path: Path) -> Any:
    """Load JSON from path, return empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def count_vault_notes(vault: Path) -> int:
    """Count .md files in vault (follows symlinks via os.walk)."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(vault, followlinks=True):
        rel = os.path.relpath(dirpath, vault)
        # Skip hidden dirs and .obsidian
        parts = rel.split(os.sep)
        if any(part.startswith(".") for part in parts if part != "."):
            continue
        # Prune hidden subdirs from further traversal
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if f.endswith(".md"):
                count += 1
    return count


def gather_metrics(vault: Path) -> dict[str, Any]:
    """Gather vault metrics for profile selection."""
    note_count = count_vault_notes(vault)

    registry = load_json(REGISTRY_FILE)
    items = registry.get("items", {})
    registry_count = len(items) if isinstance(items, dict) else 0

    # Orphan ratio: items without edges / total
    orphan_count = 0
    if isinstance(items, dict):
        for item in items.values():
            if not isinstance(item, dict):
                continue
            edges = item.get("edges", item.get("related_signals", []))
            if not edges:
                orphan_count += 1
    orphan_ratio = orphan_count / max(registry_count, 1)

    taxonomy = load_json(TAXONOMY_FILE)
    rules = taxonomy.get("classification", {}).get("category_rules", [])
    categories = [r["name"] for r in rules if isinstance(r, dict) and "name" in r]

    return {
        "note_count": note_count,
        "registry_count": registry_count,
        "orphan_count": orphan_count,
        "orphan_ratio": round(orphan_ratio, 3),
        "category_count": len(categories),
        "categories": categories,
    }


def select_profile(note_count: int) -> tuple[str, dict[str, Any]]:
    """Select optimization profile based on node count."""
    profiles = load_json(PROFILES_FILE)
    if not profiles:
        # Fallback defaults
        profiles = {
            "small": {"max_nodes": 200, "graph_physics": {"repelStrength": 300, "linkDistance": 100, "linkStrength": 0.3, "centerStrength": 0.25}, "dataview_refresh_ms": 10000},
            "medium": {"max_nodes": 1000, "graph_physics": {"repelStrength": 500, "linkDistance": 150, "linkStrength": 0.2, "centerStrength": 0.18}, "dataview_refresh_ms": 30000},
            "large": {"max_nodes": None, "graph_physics": {"repelStrength": 800, "linkDistance": 200, "linkStrength": 0.1, "centerStrength": 0.12}, "dataview_refresh_ms": 60000},
        }

    if note_count < profiles.get("small", {}).get("max_nodes", 200):
        return "small", profiles["small"]
    if note_count < (profiles.get("medium", {}).get("max_nodes", 1000) or 1000):
        return "medium", profiles["medium"]
    return "large", profiles["large"]


def build_graph_color_groups(categories: list[str]) -> list[dict[str, Any]]:
    """Build graph color groups from taxonomy categories."""
    groups: list[dict[str, Any]] = []
    for cat in categories:
        rgb = CATEGORY_COLORS.get(cat, 0x90A4AE)
        groups.append({
            "query": f"path:knowledge/graph/research/topic-{cat}",
            "color": {"a": 1, "rgb": rgb},
        })
    return groups


def compute_graph_settings(
    profile: dict[str, Any],
    categories: list[str],
) -> dict[str, Any]:
    """Compute optimal graph.json settings."""
    physics = profile.get("graph_physics", {})
    color_groups = build_graph_color_groups(categories)

    return {
        "collapse-filter": False,
        "search": " ".join(GRAPH_SEARCH_EXCLUDES),
        "showTags": True,
        "showAttachments": False,
        "hideUnresolved": True,
        "showOrphans": False,
        "colorGroups": color_groups,
        "collapse-display": True,
        "showArrow": True,
        "textFadeMultiplier": -2,
        "nodeSizeMultiplier": 1.05,
        "lineSizeMultiplier": 0.9,
        "collapse-forces": True,
        "centerStrength": physics.get("centerStrength", 0.15),
        "repelStrength": physics.get("repelStrength", 800),
        "linkStrength": physics.get("linkStrength", 0.1),
        "linkDistance": physics.get("linkDistance", 200),
        "close": True,
    }


def compute_plugin_changes(
    profile: dict[str, Any],
    profile_name: str,
) -> dict[str, dict[str, Any]]:
    """Compute per-plugin setting changes based on profile."""
    base = load_json(PLUGIN_SETTINGS_FILE)
    refresh_ms = profile.get("dataview_refresh_ms", 30000)

    changes: dict[str, dict[str, Any]] = {}

    # Dataview
    dv_settings = dict(base.get("dataview", {}))
    dv_settings["refreshInterval"] = refresh_ms
    dv_settings["enableDataviewJs"] = True
    dv_settings["enableInlineDataviewJs"] = True
    changes["dataview"] = dv_settings

    # Linter
    linter_settings = dict(base.get("obsidian-linter", {}))
    changes["obsidian-linter"] = linter_settings

    # Git
    git_settings = dict(base.get("obsidian-git", {}))
    changes["obsidian-git"] = git_settings

    # Homepage
    hp_settings = dict(base.get("homepage", {}))
    changes["homepage"] = hp_settings

    # Templater
    tp_settings = dict(base.get("templater-obsidian", {}))
    changes["templater-obsidian"] = tp_settings

    # Extended graph (only if plugin installed)
    if (PLUGINS_DIR / "extended-graph").is_dir():
        eg_settings = dict(base.get("extended-graph", {}))
        changes["extended-graph"] = eg_settings

    return changes


def merge_plugin_settings(plugin_name: str, new_settings: dict[str, Any]) -> dict[str, Any]:
    """Read existing plugin data.json, deep-merge new settings, return merged."""
    data_file = PLUGINS_DIR / plugin_name / "data.json"
    existing = load_json(data_file)

    def deep_merge(base: dict, overlay: dict) -> dict:
        result = dict(base)
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    return deep_merge(existing, new_settings)


def apply_changes(
    graph_settings: dict[str, Any],
    plugin_changes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Write optimized settings to disk."""
    written: list[str] = []

    # Write graph.json — merge with existing to preserve user scale/position
    existing_graph = load_json(GRAPH_JSON)
    merged_graph = dict(existing_graph)
    merged_graph.update(graph_settings)
    GRAPH_JSON.write_text(json.dumps(merged_graph, indent=2) + "\n", encoding="utf-8")
    written.append(str(GRAPH_JSON))

    # Write plugin data.json files
    for plugin_name, new_settings in plugin_changes.items():
        merged = merge_plugin_settings(plugin_name, new_settings)
        data_file = PLUGINS_DIR / plugin_name / "data.json"
        if not data_file.parent.is_dir():
            continue
        data_file.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        written.append(str(data_file))

    return {"written_files": written, "count": len(written)}


def run_optimization(apply: bool) -> dict[str, Any]:
    """Main optimization pipeline."""
    metrics = gather_metrics(VAULT_ROOT)
    profile_name, profile = select_profile(metrics["note_count"])

    graph_settings = compute_graph_settings(profile, metrics["categories"])
    plugin_changes = compute_plugin_changes(profile, profile_name)

    result: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "vault": str(VAULT_ROOT),
        "profile": profile_name,
        "metrics": metrics,
    }

    if apply:
        write_result = apply_changes(graph_settings, plugin_changes)
        result["applied"] = write_result
    else:
        result["proposed_graph"] = graph_settings
        result["proposed_plugins"] = {
            name: merge_plugin_settings(name, settings)
            for name, settings in plugin_changes.items()
        }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Obsidian vault optimization engine — auto-configure plugins based on vault size.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview proposed changes without writing.")
    parser.add_argument("--apply", action="store_true", help="Write optimized settings to plugin data.json files.")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1

    result = run_optimization(apply=args.apply)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
