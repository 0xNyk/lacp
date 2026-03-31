#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
DEFAULT_ROOTS = [
    HOME / "work" / "archived",
    HOME / "work" / "clients" / "builderz" / "archived",
]
REPORT_DIR = HOME / "control" / "ops" / "reports" / "space-optimization"

PRUNE_DIR_NAMES = {
    "node_modules",
    ".next",
    "dist",
    "build",
    "target",
    ".turbo",
    ".cache",
    "coverage",
    ".parcel-cache",
    ".vite",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
}

# never prune these names even if matched accidentally by path rules
PROTECTED_DIR_NAMES = {
    ".git",
    ".claude",
    ".agents",
    "docs",
    "src",
}


@dataclass
class PruneEntry:
    path: str
    size_bytes: int
    reason: str
    applied: bool = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dir_size_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    return f"{v:.2f} {units[i]}"


def should_prune_dir(path: Path) -> bool:
    name = path.name
    if name in PROTECTED_DIR_NAMES:
        return False
    return name in PRUNE_DIR_NAMES


def scan_candidates(roots: list[Path]) -> list[PruneEntry]:
    entries: list[PruneEntry] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_dir():
                continue
            if not should_prune_dir(p):
                continue
            size = dir_size_bytes(p)
            if size <= 0:
                continue
            entries.append(PruneEntry(path=str(p), size_bytes=size, reason=f"prune:{p.name}"))
    # dedupe exact paths and sort largest first
    dedup: dict[str, PruneEntry] = {}
    for e in entries:
        dedup[e.path] = e
    out = list(dedup.values())
    out.sort(key=lambda e: e.size_bytes, reverse=True)
    return out


def apply(entries: list[PruneEntry]) -> None:
    for e in entries:
        p = Path(e.path)
        if not p.exists() or not p.is_dir():
            continue
        shutil.rmtree(p)
        e.applied = True


def write_report(roots: list[Path], entries: list[PruneEntry], dry_run: bool, output: Path | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    report = output or (REPORT_DIR / f"archived-space-optimization-{stamp}.json")

    total = sum(e.size_bytes for e in entries)
    payload = {
        "generated_at": now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "roots": [str(r) for r in roots],
        "dry_run": dry_run,
        "summary": {
            "candidates": len(entries),
            "estimated_reclaim_bytes": total,
            "estimated_reclaim_human": human_bytes(total),
            "applied_count": sum(1 for e in entries if e.applied),
            "applied_reclaim_bytes": sum(e.size_bytes for e in entries if e.applied),
        },
        "entries": [asdict(e) for e in entries],
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return report


def _self_test() -> None:
    assert should_prune_dir(Path('/tmp/x/node_modules'))
    assert not should_prune_dir(Path('/tmp/x/.git'))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune regenerable build/dependency artifacts inside archived project roots.")
    parser.add_argument("--root", action="append", default=[], help="Root to scan (repeatable).")
    parser.add_argument("--apply", action="store_true", help="Apply pruning. Without this, dry-run only.")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    roots = [Path(r) for r in args.root] if args.root else DEFAULT_ROOTS
    entries = scan_candidates(roots)
    if args.apply:
        apply(entries)

    report = write_report(roots, entries, dry_run=not args.apply, output=Path(args.output) if args.output else None)
    total = sum(e.size_bytes for e in entries)
    applied = sum(e.size_bytes for e in entries if e.applied)

    print(
        json.dumps(
            {
                "report": str(report),
                "candidates": len(entries),
                "estimated_reclaim": human_bytes(total),
                "applied": bool(args.apply),
                "applied_reclaim": human_bytes(applied),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
