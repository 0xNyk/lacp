#!/Library/Frameworks/Python.framework/Versions/3.11/bin/python3
"""Render autogen skill workflow entries as individual markdown files."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path.home() / ".agents/skills/auto-skill-factory/state/workflow_ledger.json"
OUTPUT_DIR = Path.home() / "control/skills/autogen"


def humanize(key: str) -> str:
    return key.replace("-", " ").title()


def fmt_field(value, fallback: str = "") -> str:
    """Format a field that may be str, list, None, or empty."""
    if value is None:
        return fallback
    if isinstance(value, list):
        if not value:
            return fallback
        return "\n".join(f"- {item}" for item in value)
    s = str(value).strip()
    return s if s else fallback


def parse_iso(ts: str) -> datetime:
    """Parse ISO 8601 timestamp to datetime (handles +00:00 and Z)."""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def render_workflow(key: str, entry: dict) -> str:
    count = entry.get("count", 0)
    first_seen = entry.get("first_seen", "")
    last_seen = entry.get("last_seen", "")
    purpose = fmt_field(entry.get("purpose"), "No purpose recorded")
    validation_results = fmt_field(entry.get("last_validation_results"), "No validation data")
    evidence = fmt_field(entry.get("last_validation_evidence"), "No evidence recorded")
    notes = fmt_field(entry.get("last_notes"), "No notes")

    return f"""---
id: "{key}"
category: "autogen"
run_count: {count}
first_seen: "{first_seen}"
last_seen: "{last_seen}"
tags: [skills, autogen]
---
# {humanize(key)}

## Purpose
{purpose}

## Validation Results
{validation_results}

## Evidence
{evidence}

## Notes
{notes}
"""


def main():
    parser = argparse.ArgumentParser(description="Render autogen skill index from workflow ledger")
    parser.add_argument("--force", action="store_true", help="Re-render all files even if unchanged")
    args = parser.parse_args()

    if not LEDGER_PATH.exists():
        print(f"Error: ledger not found at {LEDGER_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(LEDGER_PATH) as f:
        data = json.load(f)

    workflows = data.get("workflows", {})
    if not workflows:
        print("No workflows found in ledger.")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rendered = 0
    skipped = 0

    for key, entry in workflows.items():
        out_path = OUTPUT_DIR / f"{key}.md"

        if not args.force and out_path.exists():
            last_seen = entry.get("last_seen", "")
            if last_seen:
                try:
                    ls_dt = parse_iso(last_seen)
                    file_mtime = datetime.fromtimestamp(out_path.stat().st_mtime, tz=timezone.utc)
                    if file_mtime >= ls_dt:
                        skipped += 1
                        continue
                except (ValueError, OSError):
                    pass  # re-render on parse/stat errors

        content = render_workflow(key, entry)
        out_path.write_text(content)
        rendered += 1

    print(f"Rendered {rendered} skills, skipped {skipped} unchanged")


if __name__ == "__main__":
    main()
