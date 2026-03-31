#!/usr/bin/env python3
"""Archive old Obsidian inbox items to dated subdirectories.

Moves notes older than N days from ~/obsidian/nyk/inbox/ to
~/obsidian/nyk/inbox/archive/YYYY-MM/.

Age is determined from: frontmatter 'created' > frontmatter 'captured_at' > file mtime.
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"
ARCHIVE_BASE = INBOX_DIR / "archive"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
DATE_KEY_RE = re.compile(r"^(created|captured_at)\s*:\s*(.+)$", re.MULTILINE)


def parse_date_from_frontmatter(content: str) -> datetime | None:
    """Extract date from YAML frontmatter."""
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return None
    fm_text = fm_match.group(1)
    for match in DATE_KEY_RE.finditer(fm_text):
        date_str = match.group(2).strip().strip("'\"")
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def get_file_date(path: Path) -> datetime:
    """Get date for a file: frontmatter first, then mtime."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        fm_date = parse_date_from_frontmatter(content)
        if fm_date:
            return fm_date
    except Exception:
        pass
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description="Archive old inbox items")
    parser.add_argument("--days", type=int, default=14, help="Archive items older than N days (default: 14)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived without moving")
    parser.add_argument("--verbose", action="store_true", help="Print each file processed")
    args = parser.parse_args()

    if not INBOX_DIR.is_dir():
        print(f"Inbox directory not found: {INBOX_DIR}", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    moved = 0
    skipped = 0

    for md_file in sorted(INBOX_DIR.glob("*.md")):
        if not md_file.is_file():
            continue

        file_date = get_file_date(md_file)

        if file_date < cutoff:
            archive_month = file_date.strftime("%Y-%m")
            dest_dir = ARCHIVE_BASE / archive_month
            dest_path = dest_dir / md_file.name

            if args.dry_run:
                print(f"[dry-run] {md_file.name} -> archive/{archive_month}/ (age: {file_date.date()})")
                moved += 1
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if dest_path.exists():
                    print(f"  SKIP (exists): {dest_path}", file=sys.stderr)
                    skipped += 1
                    continue
                shutil.move(str(md_file), str(dest_path))
                if args.verbose:
                    print(f"  Moved: {md_file.name} -> archive/{archive_month}/")
                moved += 1
        else:
            if args.verbose:
                print(f"  Keep: {md_file.name} (age: {file_date.date()})")

    action = "Would archive" if args.dry_run else "Archived"
    print(f"\n{action}: {moved} files. Skipped: {skipped}.")


if __name__ == "__main__":
    main()
