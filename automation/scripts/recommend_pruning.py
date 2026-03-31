#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

import tomllib


ROOT = Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent)))
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
RECOMMEND_DIR = ROOT / "data" / "recommendations"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


PROTECTED_MCP_SERVERS = {"github", "context7", "chrome-devtools", "rust-analyzer"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_recent_snapshots(limit: int) -> list[dict[str, Any]]:
    files = sorted(SNAPSHOT_DIR.glob("snapshot-*.json"))
    selected = files[-limit:] if limit > 0 else files
    return [load_json(path) for path in selected]


def load_codex_mcp_servers() -> list[str]:
    with CODEX_CONFIG.open("rb") as fh:
        data = tomllib.load(fh)
    mcp_servers = data.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        return []
    return sorted(mcp_servers.keys())


def load_claude_plugins() -> dict[str, bool]:
    data = json.loads(CLAUDE_SETTINGS.read_text())
    raw = data.get("enabledPlugins", {})
    if not isinstance(raw, dict):
        return {}
    return {k: bool(v) for k, v in raw.items()}


def build_mcp_recommendations(snapshots: list[dict[str, Any]], servers: list[str]) -> list[dict[str, Any]]:
    usage = defaultdict(int)
    for snap in snapshots:
        codex_sessions = (
            snap.get("usage", {})
            .get("codex_sessions", {})
        )
        usage_map = codex_sessions.get("mcp_server_usage", {})
        if isinstance(usage_map, dict):
            for name, count in usage_map.items():
                if isinstance(name, str) and isinstance(count, int):
                    usage[name] += count
            continue

        # Backward compatibility with earlier snapshot schema.
        for item in codex_sessions.get("top_mcp_servers", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            count = item.get("count")
            if isinstance(name, str) and isinstance(count, int):
                usage[name] += count

    recs: list[dict[str, Any]] = []
    sample_count = len(snapshots)
    for server in servers:
        count = usage.get(server, 0)
        if count > 0:
            recs.append(
                {
                    "target_type": "codex_mcp_server",
                    "target": server,
                    "action": "keep_enabled",
                    "confidence": 0.99,
                    "reason": f"Used {count} times across last {sample_count} snapshots",
                }
            )
            continue

        if server in PROTECTED_MCP_SERVERS:
            recs.append(
                {
                    "target_type": "codex_mcp_server",
                    "target": server,
                    "action": "keep_enabled",
                    "confidence": 0.95,
                    "reason": "Protected core server for common workflows",
                }
            )
            continue

        confidence = min(0.95, 0.65 + (0.05 * sample_count))
        recs.append(
            {
                "target_type": "codex_mcp_server",
                "target": server,
                "action": "disable",
                "confidence": round(confidence, 2),
                "reason": f"No calls observed across last {sample_count} snapshots",
            }
        )

    return recs


def build_claude_plugin_recommendations(plugins: dict[str, bool]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    for plugin, enabled in plugins.items():
        if not enabled:
            continue
        if not plugin.endswith("@claude-code-plugins"):
            continue
        base = plugin.replace("@claude-code-plugins", "")
        official = f"{base}@claude-plugins-official"
        if plugins.get(official, False):
            recs.append(
                {
                    "target_type": "claude_plugin",
                    "target": plugin,
                    "action": "disable",
                    "confidence": 0.9,
                    "reason": f"Official variant `{official}` is enabled; duplicate capability likely",
                }
            )
    return recs


def summarize(recommendations: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    apply_now = [
        r
        for r in recommendations
        if r["action"] == "disable" and float(r["confidence"]) >= threshold
    ]
    return {
        "total_recommendations": len(recommendations),
        "disable_candidates": sum(1 for r in recommendations if r["action"] == "disable"),
        "auto_apply_candidates": len(apply_now),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend Codex/Claude pruning actions from snapshots.")
    parser.add_argument("--snapshots", type=int, default=6, help="How many most-recent snapshots to evaluate.")
    parser.add_argument("--threshold", type=float, default=0.85, help="Confidence threshold for auto-apply candidates.")
    args = parser.parse_args()

    snapshots = load_recent_snapshots(args.snapshots)
    codex_servers = load_codex_mcp_servers()
    claude_plugins = load_claude_plugins()

    recommendations = []
    recommendations.extend(build_mcp_recommendations(snapshots, codex_servers))
    recommendations.extend(build_claude_plugin_recommendations(claude_plugins))

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshot_count": len(snapshots),
        "confidence_threshold": args.threshold,
        "summary": summarize(recommendations, args.threshold),
        "recommendations": sorted(
            recommendations,
            key=lambda x: (-float(x["confidence"]), x["target_type"], x["target"]),
        ),
    }

    RECOMMEND_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RECOMMEND_DIR / f"recommend-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

