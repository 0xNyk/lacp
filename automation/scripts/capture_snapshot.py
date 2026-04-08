#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent)))
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CODEX_HISTORY = Path.home() / ".codex" / "history.jsonl"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CLAUDE_HISTORY = Path.home() / ".claude" / "history.jsonl"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


@dataclass
class TimingStats:
    samples: list[float]

    @property
    def avg(self) -> float:
        return statistics.fmean(self.samples) if self.samples else 0.0

    @property
    def min(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples_seconds": self.samples,
            "avg_seconds": round(self.avg, 3),
            "min_seconds": round(self.min, 3),
            "max_seconds": round(self.max, 3),
        }


def safe_json_loads(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def parse_iso_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def top_counter(counter: Counter[str], n: int = 15) -> list[dict[str, Any]]:
    return [{"name": k, "count": v} for k, v in counter.most_common(n)]


def ordered_counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {k: v for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))}


def run_timing(command: str, runs: int) -> TimingStats:
    samples: list[float] = []
    for _ in range(runs):
        proc = subprocess.run(
            ["/usr/bin/time", "-p", "sh", "-lc", command],
            capture_output=True,
            text=True,
            check=False,
        )
        output = f"{proc.stdout}\n{proc.stderr}"
        for line in output.splitlines():
            if line.startswith("real "):
                try:
                    samples.append(float(line.split()[1]))
                except (IndexError, ValueError):
                    pass
                break
    return TimingStats(samples=samples)


def du_kb(path: Path) -> int | None:
    proc = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def parse_codex_sessions(window_start: datetime) -> dict[str, Any]:
    session_ids: set[str] = set()
    project_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    mcp_server_counts: Counter[str] = Counter()
    files_scanned = 0

    mcp_pattern = re.compile(r"^mcp__([a-zA-Z0-9_-]+)__")
    for file_path in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
        files_scanned += 1
        try:
            lines = file_path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            obj = safe_json_loads(line)
            if obj is None:
                continue

            ts_raw = obj.get("timestamp")
            if not isinstance(ts_raw, str):
                continue
            ts = parse_iso_utc(ts_raw)
            if ts is None or ts < window_start:
                continue

            entry_type = obj.get("type")
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue

            if entry_type == "session_meta":
                session_id = payload.get("id")
                cwd = payload.get("cwd")
                if isinstance(session_id, str):
                    session_ids.add(session_id)
                if isinstance(cwd, str) and cwd:
                    project_counts[cwd] += 1

            if entry_type == "response_item" and payload.get("type") == "function_call":
                name = payload.get("name")
                if isinstance(name, str) and name:
                    tool_counts[name] += 1
                    match = mcp_pattern.match(name)
                    if match:
                        mcp_server_counts[match.group(1)] += 1

    return {
        "files_scanned": files_scanned,
        "session_count": len(session_ids),
        "top_projects": top_counter(project_counts),
        "tool_calls_total": sum(tool_counts.values()),
        "tool_usage": ordered_counter_dict(tool_counts),
        "top_tools": top_counter(tool_counts),
        "mcp_calls_total": sum(mcp_server_counts.values()),
        "mcp_server_usage": ordered_counter_dict(mcp_server_counts),
        "top_mcp_servers": top_counter(mcp_server_counts),
    }


def parse_codex_history(window_start_epoch: int) -> dict[str, Any]:
    prompts = 0
    session_ids: set[str] = set()
    if not CODEX_HISTORY.exists():
        return {"prompt_count": 0, "session_count": 0}
    for line in CODEX_HISTORY.read_text(errors="ignore").splitlines():
        obj = safe_json_loads(line)
        if obj is None:
            continue
        ts = obj.get("ts")
        if not isinstance(ts, int) or ts < window_start_epoch:
            continue
        prompts += 1
        session_id = obj.get("session_id")
        if isinstance(session_id, str):
            session_ids.add(session_id)
    return {"prompt_count": prompts, "session_count": len(session_ids)}


def parse_claude_history(window_start_epoch_ms: int) -> dict[str, Any]:
    prompt_count = 0
    project_counts: Counter[str] = Counter()
    if not CLAUDE_HISTORY.exists():
        return {"prompt_count": 0, "top_projects": []}

    for line in CLAUDE_HISTORY.read_text(errors="ignore").splitlines():
        obj = safe_json_loads(line)
        if obj is None:
            continue
        ts = obj.get("timestamp")
        if not isinstance(ts, int) or ts < window_start_epoch_ms:
            continue
        prompt_count += 1
        project = obj.get("project")
        if isinstance(project, str) and project:
            project_counts[project] += 1
    return {"prompt_count": prompt_count, "top_projects": top_counter(project_counts)}


def read_codex_config() -> dict[str, Any]:
    if not CODEX_CONFIG.exists():
        return {}
    with CODEX_CONFIG.open("rb") as fh:
        data = tomllib.load(fh)
    mcp_servers = data.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
    return {
        "model": data.get("model"),
        "model_reasoning_effort": data.get("model_reasoning_effort"),
        "approval_policy": data.get("approval_policy"),
        "sandbox_mode": data.get("sandbox_mode"),
        "mcp_server_count": len(mcp_servers),
        "mcp_servers": sorted(mcp_servers.keys()),
    }


def read_claude_settings() -> dict[str, Any]:
    if not CLAUDE_SETTINGS.exists():
        return {}
    data = json.loads(CLAUDE_SETTINGS.read_text())
    enabled_plugins = data.get("enabledPlugins", {})
    if not isinstance(enabled_plugins, dict):
        enabled_plugins = {}
    enabled_count = sum(1 for v in enabled_plugins.values() if v is True)
    return {
        "always_thinking_enabled": data.get("alwaysThinkingEnabled"),
        "cleanup_period_days": data.get("cleanupPeriodDays"),
        "enable_all_project_mcp_servers": data.get("enableAllProjectMcpServers"),
        "enabled_plugin_count": enabled_count,
    }


def build_snapshot(hours: int, timing_runs: int) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=hours)
    window_start_epoch = int(window_start.timestamp())
    window_start_epoch_ms = window_start_epoch * 1000

    return {
        "captured_at_utc": now.isoformat().replace("+00:00", "Z"),
        "window_hours": hours,
        "window_start_utc": window_start.isoformat().replace("+00:00", "Z"),
        "system": {
            "hostname": os.uname().nodename,
            "os": f"{os.uname().sysname} {os.uname().release}",
        },
        "performance": {
            "zsh_startup": run_timing("zsh -i -c exit >/dev/null", timing_runs).as_dict(),
            "codex_help": run_timing("codex --help >/dev/null", timing_runs).as_dict(),
            "claude_help": run_timing("claude --help >/dev/null", timing_runs).as_dict(),
        },
        "usage": {
            "codex_sessions": parse_codex_sessions(window_start),
            "codex_history": parse_codex_history(window_start_epoch),
            "claude_history": parse_claude_history(window_start_epoch_ms),
        },
        "config": {
            "codex": read_codex_config(),
            "claude": read_claude_settings(),
        },
        "disk_kb": {
            "claude_dir": du_kb(Path.home() / ".claude"),
            "codex_dir": du_kb(Path.home() / ".codex"),
            "claude_history": du_kb(CLAUDE_HISTORY),
            "codex_history": du_kb(CODEX_HISTORY),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Claude/Codex optimization snapshot.")
    parser.add_argument("--hours", type=int, default=24, help="Rolling window in hours.")
    parser.add_argument("--timing-runs", type=int, default=3, help="Runs for each timing metric.")
    parser.add_argument("--output", type=str, default="", help="Output snapshot file path.")
    args = parser.parse_args()

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    now_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(args.output) if args.output else SNAPSHOT_DIR / f"snapshot-{now_tag}.json"

    snapshot = build_snapshot(hours=args.hours, timing_runs=args.timing_runs)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
