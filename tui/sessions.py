"""LACP Session Persistence — save and resume conversations.

Sessions are stored as JSONL files in ~/.lacp/sessions/.
Each line is a message (user, assistant, tool results).

Usage:
    from sessions import save_session, load_session, list_sessions, get_latest_session

    save_session(session_id, messages, metadata)
    messages, metadata = load_session(session_id)
    sessions = list_sessions(limit=10)
"""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".lacp" / "sessions" / "repl"
MAX_SESSION_SIZE = 256 * 1024  # 256KB before compaction warning


def generate_session_id() -> str:
    """Generate a unique session ID: timestamp + short random."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    pid = os.getpid()
    return f"lacp-{ts}-{pid}"


def save_session(
    session_id: str,
    messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save a session to JSONL. Returns the file path."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.jsonl"

    meta = metadata or {}
    meta.update({
        "session_id": session_id,
        "saved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "message_count": len(messages),
        "cwd": str(Path.cwd()),
    })

    with path.open("w", encoding="utf-8") as f:
        # First line: metadata
        f.write(json.dumps({"_meta": meta}) + "\n")
        # Subsequent lines: messages
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    return path


def load_session(session_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load a session from JSONL. Returns (messages, metadata)."""
    path = SESSIONS_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return [], {}

    messages = []
    metadata = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if "_meta" in data:
                metadata = data["_meta"]
            else:
                messages.append(data)
        except json.JSONDecodeError:
            continue

    return messages, metadata


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """List recent sessions, newest first."""
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for path in sorted(SESSIONS_DIR.glob("lacp-*.jsonl"), reverse=True)[:limit]:
        try:
            # Read just the metadata line (first line)
            with path.open(encoding="utf-8") as f:
                first_line = f.readline()
            data = json.loads(first_line)
            meta = data.get("_meta", {})
            meta["file"] = str(path)
            meta["size"] = path.stat().st_size
            sessions.append(meta)
        except Exception:
            sessions.append({
                "session_id": path.stem,
                "file": str(path),
                "size": path.stat().st_size,
            })

    return sessions


def get_latest_session() -> str | None:
    """Get the most recent session ID, or None."""
    sessions = list_sessions(limit=1)
    return sessions[0].get("session_id") if sessions else None


def auto_save_session(
    session_id: str,
    messages: list[dict[str, Any]],
    provider_name: str = "",
    model: str = "",
    total_tokens: int = 0,
) -> Path | None:
    """Auto-save with metadata about the session state."""
    if not messages:
        return None
    return save_session(session_id, messages, {
        "provider": provider_name,
        "model": model,
        "total_tokens": total_tokens,
    })
