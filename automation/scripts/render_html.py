#!/usr/bin/env python3
"""Render LACP artifacts to self-contained HTML pages.

Design principles:
  - Self-contained: inline CSS, no external assets, opens anywhere.
  - JSON-in, HTML-out: pure function over a structured payload — never reads
    contract state itself. Callers feed it parsed JSON.
  - Bounded: never embeds untrusted strings without HTML-escaping.
  - Build output, not source: emit to ~/.lacp/reports/ by default. Never check in.

Supported renderers:
  - handoff  : HandoffArtifact (hooks/hook_contracts.py)
  - status   : payload from `lacp status-report --json`
  - quality  : payload from `lacp-eval --json` (session quality scorecard)

CLI usage:
  cat handoff.json | python3 render_html.py handoff > handoff.html
  python3 render_html.py handoff --in handoff.json --out handoff.html
  python3 render_html.py status  --in status.json  --out status.html
  python3 render_html.py quality --in quality.json --out quality.html

Module usage:
  from render_html import render_handoff, render_status, render_quality
  html = render_handoff(payload_dict)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------- shared styling ----------

_BASE_CSS = """
:root {
  --bg: #0f1115;
  --panel: #161922;
  --panel-2: #1d2230;
  --line: #262c3a;
  --fg: #e6e8ee;
  --muted: #8a93a6;
  --accent: #6aa7ff;
  --good: #4ade80;
  --warn: #fbbf24;
  --bad: #f87171;
  --code-bg: #0b0d12;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 980px; margin: 0 auto; padding: 32px 24px 80px; }
h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted); margin: 28px 0 10px; font-weight: 600; }
.sub { color: var(--muted); font-size: 12px; margin-bottom: 24px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px 18px; margin: 12px 0; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px; }
.kpi .label { color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.06em; }
.kpi .value { font-size: 22px; font-weight: 600; margin-top: 4px; letter-spacing: -0.01em; }
.kpi .value.good { color: var(--good); }
.kpi .value.warn { color: var(--warn); }
.kpi .value.bad  { color: var(--bad); }
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.02em;
  border: 1px solid var(--line); background: var(--panel-2); color: var(--fg); }
.pill.good { color: #052e16; background: var(--good); border-color: var(--good); }
.pill.warn { color: #422006; background: var(--warn); border-color: var(--warn); }
.pill.bad  { color: #450a0a; background: var(--bad);  border-color: var(--bad); }
ul.files { list-style: none; padding: 0; margin: 0; }
ul.files li { padding: 6px 0; border-bottom: 1px dashed var(--line);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
ul.files li:last-child { border-bottom: 0; }
pre.code { background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px; overflow-x: auto;
  font: 12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #cdd5e1; }
.meta { font-size: 12px; color: var(--muted); }
.meta a { color: var(--accent); text-decoration: none; }
.meta a:hover { text-decoration: underline; }
.footer { margin-top: 40px; color: var(--muted); font-size: 11px;
  border-top: 1px solid var(--line); padding-top: 14px; }
.bar { display: inline-block; height: 6px; border-radius: 4px;
  background: var(--line); vertical-align: middle; width: 120px; position: relative; overflow: hidden; }
.bar > span { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
.recs li { margin: 4px 0; }
.trend-up    { color: var(--good); }
.trend-down  { color: var(--bad); }
.trend-flat  { color: var(--muted); }
"""


def _esc(value: Any) -> str:
    """HTML-escape any value, rendering None as empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _pill(label: str, kind: str = "") -> str:
    cls = f"pill {kind}".strip()
    return f'<span class="{cls}">{_esc(label)}</span>'


def _bar(pct: float) -> str:
    pct = max(0.0, min(100.0, float(pct)))
    return f'<span class="bar"><span style="width:{pct:.1f}%"></span></span>'


def _page(title: str, body: str, subtitle: str = "") -> str:
    sub = f'<div class="sub">{_esc(subtitle)}</div>' if subtitle else ""
    return (
        "<!doctype html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        f"<title>{_esc(title)}</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<style>{_BASE_CSS}</style>"
        "</head><body><div class=\"wrap\">"
        f"<h1>{_esc(title)}</h1>{sub}{body}"
        "<div class=\"footer\">"
        f"Generated by <code>lacp render_html.py</code> at "
        f"{_esc(datetime.now(timezone.utc).isoformat(timespec='seconds'))}"
        "</div></div></body></html>"
    )


# ---------- handoff renderer ----------

def render_handoff(payload: dict) -> str:
    """Render a HandoffArtifact dict to HTML."""
    summary = payload.get("task_summary") or "(no summary)"
    branch = payload.get("git_branch") or "(unknown)"
    test_status = (payload.get("test_status") or "unknown").lower()
    created = payload.get("created_at") or ""
    files = payload.get("files_modified") or []
    open_issues = payload.get("open_issues") or []
    next_steps = payload.get("next_steps") or []
    diff = payload.get("git_diff_summary") or ""

    test_pill_kind = {"pass": "good", "fail": "bad"}.get(test_status, "warn")

    kpis = (
        '<div class="grid">'
        f'<div class="kpi"><div class="label">Branch</div>'
        f'<div class="value" style="font-size:16px">{_esc(branch)}</div></div>'
        f'<div class="kpi"><div class="label">Tests</div>'
        f'<div class="value">{_pill(test_status, test_pill_kind)}</div></div>'
        f'<div class="kpi"><div class="label">Files touched</div>'
        f'<div class="value">{len(files)}</div></div>'
        f'<div class="kpi"><div class="label">Open issues</div>'
        f'<div class="value">{len(open_issues)}</div></div>'
        '</div>'
    )

    files_block = ""
    if files:
        items = "".join(f"<li>{_esc(f)}</li>" for f in files[:50])
        files_block = (
            f'<h2>Files modified ({len(files)})</h2>'
            f'<div class="card"><ul class="files">{items}</ul></div>'
        )

    diff_block = ""
    if diff:
        diff_block = f'<h2>Git diff</h2><pre class="code">{_esc(diff)}</pre>'

    next_block = ""
    if next_steps:
        items = "".join(f"<li>{_esc(s)}</li>" for s in next_steps)
        next_block = f'<h2>Next steps</h2><div class="card"><ul class="recs">{items}</ul></div>'

    issues_block = ""
    if open_issues:
        items = "".join(f"<li>{_esc(s)}</li>" for s in open_issues)
        issues_block = f'<h2>Open issues</h2><div class="card"><ul class="recs">{items}</ul></div>'

    body = (
        f'<h2>Task summary</h2><div class="card">{_esc(summary)}</div>'
        + kpis
        + next_block
        + issues_block
        + files_block
        + diff_block
    )
    return _page("LACP handoff", body, subtitle=f"created {created}" if created else "")


# ---------- status renderer ----------

def _kpi(label: str, value: Any, kind: str = "") -> str:
    cls = f"value {kind}".strip()
    return (
        f'<div class="kpi"><div class="label">{_esc(label)}</div>'
        f'<div class="{cls}">{_esc(value)}</div></div>'
    )


def render_status(payload: dict) -> str:
    """Render a `lacp status-report --json` payload to HTML."""
    generated = payload.get("generated_at_utc") or ""
    ok = payload.get("ok", False)
    mode = payload.get("mode") or "unknown"
    allow_remote = str(payload.get("allow_external_remote", "false"))
    provider = payload.get("remote_provider") or "n/a"
    approval = payload.get("remote_approval") or {}

    doctor = payload.get("doctor") or {}
    brain = payload.get("brain") or {}
    intervention = payload.get("intervention_rate") or {}
    memory_kpi = (payload.get("memory_kpi") or {}).get("kpis") or {}
    artifacts = payload.get("artifacts") or {}

    overall_pill = _pill("OK" if ok else "DEGRADED", "good" if ok else "bad")

    top = (
        '<div class="grid">'
        + _kpi("Overall", overall_pill)
        + _kpi("Mode", mode)
        + _kpi("Allow remote", allow_remote, "warn" if allow_remote == "true" else "")
        + _kpi("Provider", provider)
        + '</div>'
    )

    doctor_kind = "good" if doctor.get("ok") else ("warn" if doctor.get("warn", 0) else "bad")
    doctor_block = (
        '<h2>Doctor</h2><div class="grid">'
        + _kpi("Status", _pill("OK" if doctor.get("ok") else "FAIL", doctor_kind))
        + _kpi("Pass", doctor.get("pass", 0), "good")
        + _kpi("Warn", doctor.get("warn", 0), "warn" if doctor.get("warn") else "")
        + _kpi("Fail", doctor.get("fail", 0), "bad" if doctor.get("fail") else "")
        + '</div>'
    )

    brain_status = brain.get("ok")
    brain_kind = "good" if brain_status is True else ("warn" if brain_status == "unknown" else "bad")
    brain_label = "OK" if brain_status is True else ("UNKNOWN" if brain_status == "unknown" else "FAIL")
    brain_block = (
        '<h2>Brain</h2><div class="grid">'
        + _kpi("Status", _pill(brain_label, brain_kind))
        + _kpi("Pass", brain.get("pass", 0), "good")
        + _kpi("Warn", brain.get("warn", 0), "warn" if brain.get("warn") else "")
        + _kpi("Fail", brain.get("fail", 0), "bad" if brain.get("fail") else "")
        + '</div>'
    )

    iv_current = (intervention.get("current_window") or {})
    iv_baseline = (intervention.get("baseline_window") or {})
    iv_delta = (intervention.get("delta") or {})
    iv_rate = iv_current.get("intervention_rate_per_100", 0) or 0
    iv_kind = "good" if iv_rate == 0 else ("warn" if iv_rate < 5 else "bad")
    iv_block = (
        '<h2>Intervention pressure</h2><div class="grid">'
        + _kpi("Current rate / 100", iv_rate, iv_kind)
        + _kpi("Current runs", iv_current.get("total_runs", 0))
        + _kpi("Baseline rate / 100", iv_baseline.get("intervention_rate_per_100", 0))
        + _kpi("Delta", iv_delta.get("absolute", 0))
        + '</div>'
    )

    mem_block = ""
    if memory_kpi:
        mem_block = (
            '<h2>Memory quality</h2><div class="grid">'
            + _kpi("Total notes", memory_kpi.get("total_notes", 0))
            + _kpi("Canonical", memory_kpi.get("canonical_notes", 0))
            + _kpi("Schema coverage %", memory_kpi.get("required_schema_coverage_pct", 0))
            + _kpi("Source-backed %", memory_kpi.get("source_backed_pct", 0))
            + _kpi("Contradictions",
                   memory_kpi.get("contradiction_notes", 0),
                   "bad" if memory_kpi.get("contradiction_notes") else "")
            + _kpi("Stale", memory_kpi.get("stale_notes", 0),
                   "warn" if memory_kpi.get("stale_notes") else "")
            + '</div>'
        )

    approval_line = ""
    if approval:
        valid = str(approval.get("valid", "false"))
        expires = approval.get("expires_at_utc") or "n/a"
        approval_line = (
            f'<div class="meta">Remote approval: {_pill(valid, "good" if valid == "true" else "warn")} '
            f'(expires {_esc(expires)})</div>'
        )

    artifacts_rows = []
    for label, key in (
        ("Latest benchmark", "latest_benchmark"),
        ("Benchmark gate", "benchmark_gate_label"),
        ("Benchmark summary", "benchmark_summary"),
        ("Latest snapshot", "latest_snapshot"),
        ("Latest sandbox run", "latest_sandbox_run"),
        ("Latest remote smoke", "latest_remote_smoke"),
    ):
        val = artifacts.get(key)
        artifacts_rows.append(
            f'<li><span class="meta">{_esc(label)}:</span> '
            f'<code>{_esc(val) if val else "(none)"}</code></li>'
        )
    artifacts_block = (
        f'<h2>Artifacts</h2><div class="card"><ul class="files">{"".join(artifacts_rows)}</ul></div>'
    )

    body = top + approval_line + doctor_block + brain_block + iv_block + mem_block + artifacts_block
    return _page("LACP system status", body, subtitle=f"generated {generated}")


# ---------- quality scorecard renderer (session quality from lacp-eval --json) ----------

def render_quality(payload: dict) -> str:
    """Render a session-quality scorecard payload to HTML."""
    days = payload.get("window_days", 0)
    sessions = payload.get("sessions", 0)
    stop_events = payload.get("stop_events", 0)
    dim = payload.get("dimensions") or {}
    trend = payload.get("trend") or {}

    pass_rate = float(dim.get("quality_gate_pass_rate", 0) or 0)
    pass_kind = "good" if pass_rate >= 95 else ("warn" if pass_rate >= 80 else "bad")

    blocks = int(dim.get("blocks", 0) or 0)
    test_failures = int(dim.get("test_failures", 0) or 0)
    avg_sig = float(dim.get("avg_significance", 0) or 0)
    avg_files = float(dim.get("avg_files_per_episode", 0) or 0)
    handoffs = int(dim.get("handoff_artifacts", 0) or 0)
    episodes = int(dim.get("episodes_recorded", 0) or 0)

    direction = trend.get("direction") or "insufficient_data"
    trend_arrow = {"improving": "▲", "degrading": "▼", "stable": "—"}.get(direction, "?")
    trend_cls = {"improving": "trend-up", "degrading": "trend-down"}.get(direction, "trend-flat")
    delta = trend.get("delta", 0)

    top = (
        '<div class="grid">'
        + _kpi("Window (days)", days)
        + _kpi("Sessions", sessions)
        + _kpi("Stop events", stop_events)
        + _kpi("Trend",
               f'<span class="{trend_cls}">{trend_arrow} {_esc(direction)} ({delta:+.3f})</span>')
        + '</div>'
    )

    pass_visual = (
        f'<div class="kpi"><div class="label">Quality gate pass rate</div>'
        f'<div class="value {pass_kind}">{pass_rate:.1f}% {_bar(pass_rate)}</div></div>'
    )

    dims = (
        '<h2>Dimensions</h2><div class="grid">'
        + pass_visual
        + _kpi("Blocks", blocks, "bad" if blocks else "")
        + _kpi("Test failures", test_failures, "bad" if test_failures else "")
        + _kpi("Avg significance", f"{avg_sig:.3f}")
        + _kpi("Avg files / episode", f"{avg_files:.1f}")
        + _kpi("Handoff artifacts", handoffs, "warn" if handoffs == 0 else "")
        + _kpi("Episodes recorded", episodes)
        + '</div>'
    )

    # Recommendation logic mirrors lacp-eval text-mode for consistency
    recs = []
    if pass_rate < 95 and stop_events > 0:
        recs.append("Quality gate blocking >5% of stops — review threshold or heuristic patterns")
    if avg_sig < 0.3 and episodes > 5:
        recs.append("Low average significance — sessions may lack focus. Update focus brief.")
    if handoffs == 0:
        recs.append("No handoff artifacts — context may be lost between sessions")
    if episodes == 0:
        recs.append("No SMS episodes — stop hook may not have SMS integration enabled")
    if direction == "degrading":
        recs.append("Significance trending down — check if work is becoming routine")

    recs_block = ""
    if recs:
        items = "".join(f"<li>{_esc(r)}</li>" for r in recs)
        recs_block = f'<h2>Recommendations</h2><div class="card"><ul class="recs">{items}</ul></div>'

    body = top + dims + recs_block
    return _page("LACP session quality", body, subtitle=f"{days}-day window")


# ---------- CLI ----------

_RENDERERS = {
    "handoff": render_handoff,
    "status": render_status,
    "quality": render_quality,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render LACP artifacts to HTML")
    parser.add_argument("kind", choices=sorted(_RENDERERS.keys()),
                        help="Artifact kind to render")
    parser.add_argument("--in", dest="infile", default=None,
                        help="JSON input file (default: stdin)")
    parser.add_argument("--out", dest="outfile", default=None,
                        help="HTML output file (default: stdout)")
    args = parser.parse_args(argv)

    if args.infile:
        raw = Path(args.infile).read_text()
    else:
        raw = sys.stdin.read()

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(f"render_html: invalid JSON: {e}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("render_html: expected JSON object at top level", file=sys.stderr)
        return 2

    html_out = _RENDERERS[args.kind](payload)

    if args.outfile:
        out = Path(args.outfile)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_out)
    else:
        sys.stdout.write(html_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
