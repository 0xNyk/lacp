#!/usr/bin/env python3
"""Audit and optionally tidy agent-related folders in the home directory.

This script is intentionally conservative:
- It never edits tool-native homes like ~/.claude or ~/.codex.
- It only reports suspicious top-level entries by default.
- With --apply, it moves only loose files (not directories) into quarantine.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

HOME = Path.home()
ROOT_CONTROL = HOME / "control"
KM_ROOT = ROOT_CONTROL / "knowledge" / "knowledge-memory"
OUT_DIR = KM_ROOT / "data" / "hygiene"

ALLOWED_DIRS = {
    ".claude",
    ".codex",
    ".agents",
    ".claude-mem",
    ".codex-orchestrator",
    ".mcp-auth",
    "docs",
    "research",
}

ALLOWED_FILE_PREFIXES = {
    ".claude.json",
}

ALLOWED_FILES = {
    "CLAUDE.md",
    "AGENTS.md",
}

PATTERN = re.compile(r"(claude|codex|agent|orchestr|memory|rag|skill|mcp)", re.IGNORECASE)


@dataclass
class Candidate:
    path: Path
    reason: str


def iter_top_level(home: Path) -> Iterable[Path]:
    for entry in sorted(home.iterdir(), key=lambda p: p.name.lower()):
        if entry.name in {".", ".."}:
            continue
        yield entry


def classify(entry: Path) -> str | None:
    name = entry.name

    if name in ALLOWED_DIRS:
        return None
    if name in ALLOWED_FILES:
        return None
    for prefix in ALLOWED_FILE_PREFIXES:
        if name.startswith(prefix):
            return None

    # Ignore regular hidden/system folders that do not match agent patterns.
    if name.startswith(".") and not PATTERN.search(name):
        return None

    # Flag suspicious names anywhere at top-level.
    if PATTERN.search(name):
        if entry.is_dir():
            return "agent-related directory outside canonical roots"
        return "agent-related loose file at home root"

    # Flag obvious clutter file types at home root.
    if entry.is_file() and entry.suffix.lower() in {".log", ".tmp", ".bak"}:
        return "loose operational artifact at home root"

    return None


def build_report(candidates: list[Candidate]) -> dict:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "generated_at": ts,
        "home": str(HOME),
        "canonical_roots": [
            str(HOME / ".claude"),
            str(HOME / ".codex"),
            str(HOME / ".agents"),
            str(HOME / "control" / "knowledge" / "knowledge-memory"),
            os.environ.get("LACP_AUTOMATION_ROOT", str(Path.home() / "control" / "frameworks" / "lacp" / "automation")),
        ],
        "candidates": [
            {
                "path": str(c.path),
                "type": "dir" if c.path.is_dir() else "file",
                "reason": c.reason,
            }
            for c in candidates
        ],
    }


def write_outputs(report: dict) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUT_DIR / f"layout-audit-{stamp}.json"
    md_path = OUT_DIR / f"layout-audit-{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Agent System Layout Audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Canonical Roots",
        "",
    ]
    lines.extend([f"- `{root}`" for root in report["canonical_roots"]])
    lines.extend(["", "## Findings", ""])

    candidates = report["candidates"]
    if not candidates:
        lines.append("- No top-level clutter findings.")
    else:
        for item in candidates:
            lines.append(f"- `{item['path']}` ({item['type']}): {item['reason']}")

    lines.extend(
        [
            "",
            "## Action Policy",
            "",
            "- Keep tool-native locations unchanged (`~/.claude`, `~/.codex`, `~/.agents`).",
            "- Use `control/knowledge/knowledge-memory` as the single control-plane documentation + governance root.",
            "- Quarantine loose top-level files before deletion.",
        ]
    )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def apply_quarantine(candidates: list[Candidate], *, move_dirs: bool) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = HOME / "tmp" / "agent-system-quarantine" / stamp
    quarantine.mkdir(parents=True, exist_ok=True)

    moved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for candidate in candidates:
        source = candidate.path
        if source.is_dir() and not move_dirs:
            skipped.append({"path": str(source), "reason": "directory skipped (use --move-dirs to include)"})
            continue

        target = quarantine / source.name
        if target.exists():
            target = quarantine / f"{source.name}.{os.getpid()}"

        shutil.move(str(source), str(target))
        moved.append({"from": str(source), "to": str(target)})

    return {"quarantine": str(quarantine), "moved": moved, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit/clean top-level agent-system layout clutter.")
    parser.add_argument("--apply", action="store_true", help="Move findings to quarantine (safe move, not delete).")
    parser.add_argument("--move-dirs", action="store_true", help="Allow moving directories when used with --apply.")
    parser.add_argument("--self-test", action="store_true", help="Run basic self-test and exit.")
    return parser.parse_args()


def run_self_test() -> int:
    sample = [
        Candidate(path=HOME / "random-codex-notes.txt", reason="agent-related loose file at home root"),
        Candidate(path=HOME / ".claude", reason="should never appear"),
    ]
    report = build_report([sample[0]])
    assert "generated_at" in report
    assert report["candidates"][0]["path"].endswith("random-codex-notes.txt")
    print("self-test passed")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    candidates: list[Candidate] = []
    for entry in iter_top_level(HOME):
        reason = classify(entry)
        if reason:
            candidates.append(Candidate(path=entry, reason=reason))

    report = build_report(candidates)
    json_path, md_path = write_outputs(report)

    result = {
        "ok": True,
        "findings": len(candidates),
        "report_json": str(json_path),
        "report_md": str(md_path),
        "applied": False,
    }

    if args.apply:
        quarantine_result = apply_quarantine(candidates, move_dirs=args.move_dirs)
        result["applied"] = True
        result["quarantine"] = quarantine_result

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
