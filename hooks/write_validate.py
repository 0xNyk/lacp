#!/usr/bin/env python3
"""PostToolUse(Write) validation hook for knowledge notes.

Validates YAML frontmatter schema on files written to knowledge paths.
Only activates for files under configurable knowledge/vault directories.

Exit codes:
  0 — PASS or WARN (non-blocking)
  2 — FAIL (blocking, missing required frontmatter)

Output: JSON with status, issues, and file path.
"""

import json
import os
import re
import sys
from pathlib import Path

# Configurable knowledge paths (colon-separated)
KNOWLEDGE_PATHS_ENV = os.environ.get(
    "LACP_WRITE_VALIDATE_PATHS",
    os.path.expanduser("~/obsidian/nyk")
    + ":"
    + os.environ.get(
        "LACP_KNOWLEDGE_ROOT",
        os.path.expanduser("~/control/knowledge/knowledge-memory"),
    ),
)

TAXONOMY_PATH = os.environ.get(
    "LACP_TAXONOMY_PATH",
    os.path.expanduser(
        "~/control/knowledge/knowledge-memory/data/research/taxonomy.json"
    ),
)

REQUIRED_FIELDS = ["title", "category"]
RECOMMENDED_FIELDS = ["created", "tags"]

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_taxonomy_categories() -> set[str]:
    """Load valid category names from taxonomy.json."""
    try:
        data = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
        rules = data.get("classification", {}).get("category_rules", [])
        return {r["name"] for r in rules if isinstance(r, dict) and "name" in r}
    except Exception:
        return set()


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter as a dict (simple key: value parsing)."""
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None
    raw = match.group(1)
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Strip quotes
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            result[key] = value
    return result


def is_knowledge_path(file_path: str) -> bool:
    """Check if file is under a knowledge directory."""
    resolved = str(Path(file_path).resolve())
    for kpath in KNOWLEDGE_PATHS_ENV.split(":"):
        kpath = kpath.strip()
        if not kpath:
            continue
        if resolved.startswith(str(Path(kpath).resolve())):
            return True
    return False


def validate(file_path: str) -> dict:
    """Validate a file's frontmatter schema."""
    issues = []
    status = "PASS"

    if not file_path.endswith(".md"):
        return {"status": "SKIP", "file": file_path, "issues": [], "reason": "not markdown"}

    if not is_knowledge_path(file_path):
        return {"status": "SKIP", "file": file_path, "issues": [], "reason": "not in knowledge path"}

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return {"status": "SKIP", "file": file_path, "issues": [], "reason": str(e)}

    fm = parse_frontmatter(content)
    if fm is None:
        return {
            "status": "FAIL",
            "file": file_path,
            "issues": ["No YAML frontmatter found"],
        }

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            issues.append(f"Missing required field '{field}'")
            status = "FAIL"

    # Recommended fields (WARN only)
    for field in RECOMMENDED_FIELDS:
        if field not in fm or not fm[field]:
            issues.append(f"Missing recommended field '{field}'")
            if status == "PASS":
                status = "WARN"

    # Category validation
    if "category" in fm and fm["category"]:
        categories = load_taxonomy_categories()
        if categories and fm["category"] not in categories:
            issues.append(f"Category '{fm['category']}' not in taxonomy")
            if status == "PASS":
                status = "WARN"

    return {"status": status, "file": file_path, "issues": issues}


def main():
    # When invoked as a hook, read JSON from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""

    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        # PostToolUse(Write) hook provides tool_input.file_path
        tool_input = data.get("tool_input", {})
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path", "")
        else:
            file_path = ""
    elif len(sys.argv) > 1:
        # Direct invocation with file path argument
        file_path = sys.argv[1]
    else:
        print(json.dumps({"status": "SKIP", "reason": "no file path provided"}))
        sys.exit(0)

    if not file_path:
        sys.exit(0)

    result = validate(file_path)
    print(json.dumps(result))

    if result["status"] == "FAIL":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
