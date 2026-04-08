#!/usr/bin/env python3
"""LACP Watch Dashboard — curses-based live monitoring TUI.

Shows real-time view of:
- Active sessions and their health
- Memory system status (index cap, consolidation, probes)
- Recent telemetry events
- Brain health summary

Usage:
    python3 watch_dashboard.py              # interactive TUI
    python3 watch_dashboard.py --once       # single render to stdout (no curses)
    python3 watch_dashboard.py --json       # machine-readable snapshot
"""
from __future__ import annotations

import argparse
import curses
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

TELEMETRY_FILE = Path.home() / ".local" / "share" / "claude-hooks" / "telemetry.jsonl"
KNOWLEDGE_ROOT = Path(os.environ.get(
    "LACP_KNOWLEDGE_ROOT",
    str(Path.home() / "control" / "knowledge" / "knowledge-memory"),
))
LOCK_FILE = KNOWLEDGE_ROOT / "data" / ".consolidate-lock"
PROBE_DIR = KNOWLEDGE_ROOT / "data" / "probes"
STAGING_FILE = Path.home() / ".lacp" / "memory-staging" / "pending.jsonl"
REGISTRY_FILE = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"


def gather_telemetry(hours: int = 24) -> dict:
    """Gather recent telemetry data."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    sessions: dict[str, dict] = defaultdict(lambda: {
        "events": 0, "blocks": 0, "allows": 0,
        "hooks": Counter(), "first": None, "last": None,
    })

    if TELEMETRY_FILE.exists():
        for line in TELEMETRY_FILE.read_text(errors="ignore").splitlines()[-500:]:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = e.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                continue
            sid = e.get("session_id", "?")[:16]
            s = sessions[sid]
            s["events"] += 1
            decision = e.get("decision", "?")
            if decision == "block":
                s["blocks"] += 1
            else:
                s["allows"] += 1
            s["hooks"][e.get("hook", "?")] += 1
            if s["first"] is None or ts_str < s["first"]:
                s["first"] = ts_str
            if s["last"] is None or ts_str > s["last"]:
                s["last"] = ts_str

    return dict(sessions)


def gather_memory_status() -> dict:
    """Gather memory system status."""
    status = {
        "registry_items": 0,
        "lock_held": False,
        "lock_age_h": -1.0,
        "staging_pending": 0,
        "last_probe_success_rate": None,
        "index_files": [],
    }

    # Registry
    if REGISTRY_FILE.exists():
        try:
            reg = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            status["registry_items"] = len(reg.get("items", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # Consolidation lock
    if LOCK_FILE.exists():
        try:
            age_s = time.time() - LOCK_FILE.stat().st_mtime
            holder = LOCK_FILE.read_text().strip()
            status["lock_held"] = bool(holder)
            status["lock_age_h"] = round(age_s / 3600, 1)
        except OSError:
            pass

    # Staging
    if STAGING_FILE.exists():
        try:
            status["staging_pending"] = sum(1 for _ in STAGING_FILE.open())
        except OSError:
            pass

    # Latest probe
    if PROBE_DIR.exists():
        probe_files = sorted(PROBE_DIR.glob("probe-*.json"), reverse=True)
        if probe_files:
            try:
                data = json.loads(probe_files[0].read_text(encoding="utf-8"))
                status["last_probe_success_rate"] = data.get("success_rate")
            except (json.JSONDecodeError, OSError):
                pass

    # MEMORY.md files
    for memfile in Path.home().glob(".claude/projects/*/memory/MEMORY.md"):
        try:
            text = memfile.read_text(encoding="utf-8")
            lines = len(text.strip().split("\n"))
            bytes_count = len(text.encode("utf-8"))
            status["index_files"].append({
                "path": str(memfile),
                "lines": lines,
                "bytes": bytes_count,
                "pct": round(lines / 200 * 100),
            })
        except OSError:
            pass

    return status


def render_once() -> str:
    """Render a single dashboard snapshot as text."""
    sessions = gather_telemetry(hours=24)
    mem = gather_memory_status()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = []
    lines.append(f"{'═' * 60}")
    lines.append(f"  LACP Dashboard — {now}")
    lines.append(f"{'═' * 60}")
    lines.append("")

    # Memory system
    lines.append("  Memory System")
    lines.append(f"  {'─' * 40}")
    lines.append(f"  Registry items:  {mem['registry_items']}")

    lock_status = "HELD" if mem["lock_held"] else f"free ({mem['lock_age_h']}h since last)"
    lines.append(f"  Consolidation:   {lock_status}")
    lines.append(f"  Staging pending: {mem['staging_pending']}")

    if mem["last_probe_success_rate"] is not None:
        pct = int(mem["last_probe_success_rate"] * 100)
        lines.append(f"  Probe success:   {pct}%")

    top_indexes = sorted(mem["index_files"], key=lambda x: x["pct"], reverse=True)[:3]
    for idx in top_indexes:
        bar_len = idx["pct"] // 5
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"  MEMORY.md:       [{bar}] {idx['lines']}/200 lines ({idx['pct']}%)")
    if len(mem["index_files"]) > 3:
        lines.append(f"  ... +{len(mem['index_files']) - 3} more index files")

    lines.append("")

    # Sessions
    lines.append("  Sessions (24h)")
    lines.append(f"  {'─' * 40}")
    if not sessions:
        lines.append("  (no sessions)")
    else:
        lines.append(f"  {'ID':16s} {'Events':>6s} {'Allow':>6s} {'Block':>6s}  Last")
        for sid, s in sorted(sessions.items(), key=lambda x: x[1]["last"] or "", reverse=True)[:10]:
            last = s["last"][:16] if s["last"] else "?"
            marker = " ⚠" if s["blocks"] > 0 else ""
            lines.append(f"  {sid:16s} {s['events']:>6d} {s['allows']:>6d} {s['blocks']:>6d}  {last}{marker}")

    lines.append("")
    total_events = sum(s["events"] for s in sessions.values())
    total_blocks = sum(s["blocks"] for s in sessions.values())
    block_pct = (total_blocks / total_events * 100) if total_events else 0
    lines.append(f"  Total: {len(sessions)} sessions, {total_events} events, {total_blocks} blocks ({block_pct:.1f}%)")
    lines.append(f"{'═' * 60}")

    return "\n".join(lines)


def curses_main(stdscr: curses.window) -> None:
    """Run the curses-based interactive TUI."""
    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.nodelay(True)
    stdscr.timeout(2000)  # refresh every 2s

    # Define color pairs
    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        sessions = gather_telemetry(hours=24)
        mem = gather_memory_status()
        now = datetime.now(UTC).strftime("%H:%M:%S")

        row = 0

        def addstr(r: int, c: int, text: str, attr: int = 0) -> None:
            nonlocal row
            if r < height - 1 and c < width:
                try:
                    stdscr.addstr(r, c, text[:width - c - 1], attr)
                except curses.error:
                    pass

        # Header
        header = f" LACP Dashboard  {now}  (q=quit, r=refresh)"
        addstr(row, 0, header, curses.A_REVERSE | curses.A_BOLD)
        addstr(row, len(header), " " * (width - len(header) - 1), curses.A_REVERSE)
        row += 2

        # Memory section
        addstr(row, 1, "Memory System", curses.A_BOLD | curses.color_pair(4))
        row += 1
        addstr(row, 1, "─" * min(50, width - 2))
        row += 1

        addstr(row, 3, f"Registry:      {mem['registry_items']} items")
        row += 1

        lock_color = curses.color_pair(3) if mem["lock_held"] else curses.color_pair(1)
        lock_text = "HELD" if mem["lock_held"] else f"free ({mem['lock_age_h']}h ago)"
        addstr(row, 3, f"Consolidation: ")
        addstr(row, 18, lock_text, lock_color)
        row += 1

        addstr(row, 3, f"Staging:       {mem['staging_pending']} pending")
        row += 1

        if mem["last_probe_success_rate"] is not None:
            pct = int(mem["last_probe_success_rate"] * 100)
            probe_color = curses.color_pair(1) if pct >= 80 else (curses.color_pair(2) if pct >= 50 else curses.color_pair(3))
            addstr(row, 3, f"Probe rate:    ")
            addstr(row, 18, f"{pct}%", probe_color)
            row += 1

        top_indexes = sorted(mem["index_files"], key=lambda x: x["pct"], reverse=True)[:3]
        for idx in top_indexes:
            bar_len = idx["pct"] // 5
            bar = "█" * bar_len + "░" * (20 - bar_len)
            cap_color = curses.color_pair(1) if idx["pct"] < 80 else (curses.color_pair(2) if idx["pct"] < 95 else curses.color_pair(3))
            addstr(row, 3, f"MEMORY.md:     [{bar}] {idx['lines']}/200", cap_color)
            row += 1
        if len(mem["index_files"]) > 3:
            addstr(row, 3, f"... +{len(mem['index_files']) - 3} more", curses.A_DIM)
            row += 1

        row += 1

        # Sessions section
        addstr(row, 1, "Sessions (24h)", curses.A_BOLD | curses.color_pair(4))
        row += 1
        addstr(row, 1, "─" * min(50, width - 2))
        row += 1

        if not sessions:
            addstr(row, 3, "(no sessions)", curses.A_DIM)
            row += 1
        else:
            addstr(row, 3, f"{'ID':16s} {'Evts':>5s} {'OK':>4s} {'Blk':>4s}  Last", curses.A_DIM)
            row += 1
            for sid, s in sorted(sessions.items(), key=lambda x: x[1]["last"] or "", reverse=True)[:min(10, height - row - 4):]:
                last = s["last"][11:19] if s["last"] and len(s["last"]) > 19 else "?"
                line_color = curses.color_pair(3) if s["blocks"] > 0 else 0
                addstr(row, 3, f"{sid:16s} {s['events']:>5d} {s['allows']:>4d} {s['blocks']:>4d}  {last}", line_color)
                row += 1

        row += 1
        total_events = sum(s["events"] for s in sessions.values())
        total_blocks = sum(s["blocks"] for s in sessions.values())
        addstr(row, 3, f"Total: {len(sessions)} sessions, {total_events} events, {total_blocks} blocks")

        # Footer
        addstr(height - 1, 0, " q=quit  r=refresh  Refreshes every 2s ", curses.A_REVERSE)

        stdscr.refresh()

        # Handle input
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q"), 27):  # q, Q, or ESC
            break
        elif ch == ord("r"):
            continue  # force refresh
        elif ch == curses.KEY_RESIZE:
            continue


def main() -> int:
    parser = argparse.ArgumentParser(description="LACP Watch Dashboard")
    parser.add_argument("--once", action="store_true", help="Single render to stdout (no curses)")
    parser.add_argument("--json", action="store_true", help="Machine-readable snapshot")
    args = parser.parse_args()

    if args.json:
        sessions = gather_telemetry(hours=24)
        mem = gather_memory_status()
        print(json.dumps({"sessions": sessions, "memory": mem}, indent=2, default=str))
        return 0

    if args.once:
        print(render_once())
        return 0

    # Interactive TUI
    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
