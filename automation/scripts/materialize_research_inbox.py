#!/usr/bin/env python3
"""materialize_research_inbox.py — Batch-process web research spool into docs/research/inbox/ notes.

Reads JSONL events captured by capture_web_research.sh, groups by session + 10-min window,
deduplicates, renders structured research notes, and writes to the canonical inbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SPOOL_DIR = Path.home() / ".local" / "share" / "research-capture"
SPOOL_FILE = SPOOL_DIR / "spool.jsonl"
PROCESSED_DIR = SPOOL_DIR / "processed"

RESEARCH_INBOX = Path.home() / "docs" / "research" / "inbox"

# ---------------------------------------------------------------------------
# Reused from extract_shared_memory.py:20-25
# ---------------------------------------------------------------------------
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9_\-\.=]{16,}\b", re.IGNORECASE),
    re.compile(r"(api[_ -]?key|password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Reused from sync_research_knowledge.py:39-70
# ---------------------------------------------------------------------------
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
        "name": "security-governance",
        "keywords": ["security", "policy", "audit", "risk", "governance", "compliance"],
        "min_keyword_hits": 1,
    },
    {
        "name": "product-market-competitors",
        "keywords": ["competitor", "market", "pricing", "positioning", "seo", "content", "leads"],
        "min_keyword_hits": 1,
    },
    {
        "name": "infra-performance",
        "keywords": ["mac", "server", "infra", "deployment", "performance", "profiling", "benchmark"],
        "min_keyword_hits": 1,
    },
]

URL_RE = re.compile(r"https?://[^\s\]\)\",]+")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass
class SpoolEvent:
    ts: str
    session_id: str
    cwd: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: str
    raw_line: str

    @property
    def timestamp(self) -> datetime:
        try:
            return datetime.fromisoformat(self.ts.replace("Z", "+00:00")).astimezone(UTC)
        except (ValueError, AttributeError):
            return datetime.now(UTC)

    @property
    def query(self) -> str:
        if self.tool_name == "WebSearch":
            return str(self.tool_input.get("query", ""))
        if self.tool_name == "WebFetch":
            url = str(self.tool_input.get("url", ""))
            prompt = str(self.tool_input.get("prompt", ""))
            return f"{prompt} [{url}]" if prompt else url
        return ""

    @property
    def source_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        # From tool_input
        if self.tool_name == "WebFetch":
            url = self.tool_input.get("url", "")
            if isinstance(url, str) and url:
                urls.append(url)
                seen.add(url)
        # From tool_response
        for match in URL_RE.findall(self.tool_response[:20000]):
            cleaned = match.rstrip(".,;)")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)
                if len(urls) >= 20:
                    break
        return urls


@dataclass
class ResearchGroup:
    session_id: str
    events: list[SpoolEvent] = field(default_factory=list)

    @property
    def start_time(self) -> datetime:
        return min(e.timestamp for e in self.events) if self.events else datetime.now(UTC)

    @property
    def combined_query(self) -> str:
        queries = [e.query for e in self.events if e.query]
        return " | ".join(dict.fromkeys(queries))

    @property
    def all_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for event in self.events:
            for url in event.source_urls:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls[:20]

    @property
    def combined_response(self) -> str:
        parts: list[str] = []
        for event in self.events:
            resp = event.tool_response[:8000]
            if resp:
                parts.append(resp)
        return "\n\n---\n\n".join(parts)

    @property
    def fingerprint(self) -> str:
        """SHA-1 of sorted source URLs for deduplication."""
        urls = sorted(set(self.all_urls))
        if not urls:
            text = self.combined_query.lower().strip()
            return hashlib.sha1(text.encode()).hexdigest()[:16]
        return hashlib.sha1("\n".join(urls).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def redact_secrets(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def classify_categories(text: str) -> list[str]:
    low = text.lower()
    scored: list[tuple[int, str]] = []
    for rule in DEFAULT_CATEGORY_RULES:
        name = rule["name"]
        keywords = rule["keywords"]
        min_hits = rule.get("min_keyword_hits", 1)
        hits = sum(1 for kw in keywords if kw in low)
        if hits >= min_hits:
            scored.append((hits, name))
    scored.sort(reverse=True)
    if not scored:
        return ["general-research"]
    top = scored[0][0]
    categories = [name for score, name in scored if score >= max(1, top - 1)]
    return categories[:3]


def slugify(text: str, max_len: int = 50) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-") or "web-research"


def parse_spool() -> list[SpoolEvent]:
    if not SPOOL_FILE.exists():
        return []
    events: list[SpoolEvent] = []
    for line in SPOOL_FILE.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        tool_input = obj.get("tool_input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        events.append(SpoolEvent(
            ts=str(obj.get("ts", "")),
            session_id=str(obj.get("session_id", "")),
            cwd=str(obj.get("cwd", "")),
            tool_name=str(obj.get("tool_name", "")),
            tool_input=tool_input,
            tool_response=str(obj.get("tool_response", "")),
            raw_line=line,
        ))
    return events


def group_events(events: list[SpoolEvent]) -> list[ResearchGroup]:
    """Group events by session_id with 10-minute gap splitting."""
    by_session: dict[str, list[SpoolEvent]] = defaultdict(list)
    for event in events:
        by_session[event.session_id].append(event)

    groups: list[ResearchGroup] = []
    for session_id, session_events in by_session.items():
        session_events.sort(key=lambda e: e.timestamp)
        current_group = ResearchGroup(session_id=session_id)
        for event in session_events:
            if current_group.events:
                gap = event.timestamp - current_group.events[-1].timestamp
                if gap > timedelta(minutes=10):
                    groups.append(current_group)
                    current_group = ResearchGroup(session_id=session_id)
            current_group.events.append(event)
        if current_group.events:
            groups.append(current_group)

    groups.sort(key=lambda g: g.start_time)
    return groups


def existing_fingerprints() -> set[str]:
    """Scan inbox files for existing fingerprints in frontmatter."""
    fps: set[str] = set()
    if not RESEARCH_INBOX.exists():
        return fps
    for path in RESEARCH_INBOX.glob("*.md"):
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        # Look for fingerprint in frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end]
                for line in frontmatter.splitlines():
                    if line.strip().startswith("fingerprint:"):
                        fp = line.split(":", 1)[1].strip().strip('"').strip("'")
                        if fp:
                            fps.add(fp)
    return fps


def render_note(group: ResearchGroup) -> str:
    """Render a research note from a group of events."""
    date_str = group.start_time.strftime("%Y-%m-%d")
    query = redact_secrets(group.combined_query)
    urls = group.all_urls
    response_preview = redact_secrets(group.combined_response[:6000])
    all_text = f"{query} {response_preview}"
    tags = classify_categories(all_text)
    sources_yaml = "\n".join(f'  - "{url}"' for url in urls) if urls else '  - "no-url"'

    # Extract key claims from response (first few meaningful lines)
    claims: list[str] = []
    for line in response_preview.splitlines():
        line = line.strip()
        if len(line) > 30 and not line.startswith(("{", "[", "<", "http", "#", "---")):
            claims.append(line[:200])
            if len(claims) >= 5:
                break

    claims_section = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1)) if claims else "1. \n2. \n3. "

    return f"""---
title: "{query[:120]}"
date: "{date_str}"
status: "inbox"
sources:
{sources_yaml}
confidence: "medium"
tags: {json.dumps(tags)}
fingerprint: "{group.fingerprint}"
session_id: "{group.session_id}"
auto_captured: true
promotion_targets: []
---

# Summary

Auto-captured web research from Claude Code session.

Query: {query}

# Key Claims

{claims_section}

# Evidence

{chr(10).join(f'- Source: {url}{chr(10)}  Retrieved: {date_str}' for url in urls[:10]) if urls else '- No URLs captured'}

# Raw Response Preview

{response_preview[:4000]}

# Synthesis

- Decision impact:
- Recommended action:
- Open questions:

# Promotion Log

- Promoted to:
- Date:
- Notes:
"""


def materialize(*, apply: bool) -> dict[str, Any]:
    """Main materialization logic."""
    events = parse_spool()
    if not events:
        return {"ok": True, "events": 0, "groups": 0, "created": 0, "skipped_dup": 0, "mode": "apply" if apply else "dry-run"}

    groups = group_events(events)
    known_fps = existing_fingerprints()

    created = 0
    skipped_dup = 0
    created_files: list[str] = []

    RESEARCH_INBOX.mkdir(parents=True, exist_ok=True)

    for group in groups:
        fp = group.fingerprint
        if fp in known_fps:
            skipped_dup += 1
            continue

        date_str = group.start_time.strftime("%Y-%m-%d")
        slug = slugify(group.combined_query)
        filename = f"{date_str}-auto-{slug}.md"
        target = RESEARCH_INBOX / filename

        # Avoid filename collisions
        counter = 1
        while target.exists():
            filename = f"{date_str}-auto-{slug}-{counter}.md"
            target = RESEARCH_INBOX / filename
            counter += 1

        note = render_note(group)

        if apply:
            target.write_text(note, encoding="utf-8")
            known_fps.add(fp)

        created += 1
        created_files.append(str(target))

    # Rotate processed spool
    if apply and events:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        day_tag = datetime.now(UTC).strftime("%Y-%m-%d")
        archive = PROCESSED_DIR / f"{day_tag}.jsonl"
        # Append to existing archive for the day
        with open(archive, "a", encoding="utf-8") as f:
            for event in events:
                f.write(event.raw_line + "\n")
        # Clear the spool
        SPOOL_FILE.write_text("", encoding="utf-8")

    return {
        "ok": True,
        "events": len(events),
        "groups": len(groups),
        "created": created,
        "skipped_dup": skipped_dup,
        "created_files": created_files,
        "mode": "apply" if apply else "dry-run",
    }


def _self_test() -> None:
    """Inline validation checks."""
    # Secret redaction
    assert "sk-" not in redact_secrets("token sk-1234567890abcdefghijklmnop here")
    assert "[REDACTED]" in redact_secrets("api_key=mysecretvalue123")

    # Category classification
    cats = classify_categories("optimize claude codex context and memory orchestration")
    assert any(c in cats for c in ("memory-knowledge", "claude-codex-optimization")), f"unexpected: {cats}"

    # Slugify
    assert slugify("How to optimize React performance") == "how-to-optimize-react-performance"
    assert slugify("") == "web-research"

    # Fingerprint consistency
    g1 = ResearchGroup(session_id="test")
    e1 = SpoolEvent(ts="2026-01-01T00:00:00Z", session_id="test", cwd="/tmp",
                     tool_name="WebSearch", tool_input={"query": "test"},
                     tool_response="result", raw_line="{}")
    g1.events = [e1]
    fp1 = g1.fingerprint
    g2 = ResearchGroup(session_id="test")
    g2.events = [e1]
    assert fp1 == g2.fingerprint, "fingerprints should be stable"

    # URL extraction
    e2 = SpoolEvent(ts="2026-01-01T00:00:00Z", session_id="test", cwd="/tmp",
                     tool_name="WebFetch",
                     tool_input={"url": "https://example.com", "prompt": "test"},
                     tool_response="see https://other.com/page",
                     raw_line="{}")
    assert "https://example.com" in e2.source_urls
    assert "https://other.com/page" in e2.source_urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize web research spool into docs/research/inbox/ notes."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes (write files, rotate spool). Default is dry-run.")
    parser.add_argument("--self-test", action="store_true", help="Run inline checks and exit.")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("self-test passed")
        return 0

    result = materialize(apply=args.apply)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
