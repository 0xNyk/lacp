#!/usr/bin/env python3
"""Per-turn memory extraction — captures durable signals from conversation.

Lightweight Stop hook that scans the last assistant message for memory-worthy
signals and writes them to a staging file. Brain-expand later promotes from
staging into the knowledge graph.

No LLM calls — heuristic pattern matching only. Keeps hook latency <100ms.

Hook protocol (Stop hook):
  - Reads JSON from stdin: {transcript_path, session_id, cwd, ...}
  - Writes signals to staging file: ~/.lacp/memory-staging/pending.jsonl
  - Exits 0 (never blocks stop)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "automation" / "scripts"))

STAGING_DIR = Path.home() / ".lacp" / "memory-staging"
STAGING_FILE = STAGING_DIR / "pending.jsonl"
MAX_STAGING_LINES = 500  # rotate after this many

# Patterns that indicate durable, memory-worthy content
MEMORY_INDICATORS = [
    # Decisions and preferences
    re.compile(r"(?:we decided|the decision is|going with|chose to|prefer)\s+(.{20,})", re.I),
    # Lessons learned
    re.compile(r"(?:lesson learned|takeaway|key insight|important note|remember that)\s*:?\s*(.{20,})", re.I),
    # Architecture/design choices
    re.compile(r"(?:architecture|design choice|trade-?off|we.ll use|stack is)\s*:?\s*(.{20,})", re.I),
    # Process/workflow
    re.compile(r"(?:workflow|process|convention|rule|policy)\s*:?\s*(.{20,})", re.I),
    # User corrections (feedback type)
    re.compile(r"(?:don.t|never|always|stop|instead of)\s+(.{15,})", re.I),
]

# Anti-patterns — skip these even if they match indicators
SKIP_PATTERNS = [
    re.compile(r"```[\s\S]{100,}```"),  # large code blocks
    re.compile(r"^\s*[-*]\s+`[^`]+`\s*$", re.M),  # bullet list of code refs
    re.compile(r"(?:error|traceback|stack trace)", re.I),  # error output
]


def extract_signals(text: str, session_id: str, cwd: str) -> list[dict]:
    """Extract memory-worthy signals from assistant message text."""
    if not text or len(text) < 50:
        return []

    # Skip if text is mostly code
    code_ratio = text.count("```") / max(1, len(text) / 100)
    if code_ratio > 0.3:
        return []

    # Check anti-patterns
    for pattern in SKIP_PATTERNS:
        if pattern.search(text):
            return []

    signals = []
    for pattern in MEMORY_INDICATORS:
        for match in pattern.finditer(text):
            signal_text = match.group(1).strip() if match.lastindex else match.group(0).strip()
            # Clean up
            signal_text = re.sub(r"\s+", " ", signal_text)
            if len(signal_text) < 20 or len(signal_text) > 300:
                continue
            signals.append({
                "text": signal_text[:280],
                "source": "per-turn-extraction",
                "session_id": session_id,
                "cwd": cwd,
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "day": datetime.now(UTC).strftime("%Y-%m-%d"),
            })

    # Deduplicate within this extraction
    seen = set()
    unique = []
    for s in signals:
        key = s["text"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:5]  # cap at 5 per turn


def append_to_staging(signals: list[dict]) -> int:
    """Append signals to staging JSONL file. Returns count written."""
    if not signals:
        return 0

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Rotate if too large
    if STAGING_FILE.exists():
        line_count = sum(1 for _ in STAGING_FILE.open())
        if line_count > MAX_STAGING_LINES:
            archive = STAGING_DIR / f"staging-{datetime.now(UTC).strftime('%Y%m%d')}.jsonl"
            STAGING_FILE.rename(archive)

    with STAGING_FILE.open("a", encoding="utf-8") as f:
        for signal in signals:
            f.write(json.dumps(signal) + "\n")

    return len(signals)


def _extract_last_assistant(transcript_path: str) -> str:
    """Extract last assistant message from JSONL transcript."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    last = ""
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "assistant":
                        content = msg.get("message", {}).get("content", "")
                        if isinstance(content, list):
                            # Extract text parts
                            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                            content = "\n".join(text_parts)
                        if isinstance(content, str) and len(content) > 50:
                            last = content
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return last


def main() -> int:
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0  # silent exit on bad input

    session_id = hook_input.get("session_id", "")
    cwd = hook_input.get("cwd", "")
    transcript_path = hook_input.get("transcript_path", "")

    # Get the last assistant message
    last_message = hook_input.get("last_assistant_message", "")
    if not last_message:
        last_message = _extract_last_assistant(transcript_path)

    if not last_message:
        return 0

    signals = extract_signals(last_message, session_id, cwd)
    count = append_to_staging(signals)

    if count > 0 and os.environ.get("LACP_EXTRACT_DEBUG") == "1":
        print(json.dumps({"extracted": count, "signals": signals}), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
