#!/usr/bin/env python3
"""LACP Control Plane — Textual TUI Hub.

The main entry point for `lacp` when run without arguments.
A full terminal dashboard for managing workspaces, agents, memory,
and sessions.

Panels:
  - Dashboard: system health, memory status, active sessions
  - Agents: launch/manage agent sessions with model selection
  - Memory: browse registry, probe results, review queue
  - Workspace: file explorer, git status
  - Council: run deliberations

Usage:
    python3 -m tui.app        # launch TUI
    lacp                      # routes here when no args
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Markdown,
    ProgressBar,
    Static,
    TabbedContent,
    TabPane,
)

LACP_ROOT = Path(os.environ.get("LACP_ROOT", str(Path(__file__).resolve().parent.parent)))
KNOWLEDGE_ROOT = Path(os.environ.get(
    "LACP_KNOWLEDGE_ROOT",
    str(Path.home() / "control" / "knowledge" / "knowledge-memory"),
))
VERSION_FILE = LACP_ROOT / "version"


def get_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return "dev"


def load_profile_data() -> dict:
    try:
        import sys
        sys.path.insert(0, str(LACP_ROOT / "automation" / "scripts"))
        from load_profile import load_profile
        return load_profile()
    except Exception:
        return {"identity": {"name": "LACP", "emoji": "\u26a1", "tagline": "Local Agent Control Plane"}}


# ─── Data Gathering ───────────────────────────────────────────────


def gather_health() -> dict:
    """Quick health check without calling lacp-doctor (which is heavy and can trigger Obsidian)."""
    summary = {"pass": 0, "warn": 0, "fail": 0}
    ok = True

    # Check key paths exist
    for name, path in [
        ("knowledge_root", KNOWLEDGE_ROOT),
        ("automation", LACP_ROOT / "automation" / "scripts"),
        ("registry", KNOWLEDGE_ROOT / "data" / "research" / "registry.json"),
    ]:
        if path.exists():
            summary["pass"] += 1
        else:
            summary["warn"] += 1

    # Check lock file health
    lock = KNOWLEDGE_ROOT / "data" / ".consolidate-lock"
    if lock.exists():
        try:
            holder = lock.read_text().strip()
            age_s = time.time() - lock.stat().st_mtime
            if holder and age_s > 3600:
                summary["warn"] += 1  # stale lock
            else:
                summary["pass"] += 1
        except Exception:
            summary["pass"] += 1
    else:
        summary["pass"] += 1

    # Check version file
    if VERSION_FILE.exists():
        summary["pass"] += 1
    else:
        summary["warn"] += 1

    ok = summary["fail"] == 0
    return {"ok": ok, "summary": summary}


def gather_memory() -> dict:
    """Memory system status."""
    status = {"registry_items": 0, "lock_held": False, "staging": 0, "probe_rate": None}
    reg_file = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"
    if reg_file.exists():
        try:
            reg = json.loads(reg_file.read_text())
            status["registry_items"] = len(reg.get("items", {}))
        except Exception:
            pass
    lock_file = KNOWLEDGE_ROOT / "data" / ".consolidate-lock"
    if lock_file.exists():
        try:
            holder = lock_file.read_text().strip()
            status["lock_held"] = bool(holder)
        except Exception:
            pass
    staging = Path.home() / ".lacp" / "memory-staging" / "pending.jsonl"
    if staging.exists():
        try:
            status["staging"] = sum(1 for _ in staging.open())
        except Exception:
            pass
    probe_dir = KNOWLEDGE_ROOT / "data" / "probes"
    if probe_dir.exists():
        probes = sorted(probe_dir.glob("probe-*.json"), reverse=True)
        if probes:
            try:
                data = json.loads(probes[0].read_text())
                status["probe_rate"] = data.get("success_rate")
            except Exception:
                pass
    return status


def gather_sessions() -> list[dict]:
    """Recent sessions from telemetry."""
    telemetry = Path.home() / ".local" / "share" / "claude-hooks" / "telemetry.jsonl"
    if not telemetry.exists():
        return []
    cutoff = datetime.now(UTC) - timedelta(hours=48)
    sessions: dict[str, dict] = {}
    try:
        for line in telemetry.read_text(errors="ignore").splitlines()[-300:]:
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
            if sid not in sessions:
                sessions[sid] = {"id": sid, "events": 0, "blocks": 0, "last": ts_str}
            sessions[sid]["events"] += 1
            if e.get("decision") == "block":
                sessions[sid]["blocks"] += 1
            sessions[sid]["last"] = ts_str
    except Exception:
        pass
    return sorted(sessions.values(), key=lambda x: x.get("last", ""), reverse=True)[:15]


def get_focus() -> str:
    focus_file = Path.home() / ".lacp" / "focus.md"
    if not focus_file.exists():
        return "(no focus set)"
    try:
        text = focus_file.read_text()
        import re
        m = re.search(r'## (?:Current Goal|1\. Current Problem)\n(.+?)(?:\n##|\Z)', text, re.DOTALL)
        if m:
            goal = m.group(1).strip()
            if goal and "{" not in goal and "Replace" not in goal and "one sentence" not in goal:
                return goal[:120]
        return "(focus not set — run: lacp focus update \"your goal\")"
    except Exception:
        return "(error reading focus)"


def list_agents() -> list[dict]:
    """List available agent backends."""
    agents = []
    for name in ["claude", "codex", "hermes", "opencode", "gemini", "goose", "aider"]:
        native = Path.home() / ".local" / "bin" / f"{name}.native"
        found = native.exists()
        if not found:
            try:
                subprocess.run(["which", name], capture_output=True, timeout=2)
                found = True
            except Exception:
                pass
        agents.append({"name": name, "available": found})
    return agents


# ─── Widgets ──────────────────────────────────────────────────────


class StatusPanel(Static):
    """System health + memory status panel."""

    def compose(self) -> ComposeResult:
        yield Static("Loading...", id="status-content")

    def on_mount(self) -> None:
        self.refresh_data()
        self.set_interval(30, self.refresh_data)

    def refresh_data(self) -> None:
        profile = load_profile_data()
        ident = profile.get("identity", {})
        emoji = ident.get("emoji", "\u26a1")
        name = ident.get("name", "LACP")
        version = get_version()
        focus = get_focus()

        mem = gather_memory()
        health = gather_health()
        summary = health.get("summary", {})
        ok = health.get("ok", False)

        health_icon = "\u2705" if ok else "\u274c"
        lock_icon = "\U0001f512" if mem["lock_held"] else "\u2705"
        probe_text = f"{int(mem['probe_rate'] * 100)}%" if mem["probe_rate"] is not None else "n/a"

        lines = [
            f"  {emoji} {name} v{version}",
            f"  Focus: {focus[:80]}",
            "",
            f"  Health: {health_icon}  pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
            f"  Registry: {mem['registry_items']} items",
            f"  Consolidation: {lock_icon}  Staging: {mem['staging']} pending",
            f"  Probe rate: {probe_text}",
        ]

        # MEMORY.md utilization
        for memfile in sorted(Path.home().glob(".claude/projects/*/memory/MEMORY.md"))[:3]:
            try:
                text = memfile.read_text()
                line_count = len(text.strip().split("\n"))
                pct = min(100, int(line_count / 200 * 100))
                bar = "\u2588" * (pct // 5) + "\u2591" * (20 - pct // 5)
                lines.append(f"  MEMORY.md: [{bar}] {line_count}/200 ({pct}%)")
            except Exception:
                pass

        widget = self.query_one("#status-content", Static)
        widget.update("\n".join(lines))


class SessionsPanel(Static):
    """Active sessions table."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="sessions-table")

    def on_mount(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.add_columns("Session", "Events", "Blocks", "Last")
        self.refresh_data()
        self.set_interval(15, self.refresh_data)

    def refresh_data(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        table.clear()
        sessions = gather_sessions()
        for s in sessions:
            last = s.get("last", "?")[11:19] if len(s.get("last", "")) > 19 else "?"
            table.add_row(s["id"], str(s["events"]), str(s["blocks"]), last)


class AgentsPanel(Static):
    """Agent launcher."""

    def compose(self) -> ComposeResult:
        yield Static("", id="agents-content")

    def on_mount(self) -> None:
        agents = list_agents()
        lines = ["  Available Agents:", ""]
        for a in agents:
            icon = "\u2705" if a["available"] else "\u274c"
            lines.append(f"  {icon} {a['name']}")
        lines.extend([
            "",
            "  Launch: lacp --agent <name> --model <model>",
            "  Models: opus, sonnet, haiku, o3, gpt-4.1, gemini-2.5-pro",
        ])
        self.query_one("#agents-content", Static).update("\n".join(lines))


class MemoryPanel(Static):
    """Memory browser."""

    def compose(self) -> ComposeResult:
        yield Static("", id="memory-content")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        reg_file = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"
        lines = ["  Knowledge Registry:", ""]
        if reg_file.exists():
            try:
                reg = json.loads(reg_file.read_text())
                items = reg.get("items", {})
                # Category distribution
                cats: dict[str, int] = {}
                for item in items.values():
                    for cat in item.get("categories", ["uncategorized"]):
                        cats[cat] = cats.get(cat, 0) + 1
                lines.append(f"  Total items: {len(items)}")
                lines.append("")
                lines.append("  Categories:")
                for cat, count in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:12]:
                    bar = "\u2588" * min(20, count // 5)
                    lines.append(f"    {cat:30s} {count:>4d} {bar}")
            except Exception as e:
                lines.append(f"  Error: {e}")
        else:
            lines.append("  (no registry found)")

        # Recent probe results
        probe_dir = KNOWLEDGE_ROOT / "data" / "probes"
        if probe_dir.exists():
            probes = sorted(probe_dir.glob("probe-*.json"), reverse=True)
            if probes:
                try:
                    data = json.loads(probes[0].read_text())
                    lines.extend([
                        "",
                        "  Latest Probe:",
                        f"    Probed: {data.get('items_probed', 0)}",
                        f"    OK: {data.get('retrieval_ok', 0)}  Weak: {data.get('retrieval_weak', 0)}  Critical: {data.get('retrieval_critical', 0)}",
                        f"    Success rate: {int(data.get('success_rate', 0) * 100)}%",
                    ])
                except Exception:
                    pass

        self.query_one("#memory-content", Static).update("\n".join(lines))


class WorkspacePanel(Static):
    """Workspace/git status."""

    def compose(self) -> ComposeResult:
        yield Static("", id="workspace-content")

    def on_mount(self) -> None:
        lines = ["  Workspace:", ""]
        cwd = Path.cwd()
        lines.append(f"  CWD: {cwd}")

        # Git status
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5, cwd=str(cwd),
            ).stdout.strip()
            if branch:
                lines.append(f"  Branch: {branch}")

            status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, timeout=5, cwd=str(cwd),
            ).stdout.strip()
            if status:
                lines.append(f"  Changes:")
                for line in status.split("\n")[:10]:
                    lines.append(f"    {line}")
            else:
                lines.append("  Working tree clean")

            log = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True, text=True, timeout=5, cwd=str(cwd),
            ).stdout.strip()
            if log:
                lines.append("")
                lines.append("  Recent commits:")
                for line in log.split("\n"):
                    lines.append(f"    {line}")
        except Exception:
            lines.append("  (not a git repo)")

        self.query_one("#workspace-content", Static).update("\n".join(lines))


# ─── Main App ─────────────────────────────────────────────────────


class LACPApp(App):
    """LACP Control Plane TUI."""

    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 1 2;
    }
    StatusPanel, SessionsPanel, AgentsPanel, MemoryPanel, WorkspacePanel {
        height: auto;
    }
    #status-content, #agents-content, #memory-content, #workspace-content {
        height: auto;
    }
    DataTable {
        height: auto;
        max-height: 20;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "show_tab('dashboard')", "Dashboard"),
        Binding("a", "show_tab('agents')", "Agents"),
        Binding("m", "show_tab('memory')", "Memory"),
        Binding("w", "show_tab('workspace')", "Workspace"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        profile = load_profile_data()
        ident = profile.get("identity", {})
        title = f"{ident.get('emoji', '')} {ident.get('name', 'LACP')} Control Plane"

        yield Header()
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                yield StatusPanel()
                yield Label("\n  Sessions (48h)")
                yield SessionsPanel()
            with TabPane("Agents", id="agents"):
                yield AgentsPanel()
            with TabPane("Memory", id="memory"):
                yield MemoryPanel()
            with TabPane("Workspace", id="workspace"):
                yield WorkspacePanel()
        yield Footer()

    def on_mount(self) -> None:
        profile = load_profile_data()
        ident = profile.get("identity", {})
        self.title = f"{ident.get('emoji', '')} {ident.get('name', 'LACP')}"
        self.sub_title = f"v{get_version()} | Control Plane"

    def action_show_tab(self, tab_id: str) -> None:
        tabbed = self.query_one(TabbedContent)
        tabbed.active = tab_id

    def action_refresh(self) -> None:
        for panel in self.query(StatusPanel):
            panel.refresh_data()
        for panel in self.query(SessionsPanel):
            panel.refresh_data()
        for panel in self.query(MemoryPanel):
            panel.refresh_data()


def main() -> None:
    app = LACPApp()
    app.run()


if __name__ == "__main__":
    main()
