#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RENDERER="${ROOT}/automation/scripts/render_html.py"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1

assert_html() {
  local file="$1" needle="$2"
  [[ -f "${file}" ]] || { echo "[html-render] FAIL: missing file ${file}"; exit 1; }
  head -c 50 "${file}" | grep -q '^<!doctype html>' || {
    echo "[html-render] FAIL: ${file} missing doctype"; exit 1; }
  grep -q "${needle}" "${file}" || {
    echo "[html-render] FAIL: ${file} missing expected content '${needle}'"; exit 1; }
}

# ---------- 1. Direct renderer: handoff ----------
cat >"${TMP}/handoff.json" <<'JSON'
{
  "task_summary": "render_html.py smoke fixture",
  "files_modified": ["bin/lacp-handoff", "automation/scripts/render_html.py"],
  "open_issues": ["wire ci test"],
  "next_steps": ["land it"],
  "test_status": "pass",
  "git_branch": "feat/html-renderer",
  "git_diff_summary": " bin/lacp-handoff | 60 +++",
  "created_at": "2026-05-16T10:00:00Z"
}
JSON
python3 "${RENDERER}" handoff --in "${TMP}/handoff.json" --out "${TMP}/handoff.html"
assert_html "${TMP}/handoff.html" "render_html.py smoke fixture"
assert_html "${TMP}/handoff.html" "feat/html-renderer"

# ---------- 2. Direct renderer: status ----------
cat >"${TMP}/status.json" <<'JSON'
{
  "generated_at_utc": "2026-05-16T10:00:00Z",
  "ok": true,
  "mode": "standard",
  "allow_external_remote": "false",
  "remote_provider": "daytona",
  "remote_approval": {"valid": "false", "expires_at_utc": ""},
  "doctor": {"ok": true, "pass": 12, "warn": 0, "fail": 0},
  "brain":  {"ok": "unknown", "pass": 0, "warn": 0, "fail": 0},
  "intervention_rate": {
    "current_window":  {"intervention_rate_per_100": 0, "total_runs": 0},
    "baseline_window": {"intervention_rate_per_100": 0, "total_runs": 0},
    "delta": {"absolute": 0}
  },
  "memory_kpi": {"kpis": {"total_notes": 5, "canonical_notes": 1,
    "required_schema_coverage_pct": 80, "source_backed_pct": 40,
    "contradiction_notes": 0, "stale_notes": 1}},
  "artifacts": {}
}
JSON
python3 "${RENDERER}" status --in "${TMP}/status.json" --out "${TMP}/status.html"
assert_html "${TMP}/status.html" "LACP system status"
assert_html "${TMP}/status.html" "Doctor"
# Status pills must render as real markup, not appear double-escaped as text.
if grep -q '&lt;span class="pill' "${TMP}/status.html"; then
  echo "[html-render] FAIL: status pills are double-escaped (rendered as literal text)"
  exit 1
fi
grep -q '<span class="pill good">OK</span>' "${TMP}/status.html" || {
  echo "[html-render] FAIL: expected an unescaped status pill in output"; exit 1; }

# ---------- 3. Direct renderer: quality ----------
cat >"${TMP}/quality.json" <<'JSON'
{
  "window_days": 7,
  "sessions": 3,
  "stop_events": 10,
  "dimensions": {
    "quality_gate_pass_rate": 90.0,
    "blocks": 1,
    "test_failures": 0,
    "avg_significance": 0.42,
    "avg_files_per_episode": 4.2,
    "handoff_artifacts": 0,
    "episodes_recorded": 12
  },
  "trend": {"direction": "improving", "delta": 0.08}
}
JSON
python3 "${RENDERER}" quality --in "${TMP}/quality.json" --out "${TMP}/quality.html"
assert_html "${TMP}/quality.html" "session quality"
assert_html "${TMP}/quality.html" "Recommendations"

# ---------- 4. HTML-escaping guard ----------
cat >"${TMP}/inject.json" <<'JSON'
{"task_summary": "<script>alert(1)</script>", "files_modified": [],
 "test_status": "pass", "git_branch": "x", "created_at": "2026-05-16T10:00:00Z"}
JSON
python3 "${RENDERER}" handoff --in "${TMP}/inject.json" --out "${TMP}/inject.html"
if grep -q '<script>alert(1)</script>' "${TMP}/inject.html"; then
  echo "[html-render] FAIL: handoff renderer did not escape injected script tag"
  exit 1
fi
grep -q '&lt;script&gt;alert(1)&lt;/script&gt;' "${TMP}/inject.html" || {
  echo "[html-render] FAIL: expected escaped script tag in output"; exit 1; }

# ---------- 5. CLI integration: lacp-handoff html ----------
mkdir -p "${TMP}/home/.lacp/handoffs"
cwd_hash="$(echo -n "$(pwd)" | shasum -a 256 | cut -c1-12)"
cp "${TMP}/handoff.json" "${TMP}/home/.lacp/handoffs/${cwd_hash}-latest.json"
HOME="${TMP}/home" "${ROOT}/bin/lacp-handoff" html --out "${TMP}/cli-handoff.html" >/dev/null
assert_html "${TMP}/cli-handoff.html" "render_html.py smoke fixture"

json_out="$(HOME="${TMP}/home" "${ROOT}/bin/lacp-handoff" html --json)"
echo "${json_out}" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["ok"] and d["path"].endswith(".html")'

# ---------- 6. CLI integration: lacp-eval --html ----------
HOME="${TMP}/home" "${ROOT}/bin/lacp-eval" --html --out "${TMP}/cli-quality.html" >/dev/null
assert_html "${TMP}/cli-quality.html" "session quality"

# ---------- 7. CLI integration: lacp-eval (text + json paths still work) ----------
HOME="${TMP}/home" "${ROOT}/bin/lacp-eval" --days 1 >/dev/null
HOME="${TMP}/home" "${ROOT}/bin/lacp-eval" --days 1 --json | jq -e '.window_days == 1' >/dev/null

echo "[html-render] all html renderer tests passed"
