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
