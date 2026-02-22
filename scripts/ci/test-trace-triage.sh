#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter >/dev/null

# Generate deterministic blocked traces for clustering.
set +e
"/bin/bash" "${ROOT}/bin/lacp-sandbox-run" --task "triage ctx missing" --repo-trust trusted -- /bin/mkdir -p "${TMP}/ctx-missing" >/dev/null
ctx_rc=$?
"/bin/bash" "${ROOT}/bin/lacp-sandbox-run" --task "triage budget block" --repo-trust trusted --estimated-cost-usd 2 -- /bin/echo should-block >/dev/null
budget_rc=$?
set -e

if [[ "${ctx_rc}" -ne 12 ]]; then
  echo "[trace-triage-test] FAIL expected context gate rc=12, got ${ctx_rc}" >&2
  exit 1
fi
if [[ "${budget_rc}" -ne 10 ]]; then
  echo "[trace-triage-test] FAIL expected budget gate rc=10, got ${budget_rc}" >&2
  exit 1
fi

triage_json="$("/bin/bash" "${ROOT}/bin/lacp-trace-triage" --hours 24 --json)"
echo "${triage_json}" | jq -e '.kind == "trace_triage"' >/dev/null
echo "${triage_json}" | jq -e '.summary.failed_runs >= 2' >/dev/null
echo "${triage_json}" | jq -e '.clusters | map(.cause) | index("context_drift") != null' >/dev/null
echo "${triage_json}" | jq -e '.clusters | map(.cause) | index("policy_block") != null' >/dev/null
echo "${triage_json}" | jq -e '.recommendations | length >= 1' >/dev/null

echo "[trace-triage-test] trace triage tests passed"

