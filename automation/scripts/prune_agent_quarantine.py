#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path.home() / "tmp" / "agent-system-quarantine"


def _dir_time(path: Path) -> datetime | None:
    # expected: YYYYMMDDTHHMMSSZ
    try:
        return datetime.strptime(path.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune old quarantine folders with retention guardrails.")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        assert _dir_time(Path("20260219T120000Z")) is not None
        assert _dir_time(Path("bad")) is None
        print("self-test passed")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, args.days))
    candidates: list[Path] = []

    if ROOT.exists():
        for entry in sorted(ROOT.iterdir()):
            if not entry.is_dir():
                continue
            ts = _dir_time(entry)
            if ts is None:
                continue
            if ts < cutoff:
                candidates.append(entry)

    deleted: list[str] = []
    for entry in candidates:
        if args.apply:
            shutil.rmtree(entry, ignore_errors=True)
            deleted.append(str(entry))

    print(
        json.dumps(
            {
                "ok": True,
                "root": str(ROOT),
                "retention_days": args.days,
                "candidates": [str(x) for x in candidates],
                "deleted": deleted,
                "applied": args.apply,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
