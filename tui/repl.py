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
    "/model o3", "/model codex", "/model llama",
    "/skin default", "/skin cyberpunk",
    "/delegate claude", "/delegate codex", "/delegate hermes",
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
| `/model <name>` | Switch model (opus, sonnet, haiku, o3, gpt-4.1, llama) |
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
| `/quit` | Exit REPL |
"""


# ─── TUI Components ──────────────────────────────────────────────


class StatusBar(Static):
    """Top status bar showing provider/model/tokens."""

    def update_status(
        self, provider: str, model: str, tokens: int = 0,
        cost: float = 0.0, skin: Skin | None = None, elapsed: float = 0.0,
        mode: str = "Normal", mcp_servers: int = 0, mcp_tools: int = 0,
    ) -> None:
        badge = skin.badge(provider) if skin else provider
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_str = f"{mins}:{secs:02d}"
        short_model = model
        for prefix in ("claude-", "gpt-", "gemini-"):
            if short_model.startswith(prefix):
                short_model = short_model[len(prefix):]
        if len(short_model) > 15 and short_model[-8:].isdigit():
            short_model = short_model[:-9]
        mode_colors = {"Normal": "#666677", "Plan": "#4ade80", "Think": "#a78bfa", "YOLO": "#ef4444"}
        mode_color = mode_colors.get(mode, "#666677")
        mcp_str = f"  │  [dim]MCP:{mcp_tools}[/]" if mcp_tools > 0 else ""
        self.update(
            f" {badge} [bold]{short_model}[/]  │  "
            f"[{mode_color}]{mode}[/]  │  "
            f"tok:{tokens:,}  │  ${cost:.4f}  │  {time_str}{mcp_str}"
        )

    def update_mode(self, mode_label: str) -> None:
        """Update mode display in status bar (appended)."""
        pass  # Mode shown via messages, not status bar (keeps it clean)


class ThinkingIndicator(Static):
    """Animated thinking indicator with spinning faces and verbs."""

    _frame = 0
    _faces = ["◐", "◓", "◑", "◒"]
    _verb = "thinking"
    _dots = 0
    _timer = None

    def start(self, faces: list[str] | None = None, verb: str = "thinking") -> None:
        self._faces = faces or ["◐", "◓", "◑", "◒"]
        self._verb = verb
        self._frame = 0
        self._dots = 0
        self._render_frame()
        self._timer = self.set_interval(0.3, self._tick)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.remove()

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(self._faces)
        self._dots = (self._dots + 1) % 4
        self._render_frame()

    def _render_frame(self) -> None:
        face = self._faces[self._frame % len(self._faces)]
        dots = "." * self._dots
        self.update(f"  [dim]{face} {self._verb}{dots}[/dim]")


class MessageDisplay(VerticalScroll):
    """Scrollable message display area."""

    def add_message(self, role: str, content: str) -> None:
        if role == "user":
            widget = Static(f"\n[bold cyan]You:[/bold cyan]\n{content}\n", markup=True)
        elif role == "assistant":
            widget = Markdown(content, id=f"msg-{time.time_ns()}")
        elif role == "system":
            widget = Static(f"\n[dim]{content}[/dim]\n", markup=True)
        else:
            widget = Static(content)
        self.mount(widget)
        self.scroll_end(animate=False)

    def add_thinking(self, faces: list[str] | None = None, verb: str = "thinking") -> ThinkingIndicator:
        indicator = ThinkingIndicator(id="thinking")
        self.mount(indicator)
        indicator.start(faces=faces, verb=verb)
        self.scroll_end(animate=False)
        return indicator

    def remove_thinking(self) -> None:
        try:
            self.query_one("#thinking", ThinkingIndicator).stop()
        except Exception:
            pass

    def add_streaming_placeholder(self) -> Static:
        self.remove_thinking()
        # Remove any existing streaming placeholder first
        try:
            existing = self.query_one("#streaming", Static)
            existing.remove()
        except Exception:
            pass
        widget = Static("", id="streaming")
        self.mount(widget)
        self.scroll_end(animate=False)
        return widget

    def finalize_streaming(self, content: str) -> None:
        try:
            placeholder = self.query_one("#streaming", Static)
            placeholder.remove()
        except Exception:
            pass
        # Add as markdown for proper rendering
        widget = Markdown(content, id=f"msg-{time.time_ns()}")
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
        padding: 0 2;
        background: #000000;
    }
    #input-area {
        height: auto;
        max-height: 5;
        padding: 0 2 1 2;
    }
    Input {
        border: tall #333355;
        background: #0a0a14;
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
        padding: 1 2;
        margin: 0 0 1 0;
        background: #050510;
    }
    Markdown {
        margin: 0 0 1 0;
    }
    Static {
        background: transparent;
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
    ]

    def __init__(self, model: str = "sonnet", skin_name: str = "", resume: str = "", **kwargs: Any):
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

    def compose(self) -> ComposeResult:
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

    def on_mount(self) -> None:
        # Set true dark theme
        self.theme = "textual-dark"

        # Initialize provider
        try:
            self.provider = create_provider(model=self.initial_model)
            self.system_prompt = build_system_prompt()
            # Debug: show auth state
            if self.provider and hasattr(self.provider, '_client') and self.provider._client:
                c = self.provider._client
                auth_info = f"Auth debug: api_key={'set' if c.api_key else 'None'}, auth_token={'set' if getattr(c, 'auth_token', None) else 'None'}"
                self.query_one("#messages", MessageDisplay).add_message("system", auth_info)
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

        # Welcome banner
        msgs = self.query_one("#messages", MessageDisplay)
        available = list_providers()
        available_names = [p["name"] for p in available if p["available"]]

        # Build compact welcome banner
        logo = self.skin.banner_logo.strip()
        hero = self.skin.banner_hero.strip()

        # Provider status line with checkmarks
        provider_line = "  "
        for p in available:
            icon = "[green]✓[/]" if p["available"] else "[dim]✗[/]"
            name = p["name"]
            if self.provider and name == self.provider.name:
                provider_line += f"{icon} [bold]{name}[/]  "
            else:
                provider_line += f"{icon} {name}  "

        # Short model name
        short_model = self.provider.model
        for prefix in ("claude-", "gpt-", "gemini-"):
            if short_model.startswith(prefix):
                short_model = short_model[len(prefix):]
        if len(short_model) > 15 and short_model[-8:].isdigit():
            short_model = short_model[:-9]

        banner_text = ""
        if logo:
            banner_text += logo + "\n"
        banner_text += (
            f"\n  [bold]v{VERSION}[/] │ {self.skin.brand('tagline')}"
            f"\n{provider_line}"
            f"\n  Model: [bold]{short_model}[/]"
            f"\n\n  [dim]{self.skin.brand('welcome')}[/]"
            f"\n  [dim]Type /help for commands, /model <name> to switch[/]"
        )

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

        # Focus input
        self.query_one("#prompt", Input).focus()

    @property
    def current_mode(self) -> dict:
        return self.AGENT_MODES[self.current_mode_index]

    def action_cycle_mode(self) -> None:
        """Cycle through agent modes — status bar only, no session message."""
        self.current_mode_index = (self.current_mode_index + 1) % len(self.AGENT_MODES)
        mode = self.current_mode
        self._apply_mode(mode["name"])
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
                msgs.add_message("system", "Usage: /model <name>\nAvailable: opus, sonnet, haiku, o3, gpt-4.1, llama, qwen")
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
                                def update_ph(text: str = content) -> None:
                                    try:
                                        widget = msgs.query_one("#streaming", Static)
                                        widget.update(text)
                                        msgs.scroll_end(animate=False)
                                    except Exception:
                                        pass
                                self.call_from_thread(update_ph)

                            elif event.type == "tool_use":
                                if event.tool_call:
                                    # content_block_stop emits complete tool call with parsed input
                                    if event.tool_call.input:
                                        pending_tool_calls.append({
                                            "id": event.tool_call.id,
                                            "name": event.tool_call.name,
                                            "input": event.tool_call.input,
                                        })
                                    else:
                                        # content_block_start — just track for display
                                        current_tool_call = {
                                            "id": event.tool_call.id,
                                            "name": event.tool_call.name,
                                            "input": {},
                                        }

                            elif event.type == "done":
                                if event.usage:
                                    self.total_input_tokens += event.usage.get("input_tokens", 0)
                                    self.total_output_tokens += event.usage.get("output_tokens", 0)

                    loop.run_until_complete(_consume())
                finally:
                    loop.close()

            except Exception as e:
                err_str = str(e)

                # Auto-fallback on rate limit (429) or credit error (400)
                if "429" in err_str or "rate_limit" in err_str or "credit balance" in err_str:
                    import time as _time
                    # Try fallback chain
                    fallback_models = [
                        ("anthropic", "claude-haiku-4-5-20251001"),  # cheaper, less rate limited
                        ("ollama", "llama3.1:8b"),  # local, no rate limits
                    ]
                    # Remove current provider from fallbacks
                    current = self.provider.name if self.provider else ""
                    fallback_models = [(p, m) for p, m in fallback_models if p != current]

                    def clear_ph() -> None:
                        try:
                            msgs.query_one("#streaming", Static).remove()
                        except Exception:
                            pass
                    self.call_from_thread(clear_ph)

                    # Try each fallback
                    switched = False
                    for fb_provider, fb_model in fallback_models:
                        try:
                            test_provider = create_provider(provider_name=fb_provider, model=fb_model)
                            if test_provider.is_available():
                                self.provider = test_provider
                                self.provider._client = None  # force re-init
                                def show_switch(p=fb_provider, m=fb_model) -> None:
                                    msgs.add_message("system", f"⚡ Auto-switched to {p}/{m} (rate limited on previous)")
                                    self._update_status()
                                self.call_from_thread(show_switch)
                                switched = True
                                break
                        except Exception:
                            continue

                    if switched:
                        continue  # retry with new provider
                    else:
                        # No fallback available — wait and retry same provider
                        def show_retry() -> None:
                            msgs.add_message("system", "⏳ Rate limited — retrying in 5s...")
                        self.call_from_thread(show_retry)
                        _time.sleep(5)
                        continue

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
                # Remove empty placeholder
                def remove_ph() -> None:
                    try:
                        msgs.query_one("#streaming", Static).remove()
                    except Exception:
                        pass
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

            # Execute tools and collect results
            tool_results = []
            for tc in pending_tool_calls:
                tool_name = tc["name"]
                tool_input = tc["input"]

                # Show tool execution in UI
                def show_tool(name: str = tool_name, inp: dict = tool_input) -> None:
                    short_input = json.dumps(inp)[:100]
                    msgs.add_message("system", f"🔧 {name}({short_input})")
                self.call_from_thread(show_tool)

                # Execute — route MCP tools to MCP manager
                if tool_name.startswith("mcp_") and self.mcp_manager:
                    result = self.mcp_manager.call_tool(tool_name, tool_input)
                else:
                    result = execute_tool(tool_name, tool_input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result[:50000],  # truncate large results
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
    parser.add_argument("--model", default="sonnet", help="Initial model (default: sonnet)")
    parser.add_argument("--skin", default="", help="Visual skin (default, cyberpunk, minimal)")
    parser.add_argument("--resume", default="", nargs="?", const="latest",
                       help="Resume session (ID or 'latest')")
    args = parser.parse_args()

    app = LACPRepl(model=args.model, skin_name=args.skin, resume=args.resume or "")
    app.run()


if __name__ == "__main__":
    main()
