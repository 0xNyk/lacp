#!/usr/bin/env python3
"""Scan the knowledge graph for gaps; topics referenced but never defined,
orphan notes with no inbound links, and stale notes that haven't been
touched in over 30 days.

Writes a structured JSON report to:
    $LACP_KNOWLEDGE_ROOT/data/gap-detection/gaps.json

Prints a one-line JSON summary to stdout for the brain-expand orchestrator.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from brain_utils import utcnow

KNOWLEDGE_ROOT = os.environ.get("LACP_KNOWLEDGE_ROOT", "")
GRAPH_ROOT = os.environ.get("LACP_KNOWLEDGE_GRAPH_ROOT", "")
WRITE_NOTE = "--write-note" in sys.argv
STALE_DAYS = 30

def find_md_files(root):
    """Walk the tree and collect all markdown files."""
    files = {}
    for p in Path(root).rglob("*.md"):
        files[str(p)] = p
    return files

def extract_wikilinks(text):
    """Pull all [[wikilink]] targets from a note body."""
    return set(re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]", text))

def detect_gaps(root):
    """Find orphans, broken links, and stale notes."""
    if not root or not os.path.isdir(root):
        return []

    files = find_md_files(root)
    all_stems = {p.stem for p in files.values()}
    link_targets = set()
    inbound = {stem: 0 for stem in all_stems}
    gaps = []
    now = utcnow()

    for path, p in files.items():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        links = extract_wikilinks(text)
        for link in links:
            target = Path(link).stem
            link_targets.add(target)
            if target in inbound:
                inbound[target] += 1

        # check staleness
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        age = (now - mtime).days
        if age > STALE_DAYS:
            gaps.append({
                "category": "stale",
                "note": p.stem,
                "path": str(p.relative_to(root)),
                "days_old": age,
                "score": min(age / 90, 1.0)
            })

    # broken links; referenced but no file exists
    for target in link_targets - all_stems:
        gaps.append({
            "category": "broken_link",
            "note": target,
            "path": None,
            "score": 0.8
        })

    # orphans; no inbound links
    for stem, count in inbound.items():
        if count == 0:
            gaps.append({
                "category": "orphan",
                "note": stem,
                "score": 0.5
            })

    return gaps

def main():
    root = GRAPH_ROOT or KNOWLEDGE_ROOT
    gaps = detect_gaps(root)

    out_dir = os.path.join(KNOWLEDGE_ROOT, "data", "gap-detection")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "gaps.json")

    report = {
        "generated": utcnow().isoformat(),
        "root": root,
        "total_gaps": len(gaps),
        "gaps": sorted(gaps, key=lambda g: -g["score"])
    }

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps({"ok": True, "gaps_found": len(gaps)}))

if __name__ == "__main__":
    main()
