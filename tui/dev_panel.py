"""LACP Dev Panel — live CSS tweaker for the REPL TUI.

Opens a side panel where you can adjust padding, margin, background,
and spacing for each message type in real-time.

Usage: Type /dev in the LACP REPL to toggle the panel.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Label, Static
from textual.reactive import reactive


# Tweakable properties per CSS selector
TWEAKABLE_SELECTORS = {
    ".user-msg": {
        "label": "❯ You (user input)",
        "props": {
            "margin": "1 1 1 1",
            "padding": "1 3",
            "background": "#0a0a1a",
        },
    },
    ".assistant-msg": {
        "label": "⚡ LACP (response body)",
        "props": {
            "margin": "0 1 1 1",
            "padding": "0 3 1 3",
            "background": "transparent",
        },
    },
    ".assistant-label": {
        "label": "⚡ LACP (label)",
        "props": {
            "margin": "1 1 0 1",
            "padding": "0 3",
        },
    },
    ".system-msg": {
        "label": "│ System messages",
        "props": {
            "margin": "0 1",
            "padding": "0 3",
            "color": "#555577",
        },
    },
    ".tool-msg": {
        "label": "┊ Tool calls",
        "props": {
            "margin": "0 1",
            "padding": "0 3",
            "color": "#555577",
        },
    },
    ".banner-box": {
        "label": "Banner box",
        "props": {
            "padding": "1 3 1 3",
            "margin": "0 1 1 1",
            "background": "#050510",
        },
    },
    "#input-area": {
        "label": "Input area",
        "props": {
            "padding": "0 1 1 1",
        },
    },
    "Input": {
        "label": "Input field",
        "props": {
            "margin": "0 1",
            "background": "#0a0a14",
            "border": "tall #333355",
        },
    },
    "Input:focus": {
        "label": "Input (focused)",
        "props": {
            "border": "tall #00aaff",
        },
    },
    "StatusBar": {
        "label": "Status bar",
        "props": {
            "height": "3",
            "background": "#0a0a1a",
            "color": "#00d4ff",
            "padding": "0 2",
            "border-top": "solid #222244",
            "border-bottom": "solid #222244",
        },
    },
    "Footer": {
        "label": "Footer",
        "props": {
            "height": "1",
            "background": "#111122",
        },
    },
    "ThinkingIndicator": {
        "label": "Spinner / Thinking",
        "props": {
            "padding": "1 3",
        },
    },
    "MessageDisplay": {
        "label": "Message area",
        "props": {
            "padding": "0 1",
            "background": "#000000",
        },
    },
    "Screen": {
        "label": "Screen background",
        "props": {
            "background": "#000000",
        },
    },
}


class DevPropertyRow(Vertical):
    """A single CSS property input row."""

    def __init__(self, selector: str, prop: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selector = selector
        self.prop = prop
        self.initial_value = value

    def compose(self) -> ComposeResult:
        yield Label(f"  [dim]{self.prop}:[/]", markup=True)
        yield Input(
            value=self.initial_value,
            id=f"dev-{self.selector.replace('.', '').replace(' ', '-')}-{self.prop}",
            classes="dev-input",
        )


class DevPanel(VerticalScroll):
    """Live CSS tweaker panel."""

    show_panel = reactive(False)

    DEFAULT_CSS = """
    DevPanel {
        width: 45;
        dock: right;
        background: #0a0a14;
        border-left: solid #222244;
        padding: 1;
        display: none;
    }
    DevPanel.visible {
        display: block;
    }
    DevPanel Label {
        padding: 0 1;
        margin: 0;
    }
    DevPanel .section-header {
        padding: 1 1 0 1;
        color: #00d4ff;
    }
    DevPanel .dev-input {
        height: 1;
        margin: 0 1 0 1;
        border: none;
        background: #111122;
        padding: 0 1;
    }
    DevPanel .dev-input:focus {
        background: #1a1a2e;
    }
    DevPanel .dev-row {
        height: auto;
        padding: 0;
        margin: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #00d4ff]⚡ Dev Panel[/]  [dim]Live CSS Tweaker[/]\n"
            "[dim]Edit values and press Enter to apply.[/]\n"
            "[dim]/dev to close · /dev reset to restore defaults[/]",
            markup=True,
        )

        for selector, config in TWEAKABLE_SELECTORS.items():
            yield Static(
                f"\n[bold]{config['label']}[/]  [dim]{selector}[/]",
                markup=True,
                classes="section-header",
            )
            for prop, value in config["props"].items():
                yield DevPropertyRow(
                    selector, prop, value,
                    classes="dev-row",
                )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Apply CSS change when Enter is pressed in any dev input."""
        input_id = event.input.id or ""
        if not input_id.startswith("dev-"):
            return

        new_value = event.value.strip()
        if not new_value:
            return

        # Parse selector and property from input ID
        # ID format: dev-{selector}-{prop}
        parts = input_id[4:]  # strip "dev-"

        # Find matching selector
        for selector, config in TWEAKABLE_SELECTORS.items():
            clean_sel = selector.replace(".", "").replace(" ", "-")
            for prop in config["props"]:
                if parts == f"{clean_sel}-{prop}":
                    self._apply_css(selector, prop, new_value)
                    # Update stored value
                    config["props"][prop] = new_value
                    return

    def _apply_css(self, selector: str, prop: str, value: str) -> None:
        """Apply a CSS property change to the running app."""
        app = self.app
        if not app:
            return

        # Build CSS rule and inject
        css_rule = f"{selector} {{ {prop}: {value}; }}"
        try:
            # Textual allows setting CSS directly on the stylesheet
            app.stylesheet.parse(css_rule)
            app.stylesheet.reparse()
            # Force all widgets to refresh their styles
            for widget in app.query("*"):
                widget.refresh(layout=True)
        except Exception:
            # Fallback: try setting style directly on matching widgets
            try:
                for widget in app.query(selector):
                    widget.styles.parse(f"{prop}: {value}")
            except Exception:
                pass

    def toggle(self) -> None:
        """Toggle panel visibility."""
        self.show_panel = not self.show_panel
        if self.show_panel:
            self.add_class("visible")
        else:
            self.remove_class("visible")

    def reset_all(self) -> None:
        """Reset all values to defaults and re-apply."""
        # The defaults are baked into TWEAKABLE_SELECTORS initial values
        # We'd need to store originals — for now just toggle off
        self.show_panel = False
        self.remove_class("visible")

    def export_css(self) -> str:
        """Export current tweaked CSS as a string."""
        lines = []
        for selector, config in TWEAKABLE_SELECTORS.items():
            props = []
            for prop, value in config["props"].items():
                props.append(f"    {prop}: {value};")
            lines.append(f"{selector} {{")
            lines.extend(props)
            lines.append("}")
        return "\n".join(lines)
