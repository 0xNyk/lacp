#!/Library/Frameworks/Python.framework/Versions/3.11/bin/python3
"""Extract structured markdown notes from Claude/Codex JSONL session files.

Usage:
    python3 extract_sessions.py --agent claude --since-days 7
    python3 extract_sessions.py --agent codex --full
    python3 extract_sessions.py --agent claude --since-days 30 --force
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_GLOB = Path.home() / ".claude" / "projects" / "-Users-nyk" / "*.jsonl"
CODEX_GLOB = Path.home() / ".codex" / "sessions" / "**" / "*.jsonl"
OUTPUT_ROOT = Path.home() / "control" / "sessions"

DECISION_PATTERNS = re.compile(
    r"\b(decision|decided|chose|chosen|approach|instead of|because|trade-?off|"
    r"opted|prefer|rather than|went with|settle[d]? on)\b",
    re.IGNORECASE,
)

MAX_INTENT_CHARS = 500
MAX_OUTCOME_CHARS = 500
MAX_DECISIONS = 15
MAX_OUTPUT_LINES = 200


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def iter_jsonl(path: Path):
    """Stream JSONL lines, skipping malformed ones."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"  WARN: {path.name}:{lineno} — malformed JSON: {exc}",
                    file=sys.stderr,
                )


def extract_text_from_content(content) -> str:
    """Return concatenated text from assistant content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def extract_tool_uses(content) -> list:
    """Return list of (tool_name, input_dict) from content blocks."""
    if not isinstance(content, list):
        return []
    results = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "unknown")
            inp = block.get("input", {})
            results.append((name, inp if isinstance(inp, dict) else {}))
    return results


# ---------------------------------------------------------------------------
# Session processor
# ---------------------------------------------------------------------------


def process_session(jsonl_path: Path, agent: str) -> dict | None:
    """Parse a single JSONL session file and return extracted data dict."""

    session_id = None
    cwd = None
    slug = None
    timestamp_iso = None
    user_messages: list[str] = []
    assistant_texts: list[str] = []
    tool_counter: Counter = Counter()
    files_changed: set = set()
    web_searches: list[str] = []
    web_fetches: list[str] = []
    decision_lines: list[str] = []
    message_count = 0
    tool_count = 0

    for obj in iter_jsonl(jsonl_path):
        obj_type = obj.get("type")

        # -----------------------------------------------------------
        # Codex format: session_meta, response_item, turn_context
        # -----------------------------------------------------------
        if obj_type == "session_meta":
            payload = obj.get("payload", {})
            if session_id is None:
                session_id = payload.get("id")
            if cwd is None:
                cwd = payload.get("cwd")
            if timestamp_iso is None:
                timestamp_iso = payload.get("timestamp") or obj.get("timestamp")
            continue

        if obj_type == "turn_context":
            payload = obj.get("payload", {})
            if cwd is None:
                cwd = payload.get("cwd")
            continue

        if obj_type == "response_item":
            payload = obj.get("payload", {})
            role = payload.get("role", "")
            ptype = payload.get("type", "")
            content = payload.get("content", [])

            # User messages (role=user with input_text)
            if role == "user" and ptype == "message":
                message_count += 1
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "input_text":
                            text = block.get("text", "").strip()
                            # Skip system/instruction preambles
                            if text and not text.startswith(("<permissions", "<environment_context", "<collaboration_mode", "# AGENTS.md")):
                                user_messages.append(text)
                continue

            # Assistant messages (role=assistant with output_text)
            if role == "assistant" and ptype == "message":
                message_count += 1
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "output_text":
                            text = block.get("text", "").strip()
                            if text:
                                assistant_texts.append(text)
                                for line in text.split("\n"):
                                    line = line.strip()
                                    if line and DECISION_PATTERNS.search(line) and len(line) < 500:
                                        cleaned = re.sub(r"^[-*#>]+\s*", "", line).strip()
                                        if cleaned and cleaned not in decision_lines:
                                            decision_lines.append(cleaned)
                continue

            # Tool calls
            if ptype in ("function_call", "custom_tool_call"):
                tool_count += 1
                name = payload.get("name", "codex_tool")
                tool_counter[name] += 1
                args = payload.get("arguments", "")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                if name in ("write_file", "apply_diff", "create_file"):
                    fp = args.get("path", "") if isinstance(args, dict) else ""
                    if fp:
                        files_changed.add(fp)
                continue

            # Web search
            if ptype == "web_search_call":
                tool_count += 1
                tool_counter["web_search"] += 1
                q = payload.get("query", "")
                if q and q not in web_searches:
                    web_searches.append(q)
                continue

            continue

        # -----------------------------------------------------------
        # Claude format: user, assistant, file-history-snapshot, etc.
        # -----------------------------------------------------------

        # Metadata — take first non-None values
        if session_id is None:
            session_id = obj.get("sessionId")
        if cwd is None:
            cwd = obj.get("cwd")
        if slug is None:
            slug = obj.get("slug")

        # Timestamp from file-history-snapshot
        if obj_type == "file-history-snapshot":
            snap = obj.get("snapshot", {})
            ts = snap.get("timestamp") if isinstance(snap, dict) else None
            if ts and timestamp_iso is None:
                timestamp_iso = ts
            continue

        # Skip progress / other non-message types
        if obj_type == "progress":
            continue

        message = obj.get("message", {})
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if content is None:
            continue

        # User messages
        if obj_type == "user":
            message_count += 1
            text = content if isinstance(content, str) else extract_text_from_content(content)
            if text:
                user_messages.append(text)
            continue

        # Assistant messages
        if obj_type == "assistant":
            message_count += 1
            text = extract_text_from_content(content)
            if text:
                assistant_texts.append(text)
                # Extract decision-like lines
                for line in text.split("\n"):
                    line = line.strip()
                    if line and DECISION_PATTERNS.search(line) and len(line) < 500:
                        cleaned = re.sub(r"^[-*#>]+\s*", "", line).strip()
                        if cleaned and cleaned not in decision_lines:
                            decision_lines.append(cleaned)

            # Tool uses
            for tool_name, tool_input in extract_tool_uses(content):
                tool_count += 1
                tool_counter[tool_name] += 1

                # File changes
                if tool_name in ("Write", "Edit", "write", "edit"):
                    fp = tool_input.get("file_path") or tool_input.get("path", "")
                    if fp:
                        files_changed.add(fp)

                # Web searches
                if tool_name in ("WebSearch", "web_search"):
                    q = tool_input.get("query", "")
                    if q and q not in web_searches:
                        web_searches.append(q)

                # Web fetches
                if tool_name in ("WebFetch", "web_fetch"):
                    u = tool_input.get("url", "")
                    if u and u not in web_fetches:
                        web_fetches.append(u)

            continue

    # Need at least some content
    if message_count == 0:
        return None

    # Fallback values
    if not session_id:
        session_id = jsonl_path.stem
    if not slug:
        slug = jsonl_path.stem
    if not cwd:
        cwd = "/Users/nyk"

    # Determine date/time
    if timestamp_iso:
        try:
            dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)
    else:
        dt = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)

    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")

    # Build intent
    intent = ""
    if user_messages:
        intent = user_messages[0][:MAX_INTENT_CHARS]
        if len(user_messages[0]) > MAX_INTENT_CHARS:
            intent += "..."

    # Build outcome
    outcome = ""
    if assistant_texts:
        last = assistant_texts[-1]
        outcome = last[:MAX_OUTCOME_CHARS]
        if len(last) > MAX_OUTCOME_CHARS:
            outcome += "..."

    # Trim decisions
    decisions = decision_lines[:MAX_DECISIONS]

    # Top tools
    top_tools = tool_counter.most_common(10)

    return {
        "session_id": session_id,
        "date": date_str,
        "time": time_str,
        "cwd": cwd,
        "slug": slug,
        "tool_count": tool_count,
        "message_count": message_count,
        "agent": agent,
        "intent": intent,
        "decisions": decisions,
        "web_searches": web_searches[:20],
        "web_fetches": web_fetches[:20],
        "files_changed": sorted(files_changed)[:50],
        "top_tools": top_tools,
        "outcome": outcome,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(data: dict) -> str:
    """Render extracted session data as markdown."""
    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f'id: "{data["session_id"]}"')
    lines.append(f'date: "{data["date"]}"')
    lines.append(f'time: "{data["time"]}"')
    lines.append(f'cwd: "{data["cwd"]}"')
    lines.append(f'slug: "{data["slug"]}"')
    lines.append(f"tool_count: {data['tool_count']}")
    lines.append(f"message_count: {data['message_count']}")
    lines.append(f"agent: {data['agent']}")
    lines.append(f"tags: [sessions, {data['agent']}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {data['slug']}")
    lines.append("")

    # Intent
    lines.append("## Intent")
    if data["intent"]:
        lines.append(data["intent"])
    else:
        lines.append("(no user message found)")
    lines.append("")

    # Key Decisions
    lines.append("## Key Decisions")
    if data["decisions"]:
        for d in data["decisions"]:
            lines.append(f"- {d}")
    else:
        lines.append("- (none extracted)")
    lines.append("")

    # Research & Findings
    lines.append("## Research & Findings")
    has_research = False
    if data["web_searches"]:
        has_research = True
        for q in data["web_searches"]:
            lines.append(f"- Search: {q}")
    if data["web_fetches"]:
        has_research = True
        for u in data["web_fetches"]:
            lines.append(f"- Fetch: {u}")
    if not has_research:
        lines.append("- (no web research)")
    lines.append("")

    # Files Changed
    lines.append("## Files Changed")
    if data["files_changed"]:
        for f in data["files_changed"]:
            lines.append(f"- {f}")
    else:
        lines.append("- (no file modifications)")
    lines.append("")

    # Key Actions
    lines.append("## Key Actions")
    if data["top_tools"]:
        for tool_name, count in data["top_tools"]:
            lines.append(f"- {tool_name}: {count} calls")
    else:
        lines.append("- (no tool calls)")
    lines.append("")

    # Outcome
    lines.append("## Outcome")
    if data["outcome"]:
        lines.append(data["outcome"])
    else:
        lines.append("(no assistant response found)")
    lines.append("")

    # Truncate to MAX_OUTPUT_LINES
    if len(lines) > MAX_OUTPUT_LINES:
        lines = lines[:MAX_OUTPUT_LINES]
        lines.append("")
        lines.append("(truncated)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured notes from Claude/Codex session files."
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=["claude", "codex"],
        help="Which agent's sessions to process.",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only process sessions from last N days (by file mtime).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Process all sessions regardless of age.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    args = parser.parse_args()

    if args.since_days is None and not args.full:
        parser.error("Specify --since-days N or --full")

    # Resolve input files
    if args.agent == "claude":
        glob_pattern = CLAUDE_GLOB
        input_files = sorted(glob_pattern.parent.glob(glob_pattern.name))
    else:
        codex_sessions_dir = Path.home() / ".codex" / "sessions"
        input_files = sorted(codex_sessions_dir.rglob("*.jsonl"))

    if not input_files:
        print(f"No JSONL files found for {args.agent}.", file=sys.stderr)
        sys.exit(1)

    # Filter by mtime
    if args.since_days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=args.since_days)
        cutoff_ts = cutoff.timestamp()
        input_files = [f for f in input_files if f.stat().st_mtime >= cutoff_ts]

    if not input_files:
        print(f"No sessions within the specified time range.", file=sys.stderr)
        sys.exit(0)

    # Output directory
    out_dir = OUTPUT_ROOT / args.agent
    out_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    created = 0
    skipped = 0

    for jsonl_path in input_files:
        processed += 1

        # Quick pre-check: parse enough to get slug/date for filename
        data = process_session(jsonl_path, args.agent)
        if data is None:
            print(f"  SKIP (empty): {jsonl_path.name}", file=sys.stderr)
            skipped += 1
            continue

        # Build output filename
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "-", data["slug"])[:80]
        out_name = f"{data['date']}-{safe_slug}.md"
        out_path = out_dir / out_name

        if out_path.exists() and not args.force:
            skipped += 1
            continue

        md = render_markdown(data)
        out_path.write_text(md, encoding="utf-8")
        created += 1
        print(f"  Created: {out_path.relative_to(OUTPUT_ROOT)}")

    print(
        f"\nProcessed {processed} sessions, "
        f"created {created} new notes, "
        f"skipped {skipped} existing"
    )


if __name__ == "__main__":
    main()
