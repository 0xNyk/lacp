#!/usr/bin/env python3
"""Ingest Siftly X bookmark export into Obsidian inbox notes.

Reads Siftly's JSON export (flat array of bookmarks), deduplicates
against the shared x-bookmarks-seen.json, classifies with two-pass
category resolution (Siftly slug → vault category + keyword refinement),
and writes structured inbox notes.

Usage:
    python3 ingest_siftly.py --file export.json                  # dry-run
    python3 ingest_siftly.py --from-url http://localhost:3000     # dry-run from running Siftly
    python3 ingest_siftly.py --file export.json --apply           # write notes
    python3 ingest_siftly.py --file export.json --apply --skip-semantic  # skip embedding dedup
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from process_x_bookmarks import (  # noqa: E402
    INBOX_DIR,
    REGISTRY_FILE,
    extract_topic,
    find_graph_connections,
    is_semantic_duplicate,
    load_seen,
    save_seen,
    tweet_hash,
)
from sync_research_knowledge import (  # noqa: E402
    DEFAULT_CATEGORY_RULES,
    classify_categories,
    load_taxonomy,
)

# ── Siftly slug → vault category mapping ─────────────────────────────

SIFTLY_CATEGORY_MAP: dict[str, list[str]] = {
    "ai-resources": ["ai-ml-research", "llm-engineering"],
    "finance-crypto": ["web3-blockchain", "solana-defi-trading"],
    "dev-tools": ["devtools-workflow"],
    "finance-investing": ["quantitative-finance"],
    "startups-business": ["startup-business"],
    "news": ["general-research"],
    "design": ["frontend-design"],
    "health-wellness": ["general-research"],
    "security-privacy": ["security-governance", "privacy-identity"],
    "science-research": ["ai-ml-research"],
    "productivity": ["devtools-workflow", "automation-ops"],
    "funny-memes": ["general-research"],
    "general": ["general-research"],
}


def map_siftly_categories(siftly_categories: list[dict[str, str]]) -> list[str]:
    """Map Siftly category slugs to vault categories via lookup table."""
    mapped: list[str] = []
    for cat in siftly_categories:
        slug = cat.get("slug", "")
        if slug in SIFTLY_CATEGORY_MAP:
            mapped.extend(SIFTLY_CATEGORY_MAP[slug])
    return mapped


def resolve_categories(
    text: str,
    siftly_categories: list[dict[str, str]],
    *,
    rules: list[dict[str, Any]],
    default_category: str,
    max_categories: int,
) -> list[str]:
    """Two-pass category resolution: Siftly slugs + keyword classification."""
    # Pass 1: map Siftly slugs
    from_siftly = map_siftly_categories(siftly_categories)

    # Pass 2: keyword classification on tweet text
    from_keywords = classify_categories(
        text,
        rules=rules,
        default_category=default_category,
        max_categories=max_categories,
    )

    # Merge, dedup, cap at max_categories
    merged: list[str] = []
    seen_cats: set[str] = set()
    for cat in from_siftly + from_keywords:
        if cat not in seen_cats and cat != default_category:
            seen_cats.add(cat)
            merged.append(cat)

    if not merged:
        merged = [default_category]

    return merged[:max_categories]


def resolve_date(bookmark: dict[str, Any]) -> str:
    """Get best available date string (YYYY-MM-DD)."""
    for field in ("tweetCreatedAt", "importedAt"):
        val = bookmark.get(field)
        if val and isinstance(val, str):
            try:
                return val[:10]
            except (IndexError, TypeError):
                pass
    return datetime.now(UTC).strftime("%Y-%m-%d")


def render_siftly_note(
    bookmark: dict[str, Any],
    categories: list[str],
    connections: list[str],
    thash: str,
) -> str:
    """Render a Siftly bookmark as an Obsidian inbox note."""
    tweet_id = bookmark["tweetId"]
    author = bookmark.get("authorHandle", "unknown")
    author_name = bookmark.get("authorName", "")
    text = bookmark.get("text", "").strip()
    topic = extract_topic(text)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    date_str = resolve_date(bookmark)
    tags_str = ", ".join(categories) if categories else "general-research"

    siftly_cats = bookmark.get("categories", [])
    siftly_cat_names = [c.get("name", "") for c in siftly_cats if c.get("name")]

    lines = [
        "---",
        f"id: x-bookmark-{thash}",
        f"created: {today}",
        "type: research",
        "status: inbox",
        "source: x-bookmarks-siftly",
        f"tags: [{tags_str}]",
        f'description: "X bookmark from @{author} -- {topic}"',
        f'tweet_id: "{tweet_id}"',
    ]
    if siftly_cat_names:
        cats_json = json.dumps(siftly_cat_names)
        lines.append(f"siftly_categories: {cats_json}")
    lines.extend([
        "auto_captured: true",
        "---",
        "",
        f"# {topic}",
        "",
        "## Source",
        f"- Author: @{author}" + (f" ({author_name})" if author_name else ""),
        f"- URL: https://x.com/{author}/status/{tweet_id}",
        f"- Bookmarked: {date_str}",
        "- Imported via: Siftly",
        "",
        "## Content",
        text,
    ])

    # Media
    media_items = bookmark.get("mediaItems", [])
    if media_items:
        lines.extend(["", "## Media"])
        for item in media_items:
            media_type = item.get("type", "photo")
            url = item.get("url", "")
            if url:
                lines.append(f"- ![{media_type}]({url})")

    # Semantic tags
    semantic_tags = bookmark.get("semanticTags", [])
    if semantic_tags and isinstance(semantic_tags, list):
        lines.extend(["", "## Semantic Tags"])
        lines.append(" ".join(f"`{tag}`" for tag in semantic_tags))

    # Enrichment metadata
    enrichment = bookmark.get("enrichmentMeta")
    if enrichment and isinstance(enrichment, dict):
        lines.extend(["", "## Enrichment"])
        if enrichment.get("sentiment"):
            lines.append(f"- Sentiment: {enrichment['sentiment']}")
        if enrichment.get("people"):
            people = enrichment["people"]
            if isinstance(people, list):
                lines.append(f"- People: {', '.join(str(p) for p in people)}")
        if enrichment.get("companies"):
            companies = enrichment["companies"]
            if isinstance(companies, list):
                lines.append(f"- Companies: {', '.join(str(c) for c in companies)}")

    # Connections
    lines.extend(["", "## Connections"])
    if connections:
        for conn in connections:
            lines.append(f"- [[{conn}]]")
    else:
        lines.append("- None found yet")

    lines.extend(["", ""])
    return "\n".join(lines)


def load_siftly_export(file_path: str | None, from_url: str | None) -> list[dict[str, Any]]:
    """Load bookmarks from file or running Siftly instance."""
    if file_path:
        raw = Path(file_path).read_text(encoding="utf-8")
    elif from_url:
        url = from_url.rstrip("/") + "/api/export?type=json"
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    else:
        raise SystemExit("error: provide --file or --from-url")

    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit(f"error: expected JSON array, got {type(data).__name__}")
    return data


def process(
    bookmarks: list[dict[str, Any]],
    *,
    apply: bool,
    skip_semantic: bool,
) -> dict[str, Any]:
    # Load dedup state
    seen = load_seen()
    seen_set = seen.get("seen", {})

    # Load research registry for semantic matching
    registry_items: dict[str, dict] = {}
    if not skip_semantic and REGISTRY_FILE.exists():
        try:
            reg = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            registry_items = reg.get("items", {})
        except json.JSONDecodeError:
            pass

    # Load taxonomy for keyword classification
    taxonomy = load_taxonomy()
    classification = taxonomy.get("classification", {})
    if not isinstance(classification, dict):
        classification = {}
    default_category = str(classification.get("default_category", "general-research"))
    max_categories = int(classification.get("max_categories", 3))
    category_rules = classification.get("category_rules", DEFAULT_CATEGORY_RULES)
    if not isinstance(category_rules, list):
        category_rules = DEFAULT_CATEGORY_RULES

    created = 0
    skipped_seen = 0
    skipped_semantic = 0

    for bookmark in bookmarks:
        tweet_id = bookmark.get("tweetId", "")
        if not tweet_id:
            continue

        thash = tweet_hash(tweet_id)
        if thash in seen_set:
            skipped_seen += 1
            continue

        text = bookmark.get("text", "").strip()
        if not text:
            continue

        # Normalize for semantic ops
        normalized = re.sub(r"https?://\S+", " ", text.lower())
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()

        # Semantic dedup
        if registry_items and not skip_semantic:
            if is_semantic_duplicate(normalized, registry_items):
                skipped_semantic += 1
                seen_set[thash] = {
                    "tweet_id": tweet_id,
                    "skipped": "semantic_duplicate",
                    "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                    "source": "siftly",
                }
                continue

        # Two-pass category resolution
        siftly_categories = bookmark.get("categories", [])
        categories = resolve_categories(
            text,
            siftly_categories,
            rules=category_rules,
            default_category=default_category,
            max_categories=max_categories,
        )

        # Graph connections
        connections = find_graph_connections(normalized, registry_items) if registry_items else []

        # Render note
        note_content = render_siftly_note(bookmark, categories, connections, thash)
        note_filename = f"x-bookmark-{thash}.md"

        if apply:
            INBOX_DIR.mkdir(parents=True, exist_ok=True)
            (INBOX_DIR / note_filename).write_text(note_content, encoding="utf-8")

        seen_set[thash] = {
            "tweet_id": tweet_id,
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "source": "siftly",
        }
        created += 1

    seen["seen"] = seen_set
    if apply:
        save_seen(seen)

    return {
        "ok": True,
        "total_bookmarks": len(bookmarks),
        "created": created,
        "skipped_seen": skipped_seen,
        "skipped_semantic": skipped_semantic,
        "mode": "apply" if apply else "dry-run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Siftly X bookmark export into Obsidian inbox.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="Path to Siftly JSON export file")
    source.add_argument("--from-url", help="Base URL of running Siftly instance (e.g. http://localhost:3000)")
    parser.add_argument("--apply", action="store_true", help="Write notes and update seen state (default: dry-run)")
    parser.add_argument("--skip-semantic", action="store_true", help="Skip slow embedding-based dedup")
    args = parser.parse_args()

    bookmarks = load_siftly_export(args.file, args.from_url)
    result = process(bookmarks, apply=args.apply, skip_semantic=args.skip_semantic)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
