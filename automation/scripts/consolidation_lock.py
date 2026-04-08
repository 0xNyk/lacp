#!/usr/bin/env python3
"""Consolidation lock — PID-based mutex for brain-expand/consolidation.

Prevents concurrent consolidation runs from corrupting the registry.
Pattern from Claude Code's consolidationLock.ts:
- Lock file body = holder PID
- Lock file mtime = lastConsolidatedAt
- Stale detection: if holder PID is dead OR lock age > 1 hour, reclaim
- Double-check: after write, re-read to verify we won the race

Usage:
    from consolidation_lock import acquire_lock, release_lock, read_last_consolidated_at

    prior = acquire_lock()
    if prior is None:
        print("Lock held by another process")
        sys.exit(0)
    try:
        run_consolidation()
    except Exception:
        rollback_lock(prior)
        raise
"""
from __future__ import annotations

import os
import time
from pathlib import Path

KNOWLEDGE_ROOT = Path(os.environ.get(
    "LACP_KNOWLEDGE_ROOT",
    str(Path.home() / "control" / "knowledge" / "knowledge-memory"),
))
LOCK_FILE = KNOWLEDGE_ROOT / "data" / ".consolidate-lock"
STALE_TIMEOUT_S = 3600  # 1 hour


def _is_process_running(pid: int) -> bool:
    """Check if a process with given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def read_last_consolidated_at() -> float:
    """Return mtime of lock file (= last consolidation time). 0 if absent."""
    try:
        return LOCK_FILE.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def acquire_lock() -> float | None:
    """Acquire the consolidation lock.

    Returns the prior mtime (for rollback) on success, None if blocked.
    """
    prior_mtime = 0.0
    holder_pid: int | None = None

    try:
        stat = LOCK_FILE.stat()
        prior_mtime = stat.st_mtime
        raw = LOCK_FILE.read_text(encoding="utf-8").strip()
        holder_pid = int(raw) if raw.isdigit() else None
    except FileNotFoundError:
        pass  # no prior lock

    # Check if lock is held by a live process within timeout
    if prior_mtime > 0:
        age_s = time.time() - prior_mtime
        if age_s < STALE_TIMEOUT_S and holder_pid is not None and _is_process_running(holder_pid):
            return None  # lock held by live process

    # Acquire: write our PID
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")

    # Double-check: re-read to verify we won any race
    try:
        verify = LOCK_FILE.read_text(encoding="utf-8").strip()
        if verify != str(os.getpid()):
            return None  # lost race
    except FileNotFoundError:
        return None

    return prior_mtime


def release_lock() -> None:
    """Release lock by clearing PID body. Mtime stays (= lastConsolidatedAt)."""
    try:
        LOCK_FILE.write_text("", encoding="utf-8")
    except OSError:
        pass


def rollback_lock(prior_mtime: float) -> None:
    """Rollback lock to prior state after a failed consolidation.

    Rewinds mtime to pre-acquire. If prior was 0 (no lock existed), delete.
    """
    try:
        if prior_mtime == 0:
            LOCK_FILE.unlink(missing_ok=True)
            return
        LOCK_FILE.write_text("", encoding="utf-8")
        os.utime(str(LOCK_FILE), (prior_mtime, prior_mtime))
    except OSError:
        pass


def _self_test() -> None:
    """Test lock acquire/release cycle."""
    import tempfile
    global LOCK_FILE
    old = LOCK_FILE
    with tempfile.TemporaryDirectory() as tmp:
        LOCK_FILE = Path(tmp) / ".consolidate-lock"

        # Acquire should succeed (no prior lock)
        prior = acquire_lock()
        assert prior is not None, "Should acquire fresh lock"
        assert prior == 0.0, f"Prior should be 0.0 for fresh lock, got {prior}"

        # Lock file should contain our PID
        assert LOCK_FILE.read_text().strip() == str(os.getpid())

        # Second acquire should fail (we hold it — PID alive + within timeout)
        second = acquire_lock()
        assert second is None, "Should be blocked by live holder"

        # Release
        release_lock()
        assert LOCK_FILE.read_text().strip() == ""

        # Rollback to no-lock state
        prior2 = acquire_lock()
        rollback_lock(0.0)
        assert not LOCK_FILE.exists()

        # Read last consolidated at when no lock
        assert read_last_consolidated_at() == 0.0

    LOCK_FILE = old


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
        print("self-test passed")
    elif "--status" in sys.argv:
        import json
        mtime = read_last_consolidated_at()
        age_h = (time.time() - mtime) / 3600 if mtime > 0 else -1
        holder = ""
        try:
            holder = LOCK_FILE.read_text().strip()
        except FileNotFoundError:
            pass
        print(json.dumps({
            "lock_file": str(LOCK_FILE),
            "exists": LOCK_FILE.exists(),
            "last_consolidated_at": mtime,
            "age_hours": round(age_h, 2),
            "holder_pid": int(holder) if holder.isdigit() else None,
            "holder_alive": _is_process_running(int(holder)) if holder.isdigit() else False,
        }, indent=2))
