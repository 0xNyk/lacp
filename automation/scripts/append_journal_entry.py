#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent)))
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
JOURNAL = ROOT / "optimization-journal.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def find_snapshots() -> list[Path]:
    return sorted(SNAPSHOT_DIR.glob("snapshot-*.json"))


def fmt_delta(current: float, previous: float) -> str:
    if previous == 0:
        return "n/a"
    pct = ((current - previous) / previous) * 100.0
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def top_names(items: list[dict[str, Any]], limit: int = 5) -> str:
    if not items:
        return "none"
    return ", ".join(f"{x['name']} ({x['count']})" for x in items[:limit])


def latest_and_previous() -> tuple[Path, Path | None]:
    snapshots = find_snapshots()
    if not snapshots:
        raise FileNotFoundError("No snapshots found.")
    latest = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) > 1 else None
    return latest, previous


def main() -> int:
    parser = argparse.ArgumentParser(description="Append optimization journal entry from latest snapshot.")
    parser.add_argument("--snapshot", type=str, default="", help="Specific snapshot file path.")
    args = parser.parse_args()

    if args.snapshot:
        latest = Path(args.snapshot)
        previous = None
    else:
        latest, previous = latest_and_previous()

    cur = load_json(latest)
    prev = load_json(previous) if previous else None

    ts = cur.get("captured_at_utc", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    heading_ts = ts.replace("T", " ").replace("Z", " UTC")

    cur_perf = cur["performance"]
    prev_perf = prev["performance"] if prev else None

    zsh_avg = cur_perf["zsh_startup"]["avg_seconds"]
    codex_avg = cur_perf["codex_help"]["avg_seconds"]
    claude_avg = cur_perf["claude_help"]["avg_seconds"]

    if prev_perf:
        zsh_delta = fmt_delta(zsh_avg, prev_perf["zsh_startup"]["avg_seconds"])
        codex_delta = fmt_delta(codex_avg, prev_perf["codex_help"]["avg_seconds"])
        claude_delta = fmt_delta(claude_avg, prev_perf["claude_help"]["avg_seconds"])
    else:
        zsh_delta = codex_delta = claude_delta = "n/a"

    usage = cur["usage"]
    codex_sessions = usage["codex_sessions"]
    codex_history = usage["codex_history"]
    claude_history = usage["claude_history"]

    lines = [
        "",
        f"## {heading_ts} - Phase 2 Snapshot",
        "",
        "### Performance (Current)",
        f"- zsh startup avg: `{zsh_avg:.3f}s` (delta vs previous: `{zsh_delta}`)",
        f"- codex --help avg: `{codex_avg:.3f}s` (delta vs previous: `{codex_delta}`)",
        f"- claude --help avg: `{claude_avg:.3f}s` (delta vs previous: `{claude_delta}`)",
        "",
        f"### Rolling {cur['window_hours']}h Usage",
        f"- Codex prompts: `{codex_history['prompt_count']}` across `{codex_history['session_count']}` sessions",
        f"- Codex tool calls: `{codex_sessions['tool_calls_total']}`",
        f"- Codex MCP calls: `{codex_sessions['mcp_calls_total']}`",
        f"- Claude prompts: `{claude_history['prompt_count']}`",
        f"- Top Codex tools: {top_names(codex_sessions['top_tools'])}",
        f"- Top MCP servers: {top_names(codex_sessions['top_mcp_servers'])}",
        f"- Top Claude projects: {top_names(claude_history['top_projects'])}",
        "",
        "### Config Snapshot",
        f"- Codex reasoning effort: `{cur['config']['codex'].get('model_reasoning_effort')}`",
        f"- Codex MCP server count: `{cur['config']['codex'].get('mcp_server_count')}`",
        f"- Claude enabled plugin count: `{cur['config']['claude'].get('enabled_plugin_count')}`",
        f"- Claude alwaysThinkingEnabled: `{cur['config']['claude'].get('always_thinking_enabled')}`",
        "",
        "### Artifact",
        f"- Snapshot JSON: `{latest}`",
        "",
    ]

    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Appended journal entry from {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

