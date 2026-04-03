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
from textual.widgets import Footer, Input, Markdown, Static

# Add project paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "automation" / "scripts"))

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
| `/help` | Show this help |
| `/quit` | Exit REPL |
"""


# ─── TUI Components ──────────────────────────────────────────────


class StatusBar(Static):
    """Top status bar showing provider/model/tokens."""

    def update_status(self, provider: str, model: str, tokens: int = 0, cost: float = 0.0) -> None:
        self.update(
            f" ⚡ LACP v{VERSION}  │  {provider}/{model}  │  tokens: {tokens:,}  │  ${cost:.4f}"
        )


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

    def add_streaming_placeholder(self) -> Static:
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
        background: $surface;
        layout: vertical;
    }
    StatusBar {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    MessageDisplay {
        height: 1fr;
        padding: 0 1;
    }
    #input-area {
        height: auto;
        max-height: 5;
        padding: 0 1 1 1;
    }
    Input {
        border: tall $accent;
    }
    Footer {
        height: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+m", "switch_model", "Model", show=False),
    ]

    def __init__(self, model: str = "sonnet", **kwargs: Any):
        super().__init__(**kwargs)
        self.initial_model = model
        self.provider: Provider | None = None
        self.messages: list[dict[str, Any]] = []
        self.system_prompt = ""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.streaming_content = ""

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status")
        yield MessageDisplay(id="messages")
        with Vertical(id="input-area"):
            yield Input(placeholder="Message LACP... (type /help for commands)", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        # Initialize provider
        try:
            self.provider = create_provider(model=self.initial_model)
            self.system_prompt = build_system_prompt()
        except Exception as e:
            self.query_one("#messages", MessageDisplay).add_message(
                "system", f"Error initializing provider: {e}"
            )
            return

        # Update status bar
        self._update_status()

        # Welcome message
        msgs = self.query_one("#messages", MessageDisplay)
        available = list_providers()
        available_names = [p["name"] for p in available if p["available"]]
        msgs.add_message(
            "system",
            f"LACP v{VERSION} — connected to {self.provider.name}/{self.provider.model}\n"
            f"Providers available: {', '.join(available_names)}\n"
            f"Type /help for commands, /model <name> to switch models"
        )

        # Focus input
        self.query_one("#prompt", Input).focus()

    def _update_status(self) -> None:
        if self.provider:
            cost = self._estimate_cost()
            self.query_one("#status", StatusBar).update_status(
                self.provider.name,
                self.provider.model,
                self.total_input_tokens + self.total_output_tokens,
                cost,
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

        # Stream response (runs in background worker thread)
        self._stream_response()

    async def _handle_command(self, text: str) -> None:
        msgs = self.query_one("#messages", MessageDisplay)
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
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

        else:
            msgs.add_message("system", f"Unknown command: {cmd}. Type /help for commands.")

    @work(thread=True)
    def _stream_response(self) -> None:
        """Stream a response from the current provider (runs in worker thread)."""
        if not self.provider:
            return

        msgs = self.query_one("#messages", MessageDisplay)
        self.streaming_content = ""

        # Create streaming placeholder
        self.call_from_thread(lambda: msgs.add_streaming_placeholder())

        try:
            # Run the async generator in a new event loop (we're in a thread)
            loop = asyncio.new_event_loop()
            try:
                async def _consume():
                    async for event in self.provider.stream(
                        messages=self.messages,
                        system=self.system_prompt,
                    ):
                        if event.type == "text":
                            self.streaming_content += event.text
                            content = self.streaming_content
                            def update_placeholder(text: str = content) -> None:
                                try:
                                    widget = msgs.query_one("#streaming", Static)
                                    widget.update(text)
                                    msgs.scroll_end(animate=False)
                                except Exception:
                                    pass
                            self.call_from_thread(update_placeholder)

                        elif event.type == "done":
                            if event.usage:
                                self.total_input_tokens += event.usage.get("input_tokens", 0)
                                self.total_output_tokens += event.usage.get("output_tokens", 0)

                loop.run_until_complete(_consume())
            finally:
                loop.close()

        except Exception as e:
            self.streaming_content = f"**Error**: {e}"

        # Finalize: replace placeholder with rendered markdown
        final_content = self.streaming_content
        if final_content:
            self.messages.append({"role": "assistant", "content": final_content})
            def finalize(content: str = final_content) -> None:
                msgs.finalize_streaming(content)
                self._update_status()
            self.call_from_thread(finalize)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LACP REPL — multi-provider agent session")
    parser.add_argument("--model", default="sonnet", help="Initial model (default: sonnet)")
    args = parser.parse_args()

    app = LACPRepl(model=args.model)
    app.run()


if __name__ == "__main__":
    main()
