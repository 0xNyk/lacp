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
    """Write test command to session state dir for stop hook to pick up."""
    session_id = os.getenv("CLAUDE_SESSION_ID", "default")
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    state_dir = Path.home() / ".lacp" / "hooks" / "state" / safe_id
    try:
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (state_dir / "test-cmd").write_text(cmd)
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

    # Focus brief injection
    focus_file = Path(os.getenv("LACP_FOCUS_FILE", Path.home() / ".lacp" / "focus.md"))
    if focus_file.is_file():
        try:
            focus_content = focus_file.read_text().strip()
            if focus_content:
                # Check staleness (warn if >7 days old)
                import time as _t
                age_days = int((_t.time() - focus_file.stat().st_mtime) / 86400)
                stale_note = ""
                if age_days > 7:
                    stale_note = (
                        f" (STALE: {age_days} days old — run `lacp-focus edit` to refresh)"
                    )
                parts.append(f"Focus brief{stale_note}:\n{focus_content}")
        except OSError:
            pass

    # LACP context mode
    mode = os.getenv("LACP_CONTEXT_MODE", "").strip()
    if mode:
        mode_content = _load_context_mode(mode)
        if mode_content:
            parts.append(mode_content)

    # Write session start contract for stop hook and other consumers
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from hook_contracts import SessionStartOutput, write_contract as _write_contract
        import time as _time

        _branch = None
        if _is_git_repo():
            try:
                _branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip() or None
            except Exception:
                pass

        _contract = SessionStartOutput(
            test_cmd=test_cmd,
            git_branch=_branch,
            context_mode=mode if mode else None,
            started_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            context_budget_hint=int(os.getenv("LACP_CONTEXT_BUDGET_HINT", "180000")),
        )
        _write_contract("session_start", _contract)
    except Exception:
        pass  # Contract writing is best-effort

    if parts:
        print(json.dumps({"systemMessage": "\n".join(parts)}))


if __name__ == "__main__":
    main()
