#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


OBSIDIAN_DAILY_DIR = Path.home() / "obsidian" / "nyk" / "00-home" / "daily"
KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
AGENT_DAILY_GRAPH_DIR = KNOWLEDGE_ROOT / "graph" / "agent-daily"
AGENT_DAILY_INDEX_PATH = AGENT_DAILY_GRAPH_DIR / "index.md"
REPO_GRAPH_DIR = KNOWLEDGE_ROOT / "graph" / "repositories"
DEFAULT_SCAN_ROOTS = [
    Path.home() / "repos",
    Path.home() / "work",
    Path.home() / "control" / "frameworks",
]

ENTRY_HEADER_RE = re.compile(r"^###\s+(?P<time>.+?)\s+[—-]\s+(?P<agent>[A-Za-z0-9_-]+)\s*$")
FIELD_RE = re.compile(r"^- \*\*(Intent|Outcome|Key files)\*\*:\s*(.*)$", re.IGNORECASE)
ABS_PATH_RE = re.compile(r"/Users/nyk[^\s,;`]+")


@dataclass
class AgentDailyEntry:
    time_label: str
    agent: str
    intent: str = ""
    outcome: str = ""
    key_files_text: str = ""
    key_file_paths: list[str] = field(default_factory=list)


def discover_git_repos(scan_roots: list[Path]) -> list[Path]:
    repos: set[Path] = set()
    for root in scan_roots:
        if not root.exists():
            continue
        for git_dir in root.rglob(".git"):
            if git_dir.is_dir():
                repos.add(git_dir.parent.resolve())
    return sorted(repos, key=lambda p: len(str(p)), reverse=True)


def repo_note_slug_for_path(path: str, repo_paths: list[Path]) -> str | None:
    target = Path(path).resolve()
    for repo in repo_paths:
        try:
            target.relative_to(repo)
            base = re.sub(r"[^a-z0-9]+", "-", repo.name.lower()).strip("-") or "repo"
            suffix = __import__("hashlib").sha1(str(repo).replace(str(Path.home()), "~").encode("utf-8")).hexdigest()[:6]
            return f"{base}-{suffix}"
        except ValueError:
            continue
    return None


def day_cutoff(days: int) -> str | None:
    if days <= 0:
        return None
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


def extract_paths(text: str) -> list[str]:
    found = ABS_PATH_RE.findall(text)
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        clean = item.rstrip(".,;)")
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def parse_agent_daily_entries(path: Path) -> list[AgentDailyEntry]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    in_section = False
    current: AgentDailyEntry | None = None
    entries: list[AgentDailyEntry] = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("## "):
            if line.strip() == "## Agent Daily":
                in_section = True
                continue
            if in_section:
                break
            continue
        if not in_section:
            continue

        m = ENTRY_HEADER_RE.match(line)
        if m:
            if current:
                entries.append(current)
            current = AgentDailyEntry(
                time_label=m.group("time").strip(),
                agent=m.group("agent").strip().lower(),
            )
            continue

        if current is None:
            continue

        fm = FIELD_RE.match(line)
        if fm:
            field_name = fm.group(1).lower()
            value = fm.group(2).strip()
            if field_name == "intent":
                current.intent = value
            elif field_name == "outcome":
                current.outcome = value
            elif field_name == "key files":
                current.key_files_text = value
                current.key_file_paths = extract_paths(value)
            continue

        # Continuation lines for long wrapped bullets.
        if line.startswith("  ") and current.key_files_text:
            current.key_files_text += " " + line.strip()
            current.key_file_paths = extract_paths(current.key_files_text)

    if current:
        entries.append(current)
    return entries


def sanitize(text: str) -> str:
    return " ".join(text.strip().split())


def render_day_note(day: str, entries: list[AgentDailyEntry], repo_paths: list[Path], generated_at: str) -> str:
    blocks: list[str] = []
    for idx, entry in enumerate(entries, start=1):
        repo_slugs: list[str] = []
        seen: set[str] = set()
        for p in entry.key_file_paths:
            slug = repo_note_slug_for_path(p, repo_paths)
            if slug and slug not in seen:
                seen.add(slug)
                repo_slugs.append(slug)
        repo_links = ", ".join(f"[[{slug}|{slug.split('-', 1)[0]}]]" for slug in repo_slugs)
        if not repo_links:
            repo_links = "_none detected_"

        blocks.append(
            "\n".join(
                [
                    f"### {entry.time_label} — {entry.agent} ({idx})",
                    f"- **Intent**: {sanitize(entry.intent) or '_n/a_'}",
                    f"- **Outcome**: {sanitize(entry.outcome) or '_n/a_'}",
                    f"- **Key files**: {sanitize(entry.key_files_text) or '_n/a_'}",
                    f"- **Linked repos**: {repo_links}",
                ]
            )
        )

    body = "\n\n".join(blocks) if blocks else "_No agent daily entries parsed._"
    return f"""---
id: agent-daily-{day}
type: agent-daily-summary
tags: [agent-daily, operations, progress]
description: Structured extraction of Agent Daily updates for {day}.
source_daily_note: [[00-home/daily/{day}]]
generated_at_utc: {generated_at}
---

# Agent Daily Summary — {day}

{body}

## Links

- [[index]]
- [[knowledge/index]]
- [[repo-knowledge-index]]
"""


def render_index(days: list[str], generated_at: str) -> str:
    lines = [f"- [[agent-daily-{day}|{day}]]" for day in sorted(days, reverse=True)]
    body = "\n".join(lines) if lines else "- (no extracted days)"
    return f"""---
id: agent-daily-index
type: knowledge-index
tags: [agent-daily, index]
description: Index of extracted Agent Daily summaries from Obsidian daily notes.
generated_at_utc: {generated_at}
---

# Agent Daily Knowledge Index

{body}

## Links

- [[knowledge/index]]
- [[repo-knowledge-index]]
"""


def sync_agent_daily(days: int, apply: bool, scan_roots: list[Path]) -> dict[str, object]:
    cutoff = day_cutoff(days)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    repo_paths = discover_git_repos(scan_roots)

    day_notes = sorted(OBSIDIAN_DAILY_DIR.glob("*.md"))
    outputs: list[tuple[Path, str]] = []
    extracted_days: list[str] = []
    entries_total = 0

    for daily in day_notes:
        day = daily.stem
        if cutoff and day < cutoff:
            continue
        entries = parse_agent_daily_entries(daily)
        if not entries:
            continue
        entries_total += len(entries)
        extracted_days.append(day)
        outputs.append((AGENT_DAILY_GRAPH_DIR / f"agent-daily-{day}.md", render_day_note(day, entries, repo_paths, generated_at)))

    outputs.append((AGENT_DAILY_INDEX_PATH, render_index(extracted_days, generated_at)))

    changed = 0
    unchanged = 0
    if apply:
        AGENT_DAILY_GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        keep = {path.name for path, _ in outputs}
        for existing in AGENT_DAILY_GRAPH_DIR.glob("*.md"):
            if existing.name not in keep:
                existing.unlink(missing_ok=True)
        for path, content in outputs:
            if path.exists() and path.read_text(encoding="utf-8") == content:
                unchanged += 1
            else:
                path.write_text(content, encoding="utf-8")
                changed += 1
    else:
        for path, content in outputs:
            if path.exists() and path.read_text(encoding="utf-8") == content:
                unchanged += 1
            else:
                changed += 1

    return {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "days_window": days,
        "daily_notes_scanned": len(day_notes),
        "daily_notes_extracted": len(extracted_days),
        "entries_extracted": entries_total,
        "notes_targeted": len(outputs),
        "notes_changed": changed,
        "notes_unchanged": unchanged,
        "output_dir": str(AGENT_DAILY_GRAPH_DIR),
        "index_note": str(AGENT_DAILY_INDEX_PATH),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Obsidian ## Agent Daily entries into knowledge graph notes.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (0 = all)")
    parser.add_argument("--apply", action="store_true", help="Write files (default dry-run)")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    parser.add_argument("--scan-root", action="append", default=[], help="Additional repo scan roots for repo linking")
    return parser.parse_args()


def _self_test() -> None:
    sample = [
        "## Agent Daily",
        "### 09:15 — codex",
        "- **Intent**: Ship fix",
        "- **Outcome**: Done",
        "- **Key files**: /Users/nyk/repos/lacp/bin/lacp",
    ]
    p = Path("/tmp/agent-daily-test.md")
    p.write_text("\n".join(sample), encoding="utf-8")
    entries = parse_agent_daily_entries(p)
    p.unlink(missing_ok=True)
    assert len(entries) == 1
    assert entries[0].agent == "codex"
    assert entries[0].intent == "Ship fix"
    assert entries[0].key_file_paths


def main() -> None:
    _self_test()
    args = parse_args()
    roots = list(DEFAULT_SCAN_ROOTS)
    for extra in args.scan_root:
        roots.append(Path(os.path.expanduser(extra)).resolve())
    result = sync_agent_daily(args.days, args.apply, roots)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
