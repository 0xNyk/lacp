#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


DEFAULT_ARTICLES_ROOT = Path.home() / "docs" / "content" / "drafts"
DEFAULT_KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
GRAPH_ARTICLES_DIR = "graph/articles"
LEGACY_ARTICLES_ROOTS = (
    Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent))) / "articles",
    Path.home() / "control" / "frameworks" / "lacp" / "automation" / "articles",
)

HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
SUBHEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")
LIST_ITEM_RE = re.compile(r"^(\-|\*|\d+\.)\s+")


@dataclass
class ArticleEntry:
    slug: str
    source_path: Path
    title: str
    related_files: list[Path]
    modified_at: str
    quality: dict[str, Any]


def rel_home(path: Path) -> str:
    try:
        return "~/" + path.resolve().relative_to(Path.home()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def extract_title(text: str, fallback_slug: str) -> str:
    match = HEADING_RE.search(text)
    if match:
        return match.group(1).strip()
    return fallback_slug.replace("-", " ").title()


def extract_subheadings(text: str, limit: int = 12) -> list[str]:
    return [m.group(1).strip() for m in SUBHEADING_RE.finditer(text)][:limit]


def summarize_intro(text: str, max_lines: int = 4) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def assess_article_quality(
    text: str,
    min_word_count: int,
    min_heading_count: int,
    max_duplicate_line_ratio: float,
    min_lexical_diversity: float,
) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    content_lines = [line for line in lines if not line.startswith("#")]

    words = WORD_RE.findall(text.lower())
    word_count = len(words)
    unique_words = len(set(words))
    lexical_diversity = (unique_words / word_count) if word_count else 0.0

    heading_count = len(HEADING_RE.findall(text)) + len(SUBHEADING_RE.findall(text))
    duplicate_line_ratio = 0.0
    if content_lines:
        duplicate_line_ratio = 1.0 - (len(set(content_lines)) / len(content_lines))

    list_item_count = sum(1 for line in content_lines if LIST_ITEM_RE.match(line))
    list_density = (list_item_count / len(content_lines)) if content_lines else 0.0

    failures: list[str] = []
    if word_count < min_word_count:
        failures.append(f"word_count {word_count} < min_word_count {min_word_count}")
    if heading_count < min_heading_count:
        failures.append(f"heading_count {heading_count} < min_heading_count {min_heading_count}")
    if duplicate_line_ratio > max_duplicate_line_ratio:
        failures.append(
            f"duplicate_line_ratio {duplicate_line_ratio:.3f} > max_duplicate_line_ratio {max_duplicate_line_ratio:.3f}"
        )
    if lexical_diversity < min_lexical_diversity:
        failures.append(
            f"lexical_diversity {lexical_diversity:.3f} < min_lexical_diversity {min_lexical_diversity:.3f}"
        )

    score = 100
    if word_count < min_word_count:
        score -= 30
    if heading_count < min_heading_count:
        score -= 20
    if duplicate_line_ratio > max_duplicate_line_ratio:
        score -= 30
    if lexical_diversity < min_lexical_diversity:
        score -= 20
    score = max(0, score)

    return {
        "ok": len(failures) == 0,
        "score": score,
        "metrics": {
            "word_count": word_count,
            "heading_count": heading_count,
            "duplicate_line_ratio": round(duplicate_line_ratio, 6),
            "lexical_diversity": round(lexical_diversity, 6),
            "list_density": round(list_density, 6),
        },
        "failures": failures,
    }


def collect_articles(
    articles_root: Path,
    min_word_count: int,
    min_heading_count: int,
    max_duplicate_line_ratio: float,
    min_lexical_diversity: float,
) -> list[ArticleEntry]:
    entries: list[ArticleEntry] = []
    if not articles_root.exists():
        return entries

    for article_file in sorted(articles_root.glob("*/article.md")):
        slug = article_file.parent.name
        text = article_file.read_text(encoding="utf-8", errors="ignore")
        title = extract_title(text, slug)
        quality = assess_article_quality(
            text=text,
            min_word_count=min_word_count,
            min_heading_count=min_heading_count,
            max_duplicate_line_ratio=max_duplicate_line_ratio,
            min_lexical_diversity=min_lexical_diversity,
        )
        modified_at = (
            datetime.fromtimestamp(article_file.stat().st_mtime, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

        related = sorted(
            p
            for p in article_file.parent.glob("*.md")
            if p.name != "article.md"
        )
        entries.append(
            ArticleEntry(
                slug=slug,
                source_path=article_file,
                title=title,
                related_files=related,
                modified_at=modified_at,
                quality=quality,
            )
        )

    return entries


def resolve_articles_root(raw_root: Path) -> tuple[Path, bool]:
    normalized = raw_root.expanduser().resolve()
    for legacy in LEGACY_ARTICLES_ROOTS:
        if normalized == legacy.resolve():
            return DEFAULT_ARTICLES_ROOT, True
    return normalized, False


def render_article_node(entry: ArticleEntry, synced_at: str) -> str:
    article_text = entry.source_path.read_text(encoding="utf-8", errors="ignore").strip()
    intro = summarize_intro(article_text)
    sections = extract_subheadings(article_text)

    lines = [
        "---",
        f"id: article-{entry.slug}",
        "description: Imported X article draft for shared memory and retrieval.",
        f"source: {rel_home(entry.source_path)}",
        f"modified_at: {entry.modified_at}",
        f"synced_at: {synced_at}",
        "---",
        "",
        f"# {entry.title}",
        "",
        "## Why This Exists",
        "",
        "- This node makes drafted article knowledge retrievable inside `control/knowledge/knowledge-memory`.",
        "- It is auto-generated from the source article draft.",
        "",
        "## Intro Snapshot",
        "",
    ]

    if intro:
        lines.extend(f"- {line}" for line in intro)
    else:
        lines.append("- (No intro lines detected)")

    lines.extend(["", "## Key Sections", ""])
    if sections:
        lines.extend(f"- {section}" for section in sections)
    else:
        lines.append("- (No section headings detected)")

    lines.extend(["", "## Full Draft", "", article_text, ""])

    lines.extend(["## Ingestion Quality", ""])
    lines.append(f"- quality_ok: `{entry.quality['ok']}`")
    lines.append(f"- quality_score: `{entry.quality['score']}`")
    metrics = entry.quality.get("metrics", {})
    lines.append(f"- word_count: `{metrics.get('word_count', 0)}`")
    lines.append(f"- heading_count: `{metrics.get('heading_count', 0)}`")
    lines.append(f"- duplicate_line_ratio: `{metrics.get('duplicate_line_ratio', 0)}`")
    lines.append(f"- lexical_diversity: `{metrics.get('lexical_diversity', 0)}`")
    failures = entry.quality.get("failures", [])
    if failures:
        lines.append("- quality_failures:")
        lines.extend(f"  - {reason}" for reason in failures)
    else:
        lines.append("- quality_failures: none")
    lines.append("")

    lines.extend(["## Related Source Files", ""])
    if entry.related_files:
        lines.extend(f"- `{rel_home(path)}`" for path in entry.related_files)
    else:
        lines.append("- None")

    lines.append("")
    return "\n".join(lines)


def write_index(entries: list[ArticleEntry], graph_articles_dir: Path, synced_at: str) -> None:
    lines = [
        "---",
        "id: article-knowledge-index",
        "description: Map of drafted X articles imported into shared knowledge-memory.",
        f"synced_at: {synced_at}",
        "---",
        "",
        "# Article Knowledge Index",
        "",
        "This index tracks drafted X articles promoted into the shared knowledge graph.",
        "",
        "## Articles",
        "",
    ]

    if entries:
        for entry in entries:
            status = "PASS" if entry.quality.get("ok") else "FAIL"
            score = entry.quality.get("score", 0)
            lines.append(f"- [[{entry.slug}]]: {entry.title} (`{status}`, score `{score}`)")
    else:
        lines.append("- (No articles found)")

    lines.append("")
    (graph_articles_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def sync_articles(
    articles_root: Path,
    knowledge_root: Path,
    min_word_count: int,
    min_heading_count: int,
    max_duplicate_line_ratio: float,
    min_lexical_diversity: float,
) -> dict[str, Any]:
    graph_articles_dir = knowledge_root / GRAPH_ARTICLES_DIR
    graph_articles_dir.mkdir(parents=True, exist_ok=True)

    entries = collect_articles(
        articles_root=articles_root,
        min_word_count=min_word_count,
        min_heading_count=min_heading_count,
        max_duplicate_line_ratio=max_duplicate_line_ratio,
        min_lexical_diversity=min_lexical_diversity,
    )
    synced_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    kept: set[str] = set()
    for entry in entries:
        node_path = graph_articles_dir / f"{entry.slug}.md"
        node_path.write_text(render_article_node(entry, synced_at), encoding="utf-8")
        kept.add(entry.slug)

    removed = 0
    for stale in graph_articles_dir.glob("*.md"):
        if stale.name == "index.md":
            continue
        if stale.stem not in kept:
            stale.unlink()
            removed += 1

    write_index(entries, graph_articles_dir, synced_at)

    quality_failures = [
        {
            "slug": entry.slug,
            "source": str(entry.source_path),
            "score": entry.quality.get("score"),
            "failures": entry.quality.get("failures", []),
            "metrics": entry.quality.get("metrics", {}),
        }
        for entry in entries
        if not entry.quality.get("ok", False)
    ]
    return {
        "synced": len(entries),
        "removed": removed,
        "quality": {
            "checked": len(entries),
            "passed": len(entries) - len(quality_failures),
            "failed": len(quality_failures),
            "failures": quality_failures,
            "thresholds": {
                "min_word_count": min_word_count,
                "min_heading_count": min_heading_count,
                "max_duplicate_line_ratio": max_duplicate_line_ratio,
                "min_lexical_diversity": min_lexical_diversity,
            },
        },
    }


def write_quality_report(
    report_dir: Path,
    result: dict[str, Any],
    synced_at: str,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = synced_at.replace(":", "").replace("-", "").replace(".", "")
    report_path = report_dir / f"article-sync-quality-{stamp}.json"
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return report_path


def run_self_test() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        articles = root / "control" / "frameworks" / "lacp" / "automation" / "articles"
        knowledge = root / "docs" / "knowledge-memory"

        article_dir = articles / "sample-article"
        article_dir.mkdir(parents=True, exist_ok=True)
        (article_dir / "article.md").write_text(
            "# Sample Article\n\nFirst intro line.\n\n## Step 1\n\nBody text.\n",
            encoding="utf-8",
        )
        (article_dir / "launch-pack.md").write_text("Launch pack", encoding="utf-8")

        result = sync_articles(
            articles_root=articles,
            knowledge_root=knowledge,
            min_word_count=2,
            min_heading_count=1,
            max_duplicate_line_ratio=0.9,
            min_lexical_diversity=0.0,
        )
        assert result["synced"] == 1
        assert result["quality"]["checked"] == 1
        node = knowledge / "graph" / "articles" / "sample-article.md"
        idx = knowledge / "graph" / "articles" / "index.md"
        assert node.exists()
        assert idx.exists()
        text = node.read_text(encoding="utf-8")
        assert "Sample Article" in text
        assert "Full Draft" in text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync drafted X articles into knowledge-memory graph.")
    parser.add_argument("--articles-root", type=Path, default=DEFAULT_ARTICLES_ROOT)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    parser.add_argument("--quality-gate", action="store_true", help="Enable article ingestion quality checks")
    parser.add_argument("--fail-on-quality", action="store_true", help="Exit non-zero when quality failures exist")
    parser.add_argument("--min-word-count", type=int, default=180)
    parser.add_argument("--min-heading-count", type=int, default=3)
    parser.add_argument("--max-duplicate-line-ratio", type=float, default=0.2)
    parser.add_argument("--min-lexical-diversity", type=float, default=0.20)
    parser.add_argument("--quality-report-dir", type=Path, help="Optional directory for JSON quality report")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        print("self-test: ok")
        return 0

    articles_root, remapped = resolve_articles_root(args.articles_root)
    knowledge_root = args.knowledge_root.expanduser().resolve()
    min_word_count = args.min_word_count if args.quality_gate else 0
    min_heading_count = args.min_heading_count if args.quality_gate else 0
    max_duplicate_line_ratio = args.max_duplicate_line_ratio if args.quality_gate else 1.0
    min_lexical_diversity = args.min_lexical_diversity if args.quality_gate else 0.0

    result = sync_articles(
        articles_root=articles_root,
        knowledge_root=knowledge_root,
        min_word_count=min_word_count,
        min_heading_count=min_heading_count,
        max_duplicate_line_ratio=max_duplicate_line_ratio,
        min_lexical_diversity=min_lexical_diversity,
    )
    result["articles_root"] = str(articles_root)
    result["legacy_remap_applied"] = remapped
    synced_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    if args.quality_report_dir:
        report_dir = args.quality_report_dir.expanduser().resolve()
        report_path = write_quality_report(report_dir, result, synced_at)
        result["quality_report"] = str(report_path)

    print(json.dumps(result, indent=2))

    if args.quality_gate and args.fail_on_quality and int(result["quality"]["failed"]) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
