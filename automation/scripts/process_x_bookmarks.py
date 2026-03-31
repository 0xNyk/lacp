#!/usr/bin/env python3
"""Process X bookmarks into Obsidian inbox notes.

Reads X API v2 JSON from stdin (output of fetch_x_bookmarks.sh),
deduplicates against seen-state, classifies, checks semantic similarity
against research registry, and writes novel bookmarks as inbox notes.

Usage:
    echo "$JSON" | python3 process_x_bookmarks.py --apply
    echo "$JSON" | python3 process_x_bookmarks.py          # dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DATA_DIR = KNOWLEDGE_ROOT / "data" / "research"
SEEN_FILE = DATA_DIR / "x-bookmarks-seen.json"
REGISTRY_FILE = DATA_DIR / "registry.json"
INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"

# Reuse category rules from sync_research_knowledge
from sync_research_knowledge import (  # noqa: E402
    DEFAULT_CATEGORY_RULES,
    classify_categories,
    load_taxonomy,
)


def load_seen() -> dict[str, Any]:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"version": 1, "seen": {}}


def save_seen(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SEEN_FILE)


def tweet_hash(tweet_id: str) -> str:
    return hashlib.sha1(f"x-bookmark-{tweet_id}".encode()).hexdigest()[:12]


def extract_urls_from_entities(entities: dict[str, Any]) -> list[str]:
    urls = []
    for url_obj in entities.get("urls", []):
        expanded = url_obj.get("expanded_url", "")
        if expanded and not expanded.startswith("https://x.com/") and not expanded.startswith("https://twitter.com/"):
            urls.append(expanded)
    return urls


def extract_topic(text: str) -> str:
    """Extract a short topic summary from tweet text."""
    # Remove URLs
    clean = re.sub(r"https?://\S+", "", text).strip()
    # Remove leading mentions
    clean = re.sub(r"^(@\w+\s*)+", "", clean).strip()
    # Take first sentence or first 80 chars
    first_line = clean.split("\n")[0].strip()
    if len(first_line) > 80:
        cut = first_line[:80].rfind(" ")
        if cut > 40:
            first_line = first_line[:cut] + "..."
        else:
            first_line = first_line[:80] + "..."
    return first_line or "X bookmark"


def find_graph_connections(text: str, registry_items: dict[str, dict]) -> list[str]:
    """Find knowledge graph nodes with semantic similarity 0.70-0.85 (related but not duplicate)."""
    try:
        from semantic_dedup import compute_embedding, cosine_similarity
    except ImportError:
        return []

    vec = compute_embedding(text)
    if not vec:
        return []

    connections = []
    for item_id, item in registry_items.items():
        cached_vec = item.get("embedding")
        if not isinstance(cached_vec, list) or not cached_vec:
            continue
        sim = cosine_similarity(vec, cached_vec)
        if 0.70 <= sim < 0.85:
            connections.append(item_id)
            if len(connections) >= 5:
                break
    return connections


def is_semantic_duplicate(text: str, registry_items: dict[str, dict]) -> bool:
    """Check if this bookmark is semantically similar to an existing research signal."""
    try:
        from semantic_dedup import find_semantic_duplicates
    except ImportError:
        return False

    matches = find_semantic_duplicates(text, registry_items, threshold=0.85, top_k=1)
    return len(matches) > 0


def render_inbox_note(
    tweet_id: str,
    author: str,
    text: str,
    created_at: str,
    urls: list[str],
    categories: list[str],
    connections: list[str],
    metrics: dict[str, int],
) -> str:
    note_id = f"x-bookmark-{tweet_hash(tweet_id)}"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    topic = extract_topic(text)
    tags_str = ", ".join(categories) if categories else "general-research"

    lines = [
        "---",
        f"id: {note_id}",
        f"created: {today}",
        "type: research",
        "status: inbox",
        "source: x-bookmarks",
        f"tags: [{tags_str}]",
        f'description: X bookmark from @{author} about {topic}',
        f'tweet_id: "{tweet_id}"',
        "---",
        "",
        f"# {topic}",
        "",
        "## Source",
        f"- Author: @{author}",
        f"- URL: https://x.com/{author}/status/{tweet_id}",
        f"- Bookmarked: {created_at[:10] if created_at else today}",
    ]

    if metrics:
        lines.append(f"- Engagement: {metrics.get('like_count', 0)} likes, {metrics.get('retweet_count', 0)} RTs, {metrics.get('bookmark_count', 0)} bookmarks")

    lines.extend([
        "",
        "## Content",
        text,
        "",
        "## Evidence URLs",
    ])

    if urls:
        for url in urls:
            lines.append(f"- {url}")
    else:
        lines.append("- None")

    lines.extend(["", "## Connections"])
    if connections:
        for conn in connections:
            lines.append(f"- [[{conn}]]")
    else:
        lines.append("- None found yet")

    lines.extend([
        "",
        "## Open Questions",
        "-",
        "",
    ])

    return "\n".join(lines)


def process(apply: bool) -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {"ok": True, "error": "empty_input", "processed": 0}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"json_parse_error: {e}"}

    if "error" in data:
        return {"ok": False, "error": data["error"]}

    tweets = data.get("data", [])
    if not tweets:
        return {"ok": True, "processed": 0, "note": "no_bookmarks"}

    users = {u["id"]: u for u in data.get("includes", {}).get("users", []) if "id" in u}

    # Load dedup state
    seen = load_seen()
    seen_set = seen.get("seen", {})

    # Load research registry for semantic matching
    registry_items = {}
    if REGISTRY_FILE.exists():
        try:
            reg = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            registry_items = reg.get("items", {})
        except json.JSONDecodeError:
            pass

    # Load taxonomy for classification
    taxonomy = load_taxonomy()
    classification = taxonomy.get("classification", {}) if isinstance(taxonomy.get("classification"), dict) else {}
    default_category = str(classification.get("default_category", "general-research"))
    max_categories = int(classification.get("max_categories", 3))
    category_rules = classification.get("category_rules", DEFAULT_CATEGORY_RULES)
    if not isinstance(category_rules, list):
        category_rules = DEFAULT_CATEGORY_RULES

    created = 0
    skipped_seen = 0
    skipped_semantic = 0

    for tweet in tweets:
        tweet_id = tweet.get("id", "")
        if not tweet_id:
            continue

        thash = tweet_hash(tweet_id)
        if thash in seen_set:
            skipped_seen += 1
            continue

        text = tweet.get("text", "").strip()
        if not text:
            continue

        author_data = users.get(tweet.get("author_id", ""), {})
        author = author_data.get("username", "unknown")
        created_at = tweet.get("created_at", "")
        metrics = tweet.get("public_metrics", {})
        entities = tweet.get("entities", {})
        urls = extract_urls_from_entities(entities)

        # Check semantic duplicate against research registry
        normalized = re.sub(r"https?://\S+", " ", text.lower())
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        if registry_items and is_semantic_duplicate(normalized, registry_items):
            skipped_semantic += 1
            seen_set[thash] = {"tweet_id": tweet_id, "skipped": "semantic_duplicate", "date": datetime.now(UTC).strftime("%Y-%m-%d")}
            continue

        # Classify
        categories = classify_categories(
            text,
            rules=category_rules,
            default_category=default_category,
            max_categories=max_categories,
        )

        # Find graph connections (related but not duplicate)
        connections = find_graph_connections(normalized, registry_items) if registry_items else []

        # Render note
        note_content = render_inbox_note(
            tweet_id=tweet_id,
            author=author,
            text=text,
            created_at=created_at,
            urls=urls,
            categories=categories,
            connections=connections,
            metrics=metrics,
        )

        note_filename = f"x-bookmark-{thash}.md"

        if apply:
            INBOX_DIR.mkdir(parents=True, exist_ok=True)
            note_path = INBOX_DIR / note_filename
            note_path.write_text(note_content, encoding="utf-8")

        seen_set[thash] = {"tweet_id": tweet_id, "date": datetime.now(UTC).strftime("%Y-%m-%d")}
        created += 1

    seen["seen"] = seen_set

    if apply:
        save_seen(seen)

    return {
        "ok": True,
        "total_bookmarks": len(tweets),
        "created": created,
        "skipped_seen": skipped_seen,
        "skipped_semantic": skipped_semantic,
        "mode": "apply" if apply else "dry-run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process X bookmarks into Obsidian inbox notes.")
    parser.add_argument("--apply", action="store_true", help="Write notes and update seen state. Default is dry-run.")
    args = parser.parse_args()

    result = process(apply=args.apply)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
