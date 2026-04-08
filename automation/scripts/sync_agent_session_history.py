#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
CONTROL = HOME / "control"
RAW = CONTROL / "sessions" / "raw"
HISTORY = CONTROL / "session-history"

CLAUDE_HISTORY = HOME / ".claude" / "history.jsonl"
CODEX_HISTORY = HOME / ".codex" / "history.jsonl"
CODEX_SESSIONS = HOME / ".codex" / "sessions"


def _tail_lines(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if n <= 0:
        return lines
    return lines[-n:]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _session_manifest(root: Path, limit: int) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for p in files[: max(0, limit)]:
        st = p.stat()
        out.append(
            {
                "path": str(p),
                "size_bytes": int(st.st_size),
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return out


def _summary_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Session History Index",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Sources",
        "",
        f"- Claude history: `{payload['sources']['claude_history']}`",
        f"- Codex history: `{payload['sources']['codex_history']}`",
        f"- Codex sessions: `{payload['sources']['codex_sessions']}`",
        "",
        "## Captured",
        "",
        f"- Claude tail lines: `{payload['captured']['claude_tail_lines']}`",
        f"- Codex tail lines: `{payload['captured']['codex_tail_lines']}`",
        f"- Codex session manifests: `{payload['captured']['codex_session_files']}`",
        "",
        "## Files",
        "",
        f"- `{payload['outputs']['claude_tail']}`",
        f"- `{payload['outputs']['codex_tail']}`",
        f"- `{payload['outputs']['codex_manifest']}`",
        f"- `{payload['outputs']['summary_json']}`",
    ]
    return "\n".join(lines) + "\n"


def _self_test() -> None:
    assert _tail_lines(Path("/nonexistent/file"), 10) == []


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Claude/Codex session history tails into control-plane storage.")
    parser.add_argument("--tail-lines", type=int, default=5000)
    parser.add_argument("--manifest-limit", type=int, default=200)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    claude_lines = _tail_lines(CLAUDE_HISTORY, args.tail_lines)
    codex_lines = _tail_lines(CODEX_HISTORY, args.tail_lines)
    codex_manifest = _session_manifest(CODEX_SESSIONS, args.manifest_limit)

    claude_tail_path = RAW / "claude" / "history.tail.jsonl"
    codex_tail_path = RAW / "codex" / "history.tail.jsonl"
    codex_manifest_path = RAW / "codex" / "sessions.manifest.json"
    summary_json_path = HISTORY / "summary.json"
    summary_md_path = HISTORY / "index.md"

    _write_text(claude_tail_path, "\n".join(claude_lines) + ("\n" if claude_lines else ""))
    _write_text(codex_tail_path, "\n".join(codex_lines) + ("\n" if codex_lines else ""))
    _write_text(codex_manifest_path, json.dumps(codex_manifest, indent=2) + "\n")

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sources": {
            "claude_history": str(CLAUDE_HISTORY),
            "codex_history": str(CODEX_HISTORY),
            "codex_sessions": str(CODEX_SESSIONS),
        },
        "captured": {
            "claude_tail_lines": len(claude_lines),
            "codex_tail_lines": len(codex_lines),
            "codex_session_files": len(codex_manifest),
        },
        "outputs": {
            "claude_tail": str(claude_tail_path),
            "codex_tail": str(codex_tail_path),
            "codex_manifest": str(codex_manifest_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }

    _write_text(summary_json_path, json.dumps(payload, indent=2) + "\n")
    _write_text(summary_md_path, _summary_md(payload))

    print(json.dumps({"ok": True, **payload["captured"], "summary": str(summary_json_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
