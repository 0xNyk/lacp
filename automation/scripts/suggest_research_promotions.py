#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
RESEARCH_REGISTRY = KNOWLEDGE_ROOT / "data" / "research" / "registry.json"
RESEARCH_TAXONOMY = KNOWLEDGE_ROOT / "data" / "research" / "taxonomy.json"
RESEARCH_PROMOTION_DIR = KNOWLEDGE_ROOT / "data" / "research" / "promotions"
PROMOTED_STATE_FILE = RESEARCH_PROMOTION_DIR / "promoted-insights.json"
RESEARCH_INSIGHTS_FILE = KNOWLEDGE_ROOT / "graph" / "research-insights.md"
RESEARCH_ARCHIVE_FILE = KNOWLEDGE_ROOT / "graph" / "research-insights-archive.md"
MEMORY_FILE = KNOWLEDGE_ROOT / "memory" / "MEMORY.md"


NOISE_HINTS = (
    "amazing",
    "yes please",
    "sounds good",
    "thank you",
    "continue please",
)


@dataclass
class ResearchSuggestion:
    item_id: str
    text: str
    score: float
    count: int
    categories: list[str]
    last_seen: str
    source_mix: int


def normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def parse_day(day: str) -> datetime | None:
    try:
        return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def clean_text(value: str, limit: int = 220) -> str:
    return " ".join(value.strip().split())[:limit]


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if not isinstance(payload, dict):
        return default
    return payload


def load_registry() -> dict[str, Any]:
    return load_json(RESEARCH_REGISTRY, {"items": {}})


def load_taxonomy() -> dict[str, Any]:
    return load_json(
        RESEARCH_TAXONOMY,
        {
            "promotion": {
                "default_min_score": 0.8,
                "default_min_count": 2,
                "category_min_score": {},
                "stale_days": 60,
                "archive_after_days": 90,
            }
        },
    )


def score_item(
    *,
    text: str,
    count: int,
    categories: list[str],
    last_seen: str,
    source_mix: int,
    now: datetime,
) -> float:
    score = 0.0
    low = text.lower()
    if any(h in low for h in NOISE_HINTS):
        return 0.0
    if len(text) < 30:
        return 0.0

    score += min(0.55, 0.12 * count)
    if len(categories) >= 1 and "general-research" not in categories:
        score += 0.20
    if len(categories) >= 2:
        score += 0.08
    if source_mix >= 2:
        score += 0.10

    last_day = parse_day(last_seen)
    if last_day is not None:
        age_days = (now - last_day).days
        if age_days <= 7:
            score += 0.15
        elif age_days <= 30:
            score += 0.08
        elif age_days > 90:
            score -= 0.12

    if "research the web" in low and len(low) < 40:
        score -= 0.10

    return max(0.0, min(1.0, score))


def category_threshold(categories: list[str], taxonomy: dict[str, Any], default_min_score: float) -> float:
    promotion = taxonomy.get("promotion", {}) if isinstance(taxonomy.get("promotion"), dict) else {}
    raw = promotion.get("category_min_score", {})
    if not isinstance(raw, dict):
        return default_min_score
    threshold = default_min_score
    for category in categories:
        value = raw.get(category)
        if isinstance(value, (int, float)):
            threshold = max(threshold, float(value))
    return threshold


def suggest(
    *,
    days: int,
    min_score: float,
    min_count: int,
    max_items: int,
    taxonomy: dict[str, Any],
) -> list[ResearchSuggestion]:
    payload = load_registry()
    items = payload.get("items", {})
    if not isinstance(items, dict):
        return []

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days) if days > 0 else None
    out: list[ResearchSuggestion] = []
    for item_id, raw in items.items():
        if not isinstance(raw, dict):
            continue
        text = clean_text(str(raw.get("text", "")))
        count = int(raw.get("count", 0))
        categories = [str(c) for c in raw.get("categories", [])] if isinstance(raw.get("categories"), list) else []
        last_seen = str(raw.get("last_seen", ""))
        last_day = parse_day(last_seen)
        if cutoff is not None and (last_day is None or last_day < cutoff):
            continue
        if count < min_count:
            continue
        sources = raw.get("sources", {})
        source_mix = len(sources) if isinstance(sources, dict) else 0
        score = score_item(
            text=text,
            count=count,
            categories=categories,
            last_seen=last_seen,
            source_mix=source_mix,
            now=now,
        )
        item_threshold = category_threshold(categories, taxonomy, min_score)
        if score < item_threshold:
            continue
        out.append(
            ResearchSuggestion(
                item_id=str(item_id),
                text=text,
                score=score,
                count=count,
                categories=categories,
                last_seen=last_seen,
                source_mix=source_mix,
            )
        )
    out.sort(key=lambda x: (x.score, x.count), reverse=True)
    return out[:max_items]


def render_report(
    suggestions: list[ResearchSuggestion],
    *,
    days: int,
    min_score: float,
    min_count: int,
) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "---",
        f"generated_at: {now}",
        f"days: {days}",
        f"min_score: {min_score}",
        f"min_count: {min_count}",
        f"suggestions: {len(suggestions)}",
        "---",
        "",
        "# Research Promotion Suggestions",
        "",
        "## Candidates",
    ]
    if not suggestions:
        lines.append("- None")
    for item in suggestions:
        category_text = ", ".join(item.categories) if item.categories else "general-research"
        lines.append(
            f"- [[research/{item.item_id}]] {item.text} "
            f"(score={item.score:.2f}, count={item.count}, categories={category_text}, last_seen={item.last_seen}, source_mix={item.source_mix})"
        )
    lines.append("")
    return "\n".join(lines)


def load_promoted_state() -> dict[str, Any]:
    payload = load_json(PROMOTED_STATE_FILE, {"version": 1, "updated_at": "", "active": {}, "archived": {}})
    if not isinstance(payload.get("active"), dict):
        payload["active"] = {}
    if not isinstance(payload.get("archived"), dict):
        payload["archived"] = {}
    return payload


def write_promoted_state(payload: dict[str, Any]) -> None:
    RESEARCH_PROMOTION_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROMOTED_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(PROMOTED_STATE_FILE)


def render_insights_doc(active: dict[str, Any], generated_at: str) -> str:
    lines = [
        "---",
        "id: research-insights",
        "description: High-confidence promoted research insights distilled from deduplicated session research signals.",
        "---",
        "",
        "# Research Insights",
        "",
        f"- generated_at: {generated_at}",
        f"- active_insights: {len(active)}",
        "",
        "## Active Insights",
    ]
    if not active:
        lines.append("- None")
        lines.append("")
        return "\n".join(lines)

    ranked = sorted(active.items(), key=lambda kv: (float(kv[1].get("score", 0.0)), int(kv[1].get("count", 0))), reverse=True)
    for item_id, item in ranked:
        categories = item.get("categories", []) if isinstance(item.get("categories"), list) else []
        category_text = ", ".join(str(c) for c in categories) if categories else "general-research"
        lines.append(
            f"- [{item_id}] {item.get('text', '')} "
            f"(count={item.get('count', 0)}, score={float(item.get('score', 0.0)):.2f}, "
            f"categories={category_text}, last_seen={item.get('last_seen', '-')})"
        )
    lines.append("")
    return "\n".join(lines)


def render_archive_doc(archived: dict[str, Any], generated_at: str) -> str:
    lines = [
        "---",
        "id: research-insights-archive",
        "description: Archived research insights that decayed below quality or staleness thresholds.",
        "---",
        "",
        "# Research Insights Archive",
        "",
        f"- generated_at: {generated_at}",
        f"- archived_insights: {len(archived)}",
        "",
        "## Archived",
    ]
    if not archived:
        lines.append("- None")
        lines.append("")
        return "\n".join(lines)

    ranked = sorted(archived.items(), key=lambda kv: str(kv[1].get("archived_at", "")), reverse=True)
    for item_id, item in ranked[:500]:
        lines.append(
            f"- [{item_id}] {item.get('text', '')} "
            f"(reason={item.get('archive_reason', '-')}, archived_at={item.get('archived_at', '-')}, "
            f"last_seen={item.get('last_seen', '-')})"
        )
    lines.append("")
    return "\n".join(lines)


def existing_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {normalize_line(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()}


def append_under_heading(path: Path, heading: str, lines: list[str]) -> int:
    if not lines:
        return 0
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if heading not in content:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n{heading}\n\n"
    content += "".join(f"{line}\n" for line in lines)
    path.write_text(content, encoding="utf-8")
    return len(lines)


def apply_suggestions(
    suggestions: list[ResearchSuggestion],
    *,
    to_memory: bool,
    taxonomy: dict[str, Any],
) -> dict[str, int]:
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    state = load_promoted_state()
    active = state.get("active", {})
    archived = state.get("archived", {})

    if not isinstance(active, dict):
        active = {}
        state["active"] = active
    if not isinstance(archived, dict):
        archived = {}
        state["archived"] = archived

    registry = load_registry().get("items", {})
    if not isinstance(registry, dict):
        registry = {}

    promotion_cfg = taxonomy.get("promotion", {}) if isinstance(taxonomy.get("promotion"), dict) else {}
    default_min_score = float(promotion_cfg.get("default_min_score", 0.8))
    stale_days = int(promotion_cfg.get("stale_days", 60))
    archive_after_days = int(promotion_cfg.get("archive_after_days", 90))

    promoted_now = 0
    archived_now = 0

    for suggestion in suggestions:
        item = active.get(suggestion.item_id)
        if not isinstance(item, dict):
            item = {}
            promoted_now += 1

        item.update(
            {
                "item_id": suggestion.item_id,
                "text": suggestion.text,
                "score": round(float(suggestion.score), 4),
                "count": int(suggestion.count),
                "categories": suggestion.categories,
                "last_seen": suggestion.last_seen,
                "source_mix": int(suggestion.source_mix),
                "last_promoted_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "promotion_count": int(item.get("promotion_count", 0)) + 1,
                "status": "active",
            }
        )
        active[suggestion.item_id] = item

    # Revalidate and archive stale/decayed active items.
    for item_id, item in list(active.items()):
        if not isinstance(item, dict):
            continue

        registry_item = registry.get(item_id)
        if not isinstance(registry_item, dict):
            item["archive_reason"] = "missing-from-registry"
        else:
            categories = [str(c) for c in registry_item.get("categories", [])] if isinstance(registry_item.get("categories"), list) else []
            score = score_item(
                text=str(registry_item.get("text", item.get("text", ""))),
                count=int(registry_item.get("count", item.get("count", 0))),
                categories=categories,
                last_seen=str(registry_item.get("last_seen", item.get("last_seen", ""))),
                source_mix=len(registry_item.get("sources", {})) if isinstance(registry_item.get("sources"), dict) else int(item.get("source_mix", 1)),
                now=now,
            )
            item_threshold = category_threshold(categories, taxonomy, default_min_score)
            last_seen = parse_day(str(registry_item.get("last_seen", item.get("last_seen", ""))))
            if last_seen is None:
                item["archive_reason"] = "invalid-last-seen"
            else:
                age_days = (now - last_seen).days
                if age_days >= archive_after_days:
                    item["archive_reason"] = f"stale>{archive_after_days}d"
                elif age_days >= stale_days and score < (item_threshold + 0.02):
                    item["archive_reason"] = f"stale+low-score age={age_days} score={score:.2f}"
                elif score < max(0.65, item_threshold - 0.05):
                    item["archive_reason"] = f"score-decay score={score:.2f} threshold={item_threshold:.2f}"

        reason = item.get("archive_reason")
        if isinstance(reason, str) and reason:
            item["archived_at"] = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            item["status"] = "archived"
            archived[item_id] = item
            active.pop(item_id, None)
            archived_now += 1

    generated_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state["updated_at"] = generated_at
    write_promoted_state(state)

    RESEARCH_INSIGHTS_FILE.write_text(render_insights_doc(active, generated_at), encoding="utf-8")
    RESEARCH_ARCHIVE_FILE.write_text(render_archive_doc(archived, generated_at), encoding="utf-8")

    added_memory = 0
    if to_memory:
        memory_existing = existing_lines(MEMORY_FILE)
        memory_lines: list[str] = []
        for item_id, item in sorted(active.items(), key=lambda kv: float(kv[1].get("score", 0.0)), reverse=True)[:40]:
            line = f"- Research signal: {item.get('text', '')}"
            if normalize_line(line) in memory_existing:
                continue
            memory_lines.append(line)
        added_memory = append_under_heading(MEMORY_FILE, f"## Auto Promoted Research ({timestamp})", memory_lines)

    return {
        "research_insights": promoted_now,
        "research_archived": archived_now,
        "memory": added_memory,
    }


def _self_test() -> None:
    now = datetime.now(UTC)
    s = score_item(
        text="Deep research on Claude Codex memory orchestration best practices",
        count=4,
        categories=["claude-codex-optimization", "agent-orchestration"],
        last_seen=now.strftime("%Y-%m-%d"),
        source_mix=2,
        now=now,
    )
    assert s > 0.7
    assert score_item(
        text="amazing yes please",
        count=5,
        categories=["general-research"],
        last_seen=now.strftime("%Y-%m-%d"),
        source_mix=1,
        now=now,
    ) == 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest and optionally apply high-confidence research promotions.")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days. Use 0 for all.")
    parser.add_argument("--min-score", type=float, default=0.80, help="Minimum confidence score.")
    parser.add_argument("--min-count", type=int, default=2, help="Minimum observed count per research signal.")
    parser.add_argument("--max-items", type=int, default=40, help="Maximum suggestions to include.")
    parser.add_argument("--apply", action="store_true", help="Apply suggestions to research insights and optionally memory.")
    parser.add_argument("--to-memory", action="store_true", help="When applying, also append distilled signals to MEMORY.md.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    taxonomy = load_taxonomy()
    promotion_cfg = taxonomy.get("promotion", {}) if isinstance(taxonomy.get("promotion"), dict) else {}
    min_score = float(args.min_score if args.min_score is not None else promotion_cfg.get("default_min_score", 0.80))
    min_count = int(args.min_count if args.min_count is not None else promotion_cfg.get("default_min_count", 2))

    suggestions = suggest(
        days=args.days,
        min_score=min_score,
        min_count=min_count,
        max_items=args.max_items,
        taxonomy=taxonomy,
    )

    RESEARCH_PROMOTION_DIR.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = RESEARCH_PROMOTION_DIR / f"promotion-{tag}.md"
    report_path.write_text(
        render_report(
            suggestions,
            days=args.days,
            min_score=min_score,
            min_count=min_count,
        ),
        encoding="utf-8",
    )

    applied = {"research_insights": 0, "research_archived": 0, "memory": 0}
    if args.apply:
        applied = apply_suggestions(suggestions, to_memory=args.to_memory, taxonomy=taxonomy)

    print(
        json.dumps(
            {
                "report": str(report_path),
                "suggested": len(suggestions),
                "applied": applied,
                "insights_file": str(RESEARCH_INSIGHTS_FILE),
                "archive_file": str(RESEARCH_ARCHIVE_FILE),
                "memory_file": str(MEMORY_FILE),
                "state_file": str(PROMOTED_STATE_FILE),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
