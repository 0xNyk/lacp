#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
ROOT = HOME / "work" / "clients" / "builderz"
REPORT_DIR = HOME / "control" / "ops" / "reports" / "sites-migration"

SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "target", ".venv", "venv"}
RESERVED = {"active", "archived"}


@dataclass
class Move:
    kind: str  # client|subproject
    source: str
    destination: str
    client: str
    days_since_activity: int
    reason: str
    applied: bool = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def latest_activity(path: Path) -> datetime:
    latest = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = Path(root) / f
            try:
                mt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mt > latest:
                latest = mt
    return latest


def slugify(name: str) -> str:
    n = name.strip().lower()
    n = n.replace("&", " and ")
    n = re.sub(r"[^a-z0-9]+", "-", n)
    n = re.sub(r"-+", "-", n).strip("-")
    return n or "unnamed"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    i = 2
    while True:
        c = Path(f"{path}-{i}")
        if not c.exists():
            return c
        i += 1


def collect_client_dirs(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir():
            continue
        if p.name in RESERVED:
            # migrate legacy folders into active/archived buckets separately later if needed
            continue
        out.append(p)
    return out


def plan_client_moves(root: Path, archive_after_days: int) -> list[Move]:
    moves: list[Move] = []
    now = now_utc()
    active_root = root / "active"
    archived_root = root / "archived"
    active_root.mkdir(parents=True, exist_ok=True)
    archived_root.mkdir(parents=True, exist_ok=True)

    for src in collect_client_dirs(root):
        days = int((now - latest_activity(src)).total_seconds() // 86400)
        bucket = "archived" if days >= archive_after_days else "active"
        norm = slugify(src.name)
        dst_base = (archived_root if bucket == "archived" else active_root) / norm
        dst = unique_path(dst_base)
        moves.append(
            Move(
                kind="client",
                source=str(src),
                destination=str(dst),
                client=norm,
                days_since_activity=max(0, days),
                reason=f"bucket={bucket}",
            )
        )
    return moves


def plan_subproject_archives(active_root: Path, archive_after_days: int) -> list[Move]:
    moves: list[Move] = []
    now = now_utc()

    for client_dir in sorted(active_root.iterdir(), key=lambda x: x.name.lower()):
        if not client_dir.is_dir():
            continue
        archived_sub = client_dir / "_archived-subprojects"

        for child in sorted(client_dir.iterdir(), key=lambda x: x.name.lower()):
            if not child.is_dir():
                continue
            if child.name.startswith('.'):
                continue
            if child.name == "_archived-subprojects":
                continue

            # Consider only project-like child dirs: has .git or common project files inside
            likely_project = (child / ".git").exists() or any((child / fn).exists() for fn in (
                "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "requirements.txt"
            ))
            if not likely_project:
                continue

            days = int((now - latest_activity(child)).total_seconds() // 86400)
            if days < archive_after_days:
                continue

            archived_sub.mkdir(parents=True, exist_ok=True)
            dst = unique_path(archived_sub / slugify(child.name))
            moves.append(
                Move(
                    kind="subproject",
                    source=str(child),
                    destination=str(dst),
                    client=client_dir.name,
                    days_since_activity=max(0, days),
                    reason=f"inactive_{days}d",
                )
            )
    return moves


def apply_moves(moves: list[Move]) -> None:
    for m in moves:
        src = Path(m.source)
        dst = Path(m.destination)
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        m.applied = True


def write_report(root: Path, archive_after_days: int, dry_run: bool, moves: list[Move], output: Path | None = None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    out = output or REPORT_DIR / f"builderz-clients-normalization-{stamp}.json"

    payload = {
        "generated_at": now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "archive_after_days": archive_after_days,
        "dry_run": dry_run,
        "counts": {
            "total": len(moves),
            "applied": sum(1 for m in moves if m.applied),
            "client_moves": sum(1 for m in moves if m.kind == "client"),
            "subproject_moves": sum(1 for m in moves if m.kind == "subproject"),
        },
        "moves": [asdict(m) for m in moves],
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def _self_test() -> None:
    assert slugify("Royalty Whitelabel") == "royalty-whitelabel"
    assert slugify("LILY") == "lily"
    assert slugify("degen_update") == "degen-update"


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize ~/work/clients/builderz into active/archived buckets and archive stale subprojects.")
    parser.add_argument("--root", type=str, default=str(ROOT))
    parser.add_argument("--archive-after-days", type=int, default=183)
    parser.add_argument("--skip-subprojects", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"root not found: {root}")

    moves = plan_client_moves(root, args.archive_after_days)

    # Apply client moves first before subproject planning (so active root is stable)
    if args.apply:
        apply_moves(moves)

    active_root = root / "active"
    sub_moves: list[Move] = []
    if not args.skip_subprojects:
        sub_moves = plan_subproject_archives(active_root, args.archive_after_days)
        if args.apply:
            apply_moves(sub_moves)

    all_moves = moves + sub_moves
    output = Path(args.output) if args.output else None
    report = write_report(root, args.archive_after_days, dry_run=not args.apply, moves=all_moves, output=output)

    print(
        json.dumps(
            {
                "report": str(report),
                "total": len(all_moves),
                "applied": sum(1 for m in all_moves if m.applied),
                "client_moves": sum(1 for m in all_moves if m.kind == "client"),
                "subproject_moves": sum(1 for m in all_moves if m.kind == "subproject"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
