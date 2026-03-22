#!/usr/bin/env python3
"""Archive old inbox notes that have been sitting unprocessed.

Moves notes older than --days (default 30) from the inbox to an archive
directory. Only touches notes that haven't been graduated or routed.

Use --apply to actually move files. Without it, prints what would happen.

Prints a one-line JSON summary to stdout for the brain-expand orchestrator.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from brain_utils import parse_frontmatter, utcnow

KNOWLEDGE_ROOT = os.environ.get("LACP_KNOWLEDGE_ROOT", "")
INBOX_DIR = os.path.join(KNOWLEDGE_ROOT, "inbox") if KNOWLEDGE_ROOT else ""
ARCHIVE_DIR = os.path.join(KNOWLEDGE_ROOT, "archive", "inbox") if KNOWLEDGE_ROOT else ""

# parse args
APPLY = "--apply" in sys.argv
DAYS = 30
for i, arg in enumerate(sys.argv):
    if arg == "--days" and i + 1 < len(sys.argv):
        try:
            DAYS = int(sys.argv[i + 1])
        except ValueError:
            pass

def archive_inbox():
    """Move stale inbox notes to archive."""
    if not INBOX_DIR or not os.path.isdir(INBOX_DIR):
        print(json.dumps({"ok": True, "archived": 0, "kept": 0}))
        return

    now = utcnow()
    archived = 0
    kept = 0

    for p in sorted(Path(INBOX_DIR).glob("*.md")):
        if ".." in p.name:
            continue

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        fm = parse_frontmatter(text)
        status = fm.get("status", "").lower()

        # don't archive graduated or routed items; they should have been
        # moved already. if they're still here something else went wrong.
        if status in ("graduated", "routed"):
            kept += 1
            continue

        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).days

        if age_days < DAYS:
            kept += 1
            continue

        if APPLY:
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            dest = os.path.join(ARCHIVE_DIR, p.name)
            if not os.path.exists(dest):
                shutil.move(str(p), dest)
                archived += 1
            else:
                kept += 1
        else:
            print(f"  would archive: {p.name} ({age_days} days old)")
            archived += 1

    print(json.dumps({"ok": True, "archived": archived, "kept": kept}))

if __name__ == "__main__":
    archive_inbox()
