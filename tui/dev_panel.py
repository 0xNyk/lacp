"""LACP Dev Panel — full customization center for the REPL TUI.

Features:
- Theme presets (Dark, Midnight, Hacker, Warm, Ocean)
- Live CSS tweaking (padding, margin, background, border, color)
- Branding config (agent name, tagline, prompt symbol)
- Color palette editor
- Banner config (border style, background)
- Export to skin YAML
- Live preview

Usage: Type /dev in the LACP REPL to toggle the panel.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Label, Static
from textual.reactive import reactive


# ─── Theme Presets ───────────────────────────────────────────────

DEV_PRESETS: dict[str, dict[str, dict[str, str]]] = {
    "dark": {
        "Screen": {"background": "#000000"},
        ".user-msg": {"background": "#0a0a1a", "margin": "1 1 1 1", "padding": "1 3"},
        ".assistant-msg": {"background": "transparent", "padding": "0 3 1 3"},
        ".banner-box": {"background": "#050510"},
        "StatusBar": {"background": "#0a0a1a", "color": "#00d4ff"},
        "Input": {"background": "#0a0a14", "border": "tall #333355"},
        "MessageDisplay": {"background": "#000000"},
    },
    "midnight": {
        "Screen": {"background": "#0a0a1e"},
        ".user-msg": {"background": "#12122e", "margin": "1 1 1 1", "padding": "1 3"},
        ".assistant-msg": {"background": "#0e0e24", "padding": "0 3 1 3"},
        ".banner-box": {"background": "#080820"},
        "StatusBar": {"background": "#0e0e28", "color": "#6e8efb"},
        "Input": {"background": "#12122e", "border": "tall #2a2a55"},
        "MessageDisplay": {"background": "#0a0a1e"},
    },
    "hacker": {
        "Screen": {"background": "#0a0f0a"},
        ".user-msg": {"background": "#0f1a0f", "margin": "1 1 1 1", "padding": "1 3"},
        ".assistant-msg": {"background": "transparent", "padding": "0 3 1 3"},
        ".banner-box": {"background": "#050f05"},
        "StatusBar": {"background": "#0a140a", "color": "#00ff41"},
        "Input": {"background": "#0a140a", "border": "tall #1a3a1a"},
        "MessageDisplay": {"background": "#0a0f0a"},
    },
    "warm": {
        "Screen": {"background": "#1a1410"},
        ".user-msg": {"background": "#221c16", "margin": "1 1 1 1", "padding": "1 3"},
        ".assistant-msg": {"background": "#1e1812", "padding": "0 3 1 3"},
        ".banner-box": {"background": "#141008"},
        "StatusBar": {"background": "#1e1812", "color": "#e8a838"},
        "Input": {"background": "#1e1812", "border": "tall #3a3020"},
        "MessageDisplay": {"background": "#1a1410"},
    },
    "ocean": {
        "Screen": {"background": "#0a1420"},
        ".user-msg": {"background": "#0e1a2e", "margin": "1 1 1 1", "padding": "1 3"},
        ".assistant-msg": {"background": "#0c1828", "padding": "0 3 1 3"},
        ".banner-box": {"background": "#081018"},
        "StatusBar": {"background": "#0e1a2e", "color": "#38b8e8"},
        "Input": {"background": "#0e1828", "border": "tall #1a3050"},
        "MessageDisplay": {"background": "#0a1420"},
    },
}

# ─── Branding Defaults ───────────────────────────────────────────

BRANDING_DEFAULTS: dict[str, str] = {
    "agent_name": "LACP",
    "tagline": "Local Agent Control Plane",
    "prompt_symbol": "⚡ ❯ ",
    "response_label": "⚡ LACP",
    "user_label": "❯ You",
}

# ─── Color Palette ───────────────────────────────────────────────

COLOR_PALETTE: dict[str, str] = {
    "accent": "#00d4ff",
    "user_label": "#00d4ff",
    "assistant_label": "#aa88ff",
    "system_text": "#555577",
    "banner_border": "#333355",
    "banner_title": "#ffffff",
    "ok": "#4caf50",
    "error": "#ef5350",
    "warn": "#ffa726",
}

# ─── CSS Tweakable Properties ────────────────────────────────────

TWEAKABLE_SELECTORS: dict[str, dict[str, Any]] = {
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
        "label": "Banner",
        "props": {
            "padding": "1 3 1 3",
            "margin": "0 1 1 1",
            "background": "#050510",
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
    "StatusBar": {
        "label": "Status bar",
        "props": {
            "background": "#0a0a1a",
            "color": "#00d4ff",
            "padding": "0 2",
        },
    },
    "Screen": {
        "label": "Screen",
        "props": {
            "background": "#000000",
        },
    },
}

# Store original values for reset
_ORIGINAL_SELECTORS = {
    sel: {"props": {k: v for k, v in conf["props"].items()}}
    for sel, conf in TWEAKABLE_SELECTORS.items()
}
_ORIGINAL_BRANDING = dict(BRANDING_DEFAULTS)
_ORIGINAL_COLORS = dict(COLOR_PALETTE)


def _clean_id(s: str) -> str:
    """Make a string safe for Textual widget IDs."""
    return re.sub(r'[^a-zA-Z0-9_-]', '', s.replace('.', '').replace('#', '').replace(':', '-').replace(' ', '-'))


class DevPropertyRow(Vertical):
    """A single CSS property input row."""

    _clean_id = staticmethod(_clean_id)

    def __init__(self, selector: str, prop: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selector = selector
        self.prop = prop
        self.initial_value = value

    def compose(self) -> ComposeResult:
        clean_sel = _clean_id(self.selector)
        clean_prop = _clean_id(self.prop)
        yield Label(f"  [dim]{self.prop}:[/]", markup=True)
        yield Input(value=self.initial_value, id=f"dev-{clean_sel}-{clean_prop}", classes="dev-input")


class DevBrandingRow(Vertical):
    """A branding config input row."""

    def __init__(self, key: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.brand_key = key
        self.initial_value = value

    def compose(self) -> ComposeResult:
        yield Label(f"  [dim]{self.brand_key}:[/]", markup=True)
        yield Input(value=self.initial_value, id=f"brand-{_clean_id(self.brand_key)}", classes="dev-input")


class DevColorRow(Vertical):
    """A color palette input row."""

    def __init__(self, key: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.color_key = key
        self.initial_value = value

    def compose(self) -> ComposeResult:
        yield Label(f"  [dim]{self.color_key}:[/] [{self.initial_value}]■■■[/]", markup=True)
        yield Input(value=self.initial_value, id=f"color-{_clean_id(self.color_key)}", classes="dev-input")


class DevPanel(VerticalScroll):
    """Full customization center — themes, CSS, branding, colors, export."""

    show_panel = reactive(False)

    DEFAULT_CSS = """
    DevPanel {
        width: 48;
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
    DevPanel .preset-bar {
        padding: 0 1;
        margin: 0 0 1 0;
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
    DevPanel .preview-box {
        margin: 1 1;
        padding: 1 2;
        background: #0a0a1a;
        border: round #333355;
    }
    """

    def compose(self) -> ComposeResult:
        # Header
        yield Static(
            "[bold #00d4ff]⚡ LACP Dev Panel[/]\n"
            "[dim]Full customization center. Edit + Enter to apply.[/]\n"
            "[dim]/dev close · /dev reset · /dev export yaml[/]",
            markup=True,
        )

        # ── Theme Presets ──
        yield Static("\n[bold #00d4ff]Theme Presets[/]", markup=True, classes="section-header")
        preset_names = " │ ".join(f"[bold]{name}[/]" for name in DEV_PRESETS)
        yield Static(f"  /dev preset {{{preset_names}}}", markup=True, classes="preset-bar")

        # ── Colors ──
        yield Static("\n[bold #00d4ff]Colors[/]  [dim](hex values)[/]", markup=True, classes="section-header")
        for key, value in COLOR_PALETTE.items():
            yield DevColorRow(key, value, classes="dev-row")

        # ── Branding ──
        yield Static("\n[bold #00d4ff]Branding[/]", markup=True, classes="section-header")
        for key, value in BRANDING_DEFAULTS.items():
            yield DevBrandingRow(key, value, classes="dev-row")

        # ── CSS Layout ──
        yield Static("\n[bold #00d4ff]Layout & Spacing[/]", markup=True, classes="section-header")
        for selector, config in TWEAKABLE_SELECTORS.items():
            yield Static(
                f"  [bold]{config['label']}[/]  [dim]{selector}[/]",
                markup=True,
                classes="section-header",
            )
            for prop, value in config["props"].items():
                yield DevPropertyRow(selector, prop, value, classes="dev-row")

        # ── Preview ──
        yield Static("\n[bold #00d4ff]Preview[/]", markup=True, classes="section-header")
        yield Static(
            "[bold #00d4ff]❯ You[/]\n"
            "What is 2+2?\n\n"
            "[bold #aa88ff]⚡ LACP[/]\n"
            "The answer is 4.\n\n"
            "[dim #444466]│[/] [dim]Auto-switched to ollama[/]\n"
            "[dim #444466]┊[/] 💻 [bold]$        [/] echo hello  [dim]0.1s[/]",
            markup=True,
            classes="preview-box",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Route input changes to the right handler."""
        input_id = event.input.id or ""
        new_value = event.value.strip()
        if not new_value:
            return

        if input_id.startswith("dev-"):
            self._handle_css_input(input_id, new_value)
        elif input_id.startswith("brand-"):
            self._handle_branding_input(input_id, new_value)
        elif input_id.startswith("color-"):
            self._handle_color_input(input_id, new_value)

    def _handle_css_input(self, input_id: str, new_value: str) -> None:
        parts = input_id[4:]
        for selector, config in TWEAKABLE_SELECTORS.items():
            clean_sel = _clean_id(selector)
            for prop in config["props"]:
                clean_prop = _clean_id(prop)
                if parts == f"{clean_sel}-{clean_prop}":
                    self._apply_css(selector, prop, new_value)
                    config["props"][prop] = new_value
                    return

    def _handle_branding_input(self, input_id: str, new_value: str) -> None:
        key = input_id[6:]  # strip "brand-"
        for brand_key in BRANDING_DEFAULTS:
            if _clean_id(brand_key) == key:
                BRANDING_DEFAULTS[brand_key] = new_value
                # Branding changes need the app's skin to update
                if self.app and hasattr(self.app, 'skin'):
                    self.app.skin.branding[brand_key] = new_value
                return

    def _handle_color_input(self, input_id: str, new_value: str) -> None:
        key = input_id[6:]  # strip "color-"
        for color_key in COLOR_PALETTE:
            if _clean_id(color_key) == key:
                COLOR_PALETTE[color_key] = new_value
                # Map colors to CSS selectors and apply
                color_css_map = {
                    "accent": [("StatusBar", "color"), ("Input:focus", "border")],
                    "user_label": [],  # applied via Rich markup, not CSS
                    "assistant_label": [],
                    "system_text": [(".system-msg", "color"), (".tool-msg", "color")],
                    "banner_border": [(".banner-box", "border")],
                    "ok": [],
                    "error": [],
                    "warn": [],
                }
                for selector, prop in color_css_map.get(color_key, []):
                    if prop == "border":
                        self._apply_css(selector, prop, f"solid {new_value}")
                    else:
                        self._apply_css(selector, prop, new_value)
                return

    def _apply_css(self, selector: str, prop: str, value: str) -> None:
        """Apply a CSS property change to the running app."""
        app = self.app
        if not app:
            return
        try:
            for widget in app.query(selector):
                widget.styles.parse(f"{prop}: {value}")
        except Exception:
            pass

    def apply_preset(self, name: str) -> bool:
        """Apply a theme preset. Returns True if found."""
        preset = DEV_PRESETS.get(name)
        if not preset:
            return False

        for selector, props in preset.items():
            for prop, value in props.items():
                self._apply_css(selector, prop, value)
                # Update stored values
                if selector in TWEAKABLE_SELECTORS:
                    if prop in TWEAKABLE_SELECTORS[selector]["props"]:
                        TWEAKABLE_SELECTORS[selector]["props"][prop] = value
        return True

    def toggle(self) -> None:
        self.show_panel = not self.show_panel
        if self.show_panel:
            self.add_class("visible")
        else:
            self.remove_class("visible")

    def reset_all(self) -> None:
        """Reset to original defaults."""
        for sel, orig in _ORIGINAL_SELECTORS.items():
            for prop, value in orig["props"].items():
                self._apply_css(sel, prop, value)
                TWEAKABLE_SELECTORS[sel]["props"][prop] = value
        for key, value in _ORIGINAL_BRANDING.items():
            BRANDING_DEFAULTS[key] = value
        for key, value in _ORIGINAL_COLORS.items():
            COLOR_PALETTE[key] = value

    def export_css(self) -> str:
        """Export current CSS."""
        lines = []
        for selector, config in TWEAKABLE_SELECTORS.items():
            props = [f"    {prop}: {value};" for prop, value in config["props"].items()]
            lines.append(f"{selector} {{")
            lines.extend(props)
            lines.append("}")
        return "\n".join(lines)

    def export_skin_yaml(self) -> str:
        """Export current config as a YAML skin file."""
        lines = [
            'name: custom',
            'description: "Custom skin exported from /dev panel"',
            '',
            'colors:',
        ]
        for key, value in COLOR_PALETTE.items():
            lines.append(f'  {key}: "{value}"')

        lines.extend(['', 'branding:'])
        for key, value in BRANDING_DEFAULTS.items():
            lines.append(f'  {key}: "{value}"')

        lines.extend(['', 'provider_badges:'])
        lines.append('  anthropic: "[bold #a67df4]anthropic[/]"')
        lines.append('  openai: "[bold #4ade80]openai[/]"')
        lines.append('  ollama: "[bold #f97316]ollama[/]"')
        lines.append('  hermes: "[bold #e879f9]hermes[/]"')

        lines.extend([
            '', 'spinner:', '  thinking_faces:', '    - "◐"', '    - "◓"',
            '    - "◑"', '    - "◒"',
            '  thinking_verbs:', '    - reasoning', '    - analyzing',
            '    - synthesizing', '    - connecting',
        ])

        # CSS overrides section
        lines.extend(['', '# CSS overrides (apply via /dev panel)'])
        for selector, config in TWEAKABLE_SELECTORS.items():
            lines.append(f'# {selector}:')
            for prop, value in config["props"].items():
                lines.append(f'#   {prop}: {value}')

        return "\n".join(lines)

    def save_skin_yaml(self) -> str:
        """Save current config to ~/.lacp/skins/custom.yaml."""
        skin_dir = Path.home() / ".lacp" / "skins"
        skin_dir.mkdir(parents=True, exist_ok=True)
        path = skin_dir / "custom.yaml"
        path.write_text(self.export_skin_yaml(), encoding="utf-8")
        return str(path)
