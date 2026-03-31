#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CLAUDE_HISTORY = Path.home() / ".claude" / "history.jsonl"
CODEX_HISTORY = Path.home() / ".codex" / "history.jsonl"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DAILY_DIR = KNOWLEDGE_ROOT / "memory" / "daily"

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9_\-\.=]{16,}\b", re.IGNORECASE),
    re.compile(r"(api[_ -]?key|password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
]

LESSON_HINTS = (
    "bug",
    "fix",
    "regression",
    "incident",
    "root cause",
    "doesnt",
    "doesn't",
    "error",
    "failing",
    "investigate",
)


@dataclass
class PromptEntry:
    source: str
    timestamp: datetime
    project: str
    text: str


@dataclass
class ToolCallEntry:
    timestamp: datetime
    name: str
    command: str | None


def parse_iso_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def safe_json_loads(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def clean_text(raw: str, limit: int = 220) -> str:
    text = " ".join(raw.strip().split())
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def read_claude_prompts(window_start_ms: int | None = None, window_end_ms: int | None = None) -> list[PromptEntry]:
    if not CLAUDE_HISTORY.exists():
        return []
    entries: list[PromptEntry] = []
    for line in CLAUDE_HISTORY.read_text(errors="ignore").splitlines():
        obj = safe_json_loads(line)
        if obj is None:
            continue
        ts = obj.get("timestamp")
        display = obj.get("display")
        if not isinstance(ts, int) or not isinstance(display, str):
            continue
        if window_start_ms is not None and ts < window_start_ms:
            continue
        if window_end_ms is not None and ts >= window_end_ms:
            continue
        project = obj.get("project")
        entries.append(
            PromptEntry(
                source="claude",
                timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                project=project if isinstance(project, str) else "-",
                text=clean_text(display),
            )
        )
    return entries


def read_codex_prompts(window_start_s: int | None = None, window_end_s: int | None = None) -> list[PromptEntry]:
    if not CODEX_HISTORY.exists():
        return []
    entries: list[PromptEntry] = []
    for line in CODEX_HISTORY.read_text(errors="ignore").splitlines():
        obj = safe_json_loads(line)
        if obj is None:
            continue
        ts = obj.get("ts")
        text = obj.get("text")
        if not isinstance(ts, int) or not isinstance(text, str):
            continue
        if window_start_s is not None and ts < window_start_s:
            continue
        if window_end_s is not None and ts >= window_end_s:
            continue
        entries.append(
            PromptEntry(
                source="codex",
                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                project="-",
                text=clean_text(text),
            )
        )
    return entries


def parse_codex_tool_event(line: str) -> ToolCallEntry | None:
    # Fast path: most session lines are not function calls.
    if '"type":"response_item"' not in line and '"type": "response_item"' not in line:
        return None

    obj = safe_json_loads(line)
    if obj is None:
        return None
    ts_raw = obj.get("timestamp")
    if not isinstance(ts_raw, str):
        return None
    ts = parse_iso_utc(ts_raw)
    if ts is None:
        return None
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "function_call":
        return None

    name = payload.get("name")
    if not isinstance(name, str) or not name:
        return None

    command: str | None = None
    if name == "exec_command":
        args_raw = payload.get("arguments")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = None
            cmd = args.get("cmd") if isinstance(args, dict) else None
            if isinstance(cmd, str) and cmd.strip():
                command = clean_text(cmd.strip().splitlines()[0], limit=140)

    return ToolCallEntry(timestamp=ts, name=name, command=command)


def read_codex_tools_window(window_start: datetime, window_end: datetime | None = None) -> tuple[Counter[str], Counter[str]]:
    tool_counts: Counter[str] = Counter()
    cmd_counts: Counter[str] = Counter()
    if not CODEX_SESSIONS.exists():
        return tool_counts, cmd_counts

    cutoff = window_start.timestamp() - 86400
    for file_path in CODEX_SESSIONS.rglob("*.jsonl"):
        try:
            if file_path.stat().st_mtime < cutoff:
                continue
            lines = file_path.read_text(errors="ignore").splitlines()
        except OSError:
            continue

        for line in lines:
            event = parse_codex_tool_event(line)
            if event is None:
                continue
            if event.timestamp < window_start:
                continue
            if window_end is not None and event.timestamp >= window_end:
                continue
            tool_counts[event.name] += 1
            if event.command:
                cmd_counts[event.command] += 1

    return tool_counts, cmd_counts


def read_codex_tools_by_day() -> tuple[dict[str, Counter[str]], dict[str, Counter[str]]]:
    tool_by_day: dict[str, Counter[str]] = {}
    cmd_by_day: dict[str, Counter[str]] = {}
    if not CODEX_SESSIONS.exists():
        return tool_by_day, cmd_by_day

    for file_path in CODEX_SESSIONS.rglob("*.jsonl"):
        try:
            lines = file_path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            event = parse_codex_tool_event(line)
            if event is None:
                continue
            day = event.timestamp.strftime("%Y-%m-%d")
            tool_counter = tool_by_day.setdefault(day, Counter())
            cmd_counter = cmd_by_day.setdefault(day, Counter())
            tool_counter[event.name] += 1
            if event.command:
                cmd_counter[event.command] += 1
    return tool_by_day, cmd_by_day


def top_lines(counter: Counter[str], limit: int = 12) -> list[str]:
    return [f"- `{name}` ({count})" for name, count in counter.most_common(limit)]


def lesson_candidates(prompts: list[PromptEntry], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in sorted(prompts, key=lambda x: x.timestamp, reverse=True):
        low = item.text.lower()
        if not any(hint in low for hint in LESSON_HINTS):
            continue
        if item.text in seen:
            continue
        seen.add(item.text)
        out.append(f"- [{item.source}] {item.text}")
        if len(out) >= limit:
            break
    return out


def render_daily_note(
    day: str,
    generated_at: datetime,
    window_label: str,
    prompts: list[PromptEntry],
    tool_counts: Counter[str],
    cmd_counts: Counter[str],
) -> str:
    project_counts: Counter[str] = Counter(p.project for p in prompts if p.project and p.project != "-")
    top_projects = [f"- `{name}` ({count})" for name, count in project_counts.most_common(12)]
    prompt_lines: list[str] = []
    for item in sorted(prompts, key=lambda x: x.timestamp, reverse=True)[:30]:
        ts = item.timestamp.strftime("%H:%MZ")
        proj = f" @ `{item.project}`" if item.project and item.project != "-" else ""
        prompt_lines.append(f"- [{item.source} {ts}]{proj} {item.text}")

    lines = [
        "---",
        f"date: {day}",
        f"generated_at: {generated_at.isoformat().replace('+00:00', 'Z')}",
        f"window: {window_label}",
        "sources:",
        "  - ~/.claude/history.jsonl",
        "  - ~/.codex/history.jsonl",
        "  - ~/.codex/sessions/**/*.jsonl",
        "---",
        "",
        f"# Daily Memory Capture ({day})",
        "",
        "## Snapshot",
        f"- Prompt entries: {len(prompts)}",
        f"- Tool calls (Codex sessions): {sum(tool_counts.values())}",
        f"- Unique commands extracted: {len(cmd_counts)}",
        "",
        "## Top Projects",
        *(top_projects if top_projects else ["- None in this window"]),
        "",
        "## Prompt Highlights",
        *(prompt_lines if prompt_lines else ["- No prompt activity in this window"]),
        "",
        "## Reusable Command Candidates",
        *(top_lines(cmd_counts) if cmd_counts else ["- None captured"]),
        "",
        "## Tool Usage (Codex)",
        *(top_lines(tool_counts) if tool_counts else ["- None captured"]),
        "",
        "## Candidate Lessons",
        *(lesson_candidates(prompts) if prompts else ["- None captured"]),
        "",
        "## Promote Manually",
        "- Promote durable facts into `../MEMORY.md`.",
        "- Promote open loops into `../active-tasks.md`.",
        "- Promote mistakes and fixes into `../lessons.md`.",
        "- Promote repeatable commands into `../../TOOLS.md`.",
        "",
    ]
    return "\n".join(lines)


def extract_shared_memory(hours: int) -> Path:
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=hours)
    window_start_s = int(window_start.timestamp())
    window_start_ms = window_start_s * 1000

    prompts = read_claude_prompts(window_start_ms) + read_codex_prompts(window_start_s)
    tool_counts, cmd_counts = read_codex_tools_window(window_start=window_start)

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    day_tag = now.strftime("%Y-%m-%d")
    output = DAILY_DIR / f"{day_tag}.md"
    output.write_text(
        render_daily_note(
            day=day_tag,
            generated_at=now,
            window_label=f"rolling_{hours}h",
            prompts=prompts,
            tool_counts=tool_counts,
            cmd_counts=cmd_counts,
        )
    )
    return output


def extract_shared_memory_for_utc_day(day: str) -> Path:
    day_start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    start_s = int(day_start.timestamp())
    end_s = int(day_end.timestamp())
    start_ms = start_s * 1000
    end_ms = end_s * 1000

    prompts = read_claude_prompts(start_ms, end_ms) + read_codex_prompts(start_s, end_s)
    tool_counts, cmd_counts = read_codex_tools_window(window_start=day_start, window_end=day_end)

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    output = DAILY_DIR / f"{day}.md"
    output.write_text(
        render_daily_note(
            day=day,
            generated_at=datetime.now(tz=timezone.utc),
            window_label="utc_day",
            prompts=prompts,
            tool_counts=tool_counts,
            cmd_counts=cmd_counts,
        )
    )
    return output


def backfill_all_history(overwrite: bool = False) -> dict[str, Any]:
    prompts = read_claude_prompts() + read_codex_prompts()
    tool_by_day, cmd_by_day = read_codex_tools_by_day()

    prompts_by_day: dict[str, list[PromptEntry]] = {}
    for prompt in prompts:
        day = prompt.timestamp.strftime("%Y-%m-%d")
        prompts_by_day.setdefault(day, []).append(prompt)

    all_days = sorted(set(prompts_by_day.keys()) | set(tool_by_day.keys()) | set(cmd_by_day.keys()))
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    now = datetime.now(tz=timezone.utc)
    for day in all_days:
        output = DAILY_DIR / f"{day}.md"
        if output.exists() and not overwrite:
            skipped += 1
            continue
        output.write_text(
            render_daily_note(
                day=day,
                generated_at=now,
                window_label="utc_day",
                prompts=prompts_by_day.get(day, []),
                tool_counts=tool_by_day.get(day, Counter()),
                cmd_counts=cmd_by_day.get(day, Counter()),
            )
        )
        generated += 1

    return {
        "days_total": len(all_days),
        "generated": generated,
        "skipped": skipped,
        "first_day": all_days[0] if all_days else None,
        "last_day": all_days[-1] if all_days else None,
        "prompt_entries": len(prompts),
        "tool_calls": sum(sum(c.values()) for c in tool_by_day.values()),
    }


def _self_test() -> None:
    sample = "token=abc sk-1234567890abcdefghijklmnop"
    out = clean_text(sample, limit=200)
    assert "sk-" not in out
    assert "[REDACTED]" in out
    assert parse_codex_tool_event('{"type":"noop"}') is None
    parsed = parse_codex_tool_event(
        '{"timestamp":"2026-02-18T22:00:00.000Z","type":"response_item","payload":{"type":"function_call","name":"exec_command","arguments":"{\\"cmd\\":\\"git status\\"}"}}'
    )
    assert parsed is not None
    assert parsed.name == "exec_command"
    assert parsed.command == "git status"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract shared Claude/Codex memory into daily note.")
    parser.add_argument("--hours", type=int, default=24, help="Rolling window to extract.")
    parser.add_argument("--date", type=str, default="", help="Extract for exact UTC day (YYYY-MM-DD).")
    parser.add_argument("--backfill-all", action="store_true", help="Backfill all historical days.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing daily files in backfill mode.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if args.backfill_all:
        report = backfill_all_history(overwrite=args.overwrite)
        print(json.dumps(report, indent=2))
        return 0

    if args.date:
        output = extract_shared_memory_for_utc_day(day=args.date)
        print(str(output))
        return 0

    output = extract_shared_memory(hours=args.hours)
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
