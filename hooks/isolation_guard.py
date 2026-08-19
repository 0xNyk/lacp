#!/usr/bin/env python3
"""Log Claude Code subagent lifecycle events. Does not replace WorktreeCreate."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def knowledge_root() -> Path:
    raw = os.environ.get("LACP_KNOWLEDGE_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".lacp" / "knowledge"


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    event = str(payload.get("hook_event_name") or payload.get("event") or "unknown")
    record = {
        "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type"),
        "session_id": payload.get("session_id"),
        "cwd": payload.get("cwd"),
    }
    out_dir = knowledge_root() / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "isolation-events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
