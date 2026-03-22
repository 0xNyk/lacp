#!/usr/bin/env python3
"""Route inbox notes to the appropriate knowledge graph location.

Reads each unrouted note in $LACP_KNOWLEDGE_ROOT/inbox/, inspects its
frontmatter and content, and moves it to the right subdirectory under
the knowledge graph root.

Routing logic:
  - Notes with type: session-extract go to sessions/
  - Notes with type: x-bookmark go to research/
  - Notes with type: claim go to the domain specified in tags
  - Everything else stays in inbox (logged as unroutable)

Use --apply to actually move files. Without it, prints what would happen.

Prints a one-line JSON summary to stdout for the brain-expand orchestrator.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

from brain_utils import parse_frontmatter

KNOWLEDGE_ROOT = os.environ.get("LACP_KNOWLEDGE_ROOT", "")
GRAPH_ROOT = os.environ.get("LACP_KNOWLEDGE_GRAPH_ROOT", "")
INBOX_DIR = os.path.join(KNOWLEDGE_ROOT, "inbox") if KNOWLEDGE_ROOT else ""
APPLY = "--apply" in sys.argv

# domain keywords mapped to graph subdirectories
DOMAIN_MAP = {
    "seo": "seo",
    "business": "business",
    "project": "projects",
    "projects": "projects",
    "meta": "meta",
    "research": "research",
    "agent": "meta",
    "ai": "research",
}

def extract_tags(fm):
    """Get tags as a list from frontmatter."""
    raw = fm.get("tags", "")
    if raw.startswith("["):
        return [t.strip().strip('"').strip("'") for t in raw[1:-1].split(",")]
    return [t.strip() for t in raw.split(",") if t.strip()]

def determine_destination(fm, tags):
    """Figure out where this note should go."""
    note_type = fm.get("type", "").lower()

    if note_type == "session-extract":
        return "sessions"
    if note_type in ("x-bookmark", "x_bookmark"):
        return "research"
    if note_type == "claim":
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in DOMAIN_MAP:
                return DOMAIN_MAP[tag_lower]
        return "misc"

    # check tags for domain hints
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in DOMAIN_MAP:
            return DOMAIN_MAP[tag_lower]

    return None  # unroutable

def route_inbox():
    """Scan inbox and route notes."""
    if not INBOX_DIR or not os.path.isdir(INBOX_DIR):
        print(json.dumps({"ok": True, "routed": 0, "skipped": 0, "unroutable": 0}))
        return

    dest_root = GRAPH_ROOT or os.path.join(KNOWLEDGE_ROOT, "knowledge", "graph")
    routed = 0
    skipped = 0
    unroutable = 0

    for p in sorted(Path(INBOX_DIR).glob("*.md")):
        if ".." in p.name:
            continue

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        fm = parse_frontmatter(text)
        status = fm.get("status", "").lower()

        # skip already processed
        if status in ("graduated", "archived", "routed"):
            skipped += 1
            continue

        tags = extract_tags(fm)
        dest = determine_destination(fm, tags)

        if dest is None:
            unroutable += 1
            continue

        dest_dir = os.path.join(dest_root, dest)

        if APPLY:
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, p.name)
            if not os.path.exists(dest_path):
                shutil.move(str(p), dest_path)
                routed += 1
            else:
                skipped += 1
        else:
            print(f"  would route: {p.name} -> {dest}/")
            routed += 1

    print(json.dumps({"ok": True, "routed": routed, "skipped": skipped, "unroutable": unroutable}))

if __name__ == "__main__":
    route_inbox()
