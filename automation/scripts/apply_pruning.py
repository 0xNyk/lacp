#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent)))
RECOMMEND_DIR = ROOT / "data" / "recommendations"
APPLY_DIR = ROOT / "data" / "applied"
BACKUP_DIR = ROOT / "data" / "backups"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def latest_recommendation() -> Path:
    files = sorted(RECOMMEND_DIR.glob("recommend-*.json"))
    if not files:
        raise FileNotFoundError("No recommendation files found.")
    return files[-1]


def backup_file(path: Path, stamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    return target


def apply_codex_mcp_disable(config_text: str, server_name: str) -> tuple[str, bool]:
    lines = config_text.splitlines()
    section_pattern = re.compile(r"^\[mcp_servers\.([^\]]+)\]$")
    enabled_pattern = re.compile(r"^\s*enabled\s*=")

    section_starts: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        match = section_pattern.match(line.strip())
        if match:
            section_starts.append((match.group(1), idx))

    idx_map = {name: i for i, (name, _) in enumerate(section_starts)}
    if server_name not in idx_map:
        return config_text, False

    sec_i = idx_map[server_name]
    _, start = section_starts[sec_i]
    end = section_starts[sec_i + 1][1] if sec_i + 1 < len(section_starts) else len(lines)

    changed = False
    for i in range(start + 1, end):
        if enabled_pattern.match(lines[i]):
            if lines[i].strip() != "enabled = false":
                lines[i] = "enabled = false"
                changed = True
            return "\n".join(lines) + "\n", changed

    lines.insert(start + 1, "enabled = false")
    changed = True
    return "\n".join(lines) + "\n", changed


def apply_claude_plugin_disable(settings: dict[str, Any], plugin_name: str) -> bool:
    enabled_plugins = settings.get("enabledPlugins")
    if not isinstance(enabled_plugins, dict):
        return False
    if enabled_plugins.get(plugin_name) is False:
        return False
    enabled_plugins[plugin_name] = False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply high-confidence pruning recommendations.")
    parser.add_argument("--recommendation", type=str, default="", help="Recommendation JSON path (latest if omitted).")
    parser.add_argument("--threshold", type=float, default=0.9, help="Minimum confidence to apply.")
    args = parser.parse_args()

    rec_path = Path(args.recommendation) if args.recommendation else latest_recommendation()
    rec = load_json(rec_path)
    actions = rec.get("recommendations", [])
    if not isinstance(actions, list):
        actions = []

    to_apply = [
        a for a in actions
        if isinstance(a, dict)
        and a.get("action") == "disable"
        and float(a.get("confidence", 0.0)) >= args.threshold
    ]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report: dict[str, Any] = {
        "applied_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recommendation_file": str(rec_path),
        "threshold": args.threshold,
        "considered_actions": len(actions),
        "applied_actions": [],
        "backups": [],
    }

    codex_text = CODEX_CONFIG.read_text()
    codex_changed = False

    claude_settings = json.loads(CLAUDE_SETTINGS.read_text())
    claude_changed = False

    for action in to_apply:
        target_type = action.get("target_type")
        target = action.get("target")
        if not isinstance(target, str):
            continue

        if target_type == "codex_mcp_server":
            next_text, changed = apply_codex_mcp_disable(codex_text, target)
            codex_text = next_text
            if changed:
                codex_changed = True
                report["applied_actions"].append(action)

        if target_type == "claude_plugin":
            changed = apply_claude_plugin_disable(claude_settings, target)
            if changed:
                claude_changed = True
                report["applied_actions"].append(action)

    if codex_changed:
        report["backups"].append(str(backup_file(CODEX_CONFIG, stamp)))
        CODEX_CONFIG.write_text(codex_text)

    if claude_changed:
        report["backups"].append(str(backup_file(CLAUDE_SETTINGS, stamp)))
        CLAUDE_SETTINGS.write_text(json.dumps(claude_settings, indent=2) + "\n")

    APPLY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = APPLY_DIR / f"apply-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

