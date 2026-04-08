#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path.home() / "control" / "knowledge" / "knowledge-memory" / "data" / "sandbox-runs"
DAILY_DIR = Path.home() / "obsidian" / "nyk" / "00-home" / "daily"


@dataclass
class Entry:
    ts: str
    hhmm: str
    agent: str
    intent: str
    outcome: str
    run_file: Path


def map_agent(command: list[str] | None) -> str | None:
    if not command:
        return None
    base = Path(command[0]).name.lower()
    if "hermes" in base:
        return "hermes"
    if "claude" in base:
        return "claude"
    if "codex" in base:
        return "codex"
    return None


def load_entries(day: str) -> list[Entry]:
    out: list[Entry] = []
    for p in sorted(RUNS_DIR.glob("run-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        started = str(data.get("started_at_utc") or "")
        if not started:
            continue
        # Convert UTC date to local day label for note grouping.
        try:
            dt_utc = datetime.fromisoformat(started.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone()
        except Exception:
            continue
        local_day = dt_local.strftime("%Y-%m-%d")
        if local_day != day:
            continue

        agent = map_agent(data.get("command"))
        if not agent:
            continue

        task = str(data.get("task") or "interactive session")
        exit_code = data.get("exit_code")
        executed = bool(data.get("executed"))
        if executed and exit_code == 0:
            outcome = "Completed successfully"
        elif executed:
            outcome = f"Exited with code {exit_code}"
        else:
            err = str(data.get("error") or "blocked")
            outcome = f"Not executed: {err}"

        out.append(
            Entry(
                ts=str(data.get("timestamp") or p.stem),
                hhmm=dt_local.strftime("%H:%M"),
                agent=agent,
                intent=task,
                outcome=outcome,
                run_file=p,
            )
        )

    # Keep latest first, dedupe per run ts
    seen: set[str] = set()
    deduped: list[Entry] = []
    for e in sorted(out, key=lambda x: x.ts, reverse=True):
        if e.ts in seen:
            continue
        seen.add(e.ts)
        deduped.append(e)
    return deduped


def ensure_daily(day: str) -> Path:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    p = DAILY_DIR / f"{day}.md"
    capture_link = f"> See today's agent capture: [[knowledge/memory/daily/{day}]]"
    if not p.exists():
        p.write_text(f"## Agent Daily\n\n{capture_link}\n", encoding="utf-8")
    else:
        content = p.read_text(encoding="utf-8", errors="ignore")
        if "## Agent Daily" not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += "\n## Agent Daily\n"
        if capture_link not in content:
            if "## Agent Daily" in content:
                content = content.replace("## Agent Daily", f"## Agent Daily\n\n{capture_link}", 1)
            else:
                if not content.endswith("\n"):
                    content += "\n"
                content += f"\n## Agent Daily\n\n{capture_link}\n"
        p.write_text(content, encoding="utf-8")
    return p


def append_entries(day: str, entries: list[Entry], apply: bool, max_per_agent: int) -> dict:
    daily = ensure_daily(day)
    content = daily.read_text(encoding="utf-8", errors="ignore")

    by_agent: dict[str, int] = {"codex": 0, "claude": 0, "hermes": 0}
    blocks: list[str] = []
    added = 0

    for e in entries:
        if by_agent.get(e.agent, 0) >= max_per_agent:
            continue
        marker = f"<!-- lacp-run:{e.ts} -->"
        if marker in content:
            continue
        by_agent[e.agent] = by_agent.get(e.agent, 0) + 1
        blocks.append(
            "\n".join(
                [
                    marker,
                    f"### {e.hhmm} — {e.agent}",
                    f"- **Intent**: {e.intent}",
                    f"- **Outcome**: {e.outcome}",
                    f"- **Key files**: {e.run_file}",
                    "",
                ]
            )
        )
        added += 1

    if apply and blocks:
        new_content = content.rstrip() + "\n\n" + "\n".join(blocks) + "\n"
        daily.write_text(new_content, encoding="utf-8")

    return {
        "ok": True,
        "day": day,
        "entries_found": len(entries),
        "entries_added": added,
        "daily_note": str(daily),
        "applied": apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Append Claude/Codex/Hermes LACP run summaries to Obsidian daily Agent Daily section.")
    parser.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-per-agent", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    entries = load_entries(args.day)
    result = append_entries(args.day, entries, args.apply, args.max_per_agent)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
