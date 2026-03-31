#!/usr/bin/env python3
"""Ingest X/web research into Obsidian inbox using xint.

Usage:
  python3 ingest_x_research.py "<url>"                 # dry-run
  python3 ingest_x_research.py "<url>" --apply         # write note + daily entry
  python3 ingest_x_research.py "<url>" --apply --sync  # also sync research graph
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INBOX_DIR = Path.home() / "obsidian" / "nyk" / "inbox"
DAILY_DIR = Path.home() / "obsidian" / "nyk" / "00-home" / "daily"
VAULT_ROOT = Path.home() / "obsidian" / "nyk"
SYNC_SCRIPT = Path(os.environ.get("LACP_AUTOMATION_ROOT", str(Path(__file__).resolve().parent.parent))) / "scripts" / "sync_research_knowledge.py"

X_STATUS_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/]+/status/(\d+)")
SPACE_RE = re.compile(r"\s+")

QUANT_KEYWORDS = [
    "quant", "markowitz", "black-scholes", "ito", "stochastic", "bayes", "probability", "variance", "portfolio",
    "sharpe", "regression", "mle", "pca", "eigen", "convex", "derivatives", "brownian", "lmsr", "polymarket",
]


@dataclass
class Ingested:
    source_url: str
    source_kind: str
    title: str
    author: str
    created_at: str
    metrics: dict[str, Any]
    preview: str
    body: str


def run_json(cmd: list[str], timeout_sec: int = 150) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout_sec}s: {' '.join(cmd)}") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    raw = proc.stdout.strip()
    if not raw:
        raise RuntimeError(f"Empty output from command: {' '.join(cmd)}")
    return json.loads(raw)


def collapse(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip())


def text_lines(body: str) -> list[str]:
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if len(line) < 25:
            continue
        if line.startswith(("http://", "https://", "#", "---", "{", "[")):
            continue
        out.append(line)
    return out


def infer_tags(text: str, host: str) -> list[str]:
    low = text.lower()
    tags = ["research", "web-intel"]
    if "x.com" in host or "twitter.com" in host:
        tags.append("x-intel")
    if any(k in low for k in QUANT_KEYWORDS):
        tags.extend(["quantitative-finance", "learning-path"])
    return sorted(set(tags))


def summarize(body: str, max_items: int = 8) -> list[str]:
    lines = text_lines(body)
    items: list[str] = []
    for line in lines:
        clean = collapse(line)
        if clean in items:
            continue
        items.append(clean)
        if len(items) >= max_items:
            break
    return items


def extract_quant_signals(body: str) -> dict[str, list[str]]:
    lines = text_lines(body)
    buckets: dict[str, list[str]] = {
        "math_foundations": [],
        "tools_stack": [],
        "learning_resources": [],
        "career_signals": [],
    }
    for line in lines:
        low = line.lower()
        if any(k in low for k in ["probability", "statistics", "linear algebra", "stochastic", "calculus", "bayes", "markowitz"]):
            buckets["math_foundations"].append(collapse(line))
        if any(k in low for k in ["python", "numpy", "scipy", "cvxpy", "quantlib", "gurobi", "pytorch", "polars"]):
            buckets["tools_stack"].append(collapse(line))
        if any(k in low for k in ["read", "book", "guide", "lectures", "resource", "interview", "homework"]):
            buckets["learning_resources"].append(collapse(line))
        if any(k in low for k in ["comp", "salary", "$", "career", "researcher", "trader", "developer", "risk quant"]):
            buckets["career_signals"].append(collapse(line))

    for key, vals in buckets.items():
        dedup: list[str] = []
        seen: set[str] = set()
        for item in vals:
            if item not in seen:
                seen.add(item)
                dedup.append(item)
            if len(dedup) >= 7:
                break
        buckets[key] = dedup
    return buckets


def get_x_ingest(url: str, tweet_id: str) -> Ingested:
    payload = run_json(["xint", "tweet", tweet_id, "--json"])
    data = payload.get("data", {})
    article = data.get("article", {}) if isinstance(data.get("article"), dict) else {}
    body = str(article.get("plain_text") or data.get("text") or "").strip()
    title = str(article.get("title") or f"X Post {tweet_id}").strip()
    preview = str(article.get("preview_text") or data.get("text") or "").strip()
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    return Ingested(
        source_url=url,
        source_kind="x",
        title=title,
        author=str(data.get("username") or ""),
        created_at=str(data.get("created_at") or ""),
        metrics=metrics,
        preview=preview,
        body=body,
    )


def get_web_ingest(url: str) -> Ingested:
    timeout_sec = "90"
    cmd_full = ["xint", "article", url, "--json", "--full"]
    cmd_basic = ["xint", "article", url, "--json"]
    try:
        payload = run_json(["env", f"XINT_ARTICLE_TIMEOUT_SEC={timeout_sec}", *cmd_full], timeout_sec=180)
    except RuntimeError as first_err:
        try:
            payload = run_json(["env", f"XINT_ARTICLE_TIMEOUT_SEC={timeout_sec}", *cmd_basic], timeout_sec=120)
        except RuntimeError as second_err:
            fallback_msg = (
                f"xint article fetch failed.\n"
                f"full_error: {first_err}\n"
                f"basic_error: {second_err}\n"
                "Capture created as retry-needed stub."
            )
            return Ingested(
                source_url=url,
                source_kind="web",
                title=url,
                author="",
                created_at="",
                metrics={},
                preview="Fetch failed via xint (timeout/upstream). Retry later.",
                body=fallback_msg,
            )
    data = payload.get("data", {})
    article = data.get("article") if isinstance(data.get("article"), dict) else data
    body = str(article.get("plain_text") or article.get("content") or "").strip()
    title = str(article.get("title") or url).strip()
    preview = str(article.get("preview_text") or "").strip()
    return Ingested(
        source_url=url,
        source_kind="web",
        title=title,
        author="",
        created_at="",
        metrics={},
        preview=preview,
        body=body,
    )


def slugify(text: str, max_len: int = 60) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    out = out[:max_len].strip("-")
    return out or "research-note"


def render_note(item: Ingested) -> str:
    now = datetime.now(UTC)
    host = urlparse(item.source_url).netloc
    preview = collapse(item.preview) if item.preview else ""
    body = item.body.strip()
    summary_points = summarize(body, max_items=8)
    quant = extract_quant_signals(body)
    tags = infer_tags(f"{item.title}\n{preview}\n{body[:5000]}", host)

    metrics_lines: list[str] = []
    if item.metrics:
        metrics_lines = [
            f"- Impressions: `{item.metrics.get('impressions', 0)}`",
            f"- Bookmarks: `{item.metrics.get('bookmarks', 0)}`",
            f"- Likes: `{item.metrics.get('likes', 0)}`",
            f"- Retweets: `{item.metrics.get('retweets', 0)}`",
            f"- Replies: `{item.metrics.get('replies', 0)}`",
            f"- Quotes: `{item.metrics.get('quotes', 0)}`",
        ]

    frontmatter = [
        "---",
        f'title: "{item.title[:160].replace(chr(34), chr(39))}"',
        f'date: "{now.strftime("%Y-%m-%d")}"',
        'status: "inbox"',
        f'source: "{item.source_kind}"',
        f'source_url: "{item.source_url}"',
        f'tags: {json.dumps(tags)}',
        "auto_captured: true",
        "---",
    ]

    lines: list[str] = []
    lines.extend(frontmatter)
    lines.append("")
    lines.append(f"# {item.title}")
    lines.append("")
    lines.append("## Source")
    lines.append(f"- URL: {item.source_url}")
    lines.append(f"- Captured at: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if item.author:
        lines.append(f"- Author: @{item.author}")
    if item.created_at:
        lines.append(f"- Published: {item.created_at}")
    if metrics_lines:
        lines.append("")
        lines.append("## X Metrics")
        lines.extend(metrics_lines)
    if preview:
        lines.append("")
        lines.append("## Preview")
        lines.append(preview)

    lines.append("")
    lines.append("## Distilled Knowledge")
    if summary_points:
        for s in summary_points:
            lines.append(f"- {s}")
    else:
        lines.append("- No summary points extracted.")

    has_quant = any(quant[k] for k in quant)
    if has_quant:
        lines.append("")
        lines.append("## Quant Knowledge Extract")
        if quant["math_foundations"]:
            lines.append("### Math Foundations")
            for v in quant["math_foundations"]:
                lines.append(f"- {v}")
        if quant["tools_stack"]:
            lines.append("### Tooling Stack")
            for v in quant["tools_stack"]:
                lines.append(f"- {v}")
        if quant["learning_resources"]:
            lines.append("### Learning Resources")
            for v in quant["learning_resources"]:
                lines.append(f"- {v}")
        if quant["career_signals"]:
            lines.append("### Career Signals")
            for v in quant["career_signals"]:
                lines.append(f"- {v}")

    lines.append("")
    lines.append("## Next Actions")
    lines.append("- [ ] Verify high-impact numeric claims with primary sources.")
    lines.append("- [ ] Promote stable insights to `knowledge-memory` if reused.")
    lines.append("- [ ] Link this note to related projects/agents.")

    raw_excerpt = "\n".join(body.splitlines()[:220]).strip()
    if raw_excerpt:
        lines.append("")
        lines.append("## Raw Extract (Excerpt)")
        lines.append("```text")
        lines.append(raw_excerpt)
        lines.append("```")

    lines.append("")
    lines.append("## Links")
    lines.append("- [[atlas/research]]")
    lines.append("- [[research-insights]]")
    return "\n".join(lines).rstrip() + "\n"


def ensure_daily_file(day: str) -> Path:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    p = DAILY_DIR / f"{day}.md"
    if not p.exists():
        p.write_text("# Daily\n\n## Agent Daily\n", encoding="utf-8")
    return p


def format_key_files_for_daily(key_files: str) -> str:
    raw = key_files.strip()
    if not raw:
        return "Obsidian inbox note"
    parts = [p.strip() for p in re.split(r"[;,]\s*", raw) if p.strip()]
    if not parts:
        parts = [raw]

    formatted: list[str] = []
    for part in parts:
        if part.startswith("[["):
            formatted.append(part)
            continue
        if part.startswith(("/", "~")):
            path = Path(part).expanduser()
            resolved = path.resolve(strict=False)
            resolved_text = str(resolved)
            try:
                rel = resolved.relative_to(VAULT_ROOT)
                rel_text = rel.as_posix()
                if rel_text.endswith(".md"):
                    rel_text = rel_text[:-3]
                formatted.append(f"[[{rel_text}]] (`{resolved_text}`)")
            except ValueError:
                formatted.append(f"`{resolved_text}`")
            continue
        formatted.append(part)

    return "; ".join(formatted)


def append_agent_daily(intent: str, outcome: str, key_files: str = "Obsidian inbox note") -> None:
    now_local = datetime.now().astimezone()
    day = now_local.strftime("%Y-%m-%d")
    hhmm = now_local.strftime("%H:%M")
    daily_path = ensure_daily_file(day)
    content = daily_path.read_text(encoding="utf-8", errors="ignore")
    if "## Agent Daily" not in content:
        if not content.endswith("\n"):
            content += "\n"
        content += "\n## Agent Daily\n"
    key_files_fmt = format_key_files_for_daily(key_files)
    block = (
        f"\n### {hhmm} — codex\n"
        f"- **Intent**: {intent}\n"
        f"- **Outcome**: {outcome}\n"
        f"- **Key files**: {key_files_fmt}\n"
    )
    daily_path.write_text(content.rstrip() + block + "\n", encoding="utf-8")


def ingest(url: str) -> Ingested:
    m = X_STATUS_RE.match(url.strip())
    if m:
        return get_x_ingest(url, m.group(1))
    return get_web_ingest(url)


def maybe_sync(apply: bool, sync: bool) -> None:
    if not apply or not sync:
        return
    if not SYNC_SCRIPT.exists():
        return
    subprocess.run(
        ["python3", str(SYNC_SCRIPT), "--days", "30", "--apply"],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest X/web research via xint into Obsidian inbox.")
    parser.add_argument("url", help="X status URL or web URL")
    parser.add_argument("--apply", action="store_true", help="Write note + daily entry")
    parser.add_argument("--sync", action="store_true", help="Run sync_research_knowledge.py --apply after writing")
    args = parser.parse_args()

    item = ingest(args.url)
    note = render_note(item)
    slug = slugify(item.title)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    out_path = INBOX_DIR / f"{day}-xint-{slug}.md"

    if args.apply:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(note, encoding="utf-8")
        append_agent_daily(
            intent=f"Ingest and distill research from {args.url}",
            outcome=f"Captured structured knowledge note at {out_path} using xint.",
            key_files=str(out_path),
        )
        maybe_sync(args.apply, args.sync)
        print(json.dumps({"ok": True, "written": str(out_path), "applied": True}, indent=2))
        return 0

    print(json.dumps({
        "ok": True,
        "applied": False,
        "source_kind": item.source_kind,
        "title": item.title,
        "preview": item.preview,
        "output_preview_path": str(out_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
