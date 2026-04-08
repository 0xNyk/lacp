#!/usr/bin/env python3
"""Wiki Compiler — rewrite raw research signals into clean wiki articles.

Karpathy pattern: raw data is "compiled" by an LLM into polished,
interlinked wiki articles. Turns messy signal text into readable
knowledge base entries with proper structure, backlinks, and summaries.

Runs as a brain-expand step after promotion but before consolidation.
Uses local ollama for rewriting — no external API calls.

Usage:
    python3 compile_wiki.py --dry-run               # preview what would be compiled
    python3 compile_wiki.py --apply --max-items 20   # compile up to 20 articles
    python3 compile_wiki.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KNOWLEDGE_ROOT = Path(os.environ.get(
    "LACP_KNOWLEDGE_ROOT",
    str(Path.home() / "control" / "knowledge" / "knowledge-memory"),
))
REGISTRY_FILE = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"
WIKI_DIR = KNOWLEDGE_ROOT / "graph" / "wiki"
WIKI_INDEX = WIKI_DIR / "index.md"
COMPILE_STATE = KNOWLEDGE_ROOT / "data" / "wiki-compile-state.json"

OLLAMA_HOST = os.environ.get("LACP_OLLAMA_HOST", "http://127.0.0.1:11434")
COMPILE_MODEL = os.environ.get("LACP_WIKI_COMPILE_MODEL", "llama3.1:8b")

# Only compile items with importance above this threshold
MIN_IMPORTANCE = 0.4
# Only compile items seen at least this many times
MIN_COUNT = 2


def ollama_generate(prompt: str, model: str = COMPILE_MODEL, max_tokens: int = 1024) -> str:
    """Generate text via local Ollama."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": max_tokens},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw).get("response", "").strip()
    except Exception as e:
        return f"[LLM error: {e}]"


def load_compile_state() -> dict[str, Any]:
    """Load state tracking which items have been compiled."""
    if COMPILE_STATE.exists():
        try:
            return json.loads(COMPILE_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"compiled_ids": {}, "last_run": ""}


def save_compile_state(state: dict[str, Any]) -> None:
    COMPILE_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = COMPILE_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(COMPILE_STATE)


def find_related_items(
    item_id: str, item: dict[str, Any], items: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    """Find related items for backlinking."""
    related = []
    for edge in (item.get("edges") or [])[:5]:
        rel_id = edge.get("id", "")
        if rel_id in items:
            rel_item = items[rel_id]
            related.append({
                "id": rel_id,
                "text": rel_item.get("text", "")[:80],
                "type": edge.get("type", "related"),
            })
    return related


def compile_article(
    item_id: str,
    item: dict[str, Any],
    related: list[dict[str, str]],
    category: str,
) -> str:
    """Compile a raw research signal into a clean wiki article."""
    raw_text = item.get("text", "")
    evidence = item.get("evidence_urls", [])[:5]
    sources = list(item.get("sources", {}).keys())[:5]
    count = item.get("count", 1)
    first_seen = item.get("first_seen", "")
    last_seen = item.get("last_seen", "")

    # Build related items section for backlinks
    related_block = ""
    if related:
        related_lines = []
        for r in related:
            related_lines.append(f"- [[{r['id']}]]: {r['text']}")
        related_block = f"\nRelated signals:\n" + "\n".join(related_lines)

    evidence_block = ""
    if evidence:
        evidence_block = "\nEvidence URLs:\n" + "\n".join(f"- {url}" for url in evidence)

    prompt = f"""You are a knowledge base editor. Rewrite this raw research signal into a clean, well-structured wiki article.

Raw signal (observed {count} times, {first_seen} to {last_seen}):
"{raw_text}"

Category: {category}
Sources: {', '.join(sources) if sources else 'unknown'}
{evidence_block}
{related_block}

Write a clean wiki article following this structure:
1. A clear one-sentence summary as the first paragraph
2. Key details and context (2-3 paragraphs max)
3. If there are actionable takeaways, list them
4. Keep it concise — this is a wiki entry, not a blog post

Use [[wikilinks]] when referencing related items. Write only the article body, no frontmatter or title."""

    return ollama_generate(prompt, max_tokens=800)


def render_wiki_article(
    item_id: str,
    item: dict[str, Any],
    compiled_body: str,
    category: str,
) -> str:
    """Render the full markdown wiki article with frontmatter."""
    first_seen = item.get("first_seen", "")
    last_seen = item.get("last_seen", "")
    count = item.get("count", 1)
    evidence = item.get("evidence_urls", [])[:5]
    sources = list(item.get("sources", {}).keys())

    # Extract a clean title from the first sentence
    title = compiled_body.split(".")[0].strip()[:80] if compiled_body else item.get("text", "")[:80]

    evidence_section = ""
    if evidence:
        evidence_section = "\n## Sources\n\n" + "\n".join(f"- {url}" for url in evidence)

    return f"""---
id: {item_id}
type: wiki-article
category: {category}
compiled_at: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}
first_seen: {first_seen}
last_seen: {last_seen}
observations: {count}
sources: {json.dumps(sources)}
---

# {title}

{compiled_body}
{evidence_section}

---
*Auto-compiled from {count} observations ({first_seen} to {last_seen}). Category: {category}.*
"""


def render_wiki_index(articles: list[dict[str, Any]], generated_at: str) -> str:
    """Render the wiki index page."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for a in articles:
        cat = a.get("category", "uncategorized")
        by_category.setdefault(cat, []).append(a)

    sections = []
    for cat in sorted(by_category.keys()):
        items = by_category[cat]
        lines = [f"## {cat}\n"]
        for item in sorted(items, key=lambda x: x.get("last_seen", ""), reverse=True):
            lines.append(f"- [[{item['id']}]]: {item['title'][:80]}")
        sections.append("\n".join(lines))

    return f"""---
id: wiki-index
type: wiki-index
compiled_at: {generated_at}
total_articles: {len(articles)}
categories: {len(by_category)}
---

# Knowledge Wiki

> Auto-compiled by LACP brain-expand. {len(articles)} articles across {len(by_category)} categories.
> Last compiled: {generated_at}

{"".join(chr(10) + s + chr(10) for s in sections)}
"""


sys.path.insert(0, str(Path(__file__).parent))


def run_compile(apply: bool, max_items: int, force: bool = False) -> dict[str, Any]:
    """Run the wiki compilation pass."""
    from sync_research_knowledge import (
        compute_importance_score,
    )

    if not REGISTRY_FILE.exists():
        return {"ok": False, "error": "registry not found"}

    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    items = registry.get("items", {})
    state = load_compile_state()
    compiled_ids = state.get("compiled_ids", {})

    # Find items worth compiling
    candidates = []
    for item_id, item in items.items():
        edge_count = len(item.get("edges", []))
        importance = compute_importance_score(item, edge_count=edge_count)
        count = int(item.get("count", 0))

        if importance < MIN_IMPORTANCE or count < MIN_COUNT:
            continue
        if item_id in compiled_ids and not force:
            # Skip already compiled (unless content changed)
            old_hash = compiled_ids[item_id].get("text_hash", "")
            new_hash = str(hash(item.get("text", "")))
            if old_hash == new_hash:
                continue

        categories = item.get("categories", ["uncategorized"])
        candidates.append({
            "id": item_id,
            "importance": importance,
            "count": count,
            "category": categories[0] if categories else "uncategorized",
        })

    # Sort by importance descending
    candidates.sort(key=lambda x: x["importance"], reverse=True)
    candidates = candidates[:max_items]

    if not apply:
        return {
            "ok": True,
            "mode": "dry-run",
            "candidates": len(candidates),
            "already_compiled": len(compiled_ids),
            "total_items": len(items),
            "preview": [
                {"id": c["id"], "importance": round(c["importance"], 3), "category": c["category"]}
                for c in candidates[:10]
            ],
        }

    # Compile
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    compiled = 0
    errors = 0
    articles_meta = []

    for candidate in candidates:
        item_id = candidate["id"]
        item = items[item_id]
        category = candidate["category"]
        related = find_related_items(item_id, item, items)

        try:
            body = compile_article(item_id, item, related, category)
            if body.startswith("[LLM error"):
                errors += 1
                continue

            full_article = render_wiki_article(item_id, item, body, category)
            article_path = WIKI_DIR / f"{item_id}.md"
            article_path.write_text(full_article, encoding="utf-8")

            compiled_ids[item_id] = {
                "compiled_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "text_hash": str(hash(item.get("text", ""))),
                "category": category,
            }

            title = body.split(".")[0].strip()[:80] if body else item.get("text", "")[:80]
            articles_meta.append({
                "id": item_id,
                "title": title,
                "category": category,
                "last_seen": item.get("last_seen", ""),
            })
            compiled += 1
        except Exception:
            errors += 1

    # Rebuild index with ALL compiled articles
    all_articles = []
    for aid, ameta in compiled_ids.items():
        item = items.get(aid, {})
        title = item.get("text", "")[:80]
        wiki_file = WIKI_DIR / f"{aid}.md"
        if wiki_file.exists():
            # Read title from compiled article
            try:
                content = wiki_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except OSError:
                pass
        all_articles.append({
            "id": aid,
            "title": title,
            "category": ameta.get("category", "uncategorized"),
            "last_seen": item.get("last_seen", ""),
        })

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    WIKI_INDEX.write_text(render_wiki_index(all_articles, generated_at), encoding="utf-8")

    # Save state
    state["compiled_ids"] = compiled_ids
    state["last_run"] = generated_at
    save_compile_state(state)

    return {
        "ok": True,
        "mode": "apply",
        "compiled": compiled,
        "errors": errors,
        "total_wiki_articles": len(compiled_ids),
        "wiki_dir": str(WIKI_DIR),
        "index": str(WIKI_INDEX),
    }


def _self_test() -> None:
    """Test without LLM calls."""
    # Test render functions
    article = render_wiki_article(
        "test-123",
        {"text": "test signal", "first_seen": "2026-03-30", "last_seen": "2026-03-31", "count": 3, "evidence_urls": [], "sources": {"claude": 2}},
        "This is a compiled article body about testing.",
        "test-category",
    )
    assert "# This is a compiled article body" in article
    assert "test-123" in article
    assert "wiki-article" in article

    index = render_wiki_index(
        [{"id": "test-1", "title": "Test Article", "category": "testing", "last_seen": "2026-03-31"}],
        "2026-03-31T00:00:00Z",
    )
    assert "wiki-index" in index
    assert "[[test-1]]" in index


def main() -> int:
    parser = argparse.ArgumentParser(description="Wiki Compiler — compile research signals into wiki articles")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--force", action="store_true", help="Recompile already-compiled items")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1

    result = run_compile(apply=args.apply, max_items=args.max_items, force=args.force)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
