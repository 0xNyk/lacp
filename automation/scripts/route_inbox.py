#!/usr/bin/env python3
"""Route Obsidian inbox items to docs/research/<category>/ based on taxonomy.

Reads all .md files in ~/obsidian/nyk/inbox/, reclassifies items tagged
'general-research' using taxonomy keyword rules on full content, updates
frontmatter tags, and moves to docs/research/<category>/ or docs/research/notes/.

Usage:
    python3 route_inbox.py                  # dry-run (show plan)
    python3 route_inbox.py --apply          # move files
    python3 route_inbox.py --apply --days 7 # only items older than 7 days
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from sync_research_knowledge import (  # noqa: E402
    classify_categories,
    load_taxonomy,
)

INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"
RESEARCH_BASE = Path.home() / "docs" / "research"
NOTES_DIR = RESEARCH_BASE / "notes"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
DATE_RE = re.compile(r"^created\s*:\s*(.+)$", re.MULTILINE)
TAGS_RE = re.compile(r"^tags\s*:\s*\[([^\]]*)\]", re.MULTILINE)
STATUS_RE = re.compile(r"^status\s*:\s*(.+)$", re.MULTILINE)


def parse_frontmatter(content: str) -> tuple[str | None, list[str], str | None]:
    """Extract created date, tags, and status from frontmatter."""
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return None, [], None
    fm = fm_match.group(1)

    created = None
    date_match = DATE_RE.search(fm)
    if date_match:
        created = date_match.group(1).strip().strip("'\"")

    tags: list[str] = []
    tags_match = TAGS_RE.search(fm)
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]

    status = None
    status_match = STATUS_RE.search(fm)
    if status_match:
        status = status_match.group(1).strip()

    return created, tags, status


def reclassify(content: str, taxonomy: dict[str, Any]) -> list[str]:
    """Classify full note content against taxonomy rules."""
    classification = taxonomy.get("classification", {})
    rules = classification.get("category_rules", [])
    default_cat = classification.get("default_category", "general-research")
    max_cats = classification.get("max_categories", 3)
    return classify_categories(
        content,
        rules=rules,
        default_category=default_cat,
        max_categories=max_cats,
    )


def update_tags_in_content(content: str, new_tags: list[str]) -> str:
    """Replace tags in frontmatter."""
    tag_str = ", ".join(new_tags)
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return content
    fm = fm_match.group(1)
    new_fm = TAGS_RE.sub(f"tags: [{tag_str}]", fm)
    # Also update status to 'routed'
    new_fm = STATUS_RE.sub("status: routed", new_fm)
    return content[:fm_match.start(1)] + new_fm + content[fm_match.end(1):]


def route_file(
    path: Path,
    taxonomy: dict[str, Any],
    min_age_days: int,
    apply: bool,
) -> dict[str, Any] | None:
    """Process a single inbox file. Returns routing plan or None if skipped."""
    content = path.read_text(encoding="utf-8", errors="replace")
    created_str, tags, status = parse_frontmatter(content)

    # Skip already-routed items
    if status == "routed":
        return None

    # Check age filter
    if min_age_days > 0 and created_str:
        try:
            created = datetime.strptime(created_str, "%Y-%m-%d").replace(tzinfo=UTC)
            if datetime.now(UTC) - created < timedelta(days=min_age_days):
                return None
        except ValueError:
            pass

    # Determine if reclassification is needed
    needs_reclass = not tags or tags == ["general-research"]

    if needs_reclass:
        new_tags = reclassify(content, taxonomy)
        if not new_tags:
            new_tags = ["general-research"]
    else:
        new_tags = tags

    # Determine destination directory
    primary_category = new_tags[0]
    if primary_category == "general-research":
        dest_dir = NOTES_DIR
    else:
        dest_dir = RESEARCH_BASE / "notes"  # All routed items go to notes/

    dest_path = dest_dir / path.name

    plan = {
        "file": path.name,
        "old_tags": tags,
        "new_tags": new_tags,
        "dest": str(dest_dir.relative_to(Path.home())),
        "reclassified": needs_reclass,
    }

    if apply:
        dest_dir.mkdir(parents=True, exist_ok=True)
        updated_content = update_tags_in_content(content, new_tags)
        dest_path.write_text(updated_content, encoding="utf-8")
        path.unlink()

    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Route inbox items to research categories")
    parser.add_argument("--apply", action="store_true", help="Actually move files (default: dry-run)")
    parser.add_argument("--days", type=int, default=0, help="Only route items older than N days")
    args = parser.parse_args()

    taxonomy = load_taxonomy()

    if not INBOX_DIR.exists():
        print("Inbox directory not found.")
        return

    files = sorted(INBOX_DIR.glob("*.md"))
    if not files:
        print("No items in inbox.")
        return

    routed = 0
    skipped = 0
    plans: list[dict[str, Any]] = []

    for f in files:
        plan = route_file(f, taxonomy, args.days, args.apply)
        if plan:
            plans.append(plan)
            routed += 1
        else:
            skipped += 1

    # Print summary
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] Inbox routing: {routed} routed, {skipped} skipped")

    if plans:
        # Group by category
        by_cat: dict[str, int] = {}
        for p in plans:
            cat = p["new_tags"][0] if p["new_tags"] else "uncategorized"
            by_cat[cat] = by_cat.get(cat, 0) + 1

        print("\nCategory breakdown:")
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

        if not args.apply:
            print("\nSample routes:")
            for p in plans[:10]:
                reclass = " (reclassified)" if p["reclassified"] else ""
                print(f"  {p['file']} → {p['dest']} [{', '.join(p['new_tags'])}]{reclass}")
            if len(plans) > 10:
                print(f"  ... and {len(plans) - 10} more")
            print("\nRun with --apply to execute.")


if __name__ == "__main__":
    main()
