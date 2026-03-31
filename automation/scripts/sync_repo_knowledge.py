#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
REPO_GRAPH_DIR = KNOWLEDGE_ROOT / "graph" / "repositories"
REPO_INDEX_PATH = REPO_GRAPH_DIR / "index.md"
DEFAULT_SCAN_ROOTS = [
    Path.home() / "repos",
    Path.home() / "work",
    Path.home() / "control" / "frameworks",
]
MAX_EXT_BUCKETS = 8


@dataclass
class RepoInfo:
    name: str
    path: Path
    rel_path: str
    origin_url: str
    head_branch: str
    last_commit_iso: str
    last_commit_sha: str
    last_commit_subject: str
    tracked_files: int
    top_extensions: list[tuple[str, int]]
    top_directories: list[str]
    note_slug: str = ""


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def note_slug_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "repo"


def discover_git_repos(scan_roots: list[Path]) -> list[Path]:
    repos: set[Path] = set()
    for root in scan_roots:
        if not root.exists():
            continue
        for git_dir in root.rglob(".git"):
            if git_dir.is_dir():
                repos.add(git_dir.parent.resolve())
    return sorted(repos, key=lambda p: str(p).lower())


def parse_top_extensions(paths: list[str]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for rel in paths:
        p = Path(rel)
        suffix = p.suffix.lower()
        if suffix:
            key = suffix
        else:
            key = "<no-ext>"
        counter[key] += 1
    return counter.most_common(MAX_EXT_BUCKETS)


def parse_top_directories(paths: list[str]) -> list[str]:
    counter: Counter[str] = Counter()
    root_files = 0
    for rel in paths:
        parts = Path(rel).parts
        if not parts:
            continue
        if len(parts) == 1:
            root_files += 1
            continue
        counter[parts[0]] += 1
    out = [name for name, _ in counter.most_common(7)]
    if root_files > 0:
        out.append("(root-files)")
    return out[:8]


def collect_repo_info(repo: Path) -> RepoInfo:
    repo_name = repo.name
    rel = str(repo).replace(str(Path.home()), "~")
    origin_url = run_git(repo, "config", "--get", "remote.origin.url")
    head_branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    last_commit_line = run_git(repo, "log", "-1", "--format=%cI|%h|%s")
    last_commit_iso = ""
    last_commit_sha = ""
    last_commit_subject = ""
    if last_commit_line:
        parts = last_commit_line.split("|", 2)
        if len(parts) == 3:
            last_commit_iso, last_commit_sha, last_commit_subject = parts

    files_raw = run_git(repo, "ls-files")
    file_list = [line for line in files_raw.splitlines() if line.strip()]
    tracked_files = len(file_list)
    top_ext = parse_top_extensions(file_list)
    top_dirs = parse_top_directories(file_list)

    return RepoInfo(
        name=repo_name,
        path=repo,
        rel_path=rel,
        origin_url=origin_url,
        head_branch=head_branch,
        last_commit_iso=last_commit_iso,
        last_commit_sha=last_commit_sha,
        last_commit_subject=last_commit_subject,
        tracked_files=tracked_files,
        top_extensions=top_ext,
        top_directories=top_dirs,
    )


def assign_unique_slugs(repos: list[RepoInfo]) -> None:
    by_base: dict[str, list[RepoInfo]] = {}
    for repo in repos:
        base = note_slug_from_name(repo.name)
        by_base.setdefault(base, []).append(repo)

    for base, items in by_base.items():
        if len(items) == 1:
            items[0].note_slug = base
            continue
        for item in sorted(items, key=lambda r: r.rel_path.lower()):
            suffix = hashlib.sha1(item.rel_path.encode("utf-8")).hexdigest()[:6]
            item.note_slug = f"{base}-{suffix}"


def build_repo_note(info: RepoInfo, generated_at: str) -> str:
    ext_lines = "\n".join(f"- `{ext}`: {count}" for ext, count in info.top_extensions) or "- n/a"
    dir_lines = "\n".join(f"- `{name}`" for name in info.top_directories) or "- n/a"
    origin_line = info.origin_url or "(no origin remote)"
    branch_line = info.head_branch or "(detached/unknown)"
    commit_line = (
        f"- `{info.last_commit_sha}` ({info.last_commit_iso}) — {info.last_commit_subject}"
        if info.last_commit_sha
        else "- n/a"
    )
    return f"""---
id: repo-{info.note_slug}
type: codebase-repository
tags: [repo, codebase, development]
description: Codebase profile for {info.name}.
generated_at_utc: {generated_at}
---

# Repo: {info.name}

## Identity

- Path: `{info.rel_path}`
- Origin: `{origin_line}`
- Current branch: `{branch_line}`
- Tracked files: `{info.tracked_files}`

## Recent Activity

{commit_line}

## Structure Signals

### Top directories
{dir_lines}

### Top file extensions
{ext_lines}

## Links

- [[index]]
- [[knowledge/index]]
"""


def build_repo_index(repos: list[RepoInfo], generated_at: str) -> str:
    lines: list[str] = []
    for info in repos:
        lines.append(f"- [[repo-{info.note_slug}|{info.name}]] — `{info.rel_path}`")
    repo_list = "\n".join(lines) or "- (no repositories discovered)"
    return f"""---
id: repo-knowledge-index
type: knowledge-index
tags: [repo, codebase, index]
description: Index of local codebase repository notes for Obsidian graph navigation.
generated_at_utc: {generated_at}
---

# Repository Knowledge Index

Generated from local git repositories.

## Repositories

{repo_list}

## Links

- [[knowledge/index]]
- [[research-index]]
"""


def sync_repo_knowledge(scan_roots: list[Path], apply: bool) -> dict[str, object]:
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    repos = [collect_repo_info(repo) for repo in discover_git_repos(scan_roots)]
    repos.sort(key=lambda r: r.name.lower())
    assign_unique_slugs(repos)

    outputs: list[tuple[Path, str]] = []
    outputs.append((REPO_INDEX_PATH, build_repo_index(repos, generated_at)))
    for info in repos:
        outputs.append((REPO_GRAPH_DIR / f"repo-{info.note_slug}.md", build_repo_note(info, generated_at)))

    written = 0
    unchanged = 0

    if apply:
        REPO_GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        keep_names = {path.name for path, _ in outputs}
        for existing in REPO_GRAPH_DIR.glob("*.md"):
            if existing.name not in keep_names:
                existing.unlink(missing_ok=True)

        for path, content in outputs:
            if path.exists() and path.read_text(encoding="utf-8") == content:
                unchanged += 1
                continue
            path.write_text(content, encoding="utf-8")
            written += 1
    else:
        for path, content in outputs:
            if path.exists() and path.read_text(encoding="utf-8") == content:
                unchanged += 1
            else:
                written += 1

    return {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "scan_roots": [str(r) for r in scan_roots],
        "repos_found": len(repos),
        "notes_targeted": len(outputs),
        "notes_changed": written,
        "notes_unchanged": unchanged,
        "output_dir": str(REPO_GRAPH_DIR),
        "index_note": str(REPO_INDEX_PATH),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local git repositories into Obsidian knowledge graph notes.")
    parser.add_argument("--apply", action="store_true", help="Write notes (default is dry-run)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    parser.add_argument("--scan-root", action="append", default=[], help="Extra root to scan for git repositories")
    return parser.parse_args()


def _self_test() -> None:
    assert note_slug_from_name("x-article-factory") == "x-article-factory"
    assert note_slug_from_name("Repo Name!") == "repo-name"
    exts = parse_top_extensions(["a.py", "b.py", "README", "src/main.rs"])
    assert exts[0][0] in {".py", ".rs", "<no-ext>"}
    dirs = parse_top_directories(["src/main.rs", "src/lib.rs", "docs/readme.md"])
    assert dirs[0] in {"src", "docs"}


def main() -> None:
    _self_test()
    args = parse_args()

    roots = list(DEFAULT_SCAN_ROOTS)
    for extra in args.scan_root:
        p = Path(os.path.expanduser(extra)).resolve()
        roots.append(p)

    result = sync_repo_knowledge(roots, apply=args.apply)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
