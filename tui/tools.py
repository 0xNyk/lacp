#!/usr/bin/env python3
"""LACP Tool Registry — built-in tools for the native REPL.

Provides file operations, bash execution, grep, and glob —
the minimum tool set for a coding agent.

Each tool is defined with:
- name: tool identifier
- description: what the tool does
- input_schema: JSON Schema for parameters
- handler: function that executes the tool

Usage:
    from tools import TOOL_REGISTRY, execute_tool, get_tool_definitions

    # Get Anthropic-format tool definitions
    tools = get_tool_definitions()

    # Execute a tool call
    result = execute_tool("bash", {"command": "ls -la"})
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


# ─── Tool Handlers ────────────────────────────────────────────────


def _handle_bash(params: dict[str, Any]) -> str:
    """Execute a bash command and return output."""
    command = params.get("command", "")
    if not command:
        return json.dumps({"error": "No command provided"})

    # Safety: block obviously destructive commands
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd"]
    for d in dangerous:
        if d in command:
            return json.dumps({"error": f"Blocked dangerous command: {command[:50]}"})

    timeout = min(params.get("timeout", 30), 120)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        output = result.stdout
        if result.stderr:
            output += f"\n{result.stderr}" if output else result.stderr

        # Truncate large outputs
        if len(output) > 50000:
            head = output[:20000]
            tail = output[-30000:]
            output = f"{head}\n\n... (truncated {len(output) - 50000} chars) ...\n\n{tail}"

        return json.dumps({
            "stdout": result.stdout[:30000],
            "stderr": result.stderr[:10000],
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_read_file(params: dict[str, Any]) -> str:
    """Read a file and return its contents."""
    path = params.get("file_path", "")
    if not path:
        return json.dumps({"error": "No file_path provided"})

    file_path = Path(path).expanduser()
    if not file_path.exists():
        return json.dumps({"error": f"File not found: {path}"})
    if not file_path.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    try:
        size = file_path.stat().st_size
        if size > 10_000_000:  # 10MB limit
            return json.dumps({"error": f"File too large: {size} bytes (max 10MB)"})

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Optional line range
        offset = params.get("offset", 0)
        limit = params.get("limit", 0)
        if offset or limit:
            lines = content.split("\n")
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]
            content = "\n".join(lines)

        return content
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_write_file(params: dict[str, Any]) -> str:
    """Write content to a file."""
    path = params.get("file_path", "")
    content = params.get("content", "")
    if not path:
        return json.dumps({"error": "No file_path provided"})

    file_path = Path(path).expanduser()

    # Safety: don't write to system dirs
    blocked_prefixes = ["/System", "/usr", "/bin", "/sbin", "/etc"]
    for prefix in blocked_prefixes:
        if str(file_path).startswith(prefix):
            return json.dumps({"error": f"Cannot write to system path: {path}"})

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(file_path), "bytes": len(content)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_edit_file(params: dict[str, Any]) -> str:
    """Edit a file by replacing old_string with new_string."""
    path = params.get("file_path", "")
    old_string = params.get("old_string", "")
    new_string = params.get("new_string", "")

    if not path:
        return json.dumps({"error": "No file_path provided"})
    if not old_string:
        return json.dumps({"error": "No old_string provided"})

    file_path = Path(path).expanduser()
    if not file_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        content = file_path.read_text(encoding="utf-8")
        if old_string not in content:
            return json.dumps({"error": "old_string not found in file"})

        count = content.count(old_string)
        if count > 1 and not params.get("replace_all", False):
            return json.dumps({"error": f"old_string found {count} times. Use replace_all=true or provide more context."})

        if params.get("replace_all", False):
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        file_path.write_text(new_content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(file_path), "replacements": count if params.get("replace_all") else 1})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_grep(params: dict[str, Any]) -> str:
    """Search file contents with regex."""
    pattern = params.get("pattern", "")
    path = params.get("path", ".")
    if not pattern:
        return json.dumps({"error": "No pattern provided"})

    try:
        args = ["rg", "--json", "-n", "--max-count", "50"]
        if params.get("case_insensitive", False):
            args.append("-i")
        file_type = params.get("type", "")
        if file_type:
            args.extend(["--type", file_type])
        glob_filter = params.get("glob", "")
        if glob_filter:
            args.extend(["--glob", glob_filter])
        args.extend([pattern, path])

        result = subprocess.run(args, capture_output=True, text=True, timeout=15)

        # Parse ripgrep JSON output into readable format
        matches = []
        for line in result.stdout.splitlines():
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    file_path = match_data["path"]["text"]
                    line_num = match_data["line_number"]
                    line_text = match_data["lines"]["text"].rstrip()
                    matches.append(f"{file_path}:{line_num}: {line_text}")
            except (json.JSONDecodeError, KeyError):
                continue

        if not matches:
            return "No matches found."
        return "\n".join(matches[:50])
    except FileNotFoundError:
        # Fallback to grep if rg not available
        try:
            args = ["grep", "-rn", pattern, path]
            result = subprocess.run(args, capture_output=True, text=True, timeout=15)
            return result.stdout[:20000] or "No matches found."
        except Exception as e:
            return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_glob(params: dict[str, Any]) -> str:
    """Find files matching a glob pattern."""
    pattern = params.get("pattern", "")
    path = params.get("path", ".")
    if not pattern:
        return json.dumps({"error": "No pattern provided"})

    try:
        base = Path(path).expanduser()
        matches = sorted(str(p) for p in base.glob(pattern))[:100]
        if not matches:
            return "No files found."
        return "\n".join(matches)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_ls(params: dict[str, Any]) -> str:
    """List directory contents."""
    path = params.get("path", ".")
    try:
        base = Path(path).expanduser()
        if not base.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        if base.is_file():
            stat = base.stat()
            return f"{base.name}  {stat.st_size} bytes"

        entries = []
        for p in sorted(base.iterdir()):
            kind = "dir" if p.is_dir() else "file"
            size = p.stat().st_size if p.is_file() else 0
            entries.append(f"{'d' if kind == 'dir' else '-'}  {size:>10}  {p.name}")
        return "\n".join(entries[:200]) or "(empty directory)"
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool Registry ────────────────────────────────────────────────


TOOL_REGISTRY: dict[str, Tool] = {
    "bash": Tool(
        name="bash",
        description="Execute a bash command in the current working directory. Returns stdout, stderr, and exit code.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (max 120)", "default": 30},
            },
            "required": ["command"],
        },
        handler=_handle_bash,
    ),
    "read_file": Tool(
        name="read_file",
        description="Read the contents of a file. Supports optional line offset and limit.",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute or relative path to the file"},
                "offset": {"type": "integer", "description": "Line number to start from (0-indexed)", "default": 0},
                "limit": {"type": "integer", "description": "Max lines to read (0 = all)", "default": 0},
            },
            "required": ["file_path"],
        },
        handler=_handle_read_file,
    ),
    "write_file": Tool(
        name="write_file",
        description="Write content to a file. Creates parent directories if needed.",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to write the file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["file_path", "content"],
        },
        handler=_handle_write_file,
    ),
    "edit_file": Tool(
        name="edit_file",
        description="Edit a file by replacing old_string with new_string. The old_string must be unique in the file unless replace_all is true.",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file"},
                "old_string": {"type": "string", "description": "The exact string to find and replace"},
                "new_string": {"type": "string", "description": "The replacement string"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        handler=_handle_edit_file,
    ),
    "grep": Tool(
        name="grep",
        description="Search file contents using regex pattern (uses ripgrep). Returns matching lines with file paths and line numbers.",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "case_insensitive": {"type": "boolean", "description": "Case-insensitive search", "default": False},
                "type": {"type": "string", "description": "File type filter (e.g., py, ts, rs)"},
                "glob": {"type": "string", "description": "Glob pattern to filter files"},
            },
            "required": ["pattern"],
        },
        handler=_handle_grep,
    ),
    "glob": Tool(
        name="glob",
        description="Find files matching a glob pattern. Returns file paths.",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')"},
                "path": {"type": "string", "description": "Base directory to search from", "default": "."},
            },
            "required": ["pattern"],
        },
        handler=_handle_glob,
    ),
    "ls": Tool(
        name="ls",
        description="List directory contents with file sizes.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list", "default": "."},
            },
        },
        handler=_handle_ls,
    ),
}


def _handle_delegate(params: dict[str, Any]) -> str:
    """Delegate a task to an external agent CLI (claude, codex, hermes, etc.)."""
    agent = params.get("agent", "claude")
    task = params.get("task", "")
    if not task:
        return json.dumps({"error": "No task provided"})

    # Map agent names to CLI commands
    agent_cmds = {
        "claude": ["claude", "-p", task],
        "codex": ["codex", "exec", task],
        "hermes": ["hermes", "chat", "-Q", "-q", task],
        "gemini": ["gemini", "-p", task],
        "aider": ["aider", "--message", task],
    }

    cmd = agent_cmds.get(agent)
    if not cmd:
        return json.dumps({"error": f"Unknown agent: {agent}. Available: {list(agent_cmds.keys())}"})

    # Check if agent binary exists
    binary = cmd[0]
    native = Path.home() / ".local" / "bin" / f"{binary}.native"
    if native.exists():
        cmd[0] = str(native)
    else:
        import shutil
        found = shutil.which(binary)
        if not found:
            return json.dumps({"error": f"Agent '{agent}' not found in PATH"})
        cmd[0] = found

    timeout = min(params.get("timeout", 120), 300)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
            env={**os.environ, "LACP_BYPASS": "1"},  # skip LACP wrapper
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr[:5000]}"

        # Truncate
        if len(output) > 50000:
            output = output[:20000] + f"\n\n... (truncated) ...\n\n" + output[-20000:]

        return json.dumps({
            "agent": agent,
            "exit_code": result.returncode,
            "output": output,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Agent '{agent}' timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


TOOL_REGISTRY["delegate"] = Tool(
    name="delegate",
    description="Delegate a complex task to an external agent (claude, codex, hermes, gemini, aider). Use for multi-file refactors, autonomous coding, or tasks that need a full agent runtime.",
    input_schema={
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Agent to delegate to (claude, codex, hermes, gemini, aider)",
                "default": "claude",
            },
            "task": {"type": "string", "description": "Task description for the agent"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (max 300)", "default": 120},
        },
        "required": ["task"],
    },
    handler=_handle_delegate,
)


# ─── Memory Tools ────────────────────────────────────────────────


_MEMORY_DIR = Path.home() / ".lacp" / "memory"


def _handle_memory_read(params: dict[str, Any]) -> str:
    """Read a memory entry by key."""
    key = params.get("key", "")
    if not key:
        return json.dumps({"error": "No key provided"})

    file_path = _MEMORY_DIR / f"{key}.json"
    if not file_path.exists():
        return json.dumps({"error": f"Memory key not found: {key}", "available": _list_memory_keys()})

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_memory_write(params: dict[str, Any]) -> str:
    """Write or update a memory entry."""
    key = params.get("key", "")
    content = params.get("content", "")
    if not key:
        return json.dumps({"error": "No key provided"})
    if not content:
        return json.dumps({"error": "No content provided"})

    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _MEMORY_DIR / f"{key}.json"

    try:
        import time as _t
        data = {
            "key": key,
            "content": content,
            "updated_at": _t.strftime("%Y-%m-%dT%H:%M:%S"),
            "tags": params.get("tags", []),
        }
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return json.dumps({"ok": True, "key": key, "action": "updated" if file_path.exists() else "created"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _handle_memory_search(params: dict[str, Any]) -> str:
    """Search memory entries by keyword."""
    query = params.get("query", "").lower()
    if not query:
        return json.dumps({"error": "No query provided"})

    if not _MEMORY_DIR.exists():
        return json.dumps({"results": [], "count": 0})

    results = []
    for f in sorted(_MEMORY_DIR.glob("*.json")):
        try:
            text = f.read_text(encoding="utf-8")
            if query in text.lower():
                data = json.loads(text)
                results.append({
                    "key": f.stem,
                    "preview": str(data.get("content", ""))[:200],
                    "updated": data.get("updated_at", ""),
                })
        except Exception:
            continue

    return json.dumps({"results": results[:20], "count": len(results)})


def _list_memory_keys() -> list[str]:
    if not _MEMORY_DIR.exists():
        return []
    return sorted(f.stem for f in _MEMORY_DIR.glob("*.json"))


def _handle_memory_list(params: dict[str, Any]) -> str:
    """List all memory keys."""
    keys = _list_memory_keys()
    return json.dumps({"keys": keys, "count": len(keys)})


TOOL_REGISTRY["memory_read"] = Tool(
    name="memory_read",
    description="Read a persisted memory entry by key. Memory stores facts, context, and learned patterns across sessions.",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key to read"},
        },
        "required": ["key"],
    },
    handler=_handle_memory_read,
)

TOOL_REGISTRY["memory_write"] = Tool(
    name="memory_write",
    description="Write or update a persisted memory entry. Use to store facts, context, decisions, or patterns for future sessions.",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key (e.g., 'project-goals', 'user-preferences')"},
            "content": {"type": "string", "description": "Content to store"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for categorization"},
        },
        "required": ["key", "content"],
    },
    handler=_handle_memory_write,
)

TOOL_REGISTRY["memory_search"] = Tool(
    name="memory_search",
    description="Search memory entries by keyword. Returns matching entries with previews.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
    handler=_handle_memory_search,
)

TOOL_REGISTRY["memory_list"] = Tool(
    name="memory_list",
    description="List all stored memory keys.",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_memory_list,
)


# ─── Task Tools ──────────────────────────────────────────────────


_TASKS: list[dict[str, Any]] = []


def _handle_task_create(params: dict[str, Any]) -> str:
    """Create a new task."""
    title = params.get("title", "")
    if not title:
        return json.dumps({"error": "No title provided"})

    task = {
        "id": len(_TASKS) + 1,
        "title": title,
        "status": "pending",
        "description": params.get("description", ""),
    }
    _TASKS.append(task)
    return json.dumps({"ok": True, "task": task})


def _handle_task_update(params: dict[str, Any]) -> str:
    """Update task status."""
    task_id = params.get("id", 0)
    status = params.get("status", "")
    if not task_id or not status:
        return json.dumps({"error": "Need id and status"})

    for task in _TASKS:
        if task["id"] == task_id:
            task["status"] = status
            return json.dumps({"ok": True, "task": task})
    return json.dumps({"error": f"Task {task_id} not found"})


def _handle_task_list(params: dict[str, Any]) -> str:
    """List all tasks."""
    return json.dumps({"tasks": _TASKS, "count": len(_TASKS)})


TOOL_REGISTRY["task_create"] = Tool(
    name="task_create",
    description="Create a task to track work progress. Use for multi-step operations.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title"},
            "description": {"type": "string", "description": "Task details"},
        },
        "required": ["title"],
    },
    handler=_handle_task_create,
)

TOOL_REGISTRY["task_update"] = Tool(
    name="task_update",
    description="Update a task status (pending, in_progress, completed).",
    input_schema={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "Task ID"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
        },
        "required": ["id", "status"],
    },
    handler=_handle_task_update,
)

TOOL_REGISTRY["task_list"] = Tool(
    name="task_list",
    description="List all tasks with their status.",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_task_list,
)


# ─── Skill Tools ─────────────────────────────────────────────────


_SKILLS_DIR = Path.home() / ".claude" / "skills"


def _handle_skill_list(params: dict[str, Any]) -> str:
    """List available skills."""
    skills = []
    if _SKILLS_DIR.exists():
        for d in sorted(_SKILLS_DIR.iterdir()):
            if d.is_dir():
                skill_file = d / "SKILL.md"
                desc = ""
                if skill_file.exists():
                    # Read first non-empty, non-heading line as description
                    for line in skill_file.read_text().splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("---"):
                            desc = line[:100]
                            break
                skills.append({"name": d.name, "description": desc})
    return json.dumps({"skills": skills, "count": len(skills)})


def _handle_skill_read(params: dict[str, Any]) -> str:
    """Read a skill definition."""
    name = params.get("name", "")
    if not name:
        return json.dumps({"error": "No skill name provided"})

    skill_dir = _SKILLS_DIR / name
    if not skill_dir.exists():
        return json.dumps({"error": f"Skill not found: {name}"})

    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text(encoding="utf-8")[:10000]

    # Try alternative files
    for alt in ("README.md", "skill.md", "index.md"):
        alt_file = skill_dir / alt
        if alt_file.exists():
            return alt_file.read_text(encoding="utf-8")[:10000]

    return json.dumps({"error": f"No skill definition found in {skill_dir}"})


TOOL_REGISTRY["skill_list"] = Tool(
    name="skill_list",
    description="List available skills (from ~/.claude/skills/). Skills provide specialized capabilities.",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_skill_list,
)

TOOL_REGISTRY["skill_read"] = Tool(
    name="skill_read",
    description="Read a skill's definition and instructions.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name to read"},
        },
        "required": ["name"],
    },
    handler=_handle_skill_read,
)


# ─── Public API ──────────────────────────────────────────────────


def get_tool_definitions() -> list[dict[str, Any]]:
    """Get Anthropic-format tool definitions for all registered tools."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in TOOL_REGISTRY.values()
    ]


def execute_tool(name: str, params: dict[str, Any]) -> str:
    """Execute a tool by name with given parameters."""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return tool.handler(params)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}"})
