#!/usr/bin/env python3
"""Memory index guard — enforce hard size caps on MEMORY.md files.

Implements Claude Code's truncateEntrypointContent pattern:
- 200 line cap (natural boundary)
- 25KB byte cap (catches long lines that slip past line cap)
- Appends truncation warning when cap is hit

Usage:
    python3 memory_index_guard.py --check /path/to/MEMORY.md
    python3 memory_index_guard.py --enforce /path/to/MEMORY.md
    python3 memory_index_guard.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_LINES = 200
MAX_BYTES = 25_000
WARN_LINES = 180  # warn at 90% capacity
WARN_BYTES = 22_000


def truncate_entrypoint(raw: str) -> dict[str, object]:
    """Truncate MEMORY.md content to line AND byte caps.

    Line-truncates first (natural boundary), then byte-truncates
    at the last newline before the cap so we don't cut mid-line.
    Returns dict with content, metadata, and truncation status.
    """
    trimmed = raw.strip()
    lines = trimmed.split("\n")
    line_count = len(lines)
    byte_count = len(trimmed.encode("utf-8"))

    was_line_truncated = False
    was_byte_truncated = False

    # Line cap
    if line_count > MAX_LINES:
        lines = lines[:MAX_LINES]
        was_line_truncated = True

    content = "\n".join(lines)

    # Byte cap (after line truncation)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_BYTES:
        # Find last newline before byte cap
        truncated = content_bytes[:MAX_BYTES]
        last_nl = truncated.rfind(b"\n")
        if last_nl > 0:
            content = truncated[:last_nl].decode("utf-8", errors="replace")
        else:
            content = truncated.decode("utf-8", errors="replace")
        was_byte_truncated = True
        lines = content.split("\n")

    # Append warning if truncated
    if was_line_truncated or was_byte_truncated:
        caps_hit = []
        if was_line_truncated:
            caps_hit.append(f"lines ({line_count} > {MAX_LINES})")
        if was_byte_truncated:
            caps_hit.append(f"bytes ({byte_count} > {MAX_BYTES})")
        warning = f"\n\n<!-- MEMORY.md truncated: {', '.join(caps_hit)}. Run brain-expand to consolidate. -->"
        content += warning

    return {
        "content": content,
        "original_lines": line_count,
        "original_bytes": byte_count,
        "truncated_lines": len(lines),
        "truncated_bytes": len(content.encode("utf-8")),
        "was_line_truncated": was_line_truncated,
        "was_byte_truncated": was_byte_truncated,
    }


def check_index(path: Path) -> dict[str, object]:
    """Check MEMORY.md health without modifying it."""
    if not path.exists():
        return {"ok": True, "exists": False, "lines": 0, "bytes": 0}

    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.strip().split("\n")
    byte_count = len(raw.encode("utf-8"))
    line_count = len(lines)

    status = "ok"
    if line_count > MAX_LINES or byte_count > MAX_BYTES:
        status = "over_cap"
    elif line_count > WARN_LINES or byte_count > WARN_BYTES:
        status = "approaching_cap"

    return {
        "ok": status == "ok",
        "status": status,
        "exists": True,
        "lines": line_count,
        "bytes": byte_count,
        "max_lines": MAX_LINES,
        "max_bytes": MAX_BYTES,
        "line_utilization": round(line_count / MAX_LINES, 2),
        "byte_utilization": round(byte_count / MAX_BYTES, 2),
    }


def enforce_cap(path: Path) -> dict[str, object]:
    """Enforce caps on MEMORY.md, truncating if needed."""
    if not path.exists():
        return {"ok": True, "action": "none", "reason": "file not found"}

    raw = path.read_text(encoding="utf-8", errors="replace")
    result = truncate_entrypoint(raw)

    if result["was_line_truncated"] or result["was_byte_truncated"]:
        path.write_text(result["content"] + "\n", encoding="utf-8")
        return {
            "ok": True,
            "action": "truncated",
            "original_lines": result["original_lines"],
            "original_bytes": result["original_bytes"],
            "truncated_lines": result["truncated_lines"],
            "truncated_bytes": result["truncated_bytes"],
        }

    return {"ok": True, "action": "none", "reason": "within caps"}


def _self_test() -> None:
    # Test truncation
    big = "\n".join(f"- line {i}" for i in range(250))
    result = truncate_entrypoint(big)
    assert result["was_line_truncated"]
    assert result["truncated_lines"] <= MAX_LINES + 2  # +2 for warning
    assert "truncated" in result["content"]

    # Test within caps
    small = "\n".join(f"- line {i}" for i in range(50))
    result = truncate_entrypoint(small)
    assert not result["was_line_truncated"]
    assert not result["was_byte_truncated"]

    # Test byte cap
    long_lines = "\n".join("x" * 200 for _ in range(150))
    result = truncate_entrypoint(long_lines)
    assert result["was_byte_truncated"]

    # Test check
    info = check_index(Path("/nonexistent"))
    assert info["ok"]
    assert not info["exists"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Memory index guard — enforce MEMORY.md size caps")
    parser.add_argument("path", nargs="?", default="", help="Path to MEMORY.md")
    parser.add_argument("--check", action="store_true", help="Check without modifying")
    parser.add_argument("--enforce", action="store_true", help="Truncate if over cap")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if not args.path:
        print("Usage: memory_index_guard.py [--check|--enforce] <path>", file=sys.stderr)
        return 1

    path = Path(args.path)
    if args.enforce:
        result = enforce_cap(path)
    else:
        result = check_index(path)

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
