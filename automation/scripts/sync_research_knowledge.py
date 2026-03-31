#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).parent))

KNOWLEDGE_ROOT = Path.home() / "control" / "knowledge" / "knowledge-memory"
DAILY_DIR = KNOWLEDGE_ROOT / "memory" / "daily"
GRAPH_RESEARCH_DIR = KNOWLEDGE_ROOT / "graph" / "research"
DATA_RESEARCH_DIR = KNOWLEDGE_ROOT / "data" / "research"
REGISTRY_FILE = DATA_RESEARCH_DIR / "registry.json"
INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"
TAXONOMY_FILE = DATA_RESEARCH_DIR / "taxonomy.json"
QUARANTINE_FILE = GRAPH_RESEARCH_DIR / "quarantine-candidates.md"


DEFAULT_RESEARCH_HINTS = (
    "research",
    "deep research",
    "web",
    "benchmark",
    "compare",
    "competitor",
    "analyze",
    "analysis",
    "investigate",
    "study",
    "sources",
    "documentation",
    "best practices",
)


DEFAULT_CATEGORY_RULES: list[dict[str, Any]] = [
    {
        "name": "memory-knowledge",
        "keywords": ["memory", "knowledge", "rag", "retrieval", "context", "session"],
        "min_keyword_hits": 1,
    },
    {
        "name": "agent-orchestration",
        "keywords": ["sub-agent", "subagent", "multiagent", "multi-agent", "orchestration", "parallel", "swarm", "handoff"],
        "min_keyword_hits": 1,
    },
    {
        "name": "claude-codex-optimization",
        "keywords": ["claude", "codex", "optimization", "latency", "throughput", "prompt caching", "compaction"],
        "min_keyword_hits": 1,
    },
    {
        "name": "privacy-identity",
        "keywords": ["privacy", "identity", "auth", "encryption", "zero-knowledge", "credential", "gdpr"],
        "min_keyword_hits": 1,
    },
    {
        "name": "security-governance",
        "keywords": ["security", "policy", "audit", "risk", "governance", "compliance"],
        "min_keyword_hits": 1,
    },
    {
        "name": "startup-business",
        "keywords": ["startup", "revenue", "agency", "saas", "b2b", "customers", "pricing", "billing"],
        "min_keyword_hits": 1,
    },
    {
        "name": "marketing-outreach",
        "keywords": ["email", "outreach", "cold", "leads", "pipeline", "crm", "sequence", "drip", "warmup"],
        "min_keyword_hits": 1,
    },
    {
        "name": "product-market-competitors",
        "keywords": ["competitor", "market", "positioning", "seo", "content"],
        "min_keyword_hits": 1,
    },
    {
        "name": "quantitative-finance",
        "keywords": ["trading", "quant", "backtest", "strategy", "alpha", "sharpe", "portfolio", "risk management"],
        "min_keyword_hits": 1,
    },
    {
        "name": "data-engineering",
        "keywords": ["data pipeline", "etl", "warehouse", "analytics", "sql", "postgres", "dbt", "streaming"],
        "min_keyword_hits": 1,
    },
    {
        "name": "llm-engineering",
        "keywords": ["llm", "fine-tune", "prompt engineering", "token", "embedding", "inference", "rag pipeline"],
        "min_keyword_hits": 1,
    },
    {
        "name": "automation-ops",
        "keywords": ["automation", "cron", "launchd", "systemd", "pipeline", "ci/cd", "deploy", "script"],
        "min_keyword_hits": 1,
    },
    {
        "name": "prediction-markets",
        "keywords": ["prediction market", "forecast", "polymarket", "manifold", "betting", "odds", "calibration"],
        "min_keyword_hits": 1,
    },
    {
        "name": "infra-performance",
        "keywords": ["mac", "server", "infra", "deployment", "performance", "profiling", "benchmark"],
        "min_keyword_hits": 1,
    },
]


PROMPT_LINE_RE = re.compile(r"^- \[(?P<source>[a-zA-Z0-9_-]+)\s+(?P<time>[0-9]{2}:[0-9]{2}Z)\]\s*(?P<text>.+)$")
URL_RE = re.compile(r"https?://[^\s\]\)]+")
NOISE_HINTS = (
    "amazing",
    "yes please",
    "sounds good",
    "thank you",
    "continue please",
)


@dataclass
class ResearchSignal:
    day: str
    source: str
    text: str
    urls: list[str]


def clean_text(value: str, limit: int = 280) -> str:
    text = " ".join(value.strip().split())
    return text[:limit]


def normalize_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = " ".join(value.split())
    return value


def text_id(normalized: str) -> str:
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"research-{digest}"


def load_taxonomy() -> dict[str, Any]:
    if TAXONOMY_FILE.exists():
        try:
            payload = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "version": 1,
        "research_hints": list(DEFAULT_RESEARCH_HINTS),
        "classification": {
            "default_category": "general-research",
            "max_categories": 3,
            "category_rules": DEFAULT_CATEGORY_RULES,
        },
    }


def is_research_text(text: str, research_hints: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(hint in low for hint in research_hints)


def classify_categories(text: str, *, rules: list[dict[str, Any]], default_category: str, max_categories: int) -> list[str]:
    low = text.lower()
    scored: list[tuple[int, str]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name", "")).strip()
        if not name:
            continue
        keywords = rule.get("keywords", [])
        if not isinstance(keywords, list):
            continue
        min_hits = int(rule.get("min_keyword_hits", 1))
        hits = sum(1 for keyword in keywords if isinstance(keyword, str) and keyword and keyword in low)
        if hits >= min_hits:
            scored.append((hits, name))

    scored.sort(reverse=True)
    if not scored:
        return [default_category]

    top = scored[0][0]
    categories = [name for score, name in scored if score >= max(1, top - 1)]
    return categories[: max(1, max_categories)]


def extract_urls(text: str) -> list[str]:
    found = URL_RE.findall(text)
    out: list[str] = []
    seen: set[str] = set()
    for url in found:
        cleaned = url.rstrip(".,;)")
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out[:12]


def read_daily_signals(days: int, research_hints: tuple[str, ...]) -> list[ResearchSignal]:
    if not DAILY_DIR.exists():
        return []
    cutoff_day: str | None = None
    if days > 0:
        cutoff_day = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    signals: list[ResearchSignal] = []
    for path in sorted(DAILY_DIR.glob("*.md")):
        day = path.stem
        if cutoff_day and day < cutoff_day:
            continue
        in_prompt_highlights = False
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.rstrip()
            if line.startswith("## "):
                in_prompt_highlights = line.strip() == "## Prompt Highlights"
                continue
            if not in_prompt_highlights:
                continue
            if not line.startswith("- ["):
                continue
            match = PROMPT_LINE_RE.match(line)
            if not match:
                continue
            text = clean_text(match.group("text"))
            if not is_research_text(text, research_hints):
                continue
            signals.append(
                ResearchSignal(
                    day=day,
                    source=match.group("source").lower(),
                    text=text,
                    urls=extract_urls(text),
                )
            )
    return signals


def read_inbox_signals() -> list[ResearchSignal]:
    """Read X bookmark and research notes from Obsidian inbox as research signals."""
    if not INBOX_DIR.exists():
        return []

    signals: list[ResearchSignal] = []
    for path in sorted(INBOX_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")

        # Extract frontmatter fields
        source = ""
        created = ""
        fm_match = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            src_match = re.search(r"^source:\s*(.+)$", fm, re.MULTILINE)
            if src_match:
                source = src_match.group(1).strip()
            date_match = re.search(r"^created:\s*(.+)$", fm, re.MULTILINE)
            if date_match:
                created = date_match.group(1).strip()

        # Only ingest notes with source: x-bookmarks or type: research
        type_match = re.search(r"^type:\s*(.+)$", text, re.MULTILINE)
        note_type = type_match.group(1).strip() if type_match else ""
        if source != "x-bookmarks" and note_type != "research":
            continue

        # Extract content section
        content_match = re.search(r"## Content\n(.*?)(?=\n## )", text, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            # Fallback: use title
            title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
            content = title_match.group(1).strip() if title_match else ""

        if not content or len(content) < 15:
            continue

        day = created if created else datetime.now(UTC).strftime("%Y-%m-%d")
        sig_source = source if source else "inbox"

        signals.append(
            ResearchSignal(
                day=day,
                source=sig_source,
                text=clean_text(content, limit=280),
                urls=extract_urls(content),
            )
        )

    return signals


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        return {"version": 1, "updated_at": "", "items": {}}
    try:
        payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "updated_at": "", "items": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": "", "items": {}}
    if not isinstance(payload.get("items"), dict):
        payload["items"] = {}
    return payload


def write_registry(payload: dict[str, Any]) -> None:
    DATA_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(REGISTRY_FILE)


# Category → atlas/graph wikilink targets for cross-zone connectivity
CATEGORY_ATLAS_LINKS: dict[str, list[str]] = {
    "agent-orchestration": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-insights]]",
    ],
    "claude-codex-optimization": [
        "[[atlas/research|Atlas: Research]]",
        "[[claude-codex-mac-setup-optimization]]",
        "[[local-first-ai-stack-mac-what-to-run-local]]",
    ],
    "memory-knowledge": [
        "[[atlas/research|Atlas: Research]]",
        "[[memory-lifecycle]]",
        "[[memory-graphs-that-improve-agent-output]]",
    ],
    "security-governance": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-insights]]",
    ],
    "product-market-competitors": [
        "[[atlas/research|Atlas: Research]]",
        "[[why-ai-needs-crypto-and-how-to-sell-to-agents]]",
    ],
    "infra-performance": [
        "[[atlas/research|Atlas: Research]]",
        "[[system-ops-manual]]",
        "[[ollama-postmortem-runtime-vs-health]]",
    ],
    "general-research": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-index]]",
    ],
    "solana-defi-trading": [
        "[[atlas/research|Atlas: Research]]",
        "[[why-ai-needs-crypto-and-how-to-sell-to-agents]]",
    ],
    "web3-blockchain": [
        "[[atlas/research|Atlas: Research]]",
        "[[why-ai-needs-crypto-and-how-to-sell-to-agents]]",
    ],
    "ai-ml-research": [
        "[[atlas/research|Atlas: Research]]",
        "[[memory-graphs-that-improve-agent-output]]",
        "[[research-insights]]",
    ],
    "content-writing": [
        "[[atlas/research|Atlas: Research]]",
        "[[atlas/writing|Atlas: Writing]]",
    ],
    "frontend-design": [
        "[[atlas/research|Atlas: Research]]",
    ],
    "devtools-workflow": [
        "[[atlas/research|Atlas: Research]]",
    ],
    "startup-business": [
        "[[atlas/research|Atlas: Research]]",
        "[[why-ai-needs-crypto-and-how-to-sell-to-agents]]",
    ],
    "marketing-outreach": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-insights]]",
    ],
    "quantitative-finance": [
        "[[atlas/research|Atlas: Research]]",
        "[[why-ai-needs-crypto-and-how-to-sell-to-agents]]",
    ],
    "data-engineering": [
        "[[atlas/research|Atlas: Research]]",
        "[[system-ops-manual]]",
    ],
    "llm-engineering": [
        "[[atlas/research|Atlas: Research]]",
        "[[memory-graphs-that-improve-agent-output]]",
        "[[research-insights]]",
    ],
    "automation-ops": [
        "[[atlas/research|Atlas: Research]]",
        "[[system-ops-manual]]",
    ],
    "prediction-markets": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-insights]]",
    ],
    "privacy-identity": [
        "[[atlas/research|Atlas: Research]]",
        "[[research-insights]]",
    ],
}

SUPER_TOPIC_MAP: dict[str, str] = {
    "frontend-design": "design",
    "content-writing": "design",
    "llm-engineering": "development",
    "data-engineering": "development",
    "devtools-workflow": "development",
    "automation-ops": "development",
    "infra-performance": "development",
    "agent-orchestration": "development",
    "claude-codex-optimization": "development",
    "memory-knowledge": "development",
    "startup-business": "business",
    "marketing-outreach": "business",
    "product-market-competitors": "business",
    "security-governance": "security",
    "privacy-identity": "security",
    "quantitative-finance": "finance",
    "prediction-markets": "finance",
    "solana-defi-trading": "finance",
    "web3-blockchain": "finance",
    "ai-ml-research": "ai-research",
    "general-research": "general",
}


def derive_super_topics(categories: list[str]) -> list[str]:
    topics: list[str] = []
    for category in categories:
        topic = SUPER_TOPIC_MAP.get(category, "general")
        if topic not in topics:
            topics.append(topic)
    return topics or ["general"]


def category_promotion_threshold(categories: list[str], taxonomy: dict[str, Any], default_threshold: float) -> float:
    promotion = taxonomy.get("promotion", {})
    if not isinstance(promotion, dict):
        return default_threshold
    category_min = promotion.get("category_min_score", {})
    if not isinstance(category_min, dict):
        return default_threshold
    threshold = default_threshold
    for cat in categories:
        value = category_min.get(cat)
        if isinstance(value, (int, float)):
            threshold = max(threshold, float(value))
    return threshold


def promotion_score(item: dict[str, Any], now: datetime) -> float:
    text = str(item.get("text", "")).lower()
    count = int(item.get("count", 0))
    categories = item.get("categories", [])
    if not isinstance(categories, list):
        categories = []
    sources = item.get("sources", {})
    if not isinstance(sources, dict):
        sources = {}
    last_seen = str(item.get("last_seen", ""))

    if len(text) < 30:
        return 0.0
    if any(h in text for h in NOISE_HINTS):
        return 0.0

    score = 0.0
    score += min(0.55, 0.12 * count)
    if categories and "general-research" not in categories:
        score += 0.20
    if len(categories) >= 2:
        score += 0.08
    if len(sources) >= 2:
        score += 0.10
    try:
        age_days = (now - datetime.fromisoformat(last_seen)).days
    except (ValueError, TypeError):
        age_days = 365
    if age_days <= 7:
        score += 0.15
    elif age_days <= 30:
        score += 0.08
    elif age_days > 90:
        score -= 0.12
    if "research the web" in text and len(text) < 40:
        score -= 0.10
    return max(0.0, min(1.0, round(score, 4)))


METABOLIC_RATES: dict[str, float] = {
    "identity": 0.1,
    "methodology": 0.1,
    "research": 1.0,
    "decision": 1.0,
    "insight": 1.0,
    "session": 3.0,
    "operational": 3.0,
    "daily": 3.0,
}


def compute_storage_strength(item: dict[str, Any]) -> float:
    """Storage strength S — monotonically increasing with access/review.

    Represents how deeply encoded the memory is. S never decreases;
    it can only grow through repeated access (Bjork & Bjork, 1992).
    """
    count = int(item.get("count", 1))
    stored_s = float(item.get("storage_strength", 0.0))
    floor_s = min(1.0, 0.1 + 0.05 * count)
    return max(stored_s, floor_s)


def compute_retrieval_strength(item: dict[str, Any], edge_count: int = 0, content_type: str = "") -> float:
    """Retrieval strength R — decays over time (FSRS curve) with bi-temporal awareness.

    Low R + high S = 'tip of tongue' — perfect review candidate.
    R decays exponentially but is slowed by edge density (more connections
    = more retrieval pathways = slower forgetting).

    Bi-temporal model:
    - last_seen drives the primary decay (when was this last accessed)
    - ingestion freshness provides a temporary boost for recently learned items
      (new items need time to integrate; boost decays over 14 days)
    - valid_until: if set and in the past, item is expired (R forced to 0.05)
    """
    now = datetime.now(UTC)

    # Check temporal validity — expired facts get near-zero R
    valid_until = item.get("valid_until")
    if valid_until:
        try:
            vu = datetime.fromisoformat(str(valid_until))
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=UTC)
            if vu < now:
                return 0.05
        except (ValueError, TypeError):
            pass

    last_seen = item.get("last_seen", "")
    try:
        ls_dt = datetime.fromisoformat(last_seen)
        if ls_dt.tzinfo is None:
            ls_dt = ls_dt.replace(tzinfo=UTC)
        age_days = (now - ls_dt).days
    except (ValueError, TypeError):
        age_days = 365
    metabolic_rate = METABOLIC_RATES.get(content_type, 1.0)
    age_days = age_days * metabolic_rate
    stability = max(1.0, 10.0 + edge_count * 5.0)
    retrievability = 0.9 ** (age_days / stability)
    count = int(item.get("count", 1))
    access_boost = math.log1p(count) / math.log1p(20)
    base_r = retrievability * (0.6 + 0.4 * access_boost)

    # Ingestion freshness boost — recently ingested items get a temporary lift
    # that decays over 14 days (helps new items surface before they decay)
    ingested_at = item.get("ingested_at", "")
    ingestion_boost = 0.0
    if ingested_at:
        try:
            ingestion_age_days = (now - datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))).days
            if ingestion_age_days < 14:
                ingestion_boost = 0.1 * (1.0 - ingestion_age_days / 14.0)
        except (ValueError, TypeError):
            pass

    return round(min(1.0, base_r + ingestion_boost), 4)


def compute_temporal_relevance(item: dict[str, Any], reference_date: str = "") -> float:
    """Bi-temporal relevance score for a given reference date.

    Measures how temporally relevant an item is to a specific point in time.
    Uses event_time (when it happened) rather than ingestion time.
    Returns 0.0-1.0 where 1.0 = same day, decaying with temporal distance.
    """
    event_time = item.get("event_time", item.get("first_seen", ""))
    if not event_time or not reference_date:
        return 0.5  # neutral when no temporal context

    try:
        event_dt = datetime.fromisoformat(event_time)
        ref_dt = datetime.fromisoformat(reference_date)
        # Normalize to naive for comparison (avoid tz mismatch)
        if event_dt.tzinfo is not None:
            event_dt = event_dt.replace(tzinfo=None)
        if ref_dt.tzinfo is not None:
            ref_dt = ref_dt.replace(tzinfo=None)
        distance_days = abs((event_dt - ref_dt).days)
        # Gaussian-like decay: half-life of 30 days
        return round(math.exp(-(distance_days ** 2) / (2 * 30 ** 2)), 4)
    except (ValueError, TypeError):
        return 0.5


def compute_importance_score(item: dict[str, Any], edge_count: int = 0) -> float:
    """Combined importance = weighted blend of S and R.

    Backward compatible — callers get a single float score.
    Weights: 30% storage strength + 70% retrieval strength, reflecting
    that current accessibility matters more for ranking.
    """
    s = compute_storage_strength(item)
    r = compute_retrieval_strength(item, edge_count)
    return round(0.3 * s + 0.7 * r, 4)


# --- Zone classification ---
ZONE_THRESHOLDS = {
    "active": 0.6,
    "stale": 0.3,
    "fading": 0.1,
}

def classify_zone(r: float) -> str:
    """Classify memory zone based on retrieval strength R.

    Zones: active (R >= 0.6), stale (0.3 <= R < 0.6),
    fading (0.1 <= R < 0.3), archived (R < 0.1).
    """
    if r >= ZONE_THRESHOLDS["active"]:
        return "active"
    elif r >= ZONE_THRESHOLDS["stale"]:
        return "stale"
    elif r >= ZONE_THRESHOLDS["fading"]:
        return "fading"
    return "archived"


def find_articulation_points(items: dict[str, dict[str, Any]]) -> set[str]:
    """Find articulation points (bridges) in the knowledge graph using Tarjan's algorithm.

    These nodes, if removed, would disconnect parts of the graph.
    Used by consolidation to protect structural integrity during pruning.
    """
    adj: dict[str, list[str]] = {iid: [] for iid in items}
    for iid, item in items.items():
        for edge in item.get("edges", []):
            neighbor = edge.get("id", "")
            if neighbor in items:
                adj[iid].append(neighbor)

    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap_set: set[str] = set()
    timer = [0]

    def _dfs(u: str) -> None:
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        children = 0
        for v in adj[u]:
            if v not in disc:
                children += 1
                parent[v] = u
                _dfs(v)
                low[u] = min(low[u], low[v])
                if parent[u] is None and children > 1:
                    ap_set.add(u)
                if parent[u] is not None and low[v] >= disc[u]:
                    ap_set.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for iid in items:
        if iid not in disc:
            parent[iid] = None
            _dfs(iid)

    return ap_set


def classify_edge_type(sim: float) -> str:
    """Heuristic edge type classification based on cosine similarity bands."""
    if sim > 0.85:
        return "extends"
    elif sim > 0.70:
        return "supports"
    else:
        return "relates_to"


def compute_edge_confidence(similarity: float, target_importance: float) -> float:
    """Edge confidence = similarity weighted by target node importance."""
    return round(similarity * (0.6 + 0.4 * target_importance), 4)


def compute_related_signals(
    items: dict[str, dict[str, Any]],
    top_k: int = 5,
    threshold: float = 0.55,
) -> tuple[dict[str, list[tuple[str, float, str]]], dict[str, int]]:
    """Compute top-k related signals per item using cached embeddings.

    Pure in-memory computation — no Ollama calls. Returns tuple of:
    - related: item_id -> [(related_id, similarity, edge_type), ...] sorted by score desc
    - edge_counts: item_id -> number of edges above threshold
    """
    from semantic_dedup import cosine_similarity

    # Build (id, vector) pairs for items that have embeddings
    id_vecs: list[tuple[str, list[float]]] = []
    for item_id, item in items.items():
        vec = item.get("embedding")
        if isinstance(vec, list) and vec:
            id_vecs.append((item_id, vec))

    related: dict[str, list[tuple[str, float, str]]] = {}
    edge_counts: dict[str, int] = {}

    for i, (id_a, vec_a) in enumerate(id_vecs):
        scored: list[tuple[str, float]] = []
        for j, (id_b, vec_b) in enumerate(id_vecs):
            if i == j:
                continue
            sim = cosine_similarity(vec_a, vec_b)
            if sim >= threshold:
                scored.append((id_b, sim))
        edge_counts[id_a] = len(scored)
        # Weight by importance of the related item
        weighted: list[tuple[str, float, float]] = []
        for rel_id, sim in scored:
            imp = compute_importance_score(items.get(rel_id, {}), edge_count=0)
            weighted.append((rel_id, sim, sim * (0.7 + 0.3 * imp)))
        weighted.sort(key=lambda x: x[2], reverse=True)
        related[id_a] = [
            (rid, sim, classify_edge_type(sim))
            for rid, sim, _ in weighted[:top_k]
        ]

    return related, edge_counts


def spreading_activation(
    query_scores: dict[str, float],
    items: dict[str, dict[str, Any]],
    alpha: float = 0.7,
    max_hops: int = 3,
    min_activation: float = 0.01,
) -> dict[str, float]:
    """Collins & Loftus spreading activation over the knowledge graph.

    Propagates activation from anchor nodes through edges, decaying by
    alpha per hop. Uses max (not sum) to prevent runaway accumulation
    at hub nodes.

    Args:
        query_scores: anchor nodes with initial activation (e.g. from importance scores)
        items: registry items dict — each item may have an 'edges' field
        alpha: decay factor per hop (0.7 = 30% loss per hop)
        max_hops: maximum propagation depth
        min_activation: prune activations below this threshold
    Returns:
        node_id -> activation score (max across all paths)
    """
    activation: dict[str, float] = dict(query_scores)

    for _hop in range(max_hops):
        updates: dict[str, float] = {}
        for node_id, act in activation.items():
            if act < min_activation:
                continue
            edges = items.get(node_id, {}).get("edges", [])
            if not isinstance(edges, list):
                continue
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                target = edge.get("id", "")
                if not target or target not in items:
                    continue
                propagated = alpha * act
                if propagated >= min_activation:
                    updates[target] = max(updates.get(target, 0.0), propagated)
        # Apply updates using max semantics
        changed = False
        for node_id, new_act in updates.items():
            if new_act > activation.get(node_id, 0.0):
                activation[node_id] = new_act
                changed = True
        if not changed:
            break

    return {k: round(v, 4) for k, v in activation.items() if v >= min_activation}


# ---------------------------------------------------------------------------
# Mycelium network memory enhancements
# ---------------------------------------------------------------------------


def _detect_hubs(items: dict[str, dict[str, Any]]) -> set[str]:
    """Identify hub nodes: MOC nodes, items with 'hub' category, or high edge count."""
    edge_counts = []
    for item in items.values():
        edges = item.get("edges", [])
        edge_counts.append(len(edges) if isinstance(edges, list) else 0)
    median_edges = sorted(edge_counts)[len(edge_counts) // 2] if edge_counts else 0

    hubs: set[str] = set()
    for item_id, item in items.items():
        if item_id.startswith("moc-"):
            hubs.add(item_id)
            continue
        cats = item.get("categories", [])
        if isinstance(cats, list) and "hub" in cats:
            hubs.add(item_id)
            continue
        edges = item.get("edges", [])
        ec = len(edges) if isinstance(edges, list) else 0
        if median_edges > 0 and ec > median_edges * 2:
            hubs.add(item_id)
    return hubs


def reinforce_access_paths(
    item_id: str,
    items: dict[str, dict[str, Any]],
    max_depth: int = 3,
) -> dict[str, Any]:
    """Mycelium-inspired path reinforcement: boost edge confidence along access paths to hubs.

    When a node is accessed, walk its edges up to *max_depth* hops toward hub
    nodes and increase edge confidence by 0.05 (capped at 1.0) for each edge
    traversed, mimicking how mycelium networks reinforce nutrient transport
    pathways that prove useful.

    Returns:
        {"reinforced_count": int, "paths": list[list[str]]}
    """
    hubs = _detect_hubs(items)
    reinforced_count = 0
    paths: list[list[str]] = []

    # BFS from item_id, tracking paths
    queue: list[tuple[str, list[str]]] = [(item_id, [item_id])]
    visited: set[str] = {item_id}

    while queue:
        current, path = queue.pop(0)
        if len(path) - 1 >= max_depth:
            continue
        edges = items.get(current, {}).get("edges", [])
        if not isinstance(edges, list):
            continue
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            target = edge.get("id", "")
            if not target or target not in items or target in visited:
                continue
            new_path = path + [target]
            visited.add(target)

            # Boost this edge's confidence
            old_conf = float(edge.get("confidence", edge.get("similarity", 0.5)))
            edge["confidence"] = round(min(1.0, old_conf + 0.05), 4)
            reinforced_count += 1

            if target in hubs:
                paths.append(new_path)
            else:
                queue.append((target, new_path))

    return {"reinforced_count": reinforced_count, "paths": paths}


def heal_broken_paths(
    pruned_ids: set[str],
    items: dict[str, dict[str, Any]],
    hub_ids: set[str],
) -> dict[str, Any]:
    """Mycelium-inspired self-healing: reconnect orphaned neighbors after pruning.

    When nodes are removed, their neighbors may lose connectivity to hub nodes.
    This function detects such disconnections and creates new ``relates_to``
    edges to the nearest hub-reachable node (by embedding similarity), similar
    to how fungal networks reroute around damaged sections.

    Returns:
        {"healed_count": int, "new_edges": list[dict]}
    """
    from semantic_dedup import cosine_similarity

    active_items = {k: v for k, v in items.items() if k not in pruned_ids}
    healed_count = 0
    new_edges: list[dict[str, Any]] = []

    # Collect neighbors of pruned nodes
    orphan_candidates: set[str] = set()
    for pid in pruned_ids:
        edges = items.get(pid, {}).get("edges", [])
        if not isinstance(edges, list):
            continue
        for edge in edges:
            if isinstance(edge, dict):
                neighbor = edge.get("id", "")
                if neighbor and neighbor in active_items and neighbor not in hub_ids:
                    orphan_candidates.add(neighbor)

    def _can_reach_hub(start: str) -> bool:
        """BFS to check if start can reach any hub through active items."""
        visited: set[str] = {start}
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in hub_ids:
                return True
            edges = active_items.get(node, {}).get("edges", [])
            if not isinstance(edges, list):
                continue
            for edge in edges:
                if isinstance(edge, dict):
                    target = edge.get("id", "")
                    if target and target in active_items and target not in visited:
                        visited.add(target)
                        queue.append(target)
        return False

    # Find hub-connected nodes for similarity matching
    hub_connected: list[str] = []
    for nid in active_items:
        if nid in hub_ids or _can_reach_hub(nid):
            hub_connected.append(nid)

    for orphan in orphan_candidates:
        if _can_reach_hub(orphan):
            continue
        # Find nearest hub-connected node by embedding similarity
        orphan_emb = active_items.get(orphan, {}).get("embedding")
        if not isinstance(orphan_emb, list) or not orphan_emb:
            continue
        best_id, best_sim = None, -1.0
        for hc_id in hub_connected:
            hc_emb = active_items.get(hc_id, {}).get("embedding")
            if not isinstance(hc_emb, list) or not hc_emb:
                continue
            sim = cosine_similarity(orphan_emb, hc_emb)
            if sim > best_sim:
                best_sim = sim
                best_id = hc_id
        if best_id:
            new_edge = {"id": best_id, "similarity": round(best_sim, 4), "edge_type": "relates_to"}
            edges = active_items.get(orphan, {}).get("edges", [])
            if isinstance(edges, list):
                edges.append(new_edge)
            new_edges.append({"from": orphan, "to": best_id, "similarity": round(best_sim, 4)})
            healed_count += 1

    return {"healed_count": healed_count, "new_edges": new_edges}


def compute_flow_score(
    item_id: str,
    items: dict[str, dict[str, Any]],
    sample_size: int = 50,
) -> float:
    """Simplified betweenness centrality proxy via sampled shortest paths.

    Samples random node pairs and counts how often *item_id* lies on the BFS
    shortest path between them, analogous to measuring nutrient flow through a
    mycelium junction.

    Returns:
        flow_score = appearances / sample_size (float in [0, 1])
    """
    node_ids = [nid for nid in items if nid != item_id]
    if len(node_ids) < 2:
        return 0.0

    pairs = min(sample_size, len(node_ids) * (len(node_ids) - 1) // 2)
    sampled: list[tuple[str, str]] = []
    attempts = 0
    seen: set[tuple[str, str]] = set()
    while len(sampled) < pairs and attempts < pairs * 3:
        a = random.choice(node_ids)
        b = random.choice(node_ids)
        if a != b and (a, b) not in seen and (b, a) not in seen:
            sampled.append((a, b))
            seen.add((a, b))
        attempts += 1

    def _bfs_path(start: str, end: str) -> list[str] | None:
        """BFS shortest path between two nodes."""
        if start == end:
            return [start]
        visited: set[str] = {start}
        queue: list[tuple[str, list[str]]] = [(start, [start])]
        while queue:
            node, path = queue.pop(0)
            edges = items.get(node, {}).get("edges", [])
            if not isinstance(edges, list):
                continue
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                target = edge.get("id", "")
                if target and target not in visited and target in items:
                    new_path = path + [target]
                    if target == end:
                        return new_path
                    visited.add(target)
                    queue.append((target, new_path))
        return None

    appearances = 0
    for src, dst in sampled:
        path = _bfs_path(src, dst)
        if path and item_id in path[1:-1]:  # exclude endpoints
            appearances += 1

    return round(appearances / max(len(sampled), 1), 4)


CONTRADICTION_MARKERS = (
    "not recommended",
    "deprecated",
    "replaced by",
    "incorrect",
    "outdated",
    "no longer",
    "instead of",
    "do not use",
    "superseded",
    "obsolete",
    "wrong",
    "flawed",
    "disproven",
)


def prediction_error_gate(
    new_text: str,
    new_embedding: list[float],
    items: dict[str, dict[str, Any]],
    threshold_confirm: float = 0.85,
    threshold_contradict: float = 0.70,
) -> tuple[str, str | None, float]:
    """Classify incoming signal as confirming, contradicting, or novel.

    Prediction error gating: the brain allocates more encoding resources
    to surprising (high prediction error) signals. Confirming signals
    reinforce existing memories; contradicting signals trigger updating.

    Returns:
        (classification, matched_item_id, similarity_score)
        classification: 'confirming' | 'contradicting' | 'novel'
    """
    from semantic_dedup import cosine_similarity

    if not new_embedding:
        return ("novel", None, 0.0)

    scored: list[tuple[str, float]] = []
    for item_id, item in items.items():
        vec = item.get("embedding")
        if not isinstance(vec, list) or not vec:
            continue
        sim = cosine_similarity(new_embedding, vec)
        if sim >= 0.55:
            scored.append((item_id, sim))

    if not scored:
        return ("novel", None, 0.0)

    scored.sort(key=lambda x: x[1], reverse=True)
    best_id, best_sim = scored[0]

    if best_sim >= threshold_confirm:
        return ("confirming", best_id, best_sim)

    if best_sim >= threshold_contradict:
        text_lower = new_text.lower()
        for marker in CONTRADICTION_MARKERS:
            if marker in text_lower:
                return ("contradicting", best_id, best_sim)

    if best_sim < 0.55:
        return ("novel", None, 0.0)

    # Between 0.55 and 0.85, no contradiction markers — treat as novel
    return ("novel", None, best_sim)


def render_node(
    item_id: str,
    item: dict[str, Any],
    related_signals: list[tuple[str, float, str]] | None = None,
    importance: float | None = None,
) -> str:
    categories = item.get("categories", [])
    if not isinstance(categories, list):
        categories = []
    days = item.get("days", [])
    if not isinstance(days, list):
        days = []
    sources = item.get("sources", {})
    if not isinstance(sources, dict):
        sources = {}
    evidence_urls = item.get("evidence_urls", [])
    if not isinstance(evidence_urls, list):
        evidence_urls = []
    observations = item.get("observations", [])
    if not isinstance(observations, list):
        observations = []

    source_lines = [f"- `{name}`: {count}" for name, count in sorted(sources.items(), key=lambda x: (-int(x[1]), x[0]))]
    day_lines = [f"- `{day}`" for day in sorted(days, reverse=True)[:20]]
    evidence_lines = [f"- {url}" for url in evidence_urls[:20]]
    obs_lines = []
    for obs in observations[-20:]:
        if not isinstance(obs, dict):
            continue
        day = str(obs.get("day", "-"))
        source = str(obs.get("source", "-"))
        obs_lines.append(f"- `{day}` via `{source}`")

    # Build Related Signals section from semantic similarity with typed edges
    related_lines: list[str] = []
    if related_signals:
        for rel_entry in related_signals:
            if len(rel_entry) == 3:
                rel_id, score, edge_type = rel_entry
            else:
                rel_id, score = rel_entry[0], rel_entry[1]
                edge_type = classify_edge_type(score)
            related_lines.append(f"- [[{rel_id}]] ({edge_type}, {score:.2f})")
    if not related_lines:
        related_lines.append("- No related signals found")

    # Build Atlas links from categories
    atlas_lines: list[str] = []
    seen_links: set[str] = set()
    for cat in (categories if categories else ["general-research"]):
        for link in CATEGORY_ATLAS_LINKS.get(cat, CATEGORY_ATLAS_LINKS["general-research"]):
            if link not in seen_links:
                seen_links.add(link)
                atlas_lines.append(f"- {link}")
    if not atlas_lines:
        atlas_lines.append("- [[atlas/research|Atlas: Research]]")

    tag_list = categories if categories else ["general-research"]
    super_topics = derive_super_topics([str(c) for c in tag_list])
    for topic in super_topics:
        topic_tag = f"topic-{topic}"
        if topic_tag not in tag_list:
            tag_list.append(topic_tag)
    tags_str = ", ".join(tag_list)

    lines = [
        "---",
        f"id: {item_id}",
        "description: Auto-managed research signal extracted from Claude/Codex sessions.",
        f"tags: [{tags_str}]",
        "---",
        "",
        f"# Research Signal: {item_id}",
        "",
        "## Prompt",
        f"- {item.get('text', '')}",
        "",
        "## Categories",
    ]
    if categories:
        lines.extend(f"- `{cat}`" for cat in categories)
    else:
        lines.append("- `general-research`")

    lines.extend(
        [
            "",
            "## Related Signals",
            *related_lines,
            "",
            "## Topic Hubs",
            *[f"- [[topic-{topic}]]" for topic in super_topics],
            "",
            "## Atlas",
            *atlas_lines,
            "",
            "## Stats",
            f"- importance: {importance:.4f}" if importance is not None else "- importance: -",
            f"- count: {item.get('count', 0)}",
            f"- first_seen: {item.get('first_seen', '-')}",
            f"- last_seen: {item.get('last_seen', '-')}",
            "",
            "## Sources",
            *(source_lines if source_lines else ["- None"]),
            "",
            "## Seen On Days",
            *(day_lines if day_lines else ["- None"]),
            "",
            "## Evidence URLs",
            *(evidence_lines if evidence_lines else ["- None"]),
            "",
            "## Observations",
            *(obs_lines if obs_lines else ["- None"]),
            "",
            "## Notes",
            "- This node is managed by `sync_research_knowledge.py`.",
            "- Duplicate prompts are merged by normalized text fingerprint.",
            "",
        ]
    )
    return "\n".join(lines)


def render_index(items: dict[str, dict[str, Any]], generated_at: str, importance_scores: dict[str, float] | None = None) -> str:
    by_category: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    by_topic: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for item_id, item in items.items():
        categories = item.get("categories", [])
        if not isinstance(categories, list) or not categories:
            categories = ["general-research"]
        topics = derive_super_topics([str(cat) for cat in categories])
        for topic in topics:
            by_topic.setdefault(topic, []).append((item_id, item))
        for cat in categories:
            by_category.setdefault(str(cat), []).append((item_id, item))

    lines = [
        "---",
        "id: research-index",
        "description: Auto-managed index of research signals extracted from Claude/Codex sessions.",
        "---",
        "",
        "# Research Knowledge Index",
        "",
        f"- generated_at: {generated_at}",
        f"- unique_research_signals: {len(items)}",
        "",
        "## Super Topics",
    ]

    if not by_topic:
        lines.append("- No research signals captured yet.")
        lines.append("")
        return "\n".join(lines)

    scores = importance_scores or {}
    for topic in sorted(by_topic):
        entries = sorted(
            by_topic[topic],
            key=lambda kv: scores.get(kv[0], 0.0),
            reverse=True,
        )
        lines.extend(["", f"### {topic}"])
        for item_id, item in entries[:40]:
            score = scores.get(item_id, 0.0)
            lines.append(f"- [[{item_id}]] (imp:{score:.2f}, {item.get('count', 0)}x) - {item.get('text', '')}")

    lines.extend(["", "## Categories"])
    for category in sorted(by_category):
        entries = sorted(
            by_category[category],
            key=lambda kv: scores.get(kv[0], 0.0),
            reverse=True,
        )
        lines.extend(["", f"### {category}"])
        for item_id, item in entries[:60]:
            score = scores.get(item_id, 0.0)
            lines.append(f"- [[{item_id}]] (imp:{score:.2f}, {item.get('count', 0)}x) - {item.get('text', '')}")
    lines.append("")
    return "\n".join(lines)


def render_category_moc(
    category: str,
    member_items: list[tuple[str, dict[str, Any]]],
    importance_scores: dict[str, float] | None = None,
) -> str:
    """Render a category MOC (Map of Content) hub file.

    Creates a hub node that wikilinks to all member signals in the category,
    producing a visual spoke cluster in Obsidian's graph view.
    """
    scores = importance_scores or {}
    sorted_members = sorted(
        member_items,
        key=lambda kv: scores.get(kv[0], 0.0),
        reverse=True,
    )

    # Atlas cross-links for this category
    atlas_links = CATEGORY_ATLAS_LINKS.get(category, CATEGORY_ATLAS_LINKS["general-research"])

    display_name = category.replace("-", " ").title()

    lines = [
        "---",
        f"id: category-{category}",
        f"description: Map of Content hub for {display_name} research signals.",
        f"tags: [{category}, moc]",
        "---",
        "",
        f"# {display_name}",
        "",
        f"Category hub — {len(sorted_members)} research signals.",
        "",
        "## Atlas",
    ]
    for link in atlas_links:
        lines.append(f"- {link}")

    lines.extend(["", "## Signals", ""])
    for item_id, item in sorted_members:
        score = scores.get(item_id, 0.0)
        text = item.get("text", "")[:120]
        lines.append(f"- [[{item_id}]] (imp:{score:.2f}) — {text}")

    lines.extend(["", ""])
    return "\n".join(lines)


def render_topic_moc(
    topic: str,
    member_items: list[tuple[str, dict[str, Any]]],
    importance_scores: dict[str, float] | None = None,
) -> str:
    scores = importance_scores or {}
    sorted_members = sorted(
        member_items,
        key=lambda kv: scores.get(kv[0], 0.0),
        reverse=True,
    )
    display_name = topic.replace("-", " ").title()
    lines = [
        "---",
        f"id: topic-{topic}",
        f"description: Top-level research topic hub for {display_name}.",
        f"tags: [topic-{topic}, moc, research-topic]",
        "---",
        "",
        f"# Topic: {display_name}",
        "",
        f"Super-topic hub — {len(sorted_members)} research signals.",
        "",
        "## Signals",
        "",
    ]
    for item_id, item in sorted_members[:200]:
        score = scores.get(item_id, 0.0)
        text = item.get("text", "")[:120]
        lines.append(f"- [[{item_id}]] (imp:{score:.2f}) — {text}")
    lines.extend(["", ""])
    return "\n".join(lines)


def render_quarantine_report(
    quarantined: list[tuple[str, dict[str, Any], float, float]],
    generated_at: str,
    min_count: int,
) -> str:
    lines = [
        "---",
        "id: research-quarantine",
        "description: Research signals below promotion thresholds; tracked for later promotion.",
        "tags: [research, quarantine, curation]",
        "---",
        "",
        "# Research Quarantine Candidates",
        "",
        f"- generated_at: {generated_at}",
        f"- candidates: {len(quarantined)}",
        f"- min_count: {min_count}",
        "",
        "## Signals",
    ]
    if not quarantined:
        lines.append("- None")
        lines.append("")
        return "\n".join(lines)
    for item_id, item, score, threshold in sorted(quarantined, key=lambda x: x[2], reverse=True)[:300]:
        lines.append(
            f"- [[{item_id}]] score={score:.2f} threshold={threshold:.2f} count={int(item.get('count', 0))} "
            f"last_seen={item.get('last_seen', '-')}"
        )
    lines.append("")
    return "\n".join(lines)


def merge_urls(existing: list[str], incoming: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for url in [*existing, *incoming]:
        if not isinstance(url, str):
            continue
        cleaned = url.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def sync(days: int, apply_changes: bool, no_semantic: bool = False, reclassify: bool = False) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    research_hints = tuple(
        str(x).lower()
        for x in taxonomy.get("research_hints", [])
        if isinstance(x, str) and x.strip()
    )
    if not research_hints:
        research_hints = DEFAULT_RESEARCH_HINTS

    classification = taxonomy.get("classification", {}) if isinstance(taxonomy.get("classification"), dict) else {}
    default_category = str(classification.get("default_category", "general-research"))
    max_categories = int(classification.get("max_categories", 3))
    category_rules = classification.get("category_rules", DEFAULT_CATEGORY_RULES)
    if not isinstance(category_rules, list):
        category_rules = DEFAULT_CATEGORY_RULES
    promotion_cfg = taxonomy.get("promotion", {}) if isinstance(taxonomy.get("promotion"), dict) else {}
    promotion_min_score = float(promotion_cfg.get("default_min_score", 0.80))
    promotion_min_count = int(promotion_cfg.get("default_min_count", 2))

    registry = load_registry()
    items = registry.setdefault("items", {})
    if not isinstance(items, dict):
        items = {}
        registry["items"] = items

    # Load blocked IDs — permanently excluded noise signals
    blocked_ids: set[str] = set(registry.get("blocked_ids", []))

    # Reclassify all existing items with current taxonomy rules
    reclassified = 0
    if reclassify:
        for item_id, entry in items.items():
            if item_id in blocked_ids:
                continue
            if not isinstance(entry, dict):
                continue
            text = entry.get("text", "")
            if not text:
                continue
            new_cats = classify_categories(
                text,
                rules=category_rules,
                default_category=default_category,
                max_categories=max_categories,
            )
            entry["categories"] = new_cats
            reclassified += 1

    # Lazy-import semantic dedup (only when needed)
    _semantic_dedup = None
    if not no_semantic:
        try:
            from semantic_dedup import compute_embedding, find_semantic_duplicates

            _semantic_dedup = True
        except ImportError:
            _semantic_dedup = None

    signals = read_daily_signals(days=days, research_hints=research_hints)
    # Also ingest research notes from Obsidian inbox (x-bookmarks, etc.)
    signals.extend(read_inbox_signals())
    updated = 0
    created = 0
    semantic_merged = 0
    new_item_ids: set[str] = set()
    for signal in signals:
        normalized = normalize_text(signal.text)
        if not normalized:
            continue
        item_id = text_id(normalized)

        # Skip permanently blocked noise signals
        if item_id in blocked_ids:
            continue

        # Fast path: exact SHA-1 match
        entry = items.get(item_id)
        is_new = not isinstance(entry, dict)

        if is_new and _semantic_dedup:
            # Semantic dedup: check if a similar signal already exists
            matches = find_semantic_duplicates(
                normalized, items, threshold=0.85, top_k=1
            )
            if matches:
                matched_id, matched_score = matches[0]
                # Redirect merge to the existing semantically similar item
                item_id = matched_id
                entry = items[item_id]
                is_new = False
                semantic_merged += 1

        if is_new:
            # Compute embedding early for prediction error gating
            new_vec: list[float] = []
            if _semantic_dedup:
                new_vec = compute_embedding(normalized)

            # Prediction error gate: classify as confirming, contradicting, or novel
            pe_class, pe_match_id, pe_sim = "novel", None, 0.0
            if new_vec and items:
                pe_class, pe_match_id, pe_sim = prediction_error_gate(
                    normalized, new_vec, items,
                )

            if pe_class == "confirming" and pe_match_id and pe_match_id in items:
                # Confirming: boost matched node's storage strength
                matched = items[pe_match_id]
                current_s = float(matched.get("storage_strength", 0.0))
                matched["storage_strength"] = round(min(1.0, current_s + 0.2), 4)
                # Redirect merge to existing item
                item_id = pe_match_id
                entry = matched
                is_new = False
                semantic_merged += 1
            elif pe_class == "contradicting" and pe_match_id and pe_match_id in items:
                # Contradicting: create new item, add supersedes edge, decay matched R
                entry = {
                    "text": signal.text,
                    "normalized": normalized,
                    "count": 0,
                    "first_seen": signal.day,
                    "last_seen": signal.day,
                    "days": [],
                    "sources": {},
                    "categories": classify_categories(
                        signal.text,
                        rules=category_rules,
                        default_category=default_category,
                        max_categories=max_categories,
                    ),
                    "evidence_urls": signal.urls,
                    "observations": [],
                    "storage_strength": 0.8,
                    "supersedes": pe_match_id,
                }
                if new_vec:
                    entry["embedding"] = new_vec
                # Decay matched item's retrieval strength proxy (halve last_seen age effect)
                matched = items[pe_match_id]
                matched_ls = matched.get("last_seen", "")
                if matched_ls:
                    try:
                        matched_age = (datetime.now(UTC) - datetime.fromisoformat(matched_ls)).days
                        # Simulate faster decay by backdating last_seen
                        matched["last_seen"] = (
                            datetime.now(UTC) - timedelta(days=int(matched_age * 2))
                        ).strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                new_item_ids.add(item_id)
                created += 1
            else:
                # Novel: standard new item creation
                now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                entry = {
                    "text": signal.text,
                    "normalized": normalized,
                    "count": 0,
                    "first_seen": signal.day,
                    "last_seen": signal.day,
                    # Bi-temporal fields (Graphiti pattern)
                    "event_time": signal.day,      # when the fact/event occurred
                    "ingested_at": now_iso,         # when we learned about it
                    "valid_from": signal.day,       # temporal validity start
                    "valid_until": None,            # None = still valid
                    "days": [],
                    "sources": {},
                    "categories": classify_categories(
                        signal.text,
                        rules=category_rules,
                        default_category=default_category,
                        max_categories=max_categories,
                    ),
                    "evidence_urls": signal.urls,
                    "observations": [],
                    "storage_strength": 0.8 if pe_class == "novel" else 0.0,
                }
                if new_vec:
                    entry["embedding"] = new_vec
                new_item_ids.add(item_id)
                created += 1

        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_seen"] = signal.day
        if signal.day < str(entry.get("first_seen", signal.day)):
            entry["first_seen"] = signal.day

        days_list = entry.get("days", [])
        if not isinstance(days_list, list):
            days_list = []
        if signal.day not in days_list:
            days_list.append(signal.day)
        entry["days"] = sorted(days_list)

        sources = entry.get("sources", {})
        if not isinstance(sources, dict):
            sources = {}
        sources[signal.source] = int(sources.get(signal.source, 0)) + 1
        entry["sources"] = sources

        categories = classify_categories(
            signal.text,
            rules=category_rules,
            default_category=default_category,
            max_categories=max_categories,
        )
        existing_categories = entry.get("categories", [])
        if not isinstance(existing_categories, list):
            existing_categories = []
        merged_categories = sorted(set(str(cat) for cat in [*existing_categories, *categories]))
        entry["categories"] = merged_categories[:max(1, max_categories)]

        existing_urls = entry.get("evidence_urls", [])
        if not isinstance(existing_urls, list):
            existing_urls = []
        entry["evidence_urls"] = merge_urls(existing_urls, signal.urls, limit=20)

        observations = entry.get("observations", [])
        if not isinstance(observations, list):
            observations = []
        obs = {"day": signal.day, "source": signal.source}
        if obs not in observations:
            observations.append(obs)
        entry["observations"] = observations[-100:]

        # Bi-temporal: update event_time if signal is older (backdated evidence)
        if signal.day < str(entry.get("event_time", signal.day)):
            entry["event_time"] = signal.day
        # Track latest ingestion
        if "ingested_at" not in entry:
            entry["ingested_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        items[item_id] = entry
        updated += 1

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    registry["updated_at"] = generated_at

    # Compute related signals from cached embeddings (no external calls)
    related_map: dict[str, list[tuple[str, float]]] = {}
    edge_counts: dict[str, int] = {}
    if not no_semantic:
        try:
            related_map, edge_counts = compute_related_signals(items, top_k=5, threshold=0.55)
        except Exception:
            pass

    # Persist edges to registry items
    for item_id, edges in related_map.items():
        if item_id in items:
            items[item_id]["edges"] = [
                {
                    "id": rel_id,
                    "similarity": round(sim, 4),
                    "type": etype,
                    "confidence": compute_edge_confidence(
                        sim,
                        compute_importance_score(items.get(rel_id, {}), edge_count=edge_counts.get(rel_id, 0)),
                    ),
                }
                for rel_id, sim, etype in edges
            ]

    # Evolution: mark related nodes when NEW signals have high similarity to existing nodes
    for new_id in new_item_ids:
        for rel_id, sim, _ in related_map.get(new_id, []):
            if sim > 0.70 and rel_id in items and rel_id not in new_item_ids:
                items[rel_id]["last_evolved"] = generated_at
                # Synaptic tagging: retroactive S boost to neighbors of new signals
                current_s = float(items[rel_id].get("storage_strength", 0.0))
                new_s_boost = 0.1 * compute_storage_strength(items.get(new_id, {}))
                items[rel_id]["storage_strength"] = round(min(1.0, current_s + new_s_boost), 4)

    # Spreading activation: boost edge confidence for activated neighbors
    if new_item_ids and related_map:
        anchor_scores = {
            iid: compute_importance_score(items[iid], edge_count=edge_counts.get(iid, 0))
            for iid in new_item_ids if iid in items
        }
        activated = spreading_activation(
            anchor_scores, items, alpha=0.7, max_hops=3,
        )
        # Boost edge confidence for activated but not directly new items
        for item_id in activated:
            if item_id in items and item_id not in new_item_ids:
                edges = items[item_id].get("edges", [])
                if isinstance(edges, list):
                    for edge in edges:
                        if isinstance(edge, dict) and edge.get("id") in activated:
                            edge["confidence"] = round(
                                min(1.0, edge.get("confidence", 0.5) * 1.1), 4
                            )

    # Compute FSRS-inspired importance scores for all items
    importance_scores: dict[str, float] = {}
    for item_id, entry in items.items():
        importance_scores[item_id] = compute_importance_score(entry, edge_count=edge_counts.get(item_id, 0))

    now = datetime.now(UTC)
    promoted_ids: set[str] = set()
    scored_items: list[tuple[str, float, float]] = []
    quarantined_items: list[tuple[str, dict[str, Any], float, float]] = []
    for item_id, entry in items.items():
        categories = entry.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        threshold = category_promotion_threshold(categories, taxonomy, promotion_min_score)
        score = promotion_score(entry, now=now)
        scored_items.append((item_id, score, threshold))
        if int(entry.get("count", 0)) >= promotion_min_count and score >= threshold:
            promoted_ids.add(item_id)
        else:
            quarantined_items.append((item_id, entry, score, threshold))

    fallback_promotions = 0
    if not promoted_ids and scored_items:
        fallback_floor = max(0.60, promotion_min_score - 0.20)
        candidates = sorted(scored_items, key=lambda x: x[1], reverse=True)
        for item_id, score, _threshold in candidates:
            if score < fallback_floor:
                continue
            promoted_ids.add(item_id)
            fallback_promotions += 1
            if fallback_promotions >= 120:
                break
        quarantined_items = [
            (item_id, entry, score, threshold)
            for item_id, entry, score, threshold in quarantined_items
            if item_id not in promoted_ids
        ]

    if apply_changes:
        write_registry(registry)
        GRAPH_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        live_ids = set(promoted_ids)

        for item_id in sorted(promoted_ids):
            entry = items[item_id]
            node_path = GRAPH_RESEARCH_DIR / f"{item_id}.md"
            node_path.write_text(
                render_node(
                    item_id, entry,
                    related_signals=related_map.get(item_id),
                    importance=importance_scores.get(item_id),
                ),
                encoding="utf-8",
            )

        for stale in GRAPH_RESEARCH_DIR.glob("research-*.md"):
            if stale.stem not in live_ids:
                stale.unlink(missing_ok=True)

        promoted_items = {item_id: items[item_id] for item_id in promoted_ids}
        (GRAPH_RESEARCH_DIR / "index.md").write_text(
            render_index(promoted_items, generated_at, importance_scores=importance_scores),
            encoding="utf-8",
        )
        QUARANTINE_FILE.write_text(
            render_quarantine_report(quarantined_items, generated_at, promotion_min_count),
            encoding="utf-8",
        )

        # Write category MOC hub files
        by_category: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        by_topic: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for item_id in sorted(promoted_ids):
            entry = items[item_id]
            cats = entry.get("categories", [])
            if not isinstance(cats, list) or not cats:
                cats = ["general-research"]
            topics = derive_super_topics([str(cat) for cat in cats])
            for topic in topics:
                by_topic.setdefault(topic, []).append((item_id, entry))
            for cat in cats:
                by_category.setdefault(str(cat), []).append((item_id, entry))

        live_moc_stems: set[str] = set()
        for category, members in by_category.items():
            moc_stem = f"category-{category}"
            live_moc_stems.add(moc_stem)
            moc_path = GRAPH_RESEARCH_DIR / f"{moc_stem}.md"
            moc_path.write_text(
                render_category_moc(category, members, importance_scores=importance_scores),
                encoding="utf-8",
            )

        # Clean up stale MOC files for categories that no longer exist
        for stale_moc in GRAPH_RESEARCH_DIR.glob("category-*.md"):
            if stale_moc.stem not in live_moc_stems:
                stale_moc.unlink(missing_ok=True)

        # Write super-topic MOC hub files
        live_topic_stems: set[str] = set()
        for topic, members in by_topic.items():
            topic_stem = f"topic-{topic}"
            live_topic_stems.add(topic_stem)
            topic_path = GRAPH_RESEARCH_DIR / f"{topic_stem}.md"
            topic_path.write_text(
                render_topic_moc(topic, members, importance_scores=importance_scores),
                encoding="utf-8",
            )

        for stale_topic in GRAPH_RESEARCH_DIR.glob("topic-*.md"):
            if stale_topic.stem not in live_topic_stems:
                stale_topic.unlink(missing_ok=True)

    return {
        "ok": True,
        "days_window": days,
        "signals_scanned": len(signals),
        "items_total": len(items),
        "items_promoted": len(promoted_ids),
        "items_quarantined": len(quarantined_items),
        "items_created": created,
        "items_updated": updated,
        "fallback_promotions": fallback_promotions,
        "reclassified": reclassified,
        "category_mocs": len(by_category) if apply_changes else 0,
        "topic_mocs": len(by_topic) if apply_changes else 0,
        "semantic_merged": semantic_merged,
        "semantic_dedup": "enabled" if _semantic_dedup else "disabled",
        "registry_path": str(REGISTRY_FILE),
        "research_graph_dir": str(GRAPH_RESEARCH_DIR),
        "taxonomy_path": str(TAXONOMY_FILE),
        "mode": "apply" if apply_changes else "dry-run",
    }


def backfill_embeddings() -> dict[str, Any]:
    """Compute and cache embeddings for registry items that lack them."""
    from semantic_dedup import compute_embedding, compute_embeddings_batch

    registry = load_registry()
    items = registry.get("items", {})
    if not isinstance(items, dict):
        return {"ok": False, "error": "Invalid registry"}

    missing = [(item_id, item) for item_id, item in items.items() if not item.get("embedding")]
    if not missing:
        return {"ok": True, "backfilled": 0, "total": len(items), "already_had": len(items)}

    # Batch compute embeddings
    texts = [item.get("normalized", "") for _, item in missing]
    vectors = compute_embeddings_batch(texts, batch_size=32)

    filled = 0
    for (item_id, item), vec in zip(missing, vectors):
        if vec:
            item["embedding"] = vec
            filled += 1

    registry["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_registry(registry)

    return {
        "ok": True,
        "backfilled": filled,
        "failed": len(missing) - filled,
        "total": len(items),
        "already_had": len(items) - len(missing),
    }


def _self_test() -> None:
    taxonomy = load_taxonomy()
    hints = tuple(str(x) for x in taxonomy.get("research_hints", []) if isinstance(x, str))
    assert is_research_text("please do deep research on this", hints)
    assert not is_research_text("fix card spacing", hints)
    norm = normalize_text("Deep Research on Claude + Codex!")
    rid = text_id(norm)
    assert rid.startswith("research-")
    cats = classify_categories(
        "optimize claude codex context and memory orchestration",
        rules=taxonomy.get("classification", {}).get("category_rules", DEFAULT_CATEGORY_RULES),
        default_category="general-research",
        max_categories=3,
    )
    assert "memory-knowledge" in cats or "claude-codex-optimization" in cats
    urls = extract_urls("see https://example.com/a and https://example.com/a")
    assert len(urls) == 1

    # Dual-strength model backward compatibility
    test_item: dict[str, Any] = {"count": 5, "last_seen": datetime.now(UTC).isoformat()}
    score = compute_importance_score(test_item, edge_count=2)
    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
    s = compute_storage_strength(test_item)
    r = compute_retrieval_strength(test_item, edge_count=2)
    assert s > 0.0, f"Storage strength should be positive: {s}"
    assert r > 0.0, f"Retrieval strength should be positive: {r}"

    # Spreading activation
    mock_items: dict[str, dict[str, Any]] = {
        "a": {"edges": [{"id": "b", "similarity": 0.8}], "count": 1, "last_seen": datetime.now(UTC).isoformat()},
        "b": {"edges": [{"id": "c", "similarity": 0.7}], "count": 1, "last_seen": datetime.now(UTC).isoformat()},
        "c": {"edges": [], "count": 1, "last_seen": datetime.now(UTC).isoformat()},
    }
    act = spreading_activation({"a": 1.0}, mock_items, alpha=0.7, max_hops=3)
    assert "a" in act and act["a"] == 1.0
    assert "b" in act and abs(act["b"] - 0.7) < 0.01, f"Expected b~0.7, got {act.get('b')}"
    assert "c" in act and abs(act["c"] - 0.49) < 0.01, f"Expected c~0.49, got {act.get('c')}"

    # Prediction error gate (without embeddings — returns novel)
    cls, mid, sim = prediction_error_gate("test", [], {})
    assert cls == "novel" and mid is None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync research prompts into auto-managed knowledge graph nodes.")
    parser.add_argument("--days", type=int, default=30, help="How many recent days of daily memory captures to scan. Use 0 for all.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    parser.add_argument("--no-semantic", action="store_true", help="Skip embedding-based semantic dedup (faster, text-only dedup).")
    parser.add_argument("--backfill-embeddings", action="store_true", help="Compute embeddings for all registry items that lack them, then exit.")
    parser.add_argument("--reclassify", action="store_true", help="Force re-classification of ALL existing items using current taxonomy rules.")
    parser.add_argument("--activate", action="store_true", help="Enable spreading activation for new signals (boosts neighbor edge confidence).")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    if args.backfill_embeddings:
        payload = backfill_embeddings()
        print(json.dumps(payload))
        return 0 if payload.get("ok") else 1

    payload = sync(days=args.days, apply_changes=args.apply, no_semantic=args.no_semantic, reclassify=args.reclassify)
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
