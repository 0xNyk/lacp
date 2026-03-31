#!/usr/bin/env python3
"""Classify and clean up orphaned registry items.

Orphans are items with 0 edges AND no embedding — they were never connected
to the knowledge graph and were never vectorized.

Classification:
  NOISE    — raw command prompts (text starts with "@ `/Users/"), count <= 6,
             seen on only 1 day. Safe to block and remove.
  VALUABLE — everything else. Queued for re-embedding so they can be
             integrated into the graph on the next pipeline run.

Modes:
  --dry-run (default)  Print what would happen; touch nothing.
  --apply              Write changes to registry.json and reembed-queue.json.
  --json               Machine-readable output on stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_PATH = (
    Path.home()
    / "control"
    / "knowledge"
    / "knowledge-memory"
    / "data"
    / "research"
    / "registry.json"
)
REEMBED_QUEUE_PATH = REGISTRY_PATH.parent / "reembed-queue.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_registry(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def is_orphan(item: dict[str, Any]) -> bool:
    """True when an item has no edges and no embedding."""
    has_edges = bool(item.get("edges"))
    has_embedding = bool(item.get("embedding"))
    return not has_edges and not has_embedding


def is_noise(item: dict[str, Any]) -> bool:
    """True for raw command-prompt junk that is safe to discard."""
    text: str = item.get("text", "")
    count: int = item.get("count", 0)
    days: list[str] = item.get("days", [])
    return (
        text.startswith("@ `/Users/")
        and count <= 6
        and len(days) <= 1
    )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def classify_orphans(
    items: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (noise_ids, valuable_ids) from the full items dict."""
    noise_ids: list[str] = []
    valuable_ids: list[str] = []
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        if not is_orphan(item):
            continue
        if is_noise(item):
            noise_ids.append(item_id)
        else:
            valuable_ids.append(item_id)
    return sorted(noise_ids), sorted(valuable_ids)


def apply_changes(
    registry: dict[str, Any],
    noise_ids: list[str],
    valuable_ids: list[str],
    reembed_queue_path: Path,
) -> None:
    """Mutate registry in-place and write the reembed queue."""
    items: dict[str, Any] = registry.setdefault("items", {})
    blocked: list[str] = registry.setdefault("blocked_ids", [])
    blocked_set: set[str] = set(blocked)

    # Remove NOISE from items; add to blocked_ids.
    for item_id in noise_ids:
        items.pop(item_id, None)
        if item_id not in blocked_set:
            blocked.append(item_id)
            blocked_set.add(item_id)

    registry["updated_at"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    # Write reembed queue (merge with any existing queue).
    existing_queue: list[str] = []
    if reembed_queue_path.exists():
        try:
            existing_queue = json.loads(reembed_queue_path.read_text())
            if not isinstance(existing_queue, list):
                existing_queue = []
        except Exception:
            existing_queue = []

    merged: list[str] = existing_queue + [
        v for v in valuable_ids if v not in set(existing_queue)
    ]
    reembed_queue_path.write_text(json.dumps(merged, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _item_summary(item_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item_id,
        "text_preview": item.get("text", "")[:80],
        "count": item.get("count", 0),
        "days": item.get("days", []),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify and clean up orphaned registry items (0 edges, no embedding)."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Print what would happen without writing anything (default).",
    )
    mode.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Apply changes: block+remove NOISE, write reembed-queue for VALUABLE.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON to stdout.",
    )
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        msg = f"Registry not found: {REGISTRY_PATH}"
        if args.json_output:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    registry = load_registry(REGISTRY_PATH)
    items: dict[str, Any] = registry.get("items", {})
    total_items = len(items)
    blocked_before = len(registry.get("blocked_ids", []))

    noise_ids, valuable_ids = classify_orphans(items)
    total_orphans = len(noise_ids) + len(valuable_ids)

    applied = False
    if not args.dry_run:
        apply_changes(registry, noise_ids, valuable_ids, REEMBED_QUEUE_PATH)
        save_registry(REGISTRY_PATH, registry)
        applied = True

    # Build output payload.
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": args.dry_run,
        "applied": applied,
        "registry_path": str(REGISTRY_PATH),
        "reembed_queue_path": str(REEMBED_QUEUE_PATH),
        "stats": {
            "total_items": total_items,
            "total_orphans": total_orphans,
            "noise_count": len(noise_ids),
            "valuable_count": len(valuable_ids),
            "blocked_ids_before": blocked_before,
            "blocked_ids_after": blocked_before + len(noise_ids) if applied else blocked_before,
        },
        "noise_ids": noise_ids,
        "valuable_ids": valuable_ids,
        "noise_items": [
            _item_summary(i, items[i]) for i in noise_ids if i in items
        ],
        "valuable_items": [
            _item_summary(i, items[i]) for i in valuable_ids if i in items
        ],
    }

    if args.json_output:
        print(json.dumps(result, indent=2))
        return 0

    # Human-readable summary.
    mode_label = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode_label}] Registry orphan cleanup")
    print(f"  Registry : {REGISTRY_PATH}")
    print(f"  Total items in registry : {total_items}")
    print(f"  Orphans found           : {total_orphans}")
    print()

    print(f"  NOISE  ({len(noise_ids)}) — will be blocked + removed:")
    if noise_ids:
        for i, item_id in enumerate(noise_ids):
            item = items.get(item_id, {})
            preview = item.get("text", "")[:72]
            count = item.get("count", 0)
            days = item.get("days", [])
            print(f"    [{i+1:>3}] {item_id}  count={count}  days={len(days)}  {preview!r}")
    else:
        print("    (none)")
    print()

    print(f"  VALUABLE ({len(valuable_ids)}) — will be queued for re-embedding:")
    if valuable_ids:
        for i, item_id in enumerate(valuable_ids):
            item = items.get(item_id, {})
            preview = item.get("text", "")[:72]
            count = item.get("count", 0)
            days = item.get("days", [])
            print(f"    [{i+1:>3}] {item_id}  count={count}  days={len(days)}  {preview!r}")
    else:
        print("    (none)")
    print()

    if args.dry_run:
        print("  No changes written. Pass --apply to execute.")
    else:
        print(f"  Registry saved   : {REGISTRY_PATH}")
        print(f"  Reembed queue    : {REEMBED_QUEUE_PATH}")
        print(f"  blocked_ids grew : {blocked_before} -> {blocked_before + len(noise_ids)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
