"""LACP TUI panels — Dashboard, Doctor, Hooks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Label,
    LoadingIndicator,
    Select,
    Static,
)

from backend import LacpBackend

HOOK_PROFILES = [
    ("minimal-stop", "minimal-stop"),
    ("balanced", "balanced"),
    ("hardened-exec", "hardened-exec"),
    ("quality-gate", "quality-gate"),
    ("quality-gate-v2", "quality-gate-v2"),
    ("orient", "orient"),
    ("session-start", "session-start"),
    ("pretool-guard", "pretool-guard"),
    ("write-validate", "write-validate"),
]


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-box {
        width: 60;
        height: auto;
        max-height: 16;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #confirm-box Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    #confirm-buttons {
        height: auto;
        align: center middle;
    }
    #confirm-buttons Button {
        margin: 0 2;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self._message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class DashboardPanel(Static):
    """Dashboard: health summary, identity, recent runs."""

    def __init__(self, backend: LacpBackend) -> None:
        super().__init__()
        self.backend = backend

    def compose(self) -> ComposeResult:
        yield Label("Loading dashboard...", id="dash-health")
        yield Label("", id="dash-identity")
        yield Label("", id="dash-provenance")
        yield Label("", id="dash-memory")
        yield DataTable(id="dash-runs")
        yield LoadingIndicator(id="dash-loading")

    async def on_mount(self) -> None:
        table = self.query_one("#dash-runs", DataTable)
        table.add_columns("Timestamp", "Run ID", "Exit")
        self.query_one("#dash-loading", LoadingIndicator).display = False
        self.refresh_data()
        self.set_interval(30, self.refresh_data)

    def refresh_data(self) -> None:
        self.query_one("#dash-loading", LoadingIndicator).display = True
        self.run_worker(self._load_data(), exclusive=True)

    async def _load_data(self) -> None:
        try:
            doctor, agent, prov, runs, mem = await _gather_safe(
                self.backend.doctor(),
                self.backend.agent_id(),
                self.backend.provenance_verify(),
                self.backend.runs_list(limit=10),
                self.backend.memory_kpi(),
            )

            # Health summary
            summary = doctor.get("summary", {})
            p = summary.get("pass", 0)
            w = summary.get("warn", 0)
            f = summary.get("fail", 0)
            ok_text = "HEALTHY" if doctor.get("ok") else "DEGRADED"
            self.query_one("#dash-health", Label).update(
                f"Health: {ok_text}  |  "
                f"[green]{p} pass[/]  [yellow]{w} warn[/]  [red]{f} fail[/]"
            )

            # Identity
            aid = agent.get("agent_id", "unknown")
            host = agent.get("hostname", "?")
            proj = agent.get("project_slug", "?")
            self.query_one("#dash-identity", Label).update(
                f"Agent: {aid}  |  Host: {host}  |  Project: {proj}"
            )

            # Provenance
            chain_len = prov.get("chain_length", 0)
            prov_ok = prov.get("ok", True)
            breaks = len(prov.get("breaks", []))
            prov_status = (
                f"[green]intact[/] ({chain_len} receipts)"
                if prov_ok
                else f"[red]BROKEN[/] ({breaks} breaks)"
            )
            self.query_one("#dash-provenance", Label).update(
                f"Provenance: {prov_status}"
            )

            # Memory KPIs
            kpis = mem.get("kpis", {})
            if kpis:
                total = kpis.get("total_notes", 0)
                canonical = kpis.get("canonical_notes", 0)
                coverage = kpis.get("required_schema_coverage_pct", 0)
                stale = kpis.get("stale_notes", 0)
                contradictions = kpis.get("contradiction_notes", 0)
                parts = [f"Memory: {total} notes"]
                if canonical:
                    parts.append(f"{canonical} canonical")
                if coverage:
                    parts.append(f"{coverage}% schema coverage")
                if stale:
                    parts.append(f"[yellow]{stale} stale[/]")
                if contradictions:
                    parts.append(f"[red]{contradictions} contradictions[/]")
                self.query_one("#dash-memory", Label).update(
                    "  |  ".join(parts)
                )
            elif mem.get("error"):
                self.query_one("#dash-memory", Label).update(
                    f"[dim]Memory: {mem['error']}[/]"
                )

            # Runs table
            table = self.query_one("#dash-runs", DataTable)
            table.clear()
            for run in runs.get("runs", []):
                ts = run.get("timestamp", run.get("started_at", "?"))
                rid = run.get("run_id", "?")
                ec = run.get("exit_code", "?")
                style = "green" if ec == 0 else "red" if ec else ""
                exit_str = f"[{style}]{ec}[/{style}]" if style else str(ec)
                table.add_row(str(ts), str(rid), exit_str)

        except Exception:
            self.query_one("#dash-health", Label).update(
                "[red]Error loading dashboard data[/]"
            )
        finally:
            try:
                self.query_one("#dash-loading", LoadingIndicator).display = False
            except Exception:
                pass


def _extract_fix_command(check: dict, hints: list[str]) -> str | None:
    """Extract an executable fix command for a check.

    Sources (in priority order):
    1. Matching remediation hint that contains a shell command
    2. Inline command in the detail text (parenthetical)
    """
    import re

    status = check.get("status", "")
    if status == "PASS":
        return None

    name = check.get("name", "")
    detail = check.get("detail", "")
    name_lower = name.lower()

    # 1. Match from remediation_hints
    for hint in hints:
        hint_lower = hint.lower()
        check_parts = name_lower.replace(":", " ").split()
        if any(part in hint_lower for part in check_parts if len(part) > 3):
            # Extract command after colon (e.g., "Repair wrappers: bin/lacp ...")
            cmd_match = re.search(r":\s*(.+)", hint)
            if cmd_match:
                cmd = cmd_match.group(1).strip()
                if cmd and not cmd.startswith("("):
                    return cmd
            return hint

    # 2. Extract from detail parenthetical
    paren = re.search(
        r"\(([^)]*(?:run[: ]|install|start|fix|clean|ollama|bin/)[^)]*)\)",
        detail,
        re.IGNORECASE,
    )
    if paren:
        cmd = paren.group(1).strip()
        # Strip leading "run: " or "run " prefix
        cmd = re.sub(r"^run[: ]+", "", cmd, flags=re.IGNORECASE)
        return cmd

    return None


class DoctorPanel(Static):
    """Doctor: color-coded check results with View->Act detail pane."""

    def __init__(self, backend: LacpBackend) -> None:
        super().__init__()
        self.backend = backend
        self._checks: list[dict] = []
        self._hints: list[str] = []
        self._selected_fix: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="doctor-buttons"):
            yield Button("Re-run Doctor", id="doctor-rerun")
            yield Button("Auto-fix All", variant="warning", id="doctor-autofix")
            yield Button("Run Fix", variant="success", id="doctor-runfix", disabled=True)
        yield DataTable(id="doctor-table", cursor_type="row")
        yield Label("", id="doctor-detail")
        yield LoadingIndicator(id="doctor-loading")

    async def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.add_columns("Status", "Check", "Detail")
        self.query_one("#doctor-loading", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "doctor-rerun":
            self.load_data()
        elif event.button.id == "doctor-autofix":
            self.app.push_screen(
                ConfirmScreen("Run 'lacp doctor --fix'?\nThis creates missing dirs, cleans stale data, and reaps orphan processes."),
                callback=lambda confirmed: (
                    self._do_autofix() if confirmed else None
                ),
            )
        elif event.button.id == "doctor-runfix":
            if self._selected_fix:
                fix_cmd = self._selected_fix
                self.app.push_screen(
                    ConfirmScreen(f"Run fix command?\n\n{fix_cmd}"),
                    callback=lambda confirmed, cmd=fix_cmd: (
                        self._do_run_fix(cmd) if confirmed else None
                    ),
                )

    def _do_autofix(self) -> None:
        self.run_worker(self._autofix(), exclusive=True)

    async def _autofix(self) -> None:
        self.query_one("#doctor-loading", LoadingIndicator).display = True
        try:
            result = await self.backend.doctor_fix()
            ok = result.get("ok", False)
            summary = result.get("summary", {})
            self.query_one("#doctor-detail", Label).update(
                f"[bold]Auto-fix complete[/]: ok={ok}  "
                f"pass={summary.get('pass', '?')} warn={summary.get('warn', '?')} fail={summary.get('fail', '?')}\n"
                "[dim]Re-running doctor...[/]"
            )
            await self._load_data()
        except Exception as exc:
            self.query_one("#doctor-detail", Label).update(
                f"[red]Auto-fix error: {exc}[/]"
            )
            self.query_one("#doctor-loading", LoadingIndicator).display = False

    def _do_run_fix(self, cmd: str) -> None:
        self.run_worker(self._run_fix(cmd), exclusive=True)

    async def _run_fix(self, cmd: str) -> None:
        self.query_one("#doctor-loading", LoadingIndicator).display = True
        try:
            result = await self.backend.run_shell(cmd)
            ok = result.get("ok", False)
            out = result.get("stdout", "")
            err = result.get("stderr", "")

            lines = []
            if ok:
                lines.append(f"[green]Fix succeeded[/] (exit 0)")
            else:
                ec = result.get("exit_code", "?")
                lines.append(f"[red]Fix failed[/] (exit {ec})")
            if out:
                lines.append(out[:200])
            if err:
                lines.append(f"[dim]{err[:200]}[/]")
            lines.append("")
            lines.append("[dim]Re-running doctor...[/]")
            self.query_one("#doctor-detail", Label).update("\n".join(lines))

            await self._load_data()
        except Exception as exc:
            self.query_one("#doctor-detail", Label).update(
                f"[red]Fix error: {exc}[/]"
            )
            self.query_one("#doctor-loading", LoadingIndicator).display = False

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Show full detail + fix hint for the selected check."""
        if event.cursor_row is None or event.cursor_row >= len(self._checks):
            return
        check = self._checks[event.cursor_row]
        status = check.get("status", "?")
        name = check.get("name", "?")
        detail = check.get("detail", "")

        fix_cmd = _extract_fix_command(check, self._hints)
        self._selected_fix = fix_cmd

        # Enable/disable the Run Fix button
        fix_btn = self.query_one("#doctor-runfix", Button)
        fix_btn.disabled = fix_cmd is None

        lines = [f"[bold]{name}[/]  ({status})"]
        lines.append(detail)
        if fix_cmd:
            lines.append("")
            lines.append(f"[yellow]Fix:[/] {fix_cmd}")

        self.query_one("#doctor-detail", Label).update("\n".join(lines))

    def load_data(self) -> None:
        self.query_one("#doctor-loading", LoadingIndicator).display = True
        self.run_worker(self._load_data(), exclusive=True)

    async def _load_data(self) -> None:
        try:
            result = await self.backend.doctor(with_hints=True)

            self._checks = result.get("checks", [])
            self._hints = result.get("remediation_hints", [])
            self._selected_fix = None
            self.query_one("#doctor-runfix", Button).disabled = True

            table = self.query_one("#doctor-table", DataTable)
            table.clear()

            for check in self._checks:
                status = check.get("status", "?")
                name = check.get("name", "?")
                detail = check.get("detail", "")

                if status == "PASS":
                    status_styled = "[green]PASS[/]"
                elif status == "WARN":
                    status_styled = "[yellow]WARN[/]"
                elif status == "FAIL":
                    status_styled = "[red]FAIL[/]"
                else:
                    status_styled = status

                if len(detail) > 80:
                    detail = detail[:77] + "..."

                table.add_row(status_styled, name, detail)

            self.query_one("#doctor-detail", Label).update(
                "[dim]Select a check to see details and fix commands[/]"
            )
        except Exception as exc:
            table = self.query_one("#doctor-table", DataTable)
            table.clear()
            table.add_row("[red]ERROR[/]", "load", str(exc))
        finally:
            try:
                self.query_one("#doctor-loading", LoadingIndicator).display = False
            except Exception:
                pass


class RunsPanel(Static):
    """Runs: recent run results with drill-down detail pane."""

    def __init__(self, backend: LacpBackend) -> None:
        super().__init__()
        self.backend = backend
        self._runs: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Button("Refresh Runs", id="runs-refresh")
        yield Label("", id="runs-summary")
        yield DataTable(id="runs-table", cursor_type="row")
        yield Label("", id="runs-detail")
        yield LoadingIndicator(id="runs-loading")

    async def on_mount(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.add_columns("Status", "Run ID", "Runner", "Duration", "Started")
        self.query_one("#runs-loading", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "runs-refresh":
            self.load_data()

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Show full receipt for selected run."""
        if event.cursor_row is None or event.cursor_row >= len(self._runs):
            return
        run = self._runs[event.cursor_row]

        ec = run.get("exit_code", "?")
        status_color = "green" if ec == 0 else "red"

        lines = [
            f"[bold]{run.get('run_id', '?')}[/]  "
            f"[{status_color}]exit={ec}[/{status_color}]",
        ]
        lines.append(
            f"Runner: {run.get('runner', '?')}  |  "
            f"Agent: {run.get('agent_id', '?')}  |  "
            f"Task: {run.get('task_id', '?')}"
        )

        duration_ms = run.get("duration_ms")
        if isinstance(duration_ms, (int, float)) and duration_ms > 0:
            secs = duration_ms / 1000
            dur = f"{secs / 60:.1f}m" if secs >= 60 else f"{secs:.1f}s"
        else:
            dur = "?"
        lines.append(
            f"Started: {run.get('started_at', '?')}  |  "
            f"Ended: {run.get('ended_at', '?')}  |  "
            f"Duration: {dur}"
        )

        # Show stdout/stderr tail if present
        stdout_tail = run.get("stdout_tail", "")
        stderr_tail = run.get("stderr_tail", "")
        if stdout_tail:
            lines.append("")
            lines.append("[bold]stdout:[/]")
            # Show last few lines, truncated
            for line in stdout_tail.strip().split("\n")[-8:]:
                lines.append(f"  {line[:120]}")
        if stderr_tail:
            lines.append("")
            lines.append("[bold red]stderr:[/]")
            for line in stderr_tail.strip().split("\n")[-4:]:
                lines.append(f"  [red]{line[:120]}[/]")

        self.query_one("#runs-detail", Label).update("\n".join(lines))

    def load_data(self) -> None:
        self.query_one("#runs-loading", LoadingIndicator).display = True
        self.run_worker(self._load_data(), exclusive=True)

    async def _load_data(self) -> None:
        try:
            result = await self.backend.runs_list(limit=30)

            runs = result.get("runs", [])
            ok = result.get("ok", True)

            if not ok and result.get("error"):
                self.query_one("#runs-summary", Label).update(
                    f"[dim]{result.get('error', 'no runs data')}[/]"
                )
                self._runs = []
                return

            passed = sum(1 for r in runs if r.get("exit_code") == 0)
            failed = len(runs) - passed
            self.query_one("#runs-summary", Label).update(
                f"Runs: {len(runs)} total  |  "
                f"[green]{passed} passed[/]  [red]{failed} failed[/]"
            )

            # Store reversed for drill-down indexing
            self._runs = list(reversed(runs))

            table = self.query_one("#runs-table", DataTable)
            table.clear()

            for run in self._runs:
                ec = run.get("exit_code", "?")
                if ec == 0:
                    status = "[green]PASS[/]"
                elif isinstance(ec, int):
                    status = f"[red]FAIL({ec})[/]"
                else:
                    status = str(ec)

                rid = run.get("run_id", "?")
                runner = run.get("runner", "?")
                duration_ms = run.get("duration_ms")
                if isinstance(duration_ms, (int, float)) and duration_ms > 0:
                    secs = duration_ms / 1000
                    if secs >= 60:
                        duration = f"{secs / 60:.1f}m"
                    else:
                        duration = f"{secs:.1f}s"
                else:
                    duration = "?"

                started = run.get("started_at", "?")
                if isinstance(started, str) and "T" in started:
                    started = started.replace("T", " ").rstrip("Z")[:19]

                table.add_row(status, rid, runner, duration, started)

            self.query_one("#runs-detail", Label).update(
                "[dim]Select a run to see full receipt details[/]"
            )
        except Exception as exc:
            self.query_one("#runs-summary", Label).update(
                f"[red]Error: {exc}[/]"
            )
        finally:
            try:
                self.query_one("#runs-loading", LoadingIndicator).display = False
            except Exception:
                pass


class HooksPanel(Static):
    """Hooks: profile selection, audit results, repair."""

    def __init__(self, backend: LacpBackend) -> None:
        super().__init__()
        self.backend = backend

    def compose(self) -> ComposeResult:
        with Horizontal(id="hooks-controls"):
            yield Select(
                HOOK_PROFILES,
                value="minimal-stop",
                id="hooks-profile-select",
            )
            yield Button("Apply Profile", variant="warning", id="hooks-apply")
            yield Button("Repair", id="hooks-repair")
        yield Label("", id="hooks-summary")
        yield DataTable(id="hooks-table")
        yield LoadingIndicator(id="hooks-loading")

    async def on_mount(self) -> None:
        table = self.query_one("#hooks-table", DataTable)
        table.add_columns("Plugin", "Stop Hooks", "Version")
        self.query_one("#hooks-loading", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hooks-apply":
            select = self.query_one("#hooks-profile-select", Select)
            profile = str(select.value)
            self.app.push_screen(
                ConfirmScreen(f"Apply hook profile '{profile}'?"),
                callback=lambda confirmed: (
                    self._do_apply(profile) if confirmed else None
                ),
            )
        elif event.button.id == "hooks-repair":
            self.run_worker(self._do_repair(), exclusive=True)

    def _do_apply(self, profile: str) -> None:
        self.run_worker(self._apply_profile(profile), exclusive=True)

    async def _apply_profile(self, profile: str) -> None:
        self.query_one("#hooks-loading", LoadingIndicator).display = True
        try:
            result = await self.backend.hooks_apply_profile(profile)
            ok = result.get("ok", False)
            actions = len(result.get("actions", []))
            self.query_one("#hooks-summary", Label).update(
                f"Applied '{profile}': ok={ok} actions={actions}"
            )
            await self._load_audit()
        finally:
            self.query_one("#hooks-loading", LoadingIndicator).display = False

    async def _do_repair(self) -> None:
        self.query_one("#hooks-loading", LoadingIndicator).display = True
        try:
            result = await self.backend.hooks_repair()
            ok = result.get("ok", False)
            actions = len(result.get("actions", []))
            self.query_one("#hooks-summary", Label).update(
                f"Repair: ok={ok} actions={actions}"
            )
            await self._load_audit()
        finally:
            self.query_one("#hooks-loading", LoadingIndicator).display = False

    def load_data(self) -> None:
        self.query_one("#hooks-loading", LoadingIndicator).display = True
        self.run_worker(self._load_audit(), exclusive=True)

    async def _load_audit(self) -> None:
        try:
            result = await self.backend.hooks_audit()

            summary = result.get("summary", {})
            total_stop = summary.get("total_stop_hooks", 0)
            missing_plugins = summary.get("missing_plugin_paths", 0)
            missing_cmds = summary.get("missing_command_paths", 0)
            drift = summary.get("version_drift", 0)
            enabled = summary.get("enabled_plugins", 0)

            self.query_one("#hooks-summary", Label).update(
                f"Enabled plugins: {enabled}  |  Stop hooks: {total_stop}  |  "
                f"Missing paths: {missing_plugins}  |  "
                f"Missing commands: {missing_cmds}  |  Drift: {drift}"
            )

            table = self.query_one("#hooks-table", DataTable)
            table.clear()

            for contrib in result.get("plugin_stop_contributors", []):
                plugin = contrib.get("plugin", "?")
                stop = contrib.get("stop_hooks", 0)
                table.add_row(plugin, str(stop), "")

            # Show plugins with info from the full audit
            for item in result.get("missing_plugin_paths", []):
                table.add_row(
                    item.get("plugin", "?"),
                    "[red]missing[/]",
                    item.get("reason", ""),
                )
        except Exception as exc:
            self.query_one("#hooks-summary", Label).update(
                f"[red]Error loading audit: {exc}[/]"
            )
        finally:
            try:
                self.query_one("#hooks-loading", LoadingIndicator).display = False
            except Exception:
                pass


# Known fix commands for brain checks that don't have hints
_BRAIN_FIX_MAP = {
    "brain:stale_locks": "find ~/.claude/hooks -name '.remote_context.*.json' -mmin +720 -delete",
    "brain:obsidian_config": "bin/lacp-obsidian apply",
    "brain:sessions:claude": "mkdir -p ~/.lacp/sessions/claude",
    "brain:sessions:codex": "mkdir -p ~/.lacp/sessions/codex",
    "brain:obsidian_app": "open -a Obsidian",
}


def _brain_fix_command(check: dict, hints: list[str]) -> str | None:
    """Extract fix command for a brain check."""
    status = check.get("status", "")
    if status == "PASS":
        return None
    name = check.get("name", "")

    # Try remediation hints first
    cmd = _extract_fix_command(check, hints)
    if cmd:
        return cmd

    # Fall back to hardcoded brain fix map
    return _BRAIN_FIX_MAP.get(name)


class BrainPanel(Static):
    """Brain: Obsidian memory ecosystem — health, stack, KPIs, expansion."""

    def __init__(self, backend: LacpBackend) -> None:
        super().__init__()
        self.backend = backend
        self._checks: list[dict] = []
        self._hints: list[str] = []
        self._selected_fix: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="brain-buttons"):
            yield Button("Refresh", id="brain-refresh")
            yield Button("Run Brain Expand", variant="warning", id="brain-expand")
            yield Button("Run Fix", variant="success", id="brain-runfix", disabled=True)
        yield Label("", id="brain-stack-summary")
        yield Label("", id="brain-kpi-summary")
        yield DataTable(id="brain-table", cursor_type="row")
        yield Label("", id="brain-detail")
        yield LoadingIndicator(id="brain-loading")

    async def on_mount(self) -> None:
        table = self.query_one("#brain-table", DataTable)
        table.add_columns("Status", "Check", "Detail")
        self.query_one("#brain-loading", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "brain-refresh":
            self.load_data()
        elif event.button.id == "brain-expand":
            self.app.push_screen(
                ConfirmScreen(
                    "Run brain-expand --apply?\n\n"
                    "This syncs sessions, materializes research,\n"
                    "and expands knowledge graph nodes."
                ),
                callback=lambda confirmed: (
                    self._do_expand() if confirmed else None
                ),
            )
        elif event.button.id == "brain-runfix":
            if self._selected_fix:
                fix_cmd = self._selected_fix
                self.app.push_screen(
                    ConfirmScreen(f"Run fix command?\n\n{fix_cmd}"),
                    callback=lambda confirmed, cmd=fix_cmd: (
                        self._do_run_fix(cmd) if confirmed else None
                    ),
                )

    def _do_expand(self) -> None:
        self.run_worker(self._run_expand(), exclusive=True)

    async def _run_expand(self) -> None:
        self.query_one("#brain-loading", LoadingIndicator).display = True
        try:
            self.query_one("#brain-detail", Label).update(
                "[dim]Running brain-expand --apply... (this may take a minute)[/]"
            )
            result = await self.backend.brain_expand(apply=True)
            ok = result.get("ok", False)
            if ok:
                lines = ["[green]Brain expand complete[/]"]
                for key in ("sessions_synced", "research_materialized", "nodes_expanded", "steps"):
                    val = result.get(key)
                    if val is not None:
                        lines.append(f"  {key}: {val}")
                self.query_one("#brain-detail", Label).update("\n".join(lines))
            else:
                err = result.get("error", "unknown error")
                self.query_one("#brain-detail", Label).update(
                    f"[red]Brain expand failed: {err}[/]"
                )
            await self._load_data()
        except Exception as exc:
            self.query_one("#brain-detail", Label).update(
                f"[red]Error: {exc}[/]"
            )
            self.query_one("#brain-loading", LoadingIndicator).display = False

    def _do_run_fix(self, cmd: str) -> None:
        self.run_worker(self._run_fix(cmd), exclusive=True)

    async def _run_fix(self, cmd: str) -> None:
        self.query_one("#brain-loading", LoadingIndicator).display = True
        try:
            result = await self.backend.run_shell(cmd)
            ok = result.get("ok", False)
            out = result.get("stdout", "")
            err = result.get("stderr", "")

            lines = []
            if ok:
                lines.append(f"[green]Fix succeeded[/] (exit 0)")
            else:
                ec = result.get("exit_code", "?")
                lines.append(f"[red]Fix failed[/] (exit {ec})")
            if out:
                lines.append(out[:200])
            if err:
                lines.append(f"[dim]{err[:200]}[/]")
            lines.append("")
            lines.append("[dim]Refreshing brain health...[/]")
            self.query_one("#brain-detail", Label).update("\n".join(lines))

            await self._load_data()
        except Exception as exc:
            self.query_one("#brain-detail", Label).update(
                f"[red]Fix error: {exc}[/]"
            )
            self.query_one("#brain-loading", LoadingIndicator).display = False

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        if event.cursor_row is None or event.cursor_row >= len(self._checks):
            return
        check = self._checks[event.cursor_row]
        name = check.get("name", "?")
        status = check.get("status", "?")
        detail = check.get("detail", "")

        fix_cmd = _brain_fix_command(check, self._hints)
        self._selected_fix = fix_cmd

        fix_btn = self.query_one("#brain-runfix", Button)
        fix_btn.disabled = fix_cmd is None

        lines = [f"[bold]{name}[/]  ({status})", detail]
        if fix_cmd:
            lines.append("")
            lines.append(f"[yellow]Fix:[/] {fix_cmd}")

        self.query_one("#brain-detail", Label).update("\n".join(lines))

    def load_data(self) -> None:
        self.query_one("#brain-loading", LoadingIndicator).display = True
        self.run_worker(self._load_data(), exclusive=True)

    async def _load_data(self) -> None:
        try:
            doctor, stack, audit, kpi = await _gather_safe(
                self.backend.brain_doctor(with_hints=True),
                self.backend.brain_stack_status(),
                self.backend.brain_stack_audit(),
                self.backend.memory_kpi(),
            )

            self._hints = doctor.get("remediation_hints", [])
            self._selected_fix = None
            self.query_one("#brain-runfix", Button).disabled = True

            # Stack summary
            checks = stack.get("checks", {})
            if checks:
                stack_parts = []
                vault_ok = checks.get("vault_exists", False)
                mem_ok = checks.get("memory_exists", False)
                gnx_ok = checks.get("gitnexus_indexed", False)
                stack_parts.append(
                    f"Vault: {'[green]ok[/]' if vault_ok else '[red]missing[/]'}"
                )
                stack_parts.append(
                    f"Memory: {'[green]ok[/]' if mem_ok else '[red]missing[/]'}"
                )
                stack_parts.append(
                    f"GitNexus: {'[green]indexed[/]' if gnx_ok else '[yellow]not indexed[/]'}"
                )
                # Audit stats
                total_proj = audit.get("total_projects", 0)
                total_sess = audit.get("total_sessions", 0)
                with_mem = audit.get("with_memory", 0)
                stack_parts.append(
                    f"{total_proj} projects  |  {total_sess} sessions  |  "
                    f"{with_mem} with memory"
                )
                self.query_one("#brain-stack-summary", Label).update(
                    "  |  ".join(stack_parts[:3]) + "\n" + stack_parts[3]
                )
            elif stack.get("error"):
                self.query_one("#brain-stack-summary", Label).update(
                    f"[dim]Stack: {stack['error']}[/]"
                )

            # KPI summary
            kpis = kpi.get("kpis", {})
            if kpis:
                total = kpis.get("total_notes", 0)
                canonical = kpis.get("canonical_notes", 0)
                coverage = kpis.get("required_schema_coverage_pct", 0)
                source_pct = kpis.get("source_backed_pct", 0)
                stale = kpis.get("stale_notes", 0)
                contradictions = kpis.get("contradiction_notes", 0)
                kpi_line = (
                    f"KPIs: {total} notes  |  {canonical} canonical  |  "
                    f"{coverage}% schema  |  {source_pct}% sourced"
                )
                if stale:
                    kpi_line += f"  |  [yellow]{stale} stale[/]"
                if contradictions:
                    kpi_line += f"  |  [red]{contradictions} contradictions[/]"
                self.query_one("#brain-kpi-summary", Label).update(kpi_line)
            elif kpi.get("error"):
                self.query_one("#brain-kpi-summary", Label).update(
                    f"[dim]KPIs: {kpi['error']}[/]"
                )

            # Health checks table
            self._checks = doctor.get("checks", [])
            table = self.query_one("#brain-table", DataTable)
            table.clear()

            for check in self._checks:
                status = check.get("status", "?")
                name = check.get("name", "?")
                detail = check.get("detail", "")

                if status == "PASS":
                    status_styled = "[green]PASS[/]"
                elif status == "WARN":
                    status_styled = "[yellow]WARN[/]"
                elif status == "FAIL":
                    status_styled = "[red]FAIL[/]"
                else:
                    status_styled = status

                if len(detail) > 80:
                    detail = detail[:77] + "..."

                table.add_row(status_styled, name, detail)

            self.query_one("#brain-detail", Label).update(
                "[dim]Select a check for details  |  "
                "'Run Brain Expand' to sync sessions and expand knowledge[/]"
            )
        except Exception as exc:
            self.query_one("#brain-stack-summary", Label).update(
                f"[red]Error loading brain data: {exc}[/]"
            )
        finally:
            try:
                self.query_one("#brain-loading", LoadingIndicator).display = False
            except Exception:
                pass


async def _gather_safe(*coros):
    """Like asyncio.gather but returns dicts with ok=False on failure."""
    results = []
    for coro in coros:
        try:
            results.append(await coro)
        except Exception as exc:
            results.append({"ok": False, "error": str(exc)})
    return results
