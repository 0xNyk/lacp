#!/usr/bin/env python3
"""Detect file changes made by Claude during a session.

Reads a JSON object from stdin with {"transcript_path": "..."}.
Streams the JSONL transcript line-by-line, extracts file paths from
Write/Edit/NotebookEdit tool_use blocks, and reports which files exist.

Prints a single JSON line to stdout.
"""

import json
import os
import sys

TRACKED_TOOLS = {"Write", "Edit", "NotebookEdit"}


def scan_transcript(path: str) -> dict:
    files_seen: dict[str, set[str]] = {}  # file_path -> set of tool names
    tools_used: dict[str, int] = {}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                message = obj.get("message") if isinstance(obj, dict) else None
                if not isinstance(message, dict):
                    continue

                content = message.get("content")
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    name = block.get("name", "")
                    if name not in TRACKED_TOOLS:
                        continue

                    inp = block.get("input")
                    if not isinstance(inp, dict):
                        continue

                    file_path = inp.get("file_path") or inp.get("notebook_path")
                    if not file_path or not isinstance(file_path, str):
                        continue

                    tools_used[name] = tools_used.get(name, 0) + 1

                    if file_path not in files_seen:
                        files_seen[file_path] = set()
                    files_seen[file_path].add(name)

    except OSError as e:
        return {"files_changed": -1, "files": [], "tools_used": {}, "error": str(e)}

    # Only report files that still exist on disk
    existing = [p for p in files_seen if os.path.exists(p)]
    existing.sort()

    return {
        "files_changed": len(existing),
        "files": existing,
        "tools_used": tools_used,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        request = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        json.dump(
            {"files_changed": -1, "files": [], "tools_used": {}, "error": f"invalid input JSON: {e}"},
            sys.stdout,
        )
        print()
        return

    if not isinstance(request, dict):
        json.dump(
            {"files_changed": -1, "files": [], "tools_used": {}, "error": "input must be a JSON object"},
            sys.stdout,
        )
        print()
        return

    transcript_path = request.get("transcript_path")
    if not transcript_path or not isinstance(transcript_path, str):
        json.dump(
            {"files_changed": -1, "files": [], "tools_used": {}, "error": "missing transcript_path"},
            sys.stdout,
        )
        print()
        return

    if not os.path.isfile(transcript_path):
        json.dump(
            {"files_changed": -1, "files": [], "tools_used": {}, "error": f"file not found: {transcript_path}"},
            sys.stdout,
        )
        print()
        return

    result = scan_transcript(transcript_path)
    json.dump(result, sys.stdout)
    print()


if __name__ == "__main__":
    main()
