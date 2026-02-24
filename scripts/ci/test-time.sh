#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_TIME_TRACKING_ROOT="${TMP}/knowledge/data/time-tracking"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

start_json="$("${ROOT}/bin/lacp-time" start --project "${TMP}/clients/acme/app-a" --client client-a --session s1 --json)"
echo "${start_json}" | jq -e '.ok == true' >/dev/null

active_json="$("${ROOT}/bin/lacp-time" active --json)"
echo "${active_json}" | jq -e '.active_count == 1' >/dev/null

stop_json="$("${ROOT}/bin/lacp-time" stop --session s1 --json)"
echo "${stop_json}" | jq -e '.ok == true' >/dev/null
echo "${stop_json}" | jq -e '.session.project == "'"${TMP}/clients/acme/app-a"'"' >/dev/null
echo "${stop_json}" | jq -e '.session.client == "client-a"' >/dev/null

"${ROOT}/bin/lacp-time" start --project "${TMP}/projects/lacp-core" --session s2 --json >/dev/null
"${ROOT}/bin/lacp-time" stop --session s2 --json >/dev/null
"${ROOT}/bin/lacp-time" start --project "${TMP}/experiments/rag-eval" --session s3 --json >/dev/null
"${ROOT}/bin/lacp-time" stop --session s3 --json >/dev/null

month="$(date -u +%Y-%m)"
report_json="$("${ROOT}/bin/lacp-time" report --month "${month}" --json)"
echo "${report_json}" | jq -e '.ok == true' >/dev/null
echo "${report_json}" | jq -e '.summary.sessions == 3' >/dev/null
echo "${report_json}" | jq -e '.directory_split.clients[0].name == "acme"' >/dev/null
echo "${report_json}" | jq -e '.directory_split.projects[0].name == "lacp-core"' >/dev/null
echo "${report_json}" | jq -e '.directory_split.experiments[0].name == "rag-eval"' >/dev/null

report_ops="$("${ROOT}/bin/lacp-report" --hours 24 --json)"
echo "${report_ops}" | jq -e '.time_tracking.month == "'"${month}"'"' >/dev/null
echo "${report_ops}" | jq -e '.time_tracking.sessions == 3' >/dev/null
echo "${report_ops}" | jq -e '.time_tracking.directory_split.clients[0].name == "acme"' >/dev/null

echo "[time-test] time tracking tests passed"
