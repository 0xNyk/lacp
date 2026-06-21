"""LACP TUI — Interactive Control Panel."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the tui package directory is on sys.path for sibling imports
_tui_dir = str(Path(__file__).resolve().parent)
if _tui_dir not in sys.path:
    sys.path.insert(0, _tui_dir)

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from backend import LacpBackend
from widgets import BrainPanel, DashboardPanel, DoctorPanel, HooksPanel, RunsPanel


class LacpTUI(App):
    """LACP interactive control panel."""

    TITLE = "LACP Control Panel"
    CSS_PATH = "lacp.tcss"
    BINDINGS = [
        ("d", "switch_tab('dashboard')", "Dashboard"),
        ("b", "switch_tab('brain')", "Brain"),
        ("o", "switch_tab('doctor')", "Doctor"),
        ("h", "switch_tab('hooks')", "Hooks"),
        ("u", "switch_tab('runs')", "Runs"),
        ("r", "refresh_tab", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.backend = LacpBackend()

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent("Dashboard", "Brain", "Doctor", "Hooks", "Runs", id="tabs"):
            with TabPane("Dashboard", id="dashboard"):
                yield DashboardPanel(self.backend)
            with TabPane("Brain", id="brain"):
                yield BrainPanel(self.backend)
            with TabPane("Doctor", id="doctor"):
                yield DoctorPanel(self.backend)
            with TabPane("Hooks", id="hooks"):
                yield HooksPanel(self.backend)
            with TabPane("Runs", id="runs"):
                yield RunsPanel(self.backend)
        yield Footer()

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Load data when a tab is activated."""
        pane_id = event.pane.id
        if pane_id == "brain":
            self.query_one(BrainPanel).load_data()
        elif pane_id == "doctor":
            self.query_one(DoctorPanel).load_data()
        elif pane_id == "hooks":
            self.query_one(HooksPanel).load_data()
        elif pane_id == "runs":
            self.query_one(RunsPanel).load_data()

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_refresh_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        active = tabs.active
        if active == "dashboard":
            self.query_one(DashboardPanel).refresh_data()
        elif active == "brain":
            self.query_one(BrainPanel).load_data()
        elif active == "doctor":
            self.query_one(DoctorPanel).load_data()
        elif active == "hooks":
            self.query_one(HooksPanel).load_data()
        elif active == "runs":
            self.query_one(RunsPanel).load_data()


def main() -> None:
    app = LacpTUI()
    app.run()


if __name__ == "__main__":
    main()
