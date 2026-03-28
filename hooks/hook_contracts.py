#!/usr/bin/env python3
"""Typed hook state contracts — shared state between hooks within a session.

Provides a simple contract system where hooks can write structured data
that other hooks can read with schema validation. Contracts are stored
per-session and auto-cleaned.

Inspired by herm's tool interface (Definition → ToolDefinition, Execute → (string, error))
and langdag's typed ContentBlock/Node structures.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


def _safe_session_id(session_id: str) -> str:
    """Sanitize session_id for use in file paths (L1: CWE-22)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id) if session_id else "default"


# Contract storage location
def _contracts_dir(session_id: str) -> Path:
    return Path.home() / ".lacp" / "hooks" / "contracts" / _safe_session_id(session_id)


@dataclass
class SessionStartOutput:
    test_cmd: Optional[str] = None
    git_branch: Optional[str] = None
    context_mode: Optional[str] = None
    started_at: Optional[str] = None
    context_budget_hint: Optional[int] = None


@dataclass
class StopGateInput:
    test_cmd: Optional[str] = None
    session_changes: Optional[list[str]] = None
    transcript_path: Optional[str] = None
    session_started_at: Optional[str] = None
    context_budget_hint: Optional[int] = None
    tool_use_count: Optional[int] = None


def write_contract(name: str, data: object, session_id: str | None = None) -> Path | None:
    """Write a contract to disk. Returns the path written, or None on failure."""
    sid = session_id or os.getenv("CLAUDE_SESSION_ID", "default")
    contracts = _contracts_dir(sid)
    try:
        contracts.mkdir(parents=True, exist_ok=True)
        path = contracts / f"{name}.json"
        payload = asdict(data) if hasattr(data, "__dataclass_fields__") else data
        path.write_text(json.dumps(payload, default=str))
        return path
    except (OSError, TypeError):
        return None


def read_contract(name: str, session_id: str | None = None) -> dict | None:
    """Read a contract from disk. Returns dict or None if missing/invalid."""
    sid = session_id or os.getenv("CLAUDE_SESSION_ID", "default")
    path = _contracts_dir(sid) / f"{name}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@dataclass
class SprintContract:
    acceptance_criteria: list[str]
    expected_files: list[str]
    expected_tests: list[str]
    agreed_at: str = ""


@dataclass
class EvalCheckpoint:
    write_count: int = 0
    last_check_at: str = ""
    last_result: str = ""  # "pass", "fail", or ""
    fail_count: int = 0


@dataclass
class HandoffArtifact:
    task_summary: str = ""
    files_modified: list[str] = None
    open_issues: list[str] = None
    next_steps: list[str] = None
    test_status: str = "unknown"  # "pass", "fail", "unknown"
    git_branch: str = ""
    git_diff_summary: str = ""
    created_at: str = ""

    def __post_init__(self):
        if self.files_modified is None:
            self.files_modified = []
        if self.open_issues is None:
            self.open_issues = []
        if self.next_steps is None:
            self.next_steps = []


def cleanup_contracts(session_id: str | None = None) -> int:
    """Remove all contracts for a session. Returns count of files removed."""
    sid = session_id or os.getenv("CLAUDE_SESSION_ID", "default")
    contracts = _contracts_dir(sid)
    if not contracts.is_dir():
        return 0
    count = 0
    try:
        for f in contracts.iterdir():
            f.unlink()
            count += 1
        contracts.rmdir()
    except OSError:
        pass
    return count


def cleanup_stale_contracts(max_age_hours: int = 48) -> int:
    """Remove contract directories older than max_age_hours. Returns count removed."""
    import time as _time
    contracts_root = Path.home() / ".lacp" / "hooks" / "contracts"
    if not contracts_root.is_dir():
        return 0
    cutoff = _time.time() - (max_age_hours * 3600)
    removed = 0
    try:
        for d in contracts_root.iterdir():
            if not d.is_dir():
                continue
            try:
                mtime = max(f.stat().st_mtime for f in d.iterdir()) if any(d.iterdir()) else d.stat().st_mtime
                if mtime < cutoff:
                    for f in d.iterdir():
                        f.unlink()
                    d.rmdir()
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed


def cleanup_stale_state(max_age_hours: int = 48) -> int:
    """Remove session state directories older than max_age_hours. Returns count removed."""
    import time as _time
    state_root = Path.home() / ".lacp" / "hooks" / "state"
    if not state_root.is_dir():
        return 0
    cutoff = _time.time() - (max_age_hours * 3600)
    removed = 0
    try:
        for d in state_root.iterdir():
            if not d.is_dir():
                continue
            if d.name == "quality-gate.log":
                continue  # skip the debug log file
            try:
                mtime = max(f.stat().st_mtime for f in d.iterdir()) if any(d.iterdir()) else d.stat().st_mtime
                if mtime < cutoff:
                    for f in d.iterdir():
                        f.unlink()
                    d.rmdir()
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed
