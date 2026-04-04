"""LACP Display Helpers — hermes-agent-style tool formatting + Claude Code-style UX.

Provides formatted tool call messages with emojis, fixed-width verbs,
detail previews, and duration timing.

Usage:
    from display import format_tool_call, TOOL_EMOJIS

    msg = format_tool_call("bash", {"command": "git status"}, duration=1.2)
    # → "💻 $         git status  1.2s"
"""
from __future__ import annotations

from pathlib import Path

# ─── Tool Emoji Map (hermes-agent compatible) ─────────────────────

TOOL_EMOJIS: dict[str, str] = {
    # File operations
    "read_file": "📖",
    "write_file": "✍️",
    "edit_file": "🔧",
    "ls": "📂",
    # Search
    "grep": "🔍",
    "glob": "🔎",
    # Shell
    "bash": "💻",
    # Delegation
    "delegate": "🔀",
    # MCP tools
    "mcp_memory_search": "🧠",
    "mcp_memory_store": "🧠",
    "mcp_memory_create": "🧠",
    "mcp_memory_update": "🧠",
    "mcp_memory_delete": "🧠",
    "mcp_obsidian_search": "📚",
    "mcp_obsidian_read": "📚",
    "mcp_obsidian_write": "📚",
    "mcp_qmd_search": "🔍",
    "mcp_qmd_vsearch": "🔍",
    "mcp_qmd_get": "📄",
    "mcp_web_search": "🌐",
    "mcp_web_extract": "📄",
    "mcp_smart-connections_search": "🧠",
    # Browser
    "browser_navigate": "🌐",
    "browser_click": "👆",
    "browser_snapshot": "📸",
    "browser_type": "⌨️",
    # Generic fallback
    "_default": "⚙️",
}

# ─── Tool Verb Map ────────────────────────────────────────────────

TOOL_VERBS: dict[str, str] = {
    "bash": "$",
    "read_file": "read",
    "write_file": "write",
    "edit_file": "edit",
    "grep": "grep",
    "glob": "glob",
    "ls": "ls",
    "delegate": "delegate",
}


def _shorten_path(path: str, max_len: int = 35) -> str:
    """Shorten a file path for display."""
    if not path:
        return ""
    p = Path(path)
    home = Path.home()
    try:
        rel = p.relative_to(home)
        short = f"~/{rel}"
    except ValueError:
        try:
            short = str(p.relative_to(Path.cwd()))
        except ValueError:
            short = str(p)
    if len(short) > max_len:
        short = "..." + short[-(max_len - 3):]
    return short


def _get_tool_detail(tool_name: str, tool_input: dict) -> str:
    """Extract a meaningful detail string from tool input."""
    if tool_name == "bash":
        cmd = tool_input.get("command", "")
        if len(cmd) > 42:
            cmd = cmd[:39] + "..."
        return cmd

    if tool_name in ("read_file", "write_file", "edit_file"):
        return _shorten_path(tool_input.get("file_path", ""))

    if tool_name == "grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", ".")
        if len(pattern) > 20:
            pattern = pattern[:17] + "..."
        return f'"{pattern}" {_shorten_path(path, 15)}'

    if tool_name == "glob":
        return tool_input.get("pattern", "")

    if tool_name == "ls":
        return _shorten_path(tool_input.get("path", "."))

    if tool_name == "delegate":
        agent = tool_input.get("agent", "claude")
        task = tool_input.get("task", "")
        if len(task) > 30:
            task = task[:27] + "..."
        return f"{agent}: {task}"

    # MCP tools — show first meaningful param
    for key in ("query", "search", "path", "name", "url", "note", "content", "arguments"):
        val = tool_input.get(key, "")
        if val:
            val_str = str(val)
            if len(val_str) > 35:
                val_str = val_str[:32] + "..."
            return val_str

    return ""


def get_tool_emoji(tool_name: str) -> str:
    """Get emoji for a tool name, with MCP prefix matching."""
    if tool_name in TOOL_EMOJIS:
        return TOOL_EMOJIS[tool_name]
    # Try partial match for MCP tools (mcp_server_toolname)
    for key, emoji in TOOL_EMOJIS.items():
        if tool_name.startswith(key):
            return emoji
    return TOOL_EMOJIS["_default"]


def get_tool_verb(tool_name: str) -> str:
    """Get verb for a tool name, extracting from MCP prefix if needed."""
    if tool_name in TOOL_VERBS:
        return TOOL_VERBS[tool_name]
    # MCP tools: use a short, readable verb
    if tool_name.startswith("mcp_"):
        parts = tool_name.split("_", 2)
        if len(parts) >= 3:
            suffix = parts[2]
            # Map common MCP actions to short verbs
            verb_map = {
                "search": "search",
                "read": "read",
                "write": "write",
                "create": "create",
                "update": "update",
                "delete": "delete",
                "get": "get",
                "list": "list",
            }
            for prefix, short in verb_map.items():
                if suffix.startswith(prefix):
                    return short
            return suffix[:9]
        return parts[-1][:9]
    return tool_name[:9]


def format_tool_call(
    tool_name: str,
    tool_input: dict,
    duration: float | None = None,
    success: bool = True,
) -> str:
    """Format a tool call in hermes-agent style.

    Returns a Rich-markup string like:
        [dim]┊[/] 💻 [bold]$[/]         git status  [dim]1.2s[/]
    """
    emoji = get_tool_emoji(tool_name)
    verb = get_tool_verb(tool_name)
    detail = _get_tool_detail(tool_name, tool_input)

    # Fixed-width verb (9 chars) like hermes-agent
    verb_padded = f"{verb:<9}"

    # Duration string
    duration_str = ""
    if duration is not None:
        duration_str = f"  [dim]{duration:.1f}s[/]"

    # Failure marker
    fail_str = ""
    if not success:
        fail_str = " [red]\\[error][/]"

    return f"[dim #444466]┊[/] {emoji} [bold]{verb_padded}[/] {detail}{duration_str}{fail_str}"


def format_tool_result_preview(tool_name: str, result: str, max_len: int = 60) -> str:
    """Format a short preview of a tool result."""
    if not result:
        return ""
    # Try to parse as JSON for structured preview
    try:
        import json
        data = json.loads(result)
        if isinstance(data, dict):
            if "error" in data:
                return f"[red]error: {str(data['error'])[:max_len]}[/]"
            if "exit_code" in data and data["exit_code"] != 0:
                return f"[yellow]exit {data['exit_code']}[/]"
            if "ok" in data:
                return "[green]ok[/]"
        return ""
    except (ValueError, TypeError):
        pass
    # Plain text preview
    first_line = result.split("\n")[0][:max_len]
    if len(result) > max_len:
        first_line += "..."
    return first_line


def format_thinking_status(elapsed: float, verb: str = "thinking") -> str:
    """Format the thinking status with duration like Claude Code."""
    if elapsed < 2:
        return f"{verb}..."
    return f"{verb} for {elapsed:.0f}s"


def format_delegation_tree(agent: str, task: str, index: int = 0) -> str:
    """Format a delegation call in hermes-agent tree style."""
    task_short = task[:55] if len(task) <= 55 else task[:52] + "..."
    prefix = f"[{index + 1}]" if index >= 0 else ""
    return f"[dim]  {prefix} ├─[/] 🔀 {agent}  \"{task_short}\""
