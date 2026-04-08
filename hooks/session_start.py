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
import time
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

    # Budget-aware injection: collect (priority, label, content) tuples
    # Lower priority number = higher importance = injected first
    injections: list[tuple[int, str, str]] = []
    budget_tokens = int(os.getenv("LACP_SESSION_BUDGET_TOKENS", "1500"))

    # Priority 1: LACP identity (always)
    lacp_agent = os.environ.get("LACP_BANNER_AGENT", "")
    lacp_model = os.environ.get("LACP_BANNER_MODEL", "")
    lacp_mode = os.environ.get("LACP_BANNER_MODE", "")
    lacp_ver = os.environ.get("LACP_BANNER_VERSION", "")
    if lacp_agent or lacp_ver:
        identity_parts = ["Session managed by LACP (Local Agent Control Plane)"]
        if lacp_ver:
            identity_parts[0] += f" v{lacp_ver}"
        if lacp_agent:
            identity_parts.append(f"Agent: {lacp_agent}")
        if lacp_model:
            identity_parts.append(f"Model: {lacp_model}")
        if lacp_mode:
            identity_parts.append(f"Mode: {lacp_mode}")
        injections.append((1, "identity", " | ".join(identity_parts)))

    # Priority 5: Git context (always, when in a repo)
    if _is_git_repo():
        git_parts = _git_context()
        if git_parts:
            injections.append((5, "git", "gitStatus: " + " | ".join(git_parts)))

    # Priority 6: Detect and cache test command
    test_cmd = _detect_test_command()
    if test_cmd:
        injections.append((6, "test_cmd", f"Test command: {test_cmd}"))
        _cache_test_command(test_cmd)

    # Compact-specific reminder
    if matcher == "compact":
        injections.append((1, "compact",
            "Post-compaction reminder: Review CLAUDE.md for project conventions. "
            "Check git branch and recent commits for context. "
            "Verify build/test commands before making changes."
        ))

    # Priority 3: Focus brief injection (skip if blank template)
    focus_file = Path(os.getenv("LACP_FOCUS_FILE", Path.home() / ".lacp" / "focus.md"))
    if focus_file.is_file():
        try:
            focus_content = focus_file.read_text().strip()
            # Skip if it's still the blank template (all placeholders present)
            is_blank = all(marker in focus_content for marker in [
                "<!-- Replace", "{one sentence", "{decision 1}", "{blocker"
            ])
            if focus_content and not is_blank:
                age_days = int((time.time() - focus_file.stat().st_mtime) / 86400)
                stale_note = ""
                if age_days > 7:
                    stale_note = (
                        f" (STALE: {age_days} days old — run `lacp focus edit` to refresh)"
                    )
                injections.append((3, "focus", f"Focus brief{stale_note}:\n{focus_content}"))
        except OSError:
            pass

    # Priority 4: Handoff artifact injection
    try:
        import hashlib
        cwd_hash = hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:12]
        handoff_file = Path.home() / ".lacp" / "handoffs" / f"{cwd_hash}-latest.json"
        if handoff_file.is_file():
            age_hours = (time.time() - handoff_file.stat().st_mtime) / 3600
            if age_hours < 24:
                handoff = json.loads(handoff_file.read_text())
                summary = handoff.get("task_summary", "")[:200]
                branch = handoff.get("git_branch", "")
                test_status = handoff.get("test_status", "unknown")
                files = handoff.get("files_modified", [])
                next_steps = handoff.get("next_steps", [])
                handoff_parts = [f"Previous session handoff ({int(age_hours)}h ago):"]
                if summary:
                    handoff_parts.append(f"  Summary: {summary}")
                if branch:
                    handoff_parts.append(f"  Branch: {branch}")
                if test_status != "unknown":
                    handoff_parts.append(f"  Tests: {test_status}")
                if files:
                    handoff_parts.append(f"  Modified: {', '.join(files[:10])}")
                if next_steps:
                    handoff_parts.append(f"  Next: {'; '.join(next_steps[:5])}")
                injections.append((4, "handoff", "\n".join(handoff_parts)))
    except Exception:
        pass

    # Priority 8: Health snapshot context
    try:
        snapshot_dir = Path.home() / ".lacp" / "health" / "snapshots"
        if snapshot_dir.is_dir():
            snapshots = sorted(snapshot_dir.glob("snapshot-*.json"))
            if snapshots:
                latest = json.loads(snapshots[-1].read_text())
                score = latest.get("health_score", "?")
                penalties = latest.get("penalties", [])
                age_h = int((time.time() - snapshots[-1].stat().st_mtime) / 3600)
                if age_h < 24:
                    health_line = f"System health: {score}/100 ({age_h}h ago)"
                    if penalties:
                        health_line += f" [{'; '.join(penalties[:3])}]"
                    injections.append((8, "health", health_line))
    except Exception:
        pass

    # Priority 7: Self-Memory System context (Conway SMS)
    try:
        from self_memory_system import build_session_context
        sms_context = build_session_context()
        if sms_context:
            injections.append((7, "sms", f"Agent memory (SMS):\n{sms_context}"))
    except Exception:
        pass

    # Priority 2: LACP context mode (high priority — behavioral rules)
    mode = os.getenv("LACP_CONTEXT_MODE", "").strip()
    if mode:
        mode_content = _load_context_mode(mode)
        if mode_content:
            injections.append((2, "mode", mode_content))

    # Cleanup stale contracts/state from old sessions (cheap, best-effort)
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from hook_contracts import cleanup_stale_contracts, cleanup_stale_state
        stale_contracts = cleanup_stale_contracts(max_age_hours=48)
        stale_state = cleanup_stale_state(max_age_hours=48)
        if stale_contracts > 0 or stale_state > 0:
            parts.append(f"Cleaned {stale_contracts} stale contracts, {stale_state} stale state dirs")
    except Exception:
        pass

    # Write session start contract for stop hook and other consumers
    try:
        from hook_contracts import SessionStartOutput, write_contract as _write_contract

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
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            context_budget_hint=int(os.getenv("LACP_CONTEXT_BUDGET_HINT", "180000")),
        )
        _write_contract("session_start", _contract)
    except Exception:
        pass  # Contract writing is best-effort

    # Priority 9: Graceful degradation feedback
    degraded = []
    if not test_cmd:
        degraded.append("test verification (no test command detected)")
    if os.getenv("LACP_EVAL_CHECKPOINT_ENABLED") == "1" and not test_cmd:
        degraded.append("eval checkpoint (requires test command)")
    if degraded:
        injections.append((9, "degraded", f"Degraded: {', '.join(degraded)}"))

    # Budget-aware assembly: sort by priority, include until budget exhausted
    injections.sort(key=lambda x: x[0])
    parts: list[str] = []
    token_estimate = 0
    for _priority, _label, content in injections:
        content_tokens = len(content) // 4  # rough estimate
        if token_estimate + content_tokens > budget_tokens and parts:
            break  # budget exceeded, skip remaining lower-priority items
        parts.append(content)
        token_estimate += content_tokens

    if parts:
        print(json.dumps({"systemMessage": "\n".join(parts)}))


if __name__ == "__main__":
    main()
