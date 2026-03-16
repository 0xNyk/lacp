#!/usr/bin/env python3
"""Unified SessionStart hook — replaces 3 separate hook entries.

Injects git context, detects + caches test commands, handles compact/startup
matchers, and loads LACP context modes.

Hook protocol:
  - exit 0 with {"systemMessage": "..."} → inject system context
  - exit 0 with no output → no-op
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def _is_git_repo() -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _git_context() -> list[str]:
    """Gather branch, recent commits, and modified files."""
    parts = []
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if branch:
            parts.append(f"Branch: {branch}")
    except Exception:
        pass

    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if log:
            parts.append(f"Recent commits:\n{log}")
    except Exception:
        pass

    try:
        status = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if status:
            parts.append(f"Modified files:\n{status}")
    except Exception:
        pass

    return parts


def _detect_test_command() -> str | None:
    """Auto-detect test command from project files in cwd."""
    cwd = Path.cwd()

    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                for runner in ("bun", "pnpm", "yarn", "npm"):
                    try:
                        subprocess.run(["which", runner], capture_output=True, timeout=3, check=True)
                        return f"{runner} test"
                    except Exception:
                        continue
        except (json.JSONDecodeError, OSError):
            pass

    if (cwd / "Makefile").exists():
        try:
            content = (cwd / "Makefile").read_text()
            if re.search(r"^test\s*:", content, re.MULTILINE):
                return "make test"
        except OSError:
            pass

    if (cwd / "Cargo.toml").exists():
        return "cargo test"

    if (cwd / "pyproject.toml").exists():
        return "python3 -m pytest"

    return None


def _cache_test_command(cmd: str) -> None:
    """Write test command to /tmp for stop hook to pick up."""
    session_id = os.getenv("CLAUDE_SESSION_ID", "default")
    path = Path(f"/tmp/lacp-session-test-cmd-{session_id}")
    try:
        path.write_text(cmd)
    except OSError:
        pass


def _load_context_mode(mode: str) -> str | None:
    """Load LACP context mode file if available."""
    hooks_dir = Path(__file__).parent
    lacp_root = hooks_dir.parent

    mode_file = lacp_root / "config" / "context-modes" / f"{mode}.md"
    if mode_file.is_file():
        try:
            content = mode_file.read_text()
            return f"Active context mode: {mode}\n\n{content}"
        except OSError:
            pass

    # Try brew location
    try:
        brew_prefix = subprocess.run(
            ["brew", "--prefix", "lacp"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if brew_prefix:
            brew_mode = Path(brew_prefix) / "libexec" / "config" / "context-modes" / f"{mode}.md"
            if brew_mode.is_file():
                content = brew_mode.read_text()
                return f"Active context mode: {mode}\n\n{content}"
    except Exception:
        pass

    return None


def main() -> None:
    payload = _read_payload()
    matcher = payload.get("matcher") or ""
    parts: list[str] = []

    # Git context (always, when in a repo)
    if _is_git_repo():
        git_parts = _git_context()
        if git_parts:
            parts.append("gitStatus: " + " | ".join(git_parts))

    # Detect and cache test command
    test_cmd = _detect_test_command()
    if test_cmd:
        parts.append(f"Test command: {test_cmd}")
        _cache_test_command(test_cmd)

    # Compact-specific reminder
    if matcher == "compact":
        parts.append(
            "Post-compaction reminder: Review CLAUDE.md for project conventions. "
            "Check git branch and recent commits for context. "
            "Verify build/test commands before making changes."
        )

    # LACP context mode
    mode = os.getenv("LACP_CONTEXT_MODE", "").strip()
    if mode:
        mode_content = _load_context_mode(mode)
        if mode_content:
            parts.append(mode_content)

    if parts:
        print(json.dumps({"systemMessage": "\n".join(parts)}))


if __name__ == "__main__":
    main()
