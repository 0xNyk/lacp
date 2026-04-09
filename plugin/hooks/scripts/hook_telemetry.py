#!/usr/bin/env python3
"""Lightweight telemetry logger for Claude Code hooks.

Append-only JSONL log with auto-rotation. Usable as CLI or importable module.
Python 3.11 stdlib only.
"""

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TELEMETRY_DIR = Path.home() / ".local" / "share" / "claude-hooks"
TELEMETRY_FILE = TELEMETRY_DIR / "telemetry.jsonl"
MAX_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ROTATIONS = 3


def _rotate_if_needed() -> None:
    """Rotate telemetry file if it exceeds MAX_SIZE."""
    try:
        if not TELEMETRY_FILE.exists() or TELEMETRY_FILE.stat().st_size < MAX_SIZE:
            return
    except OSError:
        return

    # Shift .3 -> delete, .2 -> .3, .1 -> .2, current -> .1
    for i in range(MAX_ROTATIONS, 0, -1):
        src = TELEMETRY_FILE.with_suffix(f".{i}")
        if i == MAX_ROTATIONS:
            src.unlink(missing_ok=True)
        else:
            dst = TELEMETRY_FILE.with_suffix(f".{i + 1}")
            if src.exists():
                src.rename(dst)

    TELEMETRY_FILE.rename(TELEMETRY_FILE.with_suffix(".1"))


def log_decision(
    hook: str,
    decision: str,
    reason: str,
    session_id: str = "unknown",
    elapsed_ms: int = 0,
    details: dict | None = None,
) -> None:
    """Append a single telemetry entry (thread-safe)."""
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed()

    entry = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(),
        "hook": hook,
        "session_id": session_id,
        "decision": decision,
        "reason": reason,
        "elapsed_ms": elapsed_ms,
        "details": details or {},
    }

    line = json.dumps(entry, separators=(",", ":")) + "\n"

    fd = os.open(str(TELEMETRY_FILE), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode())
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a hook telemetry decision")
    parser.add_argument("--hook", required=True, help="Hook name")
    parser.add_argument("--session-id", default="unknown", help="Session ID")
    parser.add_argument(
        "--decision",
        required=True,
        choices=["allow", "block", "skip"],
        help="Decision outcome",
    )
    parser.add_argument("--reason", required=True, help="Human-readable reason")
    parser.add_argument("--elapsed", type=int, default=0, help="Elapsed time in ms")
    parser.add_argument(
        "--detail",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra key=value detail (repeatable)",
    )

    args = parser.parse_args()

    details = {}
    for kv in args.detail:
        if "=" in kv:
            k, v = kv.split("=", 1)
            details[k] = v
        else:
            details[kv] = True

    log_decision(
        hook=args.hook,
        session_id=args.session_id,
        decision=args.decision,
        reason=args.reason,
        elapsed_ms=args.elapsed,
        details=details,
    )


if __name__ == "__main__":
    main()
