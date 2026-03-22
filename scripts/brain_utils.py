"""Shared utilities for brain-expand pipeline scripts."""

from datetime import datetime, timezone


def parse_frontmatter(text):
    """Pull YAML frontmatter into a dict. Handles simple key: value pairs."""
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("---", 3)
    if end < 0:
        return fm
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def utcnow():
    """Return current UTC datetime (non-deprecated)."""
    return datetime.now(timezone.utc)
