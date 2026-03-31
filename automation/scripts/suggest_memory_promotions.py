#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DAILY_DIR = KNOWLEDGE_ROOT / "memory" / "daily"
PROMOTION_DIR = KNOWLEDGE_ROOT / "data" / "promotions"

MEMORY_FILE = KNOWLEDGE_ROOT / "memory" / "MEMORY.md"
ACTIVE_TASKS_FILE = KNOWLEDGE_ROOT / "memory" / "active-tasks.md"
LESSONS_FILE = KNOWLEDGE_ROOT / "memory" / "lessons.md"
TOOLS_FILE = KNOWLEDGE_ROOT / "TOOLS.md"

ACTION_HINTS = (
    "fix",
    "investigate",
    "add",
    "implement",
    "review",
    "audit",
    "optimize",
    "research",
    "enable",
    "migrate",
    "build",
    "create",
    "backfill",
)
DONE_HINTS = ("completed", "done", "resolved", "fixed")
PROJECT_HINTS = (
    "memory",
    "knowledge",
    "workflow",
    "automation",
    "extract",
    "backfill",
    "index",
    "rag",
    "launchd",
    "optimiz",
    "docs",
    "test",
    "ci",
    "lint",
)
DEFAULT_FOCUS_KEYWORDS = (
    "memory",
    "knowledge",
    "claude",
    "codex",
    "optimization",
    "automation",
    "rag",
    "index",
    "backfill",
    "launchd",
    "session",
    "history",
)
PREFERENCE_HINTS = (
    "prefer",
    "always",
    "never",
    "we use",
    "our setup",
    "local",
    "fixed",
    "memory",
    "automation",
)
MEMORY_STATEMENT_HINTS = ("we ", "our ", "always", "never", "prefer", "should", "must")
NOISE_HINTS = ("amazing", "yes please", "continue please", "sounds good", "thank you")
LESSON_HINTS = ("bug", "regression", "error", "failing", "root cause", "doesn't", "doesnt", "incident", "fix")
SENSITIVE_HINTS = ("token", "password", "secret", "service account", "api key", "credential", "op_")
TOOL_ALLOWED_PREFIXES = ("git ", "cargo ", "npm ", "pnpm ", "bun ", "python3 ", "launchctl ", "zsh ", "sh ")


@dataclass
class Suggestion:
    text: str
    score: float
    source_file: str
    source_section: str


def normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def strip_prompt_prefix(line: str) -> str:
    # Input lines look like:
    # - [codex 22:14Z] text...
    stripped = re.sub(r"^\-\s+\[[^\]]+\]\s*", "", line.strip())
    stripped = re.sub(r"@\s*`[^`]+`\s*", "", stripped)
    return stripped.strip()


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "__root__"
    sections[current] = []
    for raw in text.splitlines():
        if raw.startswith("## "):
            current = raw[3:].strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw)
    return sections


def get_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        if line.strip().startswith("- "):
            bullets.append(line.strip())
    return bullets


def score_active(text: str) -> float:
    low = text.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return 0.0
    if any(secret in low for secret in SENSITIVE_HINTS):
        return 0.0
    if any(noise in low for noise in NOISE_HINTS):
        return 0.0
    if any(done in low for done in DONE_HINTS):
        return 0.0
    score = 0.0
    if any(h in low for h in ACTION_HINTS):
        score += 0.5
    if any(h in low for h in PROJECT_HINTS):
        score += 0.35
    if "?" in text:
        score -= 0.15
    if 35 <= len(text) <= 180:
        score += 0.1
    if len(text) > 220:
        score -= 0.2
    return min(score, 1.0)


def score_memory(text: str) -> float:
    low = text.lower()
    if any(secret in low for secret in SENSITIVE_HINTS):
        return 0.0
    if any(noise in low for noise in NOISE_HINTS):
        return 0.0
    if "?" in text:
        return 0.0
    if low.startswith(("can you", "please", "lets ", "let's ", "i want ", "i would like ")):
        return 0.0
    score = 0.0
    if any(h in low for h in MEMORY_STATEMENT_HINTS):
        score += 0.5
    if any(h in low for h in PREFERENCE_HINTS):
        score += 0.3
    if any(h in low for h in PROJECT_HINTS):
        score += 0.2
    if "workflow" in low or "process" in low:
        score += 0.2
    if len(text) > 35:
        score += 0.1
    return min(score, 1.0)


def score_lesson(text: str) -> float:
    low = text.lower()
    if any(secret in low for secret in SENSITIVE_HINTS):
        return 0.0
    if any(noise in low for noise in NOISE_HINTS):
        return 0.0
    score = 0.0
    if any(h in low for h in LESSON_HINTS):
        score += 0.8
    if "failed" in low or "issue" in low:
        score += 0.1
    if len(text) > 30:
        score += 0.1
    return min(score, 1.0)


def score_tool(text: str) -> float:
    # input format: - `cmd` (count)
    m = re.search(r"\((\d+)\)\s*$", text)
    count = int(m.group(1)) if m else 1
    return min(1.0, 0.4 + (count / 25.0))


def is_reusable_command(command: str) -> bool:
    low = command.lower()
    if any(secret in low for secret in SENSITIVE_HINTS):
        return False
    if "<<" in command:
        return False
    if command.strip().startswith("ssh "):
        return False
    if command.startswith("cd ") or " && " in command:
        # these are usually local one-offs; keep command catalog clean
        return False
    return any(command.startswith(prefix) for prefix in TOOL_ALLOWED_PREFIXES)


def dedupe_suggestions(items: list[Suggestion], limit: int) -> list[Suggestion]:
    seen: set[str] = set()
    out: list[Suggestion] = []
    for item in sorted(items, key=lambda x: x.score, reverse=True):
        key = normalize_line(item.text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def existing_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {normalize_line(line) for line in path.read_text(errors="ignore").splitlines() if line.strip()}


def append_under_heading(path: Path, heading: str, lines: list[str]) -> int:
    if not lines:
        return 0
    content = path.read_text() if path.exists() else ""
    if heading not in content:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n{heading}\n\n"
    add_block = "".join(f"- {line}\n" for line in lines)
    content += add_block
    path.write_text(content)
    return len(lines)


def gather_daily_files(days: int) -> list[Path]:
    if not DAILY_DIR.exists():
        return []
    all_files = sorted(DAILY_DIR.glob("*.md"))
    if days <= 0:
        return all_files
    return all_files[-days:]


def has_focus(text: str, focus_keywords: tuple[str, ...]) -> bool:
    if not focus_keywords:
        return True
    low = text.lower()
    return any(keyword in low for keyword in focus_keywords)


def suggest_from_daily(
    days: int,
    max_items: int,
    min_score: float,
    focus_keywords: tuple[str, ...],
) -> dict[str, list[Suggestion]]:
    memory_suggestions: list[Suggestion] = []
    task_suggestions: list[Suggestion] = []
    lesson_suggestions: list[Suggestion] = []
    tool_suggestions: list[Suggestion] = []

    for daily_file in gather_daily_files(days):
        content = daily_file.read_text(errors="ignore")
        sections = parse_sections(content)

        prompt_lines = get_bullets(sections.get("Prompt Highlights", []))
        for raw in prompt_lines:
            text = strip_prompt_prefix(raw)
            if not text:
                continue
            if not has_focus(text, focus_keywords):
                continue
            task_score = score_active(text)
            if task_score >= min_score:
                task_suggestions.append(
                    Suggestion(text=text, score=task_score, source_file=daily_file.name, source_section="Prompt Highlights")
                )
            mem_score = score_memory(text)
            if mem_score >= min_score:
                memory_suggestions.append(
                    Suggestion(text=text, score=mem_score, source_file=daily_file.name, source_section="Prompt Highlights")
                )

        lesson_lines = get_bullets(sections.get("Candidate Lessons", []))
        for raw in lesson_lines:
            text = strip_prompt_prefix(raw)
            if not text:
                continue
            score = score_lesson(text)
            if score >= min_score:
                lesson_suggestions.append(
                    Suggestion(text=text, score=score, source_file=daily_file.name, source_section="Candidate Lessons")
                )

        tool_lines = get_bullets(sections.get("Reusable Command Candidates", []))
        for raw in tool_lines:
            command = re.sub(r"^\-\s*`", "", raw)
            command = re.sub(r"`\s*\(\d+\)\s*$", "", command).strip()
            if not command:
                continue
            if not is_reusable_command(command):
                continue
            score = score_tool(raw)
            if score >= min_score:
                tool_suggestions.append(
                    Suggestion(text=command, score=score, source_file=daily_file.name, source_section="Reusable Command Candidates")
                )

    return {
        "memory": dedupe_suggestions(memory_suggestions, max_items),
        "active_tasks": dedupe_suggestions(task_suggestions, max_items),
        "lessons": dedupe_suggestions(lesson_suggestions, max_items),
        "tools": dedupe_suggestions(tool_suggestions, max_items),
    }


def render_report(
    suggestions: dict[str, list[Suggestion]],
    days: int,
    min_score: float,
    focus_keywords: tuple[str, ...],
) -> str:
    now = datetime.now(tz=timezone.utc)
    lines = [
        "---",
        f"generated_at: {now.isoformat().replace('+00:00', 'Z')}",
        f"window_days: {days}",
        f"min_score: {min_score}",
        f"focus_keywords: {', '.join(focus_keywords) if focus_keywords else '(none)'}",
        "---",
        "",
        "# Memory Promotion Suggestions",
        "",
        "## MEMORY.md Candidates",
    ]
    if suggestions["memory"]:
        lines.extend(
            [
                f"- {item.text} (score={item.score:.2f}, source={item.source_file}:{item.source_section})"
                for item in suggestions["memory"]
            ]
        )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## active-tasks.md Candidates")
    if suggestions["active_tasks"]:
        lines.extend(
            [
                f"- {item.text} (score={item.score:.2f}, source={item.source_file}:{item.source_section})"
                for item in suggestions["active_tasks"]
            ]
        )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## lessons.md Candidates")
    if suggestions["lessons"]:
        lines.extend(
            [
                f"- {item.text} (score={item.score:.2f}, source={item.source_file}:{item.source_section})"
                for item in suggestions["lessons"]
            ]
        )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## TOOLS.md Candidates")
    if suggestions["tools"]:
        lines.extend(
            [
                f"- `{item.text}` (score={item.score:.2f}, source={item.source_file}:{item.source_section})"
                for item in suggestions["tools"]
            ]
        )
    else:
        lines.append("- None")

    lines.append("")
    return "\n".join(lines)


def apply_suggestions(suggestions: dict[str, list[Suggestion]], targets: set[str]) -> dict[str, int]:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    added = {"memory": 0, "active_tasks": 0, "lessons": 0, "tools": 0}

    if "memory" in targets:
        mem_existing = existing_lines(MEMORY_FILE)
        mem_lines = [s.text for s in suggestions["memory"] if normalize_line(s.text) not in mem_existing]
        added["memory"] = append_under_heading(MEMORY_FILE, f"## Auto Promoted ({timestamp})", mem_lines)

    if "active_tasks" in targets:
        task_existing = existing_lines(ACTIVE_TASKS_FILE)
        task_lines = []
        for suggestion in suggestions["active_tasks"]:
            candidate = f"[ ] {suggestion.text}"
            if normalize_line(candidate) in task_existing:
                continue
            task_lines.append(candidate)
        added["active_tasks"] = append_under_heading(ACTIVE_TASKS_FILE, f"## Auto Promoted ({timestamp})", task_lines)

    if "lessons" in targets:
        lesson_existing = existing_lines(LESSONS_FILE)
        lesson_lines = [s.text for s in suggestions["lessons"] if normalize_line(s.text) not in lesson_existing]
        added["lessons"] = append_under_heading(LESSONS_FILE, f"## Auto Promoted ({timestamp})", lesson_lines)

    if "tools" in targets:
        tools_existing = existing_lines(TOOLS_FILE)
        tool_lines = [f"`{s.text}`" for s in suggestions["tools"] if normalize_line(s.text) not in tools_existing]
        added["tools"] = append_under_heading(TOOLS_FILE, f"## Auto Promoted ({timestamp})", tool_lines)

    return added


def _self_test() -> None:
    assert strip_prompt_prefix("- [codex 22:14Z] fix parser issue").startswith("fix parser issue")
    assert score_active("please fix this bug now") >= 0.5
    assert score_active("amazing yes please") == 0.0
    assert score_active("where do i add token for service account?") == 0.0
    assert score_lesson("root cause and regression fix") > 0.7
    assert not is_reusable_command("ssh jarv 'sudo -n python3 - <<\"PY\"'")
    assert is_reusable_command("git status --short")


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest and optionally apply memory promotions.")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in daily files.")
    parser.add_argument("--max-items", type=int, default=12, help="Max suggestions per target file.")
    parser.add_argument("--min-score", type=float, default=0.75, help="Minimum confidence score.")
    parser.add_argument(
        "--focus-keywords",
        type=str,
        default=",".join(DEFAULT_FOCUS_KEYWORDS),
        help="Comma-separated keywords to scope memory/task promotion relevance. Use empty string to disable.",
    )
    parser.add_argument(
        "--apply-targets",
        type=str,
        default="memory,active_tasks,lessons,tools",
        help="Comma-separated targets to apply when --apply is set.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply suggestions directly to memory files.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    focus_keywords = tuple(k.strip().lower() for k in args.focus_keywords.split(",") if k.strip())
    apply_targets = {k.strip() for k in args.apply_targets.split(",") if k.strip()}
    suggestions = suggest_from_daily(
        days=args.days,
        max_items=args.max_items,
        min_score=args.min_score,
        focus_keywords=focus_keywords,
    )

    PROMOTION_DIR.mkdir(parents=True, exist_ok=True)
    report_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = PROMOTION_DIR / f"promotion-{report_tag}.md"
    report_path.write_text(
        render_report(
            suggestions,
            days=args.days,
            min_score=args.min_score,
            focus_keywords=focus_keywords,
        )
    )

    applied = {"memory": 0, "active_tasks": 0, "lessons": 0, "tools": 0}
    if args.apply:
        applied = apply_suggestions(suggestions, targets=apply_targets)

    summary = {
        "report": str(report_path),
        "suggested": {k: len(v) for k, v in suggestions.items()},
        "applied": applied,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
