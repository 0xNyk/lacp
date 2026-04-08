#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

HOME = Path.home()
SITES_ROOT = HOME / "sites"
WORK_ROOT = HOME / "work"
REPORT_DIR = HOME / "control" / "ops" / "reports" / "sites-migration"

DEFAULT_BUCKETS = ("clients", "products", "experiments", "archived")

EXPERIMENT_KEYWORDS = {
    "test", "sandbox", "tutorial", "bootcamp", "course", "demo", "research",
    "example", "playground", "poc", "prototype", "side", "lab", "algo",
}
CLIENT_KEYWORDS = {
    "client", "agency", "customer", "consult", "contract", "freelance", "portfolio",
}


@dataclass
class MovePlan:
    name: str
    source: str
    destination: str
    bucket: str
    latest_activity_utc: str
    days_since_activity: int
    reason: str
    applied: bool = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def safe_name(path: Path) -> str:
    return path.name.strip()


def latest_activity(path: Path) -> datetime:
    latest = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "target"}]
        for name in files:
            p = Path(root) / name
            try:
                mt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mt > latest:
                latest = mt
    return latest


def classify(name: str, days_inactive: int, archive_after_days: int) -> tuple[str, str]:
    lower = name.lower()
    tokens = {t for t in lower.replace("_", "-").split("-") if t}

    if days_inactive >= archive_after_days:
        return "archived", f"inactive_{days_inactive}d"
    if tokens & CLIENT_KEYWORDS:
        return "clients", "name_keyword_client"
    if tokens & EXPERIMENT_KEYWORDS:
        return "experiments", "name_keyword_experiment"
    return "products", "default_active_product"


def unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stamp = now_utc().strftime("%Y%m%d")
    candidate = Path(f"{dest}-{stamp}")
    idx = 2
    while candidate.exists():
        candidate = Path(f"{dest}-{stamp}-{idx}")
        idx += 1
    return candidate


def iter_site_dirs(root: Path) -> Iterable[Path]:
    for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir():
            continue
        if p.name.startswith('.'):
            continue
        yield p


def build_plan(sites_root: Path, work_root: Path, archive_after_days: int) -> list[MovePlan]:
    plans: list[MovePlan] = []
    now = now_utc()

    for site_dir in iter_site_dirs(sites_root):
        latest = latest_activity(site_dir)
        inactive_days = max(0, int((now - latest).total_seconds() // 86400))
        bucket, reason = classify(site_dir.name, inactive_days, archive_after_days)

        dest_root = work_root / bucket
        dest_root.mkdir(parents=True, exist_ok=True)
        dest_path = unique_destination(dest_root / safe_name(site_dir))

        plans.append(
            MovePlan(
                name=site_dir.name,
                source=str(site_dir),
                destination=str(dest_path),
                bucket=bucket,
                latest_activity_utc=latest.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                days_since_activity=inactive_days,
                reason=reason,
            )
        )

    return plans


def apply_plan(plans: list[MovePlan]) -> None:
    for plan in plans:
        src = Path(plan.source)
        dst = Path(plan.destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        plan.applied = True


def write_report(plans: list[MovePlan], archive_after_days: int, dry_run: bool, output: Path | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    out = output or REPORT_DIR / f"sites-migration-{stamp}.json"

    by_bucket: dict[str, int] = {}
    for p in plans:
        by_bucket[p.bucket] = by_bucket.get(p.bucket, 0) + 1

    payload = {
        "generated_at": now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sites_root": str(SITES_ROOT),
        "work_root": str(WORK_ROOT),
        "archive_after_days": archive_after_days,
        "dry_run": dry_run,
        "counts": {
            "total": len(plans),
            "by_bucket": by_bucket,
            "applied": sum(1 for p in plans if p.applied),
        },
        "moves": [asdict(p) for p in plans],
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def _self_test() -> None:
    bucket, reason = classify("my-client-portal", 10, 180)
    assert bucket == "clients" and reason == "name_keyword_client"
    bucket, reason = classify("sandbox-test", 10, 180)
    assert bucket == "experiments"
    bucket, _ = classify("production-app", 400, 180)
    assert bucket == "archived"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate ~/sites directories into ~/work buckets.")
    parser.add_argument("--sites-root", type=str, default=str(SITES_ROOT))
    parser.add_argument("--work-root", type=str, default=str(WORK_ROOT))
    parser.add_argument("--archive-after-days", type=int, default=183, help="Archive if inactive at least this many days.")
    parser.add_argument("--apply", action="store_true", help="Apply moves. Without this flag, performs dry run only.")
    parser.add_argument("--output", type=str, default="", help="Optional output report file path.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    sites_root = Path(args.sites_root)
    work_root = Path(args.work_root)
    output = Path(args.output) if args.output else None

    if not sites_root.exists() or not sites_root.is_dir():
        raise SystemExit(f"sites root not found: {sites_root}")

    for bucket in DEFAULT_BUCKETS:
        (work_root / bucket).mkdir(parents=True, exist_ok=True)

    plans = build_plan(sites_root, work_root, args.archive_after_days)

    if args.apply:
        apply_plan(plans)

    report = write_report(plans, args.archive_after_days, dry_run=not args.apply, output=output)

    preview = {
        "report": str(report),
        "total": len(plans),
        "applied": sum(1 for p in plans if p.applied),
        "by_bucket": {
            b: sum(1 for p in plans if p.bucket == b)
            for b in DEFAULT_BUCKETS
        },
    }
    print(json.dumps(preview, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
