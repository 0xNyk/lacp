#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p \
  "${LACP_AUTOMATION_ROOT}/data/snapshots" \
  "${LACP_KNOWLEDGE_ROOT}/data/sandbox-runs" \
  "${LACP_KNOWLEDGE_ROOT}/data/benchmarks" \
  "${LACP_DRAFTS_ROOT}"

json_out="$("${ROOT}/bin/lacp-automations-tui" --offline --json)"
echo "${json_out}" | jq -e '.kind == "automations_tui"' >/dev/null
echo "${json_out}" | jq -e '.automations.schedule_health != null' >/dev/null
echo "${json_out}" | jq -e '.automations.orchestrate != null' >/dev/null
echo "${json_out}" | jq -e '.automations.vendor_watch.offline == true' >/dev/null
echo "${json_out}" | jq -e '.summary.vendor_degraded == true' >/dev/null
echo "${json_out}" | jq -e '.summary.vendor_source_groups_total >= 4' >/dev/null
echo "${json_out}" | jq -e '.summary.vendor_claude_sources_ok == false' >/dev/null
echo "${json_out}" | jq -e '.summary.vendor_codex_sources_ok == false' >/dev/null

text_out="$("${ROOT}/bin/lacp-automations-tui" --offline)"
echo "${text_out}" | rg -q "LACP Automations TUI"
echo "${text_out}" | rg -q "Automation Inventory"
echo "${text_out}" | rg -q "^ALERT: vendor sources degraded"
echo "${text_out}" | rg -q "vendor health: status=DEGRADED"

echo "[automations-tui-test] automations tui tests passed"
