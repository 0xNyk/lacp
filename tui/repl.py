#!/usr/bin/env python3
"""LACP REPL — Native multi-provider agent session.

Textual-based TUI that talks directly to LLM providers via their SDKs.
Supports mid-conversation model/provider switching, tool use, and
agent delegation.

Usage:
    python3 -m tui.repl              # launch REPL
    python3 -m tui.repl --model opus # start with specific model
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Input, Markdown, Static

# Slash commands for autocomplete
SLASH_COMMANDS = [
    "/help", "/model", "/provider", "/mcp", "/skin",
    "/sessions", "/resume", "/delegate", "/tokens",
    "/save", "/clear", "/system", "/quit",
    "/model opus", "/model sonnet", "/model haiku",
    "/model o3", "/model codex", "/model hermes", "/model llama",
    "/skin default", "/skin cyberpunk",
    "/delegate claude", "/delegate codex", "/delegate hermes",
    "/memory", "/tasks", "/skills",
    "/dev", "/dev reset", "/dev export", "/dev export yaml",
    "/dev preset dark", "/dev preset midnight", "/dev preset hacker",
    "/dev preset warm", "/dev preset ocean",
    "/autoresearch", "/autoresearch on", "/autoresearch off",
    "/autoresearch start", "/autoresearch score",
    "/autoresearch status", "/autoresearch config",
    "/resume latest",
]

# Add project root to path so both `tui.X` and direct imports work
_LACP_ROOT = str(Path(__file__).parent.parent)
if _LACP_ROOT not in sys.path:
    sys.path.insert(0, _LACP_ROOT)
_TUI_DIR = str(Path(__file__).parent)
if _TUI_DIR not in sys.path:
    sys.path.insert(0, _TUI_DIR)
_SCRIPTS_DIR = str(Path(__file__).parent.parent / "automation" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from providers import (
    AnthropicProvider,
    OpenAIProvider,
    OllamaProvider,
    Provider,
    StreamEvent,
    create_provider,
    list_providers,
    read_claude_oauth,
    read_codex_oauth,
)
from skins import Skin, load_skin, list_skins
from tools import TOOL_REGISTRY, execute_tool, get_tool_definitions
from sessions import (
    auto_save_session,
    generate_session_id,
    get_latest_session,
    list_sessions,
    load_session,
)
from mcp import MCPManager
from display import format_tool_call, format_tool_result_preview, format_thinking_status
from dev_panel import DevPanel
from idle_agent import IdleAgent

LACP_ROOT = Path(__file__).parent.parent
VERSION = (LACP_ROOT / "version").read_text().strip() if (LACP_ROOT / "version").exists() else "dev"


# ─── Context Builder ──────────────────────────────────────────────


def build_system_prompt() -> str:
    """Build the LACP system prompt with identity + focus + memory."""
    parts = [f"You are operating in an LACP (Local Agent Control Plane) v{VERSION} session."]

    # Focus brief
    focus_file = Path.home() / ".lacp" / "focus.md"
    if focus_file.exists():
        try:
            import re
            text = focus_file.read_text()
            m = re.search(r'## (?:Current Goal|1\. Current Problem)\n(.+?)(?:\n##|\Z)', text, re.DOTALL)
            if m:
                goal = m.group(1).strip()
                if goal and "{" not in goal and "Replace" not in goal:
                    parts.append(f"Current focus: {goal[:200]}")
        except Exception:
            pass

    # Git context
    try:
        import subprocess
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        if branch:
            parts.append(f"Git branch: {branch}")
    except Exception:
        pass

    # Working directory
    parts.append(f"Working directory: {Path.cwd()}")

    return "\n".join(parts)


# ─── Slash Commands ───────────────────────────────────────────────


HELP_TEXT = """## LACP REPL Commands

| Command | Description |
|---------|-------------|
| `/model <name>` | Switch model (opus, sonnet, haiku, o3, codex, hermes, llama) |
| `/provider` | Show current provider + available providers |
| `/clear` | Clear conversation history |
| `/save [path]` | Save conversation to file |
| `/system` | Show current system prompt |
| `/tokens` | Show token usage for this session |
| `/skin [name]` | Switch visual skin (list available) |
| `/mcp` | Show MCP server status + tools |
| `/sessions` | List recent sessions |
| `/resume [id]` | Resume a previous session |
| `/delegate <agent> <task>` | Delegate task to external agent |
| `/help` | Show this help |
| `/dev` | Toggle customization panel |
| `/dev preset <name>` | Apply theme (dark, midnight, hacker, warm, ocean) |
| `/dev export yaml` | Export config as skin YAML |
| `/autoresearch on/off` | Toggle idle self-improvement agent |
| `/autoresearch start` | Run experiment immediately |
| `/autoresearch score` | Show current health score |
| `/autoresearch status` | Show experiment history |
| `/quit` | Exit REPL |
"""


# ─── TUI Components ──────────────────────────────────────────────


class StatusBar(Static):
    """Interactive status bar — model, mode, MCP, tokens, memory, cost, time.

    Each segment is visually distinct and actionable via keyboard shortcuts
    shown in the footer. The bar acts as the single source of runtime info.
    """

    def update_status(
        self, provider: str, model: str, tokens: int = 0,
        cost: float = 0.0, skin: Skin | None = None, elapsed: float = 0.0,
        mode: str = "Normal", mcp_servers: int = 0, mcp_tools: int = 0,
        memory_count: int = 0, research_count: int = 0, researching: bool = False,
    ) -> None:
        badge = skin.badge(provider) if skin else provider
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_str = f"{mins}:{secs:02d}"

        # Shorten model name
        short_model = model
        for prefix in ("claude-", "gpt-", "gemini-"):
            if short_model.startswith(prefix):
                short_model = short_model[len(prefix):]
        if len(short_model) > 15 and short_model[-8:].isdigit():
            short_model = short_model[:-9]

        # Mode colors
        mode_colors = {
            "Normal": "#666677", "Plan": "#4ade80",
            "Think": "#a78bfa", "YOLO": "#ef4444",
        }
        mode_color = mode_colors.get(mode, "#666677")

        # Shorten cwd
        cwd = str(Path.cwd())
        home = str(Path.home())
        if cwd.startswith(home):
            cwd_short = "~" + cwd[len(home):]
        else:
            cwd_short = cwd
        if len(cwd_short) > 30:
            cwd_short = "…" + cwd_short[-28:]

        # Build segments adaptively based on terminal width
        try:
            term_width = self.app.size.width
        except Exception:
            term_width = 120

        parts = [f" {badge} [bold]{short_model}[/]"]

        if term_width >= 50:
            parts.append(f"[{mode_color}]{mode}[/]")

        if term_width >= 100 and mcp_tools > 0:
            parts.append(f"[dim]MCP:{mcp_tools}[/]")

        if term_width >= 100 and memory_count > 0:
            parts.append(f"[dim]🧠{memory_count}[/]")

        if term_width >= 70:
            parts.append(f"tok:{tokens:,}")

        if term_width >= 90 and cost > 0:
            parts.append(f"${cost:.4f}")

        if term_width >= 60:
            parts.append(time_str)

        if researching:
            parts.append("[bold #e8a838]🔬[/]" if term_width < 80 else "[bold #e8a838]🔬 researching[/]")
        elif term_width >= 100 and research_count > 0:
            parts.append(f"[dim]🔬{research_count}[/]")

        if term_width >= 120:
            parts.append(f"[dim]{cwd_short}[/]")

        sep = " │ " if term_width >= 80 else " "
        self.update(sep.join(parts))


class ThinkingIndicator(Static):
    """Claude Code-style animated spinner with elapsed time and token count.

    Shows: ● Reasoning… (12s · ↓ 1.4k tokens)
    Animates with face rotation and shimmer-style verb cycling.
    Sticks at the bottom of the message stream during streaming.
    """

    _frame = 0
    _faces = ["◐", "◓", "◑", "◒"]
    _verb = "thinking"
    _dots = 0
    _timer = None
    _start_time = 0.0
    _token_count = 0
    _streaming = False  # True when receiving tokens (switch verb to streaming)
    _stalled_since = 0.0  # track stalls

    def start(self, faces: list[str] | None = None, verb: str = "thinking") -> None:
        self._faces = faces or ["◐", "◓", "◑", "◒"]
        self._verb = verb
        self._frame = 0
        self._dots = 0
        self._start_time = time.time()
        self._token_count = 0
        self._streaming = False
        self._stalled_since = 0.0
        self._render_frame()
        self._timer = self.set_interval(0.2, self._tick)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.remove()

    def update_tokens(self, count: int) -> None:
        """Update token count (called during streaming)."""
        if count > self._token_count:
            self._stalled_since = 0.0  # reset stall
        self._token_count = count
        if not self._streaming:
            self._streaming = True

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(self._faces)
        self._dots = (self._dots + 1) % 4
        self._render_frame()

    def _render_frame(self) -> None:
        face = self._faces[self._frame % len(self._faces)]
        dots = "." * self._dots
        elapsed = self.elapsed

        # Choose verb based on state
        if self._streaming:
            verb = "Streaming"
        else:
            verb = self._verb.capitalize()

        # Build status parts
        parts = [f"{face} {verb}{dots}"]

        if elapsed >= 1:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            if mins > 0:
                parts.append(f"{mins}m {secs:02d}s")
            else:
                parts.append(f"{secs}s")

        if self._token_count > 0:
            if self._token_count >= 1000:
                parts.append(f"↓ {self._token_count / 1000:.1f}k tokens")
            else:
                parts.append(f"↓ {self._token_count} tokens")

        status = " · ".join(parts)
        self.update(f"   [bold #00d4ff]+ {status}[/]")


class MessageDisplay(VerticalScroll):
    """Scrollable message display area."""

    def add_message(self, role: str, content: str) -> None:
        if role == "user":
            widget = Static(f"[bold #00d4ff]❯ You[/]\n[#cccccc]{content}[/]", markup=True, classes="user-msg")
        elif role == "assistant":
            label = Static("[bold #aa88ff]⚡ LACP[/]", markup=True, classes="assistant-label")
            self.mount(label)
            widget = Markdown(content, id=f"msg-{time.time_ns()}", classes="assistant-msg")
        elif role == "system":
            widget = Static(f"[dim #444466]│[/] [#555577]{content}[/]", markup=True, classes="system-msg")
        elif role == "tool":
            widget = Static(f"[dim #444466]│[/] [dim #666688]{content}[/]", markup=True, classes="tool-msg")
        elif role == "research":
            widget = Static(
                f"[bold #666688]🔬 Autoresearch[/]\n{content}",
                markup=True, classes="research-box",
            )
        else:
            widget = Static(content)
        self.mount(widget)
        self.scroll_end(animate=False)

    def add_thinking(self, faces: list[str] | None = None, verb: str = "thinking") -> ThinkingIndicator:
        indicator = ThinkingIndicator(id="thinking", classes="thinking-spinner")
        self.mount(indicator)
        indicator.start(faces=faces, verb=verb)
        # Ensure spinner is visible at bottom
        self.call_after_refresh(lambda: self.scroll_end(animate=False))
        return indicator

    def remove_thinking(self) -> None:
        try:
            self.query_one("#thinking", ThinkingIndicator).stop()
        except Exception:
            pass

    def add_streaming_placeholder(self) -> Static:
        # Keep thinking indicator alive — it becomes the progress spinner
        # Don't call remove_thinking() here
        self._streaming_id = f"stream-{time.time_ns()}"
        self._streaming_label_id = f"label-{time.time_ns()}"
        label = Static("[bold #aa88ff]⚡ LACP[/]", markup=True, id=self._streaming_label_id, classes="assistant-label")
        self.mount(label)
        widget = Static("", id=self._streaming_id, classes="assistant-msg")
        self.mount(widget)
        self.scroll_end(animate=False)
        return widget

    def get_thinking_indicator(self) -> ThinkingIndicator | None:
        """Get the active thinking indicator if present."""
        try:
            return self.query_one("#thinking", ThinkingIndicator)
        except Exception:
            return None

    def remove_streaming(self) -> None:
        """Remove label, placeholder, and thinking indicator (used on retry/fallback)."""
        self.remove_thinking()
        for attr in ("_streaming_id", "_streaming_label_id"):
            sid = getattr(self, attr, "")
            if sid:
                try:
                    self.query_one(f"#{sid}").remove()
                except Exception:
                    pass

    def finalize_streaming(self, content: str) -> None:
        # Remove thinking indicator (spinner)
        self.remove_thinking()
        # Remove streaming placeholder
        sid = getattr(self, "_streaming_id", "")
        if sid:
            try:
                self.query_one(f"#{sid}", Static).remove()
            except Exception:
                pass
        widget = Markdown(content, id=f"msg-{time.time_ns()}", classes="assistant-msg")
        self.mount(widget)
        self.scroll_end(animate=False)


# ─── Main App ─────────────────────────────────────────────────────


class LACPRepl(App):
    """LACP native REPL — multi-provider agent session."""

    CSS = """
    Screen {
        background: #000000;
        layout: vertical;
    }
    StatusBar {
        height: 3;
        background: #0a0a1a;
        color: #00d4ff;
        padding: 0 2;
        border-top: solid #222244;
        border-bottom: solid #222244;
    }
    MessageDisplay {
        height: 1fr;
        padding: 0 1;
        background: #000000;
    }
    #input-area {
        height: auto;
        max-height: 5;
        padding: 0 1 1 1;
    }
    Input {
        border: tall #333355;
        background: #0a0a14;
        margin: 0 1;
    }
    Input:focus {
        border: tall #00aaff;
    }
    Footer {
        height: 1;
        background: #111122;
    }
    .banner-box {
        border: round #333355;
        padding: 1 3 1 3;
        margin: 0 1 1 1;
        background: #050510;
    }
    .user-msg {
        margin: 1 1 1 1;
        padding: 1 3;
        background: #0a0a1a;
    }
    .assistant-msg {
        margin: 0 1 1 1;
        padding: 0 3 1 3;
    }
    .assistant-label {
        margin: 1 1 0 1;
        padding: 0 3;
    }
    .system-msg {
        margin: 0 1;
        padding: 0 3;
        color: #555577;
    }
    .tool-msg {
        margin: 0 1;
        padding: 0 3;
        color: #555577;
    }
    ThinkingIndicator, .thinking-spinner {
        padding: 1 3;
        height: auto;
        dock: bottom;
    }
    .research-box {
        margin: 1 1;
        padding: 1 3;
        background: #080812;
        border: round #333355;
        color: #888899;
    }
    Static {
        background: transparent;
    }

    /* Compact layout classes applied dynamically on resize */
    .compact .banner-box {
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .compact .user-msg {
        margin: 0 0;
        padding: 0 1;
    }
    .compact .assistant-msg {
        margin: 0 0 0 0;
        padding: 0 1 0 1;
    }
    .compact .assistant-label {
        margin: 0 0 0 0;
        padding: 0 1;
    }
    .compact .system-msg, .compact .tool-msg {
        margin: 0;
        padding: 0 1;
    }
    .compact .research-box {
        margin: 0;
        padding: 0 1;
    }
    .compact StatusBar {
        padding: 0 1;
    }
    .compact ThinkingIndicator, .compact .thinking-spinner {
        padding: 0 1;
    }
    """

    # Agent modes: cycle with Shift+Tab
    AGENT_MODES = [
        {"name": "normal", "label": "Normal", "description": "Standard agent mode"},
        {"name": "plan", "label": "Plan", "description": "Planning mode — think before acting"},
        {"name": "thinking", "label": "Think", "description": "Extended thinking — show reasoning"},
        {"name": "yolo", "label": "YOLO", "description": "Skip all permission checks"},
    ]

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+t", "cycle_mode", "Mode", priority=True),
        Binding("shift+tab", "cycle_mode", show=False, priority=True),
        Binding("ctrl+e", "cycle_model", "Model", priority=True),
        Binding("ctrl+p", "command_palette", "palette", show=True, priority=True),
    ]

    def __init__(self, model: str = "haiku", skin_name: str = "", resume: str = "", **kwargs: Any):
        super().__init__(**kwargs)
        self.initial_model = model
        self.skin = load_skin(skin_name)
        self.provider: Provider | None = None
        self.messages: list[dict[str, Any]] = []
        self.system_prompt = ""
        self.total_input_tokens = 0
        self.current_mode_index = 0
        self.total_output_tokens = 0
        self.streaming_content = ""
        self.session_start = time.time()
        self.session_id = generate_session_id()
        self.resume_id = resume
        self.mcp_manager: MCPManager | None = None
        self.mcp_servers_count = 0
        self.mcp_tools_count = 0
        self.idle_agent: IdleAgent | None = None

    def compose(self) -> ComposeResult:
        yield DevPanel(id="dev-panel")
        yield MessageDisplay(id="messages")
        with Vertical(id="input-area"):
            prompt_symbol = self.skin.brand("prompt_symbol") or "⚡ ❯ "
            yield Input(
                placeholder=f"{prompt_symbol}Message LACP... (/help for commands)",
                id="prompt",
                suggester=SuggestFromList(SLASH_COMMANDS, case_sensitive=False),
            )
        yield StatusBar(id="status")
        yield Footer()

    def on_resize(self, event=None) -> None:
        """Adapt layout based on terminal width."""
        w = self.size.width
        screen = self.screen
        if w < 80:
            screen.add_class("compact")
        else:
            screen.remove_class("compact")
        # Update status bar with new width context
        if self.provider:
            self._update_status()

    def on_mount(self) -> None:
        # Set true dark theme
        self.theme = "textual-dark"

        # Initialize provider
        try:
            self.provider = create_provider(model=self.initial_model)
            self.system_prompt = build_system_prompt()
        except Exception as e:
            self.query_one("#messages", MessageDisplay).add_message(
                "system", f"Error initializing provider: {e}"
            )
            return

        # Start MCP servers (non-blocking, best-effort)
        try:
            self.mcp_manager = MCPManager()
            # Start servers in background to avoid blocking UI
            import threading
            def _start_mcp():
                self.mcp_manager.start_servers()
                self.mcp_tools_count = sum(
                    s["tools"] for s in self.mcp_manager.status().values() if s["running"]
                )
                self.mcp_servers_count = sum(
                    1 for s in self.mcp_manager.status().values() if s["running"]
                )
                # Update status bar to show MCP info — no session message
                self.call_from_thread(self._update_status)
            threading.Thread(target=_start_mcp, daemon=True).start()
        except Exception:
            self.mcp_manager = None

        # Update status bar
        self._update_status()

        # Welcome banner — hermes-style: logo + tools/skills/providers
        msgs = self.query_one("#messages", MessageDisplay)
        available = list_providers()
        tool_defs = get_tool_definitions()

        # Adaptive: skip logo on narrow terminals
        term_width = self.size.width
        logo = self.skin.banner_logo.strip() if term_width >= 80 else ""

        # Categorize tools
        tool_categories = {
            "file": [t["name"] for t in tool_defs if t["name"] in ("read_file", "write_file", "edit_file", "ls")],
            "search": [t["name"] for t in tool_defs if t["name"] in ("grep", "glob")],
            "shell": [t["name"] for t in tool_defs if t["name"] == "bash"],
            "memory": [t["name"] for t in tool_defs if t["name"].startswith("memory_")],
            "tasks": [t["name"] for t in tool_defs if t["name"].startswith("task_")],
            "skills": [t["name"] for t in tool_defs if t["name"].startswith("skill_")],
            "agents": [t["name"] for t in tool_defs if t["name"] == "delegate"],
        }

        # Provider line
        prov_parts = []
        for p in available:
            icon = "[green]✓[/]" if p["available"] else "[dim]✗[/]"
            name = p["name"]
            if self.provider and name == self.provider.name:
                prov_parts.append(f"{icon} [bold]{name}[/]")
            else:
                prov_parts.append(f"{icon} {name}")
        providers_line = "  ".join(prov_parts)

        # Short model
        short_model = self.provider.model
        for prefix in ("claude-", "gpt-", "gemini-"):
            if short_model.startswith(prefix):
                short_model = short_model[len(prefix):]
        if len(short_model) > 15 and short_model[-8:].isdigit():
            short_model = short_model[:-9]

        # Build banner — adaptive to terminal width
        sep_width = min(term_width - 6, 62)
        banner_text = ""
        if logo:
            banner_text += f"{logo}\n"
        banner_text += f"  [dim #333355]{'─' * sep_width}[/]\n"

        # Tools summary — compact on narrow
        tool_lines = []
        for cat, names in tool_categories.items():
            if names:
                tool_lines.append(f"[dim #666688]{cat}:[/] [bold]{', '.join(names)}[/]")
        if term_width >= 100:
            banner_text += "  [bold #00d4ff]Tools[/]  " + "  │  ".join(tool_lines[:4]) + "\n"
            if len(tool_lines) > 4:
                banner_text += "         " + "  │  ".join(tool_lines[4:]) + "\n"
        else:
            banner_text += f"  [bold #00d4ff]{len(tool_defs)} tools[/]  │  "
            banner_text += f"{providers_line}\n"

        # Providers + model + session
        if term_width >= 100:
            banner_text += f"\n  {providers_line}  │  [bold]{short_model}[/]  │  {len(tool_defs)} tools\n"
        banner_text += f"  [dim]Session: {self.session_id[:16]}[/]  ·  [bold]{short_model}[/]\n"
        if term_width >= 80:
            banner_text += f"  [dim]{self.skin.brand('welcome')} /help · Ctrl+T mode · Ctrl+E model[/]"
        else:
            banner_text += f"  [dim]/help for commands[/]"

        banner_widget = Static(banner_text, markup=True, classes="banner-box")
        msgs.mount(banner_widget)

        # Resume previous session if requested
        if self.resume_id:
            resume_target = self.resume_id
            if resume_target == "latest":
                resume_target = get_latest_session() or ""
            if resume_target:
                loaded_msgs, meta = load_session(resume_target)
                if loaded_msgs:
                    self.messages = loaded_msgs
                    self.session_id = resume_target
                    msgs.add_message("system",
                        f"Resumed session {resume_target} ({len(loaded_msgs)} messages)")
                    # Replay last few messages in display
                    for msg in loaded_msgs[-4:]:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if isinstance(content, str) and role in ("user", "assistant"):
                            msgs.add_message(role, content[:500])

        # Initialize idle agent (for autoresearch)
        def _on_research_status(msg: str) -> None:
            try:
                self.call_from_thread(
                    lambda m=msg: self.query_one("#messages", MessageDisplay).add_message("research", m)
                )
            except Exception:
                pass
        self.idle_agent = IdleAgent(on_status=_on_research_status)
        self.idle_agent.touch_input()

        # Focus input
        self.query_one("#prompt", Input).focus()

    @property
    def current_mode(self) -> dict:
        return self.AGENT_MODES[self.current_mode_index]

    # Model cycle order
    MODEL_CYCLE = ["sonnet", "opus", "haiku", "codex", "hermes", "llama"]
    _model_cycle_index = 0

    def action_cycle_mode(self) -> None:
        """Cycle through agent modes — status bar only."""
        self.current_mode_index = (self.current_mode_index + 1) % len(self.AGENT_MODES)
        mode = self.current_mode
        self._apply_mode(mode["name"])
        self._update_status()

    def action_cycle_model(self) -> None:
        """Cycle through models with Ctrl+E."""
        self._model_cycle_index = (self._model_cycle_index + 1) % len(self.MODEL_CYCLE)
        model_name = self.MODEL_CYCLE[self._model_cycle_index]
        try:
            self.provider = create_provider(model=model_name)
            self._update_status()
        except Exception:
            # Skip unavailable, try next
            self.action_cycle_model()

    def action_clear_screen(self) -> None:
        """Clear conversation."""
        self.messages.clear()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        display = self.query_one("#messages", MessageDisplay)
        for child in list(display.children):
            child.remove()
        self._update_status()

    def _apply_mode(self, mode_name: str) -> None:
        """Apply mode-specific system prompt modifications."""
        base_prompt = build_system_prompt()
        if mode_name == "plan":
            self.system_prompt = base_prompt + (
                "\n\nYou are in PLAN mode. Before taking any action:"
                "\n1. Analyze the request thoroughly"
                "\n2. List the steps you'll take"
                "\n3. Identify risks and edge cases"
                "\n4. Only then proceed with implementation"
                "\nAlways present your plan before executing tools."
            )
        elif mode_name == "thinking":
            self.system_prompt = base_prompt + (
                "\n\nYou are in THINKING mode. For every response:"
                "\n- Show your reasoning process step by step"
                "\n- Consider multiple approaches before choosing"
                "\n- Explain trade-offs explicitly"
                "\n- Think out loud before acting"
            )
        elif mode_name == "yolo":
            self.system_prompt = base_prompt + (
                "\n\nYou are in YOLO mode (dangerously skip permissions)."
                "\n- Execute commands without asking for confirmation"
                "\n- Make changes directly, don't ask permission"
                "\n- Move fast, fix things later if needed"
                "\n- No safety checks, no guards, just do it"
            )
        else:
            self.system_prompt = base_prompt

    def _update_status(self) -> None:
        if self.provider:
            cost = self._estimate_cost()
            elapsed = time.time() - self.session_start
            mode_label = self.current_mode["label"]
            # Count memory entries
            mem_dir = Path.home() / ".lacp" / "memory"
            mem_count = len(list(mem_dir.glob("*.json"))) if mem_dir.exists() else 0
            self.query_one("#status", StatusBar).update_status(
                self.provider.name,
                self.provider.model,
                self.total_input_tokens + self.total_output_tokens,
                cost,
                skin=self.skin,
                elapsed=elapsed,
                mode=mode_label,
                mcp_servers=self.mcp_servers_count,
                mcp_tools=self.mcp_tools_count,
                memory_count=mem_count,
                research_count=self.idle_agent.experiment_count if self.idle_agent else 0,
                researching=self.idle_agent.is_researching if self.idle_agent else False,
            )

    def _estimate_cost(self) -> float:
        """Rough cost estimate based on model pricing."""
        # Approximate $/1M tokens
        prices = {
            "opus": (15.0, 75.0),
            "sonnet": (3.0, 15.0),
            "haiku": (0.25, 1.25),
            "o3": (10.0, 40.0),
            "gpt-4.1": (2.0, 8.0),
        }
        model_short = self.provider.model if self.provider else ""
        for name, (input_price, output_price) in prices.items():
            if name in model_short:
                return (
                    self.total_input_tokens * input_price / 1_000_000
                    + self.total_output_tokens * output_price / 1_000_000
                )
        return 0.0

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        # Track user activity for idle agent
        if self.idle_agent:
            self.idle_agent.touch_input()

        # Clear input
        event.input.value = ""

        # Handle slash commands
        if text.startswith("/"):
            await self._handle_command(text)
            return

        # Regular message
        msgs = self.query_one("#messages", MessageDisplay)
        msgs.add_message("user", text)
        self.messages.append({"role": "user", "content": text})

        # Show animated thinking indicator
        import random
        verbs = self.skin.spinner.get("thinking_verbs", ["thinking"]) if self.skin else ["thinking"]
        faces = self.skin.spinner.get("thinking_faces", ["◐", "◓", "◑", "◒"]) if self.skin else ["◐", "◓", "◑", "◒"]
        verb = random.choice(verbs)
        msgs.add_thinking(faces=faces, verb=verb)

        # Stream response (runs in background worker thread)
        self._stream_response()

    async def _handle_command(self, text: str) -> None:
        msgs = self.query_one("#messages", MessageDisplay)
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            # Save session and cleanup
            if self.messages:
                auto_save_session(
                    self.session_id, self.messages,
                    provider_name=self.provider.name if self.provider else "",
                    model=self.provider.model if self.provider else "",
                    total_tokens=self.total_input_tokens + self.total_output_tokens,
                )
            if self.mcp_manager:
                self.mcp_manager.stop_all()
            self.exit()

        elif cmd == "/help":
            msgs.add_message("system", HELP_TEXT)

        elif cmd == "/model":
            if not arg:
                msgs.add_message("system", "Usage: /model <name>\nAvailable: opus, sonnet, haiku, o3, codex, hermes, gpt-4.1, llama, qwen")
                return
            try:
                self.provider = create_provider(model=arg)
                self._update_status()
                msgs.add_message("system", f"Switched to {self.provider.name}/{self.provider.model}")
            except Exception as e:
                msgs.add_message("system", f"Error switching model: {e}")

        elif cmd == "/provider":
            available = list_providers()
            lines = ["Available providers:"]
            for p in available:
                icon = "✅" if p["available"] else "❌"
                current = " ← current" if self.provider and p["name"] == self.provider.name else ""
                lines.append(f"  {icon} {p['name']}{current}")
            msgs.add_message("system", "\n".join(lines))

        elif cmd == "/clear":
            self.messages.clear()
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            # Remove all message widgets
            display = self.query_one("#messages", MessageDisplay)
            for child in list(display.children):
                child.remove()
            self._update_status()
            msgs.add_message("system", "Conversation cleared")

        elif cmd == "/system":
            msgs.add_message("system", f"System prompt:\n```\n{self.system_prompt}\n```")

        elif cmd == "/tokens":
            cost = self._estimate_cost()
            msgs.add_message(
                "system",
                f"Session tokens: {self.total_input_tokens + self.total_output_tokens:,}\n"
                f"  Input: {self.total_input_tokens:,}\n"
                f"  Output: {self.total_output_tokens:,}\n"
                f"  Est. cost: ${cost:.4f}"
            )

        elif cmd == "/save":
            path = arg or f"lacp-session-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.jsonl"
            try:
                with open(path, "w") as f:
                    for msg in self.messages:
                        f.write(json.dumps(msg) + "\n")
                msgs.add_message("system", f"Saved {len(self.messages)} messages to {path}")
            except Exception as e:
                msgs.add_message("system", f"Error saving: {e}")

        elif cmd == "/sessions":
            sessions = list_sessions(limit=10)
            if not sessions:
                msgs.add_message("system", "No saved sessions.")
            else:
                lines = ["Recent sessions:", ""]
                for s in sessions:
                    sid = s.get("session_id", "?")
                    size = s.get("size", 0)
                    count = s.get("message_count", "?")
                    provider = s.get("provider", "?")
                    lines.append(f"  {sid}  {count} msgs  {size//1024}KB  {provider}")
                lines.append(f"\nCurrent: {self.session_id}")
                lines.append("Resume: /resume <session_id> or /resume latest")
                msgs.add_message("system", "\n".join(lines))

        elif cmd == "/resume":
            target = arg or "latest"
            if target == "latest":
                target = get_latest_session() or ""
            if not target:
                msgs.add_message("system", "No sessions to resume.")
                return
            loaded_msgs, meta = load_session(target)
            if loaded_msgs:
                self.messages = loaded_msgs
                self.session_id = target
                msgs.add_message("system", f"Resumed {target} ({len(loaded_msgs)} msgs)")
            else:
                msgs.add_message("system", f"Session not found: {target}")

        elif cmd == "/mcp":
            if not self.mcp_manager:
                msgs.add_message("system", "MCP not initialized")
                return
            status = self.mcp_manager.status()
            lines = ["MCP Servers:", ""]
            for name, info in status.items():
                icon = "✅" if info["running"] else "❌"
                tools_count = info["tools"]
                lines.append(f"  {icon} {name:20s} {tools_count:>3d} tools  {info['command'][:40]}")
            total = sum(info["tools"] for info in status.values() if info["running"])
            lines.append(f"\nTotal: {total} MCP tools available")
            msgs.add_message("system", "\n".join(lines))

        elif cmd == "/delegate":
            if not arg:
                msgs.add_message("system", "Usage: /delegate <agent> <task>\nAgents: claude, codex, hermes, gemini, aider")
                return
            parts_d = arg.split(None, 1)
            if len(parts_d) == 1:
                d_agent, d_task = "claude", parts_d[0]
            else:
                d_agent, d_task = parts_d[0], parts_d[1]
            msgs.add_message("system", f"Delegating to {d_agent}: {d_task[:80]}...")
            result = execute_tool("delegate", {"agent": d_agent, "task": d_task})
            try:
                data = json.loads(result)
                output = data.get("output", data.get("error", "no output"))
                msgs.add_message("system", f"{d_agent} result:\n{output[:2000]}")
            except (json.JSONDecodeError, TypeError):
                msgs.add_message("system", f"{d_agent} result:\n{result[:2000]}")

        elif cmd == "/skin":
            if not arg:
                skins = list_skins()
                lines = [f"Current skin: {self.skin.name}", ""]
                for s in skins:
                    current = " ← active" if s["name"] == self.skin.name else ""
                    lines.append(f"  {s['name']:20s} {s['description'][:40]}{current}")
                lines.append("\nUsage: /skin <name>")
                msgs.add_message("system", "\n".join(lines))
            else:
                self.skin = load_skin(arg)
                msgs.add_message("system", f"Skin switched to: {self.skin.name} — {self.skin.description}")
                self._update_status()

        elif cmd == "/dev":
            dev = self.query_one("#dev-panel", DevPanel)
            if arg == "reset":
                dev.reset_all()
                msgs.add_message("system", "Dev panel reset to defaults")
            elif arg == "export":
                css = dev.export_css()
                msgs.add_message("system", f"Current CSS:\n```\n{css}\n```")
            elif arg == "export yaml":
                path = dev.save_skin_yaml()
                msgs.add_message("system", f"Skin saved to {path}\nLoad with: /skin custom")
            elif arg.startswith("preset"):
                preset_name = arg.split(None, 1)[1] if " " in arg else ""
                if not preset_name:
                    from dev_panel import DEV_PRESETS
                    names = ", ".join(DEV_PRESETS.keys())
                    msgs.add_message("system", f"Available presets: {names}")
                elif dev.apply_preset(preset_name):
                    msgs.add_message("system", f"Applied preset: {preset_name}")
                else:
                    from dev_panel import DEV_PRESETS
                    msgs.add_message("system", f"Unknown preset: {preset_name}. Available: {', '.join(DEV_PRESETS.keys())}")
            elif arg in ("close", ""):
                dev.toggle()
            else:
                msgs.add_message("system", "Usage: /dev [close|reset|export|export yaml|preset <name>]")

        elif cmd == "/autoresearch":
            if not self.idle_agent:
                msgs.add_message("system", "Idle agent not initialized")
                return
            if arg == "on":
                self.idle_agent.start()
                msgs.add_message("system", "🔬 Autoresearch enabled — will start after idle timeout")
            elif arg == "start":
                self.idle_agent.start_now()
                msgs.add_message("system", "🔬 Autoresearch started immediately")
            elif arg == "score":
                # Run full two-tier metrics
                import subprocess as _sp
                result = _sp.run(
                    ["python3", str(Path(__file__).parent / "autoresearch_metrics.py"), "--full"],
                    capture_output=True, text=True, timeout=60,
                    cwd=str(Path(__file__).parent.parent),
                )
                msgs.add_message("research", result.stdout.strip() if result.stdout else "Failed to compute score")
            elif arg == "off":
                self.idle_agent.stop()
                msgs.add_message("system", "🔬 Autoresearch stopped")
            elif arg == "status":
                msgs.add_message("research", self.idle_agent.status())
            elif arg == "config":
                config = json.dumps(self.idle_agent.state.config, indent=2)
                msgs.add_message("system", f"Autoresearch config:\n```\n{config}\n```")
            else:
                msgs.add_message("system",
                    "Usage: /autoresearch [on|off|start|score|status|config]\n"
                    "  on     — enable idle monitoring (starts after 5 min idle)\n"
                    "  start  — run experiment immediately\n"
                    "  score  — show current health score\n"
                    "  status — show experiment history\n"
                    "  off    — stop autoresearch")

        else:
            msgs.add_message("system", f"Unknown command: {cmd}. Type /help for commands.")

    @work(thread=True)
    def _stream_response(self) -> None:
        """Agentic loop: stream response, execute tool calls, continue until done."""
        if not self.provider:
            return

        msgs = self.query_one("#messages", MessageDisplay)
        tools = get_tool_definitions()
        # Add MCP tools if available
        if self.mcp_manager:
            mcp_tools = self.mcp_manager.get_tools()
            tools.extend(mcp_tools)
        max_turns = 20  # safety limit

        for turn in range(max_turns):
            self.streaming_content = ""
            self.call_from_thread(lambda: msgs.add_streaming_placeholder())

            # Collect tool calls from this turn
            pending_tool_calls: list[dict] = []
            current_tool_call: dict | None = None
            tool_input_json = ""

            try:
                loop = asyncio.new_event_loop()
                try:
                    async def _consume():
                        nonlocal pending_tool_calls, current_tool_call, tool_input_json
                        async for event in self.provider.stream(
                            messages=self.messages,
                            system=self.system_prompt,
                            tools=tools if isinstance(self.provider, AnthropicProvider) else None,
                        ):
                            if event.type == "text":
                                self.streaming_content += event.text
                                content = self.streaming_content
                                char_count = len(self.streaming_content)
                                def update_ph(text: str = content, chars: int = char_count) -> None:
                                    try:
                                        widget = msgs.query_one(f"#{msgs._streaming_id}", Static)
                                        widget.update(text)
                                        msgs.scroll_end(animate=False)
                                    except Exception:
                                        pass
                                    # Update thinking indicator with approximate token count
                                    indicator = msgs.get_thinking_indicator()
                                    if indicator:
                                        indicator.update_tokens(chars // 4)  # ~4 chars per token
                                self.call_from_thread(update_ph)

                            elif event.type == "tool_use":
                                if event.tool_call:
                                    if event.tool_call.input:
                                        # content_block_stop — complete tool call
                                        pending_tool_calls.append({
                                            "id": event.tool_call.id,
                                            "name": event.tool_call.name,
                                            "input": event.tool_call.input,
                                        })
                                    else:
                                        # content_block_start — show tool name immediately
                                        current_tool_call = {
                                            "id": event.tool_call.id,
                                            "name": event.tool_call.name,
                                            "input": {},
                                        }
                                        tc_name = event.tool_call.name
                                        def show_tool_pending(name: str = tc_name) -> None:
                                            from display import get_tool_emoji, get_tool_verb
                                            emoji = get_tool_emoji(name)
                                            verb = get_tool_verb(name)
                                            msgs.add_message("tool", f"[dim #444466]┊[/] {emoji} [dim]{verb}...[/]")
                                        self.call_from_thread(show_tool_pending)

                            elif event.type == "done":
                                if event.usage:
                                    self.total_input_tokens += event.usage.get("input_tokens", 0)
                                    self.total_output_tokens += event.usage.get("output_tokens", 0)

                    loop.run_until_complete(_consume())
                finally:
                    loop.close()

            except Exception as e:
                err_str = str(e)

                # Auto-fallback on rate limit (429), credit error (400), or auth error (401)
                if any(x in err_str for x in ("429", "rate_limit", "credit balance", "401", "missing_scope")):
                    import time as _time

                    def clear_ph() -> None:
                        msgs.remove_streaming()
                    self.call_from_thread(clear_ph)

                    is_auth_error = any(x in err_str for x in ("401", "missing_scope", "credit balance"))

                    if is_auth_error and hasattr(self.provider, 'refresh_token'):
                        def show_refresh() -> None:
                            msgs.add_message("system", "🔑 Auth error — refreshing OAuth token...")
                        self.call_from_thread(show_refresh)
                        if self.provider.refresh_token():
                            continue

                    # Rate limit — check concurrent sessions and retry with backoff
                    current_model = self.provider.model if self.provider else ""
                    import subprocess as _sp
                    try:
                        cc_count = len(_sp.run(["pgrep", "-la", "claude"], capture_output=True, text=True, timeout=3).stdout.strip().splitlines())
                    except Exception:
                        cc_count = 0

                    # Exponential backoff: 5s, 10s, 20s (max 3 retries then fall to haiku)
                    retry_key = "_rate_limit_retries"
                    retries = getattr(self, retry_key, 0)
                    if retries < 3:
                        wait_secs = 5 * (2 ** retries)
                        setattr(self, retry_key, retries + 1)
                        sessions_note = f" ({cc_count} Claude Code sessions active)" if cc_count > 1 else ""
                        def show_wait(model=current_model, secs=wait_secs, note=sessions_note) -> None:
                            msgs.add_message("system", f"⏳ Rate limited on {model}{note} — retry in {secs}s...")
                        self.call_from_thread(show_wait)
                        _time.sleep(wait_secs)
                        if hasattr(self.provider, '_client'):
                            self.provider._client = None
                        continue
                    else:
                        # After 3 retries, fall back to Haiku
                        setattr(self, retry_key, 0)
                        try:
                            self.provider = create_provider(provider_name="anthropic", model="claude-haiku-4-5-20251001")
                            self.provider._client = None
                            def show_fallback() -> None:
                                msgs.add_message("system",
                                    f"⚡ Switched to Haiku (Sonnet/Opus quota exhausted by {cc_count} concurrent sessions). "
                                    f"Use /model sonnet when sessions free up.")
                                self._update_status()
                            self.call_from_thread(show_fallback)
                            continue
                        except Exception:
                            pass

                # Add debug info for auth errors
                if "credit balance" in err_str or "400" in err_str:
                    auth_info = f"\n\nDebug: provider={self.provider.name}, model={self.provider.model}"
                    if hasattr(self.provider, '_client') and self.provider._client:
                        c = self.provider._client
                        auth_info += f", api_key={'set' if c.api_key else 'None'}"
                        auth_info += f", auth_token={'set' if getattr(c, 'auth_token', None) else 'None'}"
                    err_str += auth_info
                self.streaming_content = f"**Error**: {err_str}"

            # Finalize streaming text for this turn
            final_content = self.streaming_content
            if final_content:
                def finalize_text(content: str = final_content) -> None:
                    msgs.finalize_streaming(content)
                self.call_from_thread(finalize_text)
            else:
                # Remove empty placeholder + label
                def remove_ph() -> None:
                    msgs.remove_streaming()
                self.call_from_thread(remove_ph)

            # If no tool calls, we're done — add assistant message, auto-save, break
            if not pending_tool_calls:
                if final_content:
                    self.messages.append({"role": "assistant", "content": final_content})
                # Auto-save session
                auto_save_session(
                    self.session_id,
                    self.messages,
                    provider_name=self.provider.name if self.provider else "",
                    model=self.provider.model if self.provider else "",
                    total_tokens=self.total_input_tokens + self.total_output_tokens,
                )
                def update_ui() -> None:
                    self._update_status()
                self.call_from_thread(update_ui)
                break

            # Build assistant message with tool use blocks
            content_blocks = []
            if final_content:
                content_blocks.append({"type": "text", "text": final_content})
            for tc in pending_tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            self.messages.append({"role": "assistant", "content": content_blocks})

            # Execute tools and collect results (with hermes-style display)
            tool_results = []
            for tc in pending_tool_calls:
                tool_name = tc["name"]
                tool_input = tc["input"]
                tool_start = time.time()

                # Execute — route MCP tools to MCP manager
                if tool_name.startswith("mcp_") and self.mcp_manager:
                    result = self.mcp_manager.call_tool(tool_name, tool_input)
                else:
                    result = execute_tool(tool_name, tool_input)

                tool_duration = time.time() - tool_start

                # Detect success/failure
                success = True
                try:
                    rdata = json.loads(result)
                    if isinstance(rdata, dict) and ("error" in rdata or rdata.get("exit_code", 0) != 0):
                        success = False
                except (json.JSONDecodeError, TypeError):
                    pass

                # Show hermes-style tool call line with timing
                def show_tool(
                    name: str = tool_name,
                    inp: dict = tool_input,
                    dur: float = tool_duration,
                    ok: bool = success,
                ) -> None:
                    formatted = format_tool_call(name, inp, duration=dur, success=ok)
                    msgs.add_message("tool", formatted)
                self.call_from_thread(show_tool)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result[:50000],
                })

            # Add tool results to conversation
            self.messages.append({"role": "user", "content": tool_results})

            # Update status
            def update_status_mid() -> None:
                self._update_status()
            self.call_from_thread(update_status_mid)

            # Loop continues — next turn will get the model's response to tool results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LACP REPL — multi-provider agent session")
    parser.add_argument("--model", default="haiku", help="Initial model (default: haiku, switch with /model)")
    parser.add_argument("--skin", default="", help="Visual skin (default, cyberpunk, minimal)")
    parser.add_argument("--resume", default="", nargs="?", const="latest",
                       help="Resume session (ID or 'latest')")
    args = parser.parse_args()

    app = LACPRepl(model=args.model, skin_name=args.skin, resume=args.resume or "")
    app.run()


if __name__ == "__main__":
    main()
