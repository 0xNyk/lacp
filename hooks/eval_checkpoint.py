#!/usr/bin/env python3
"""PostToolUse(Write|Edit) checkpoint — continuous QA during work.

Runs the project's test command at configurable intervals during a session.
Injects feedback via systemMessage when tests fail, without blocking.

Hook protocol (PostToolUse hook, matcher: Write|Edit):
  - exit 0 with no stdout → no-op (silent pass or not yet at interval)
  - exit 0 with {"systemMessage": "..."} → inject test failure feedback
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


# -- Configuration --

CHECKPOINT_ENABLED = os.getenv("LACP_EVAL_CHECKPOINT_ENABLED", "0") == "1"
CHECKPOINT_INTERVAL = int(os.getenv("LACP_EVAL_CHECKPOINT_INTERVAL", "10"))
TEST_TIMEOUT = int(os.getenv("LACP_EVAL_CHECKPOINT_TIMEOUT", "30"))

_LACP_STATE_DIR = Path.home() / ".lacp" / "hooks" / "state"

# Allowed test runner prefixes (same as stop_quality_gate.py)
_ALLOWED_TEST_RUNNERS = (
    "bun test", "pnpm test", "yarn test", "npm test",
    "make test", "cargo test", "python3 -m pytest",
    "bin/lacp-test",
)

HOOKS_DIR = Path(__file__).parent
sys.path.insert(0, str(HOOKS_DIR))


def _safe_session_id(session_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id) if session_id else "default"


def _session_state_dir(session_id: str) -> Path:
    safe_id = _safe_session_id(session_id)
    d = _LACP_STATE_DIR / safe_id
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _get_write_count(session_id: str) -> int:
    counter_file = _session_state_dir(session_id) / "write-count"
    try:
        return int(counter_file.read_text().strip()) if counter_file.exists() else 0
    except (ValueError, OSError):
        return 0


def _set_write_count(session_id: str, count: int) -> None:
    counter_file = _session_state_dir(session_id) / "write-count"
    try:
        counter_file.write_text(str(count))
    except OSError:
        pass


def _get_test_command(session_id: str) -> Optional[str]:
    """Read cached test command from session start contract."""
    try:
        from hook_contracts import read_contract
        contract = read_contract("session_start", session_id)
        if contract and contract.get("test_cmd"):
            cmd = contract["test_cmd"]
            if any(cmd.startswith(prefix) for prefix in _ALLOWED_TEST_RUNNERS):
                return cmd
    except Exception:
        pass
    return None


def _update_checkpoint_contract(session_id: str, result: str, fail_count: int) -> None:
    """Update the eval checkpoint contract for telemetry/stop hook consumption."""
    try:
        from hook_contracts import EvalCheckpoint, write_contract
        checkpoint = EvalCheckpoint(
            write_count=_get_write_count(session_id),
            last_check_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            last_result=result,
            fail_count=fail_count,
        )
        write_contract("eval_checkpoint", checkpoint, session_id)
    except Exception:
        pass


def _get_fail_count(session_id: str) -> int:
    """Read current fail count from checkpoint contract."""
    try:
        from hook_contracts import read_contract
        contract = read_contract("eval_checkpoint", session_id)
        if contract:
            return int(contract.get("fail_count", 0))
    except Exception:
        pass
    return 0


def main() -> None:
    if not CHECKPOINT_ENABLED:
        return

    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return

    session_id = hook_input.get("session_id") or ""
    cwd = hook_input.get("cwd") or ""

    # Increment write counter
    count = _get_write_count(session_id) + 1
    _set_write_count(session_id, count)

    # Check if we're at an interval
    if count % CHECKPOINT_INTERVAL != 0:
        return

    # Find test command
    test_cmd = _get_test_command(session_id)
    if not test_cmd:
        return

    # Run tests
    try:
        result = subprocess.run(
            shlex.split(test_cmd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT,
            cwd=cwd or None,
        )
    except (subprocess.TimeoutExpired, OSError):
        return  # Fail-open

    fail_count = _get_fail_count(session_id)

    if result.returncode == 0:
        _update_checkpoint_contract(session_id, "pass", fail_count)
        return  # Silent success

    # Tests failed — inject feedback (don't block)
    fail_count += 1
    _update_checkpoint_contract(session_id, "fail", fail_count)

    output = (result.stdout or "") + (result.stderr or "")
    last_lines = "\n".join(output.strip().splitlines()[-8:])
    msg = (
        f"Checkpoint ({count} writes): tests failing (exit {result.returncode}). "
        f"Fix before continuing:\n{last_lines}"
    )
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
