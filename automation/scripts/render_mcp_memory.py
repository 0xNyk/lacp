#!/Library/Frameworks/Python.framework/Versions/3.11/bin/python3
"""Render MCP memory entities as individual markdown files.

Reads entities from mcp-entities.json and writes one .md per entity
to the entities/ output directory with frontmatter and observations.
"""

import json
import re
import sys
from pathlib import Path

MEMORY_DIR = Path.home() / "control" / "knowledge" / "knowledge-memory" / "memory"
INPUT_FILE = MEMORY_DIR / "mcp-entities.json"
OUTPUT_DIR = MEMORY_DIR / "entities"


def slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric with hyphens, collapse and strip."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def render_entity(entity: dict, output_dir: Path) -> str:
    """Render a single entity to a markdown file. Returns the filename."""
    name = entity.get("name", "unnamed")
    entity_type = entity.get("entityType", "unknown")
    observations = entity.get("observations", [])
    slug = slugify(name)
    filename = f"{slug}.md"

    observations_md = "\n".join(f"- {obs}" for obs in observations) if observations else "- (none)"

    content = f"""---
id: "entity-{slug}"
entity_type: "{entity_type}"
source: "mcp-memory"
tags: [entities, mcp-memory]
---
# {name}

## Type
{entity_type}

## Observations
{observations_md}
"""

    (output_dir / filename).write_text(content, encoding="utf-8")
    return filename


def main() -> None:
    if not INPUT_FILE.exists():
        print("No MCP entities file found, skipping")
        sys.exit(0)

    raw = INPUT_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        print("MCP entities file is empty, skipping")
        sys.exit(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("MCP entities file contains invalid JSON, skipping")
        sys.exit(0)

    entities = data.get("entities", [])
    if not entities:
        print("No entities found in file, skipping")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for entity in entities:
        if not isinstance(entity, dict) or "name" not in entity:
            continue
        render_entity(entity, OUTPUT_DIR)
        count += 1

    print(f"Rendered {count} entities")


if __name__ == "__main__":
    main()
