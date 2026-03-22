#!/usr/bin/env python3
"""Build a review queue from inbox items that are ready for human triage.

Scans the inbox for notes older than 24 hours that haven't been routed yet,
ranks them by age and connection density, and writes a prioritized queue.

Writes to:
    $LACP_KNOWLEDGE_ROOT/data/review-queue/review-queue.md

Prints a one-line JSON summary to stdout for the brain-expand orchestrator.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from brain_utils import parse_frontmatter, utcnow

KNOWLEDGE_ROOT = os.environ.get("LACP_KNOWLEDGE_ROOT", "")
INBOX_DIR = os.path.join(KNOWLEDGE_ROOT, "inbox") if KNOWLEDGE_ROOT else ""
MIN_AGE_HOURS = 24

def scan_inbox(inbox_dir):
    """Find inbox notes that are old enough and not yet routed."""
    if not inbox_dir or not os.path.isdir(inbox_dir):
        return []

    items = []
    now = utcnow()

    for p in sorted(Path(inbox_dir).glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        fm = parse_frontmatter(text)

        # skip already graduated items
        status = fm.get("status", "").lower()
        if status in ("graduated", "archived", "routed"):
            continue

        # check age
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        age_hours = (now - mtime).total_seconds() / 3600
        if age_hours < MIN_AGE_HOURS:
            continue

        # count wikilinks as a signal of connection density
        links = re.findall(r"\[\[([^\]]+?)\]\]", text)

        items.append({
            "file": p.name,
            "title": fm.get("title", p.stem),
            "type": fm.get("type", "unknown"),
            "age_days": round(age_hours / 24, 1),
            "links": len(links),
            "priority": round(min(age_hours / 24, 7) + len(links) * 0.5, 2)
        })

    return sorted(items, key=lambda x: -x["priority"])

def write_queue(items, out_path):
    """Write the review queue as a readable markdown file."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    lines = [
        "# Review Queue",
        "",
        f"Generated: {utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        f"Items pending: {len(items)}",
        "",
    ]

    if not items:
        lines.append("Nothing to review. Inbox is clean.")
    else:
        lines.append("| Priority | File | Type | Age (days) | Links |")
        lines.append("|----------|------|------|------------|-------|")
        for item in items:
            lines.append(
                f"| {item['priority']} | {item['file']} "
                f"| {item['type']} | {item['age_days']} | {item['links']} |"
            )

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")

def main():
    items = scan_inbox(INBOX_DIR)

    out_path = os.path.join(KNOWLEDGE_ROOT, "data", "review-queue", "review-queue.md")
    write_queue(items, out_path)

    print(json.dumps({"ok": True, "items": len(items)}))

if __name__ == "__main__":
    main()
