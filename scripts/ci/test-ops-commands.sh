#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[ops-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[ops-test] PASS ${label}: ${actual}"
}

AUTOMATION_ROOT="${TMP}/automation"
KNOWLEDGE_ROOT="${TMP}/knowledge"
DRAFTS_ROOT="${TMP}/drafts"

mkdir -p "${AUTOMATION_ROOT}" "${KNOWLEDGE_ROOT}" "${DRAFTS_ROOT}"

export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${AUTOMATION_ROOT}"
export LACP_KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT}"
export LACP_KNOWLEDGE_GRAPH_ROOT="${KNOWLEDGE_ROOT}"
export LACP_DRAFTS_ROOT="${DRAFTS_ROOT}"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"

# doctor --fix should create required scaffolding and succeed when starter scripts exist.
"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter --with-verify --hours 1 >/dev/null
"/bin/bash" "${ROOT}/bin/lacp-doctor" --fix --json | jq -e '.ok == true' >/dev/null
echo "[ops-test] PASS doctor.fix"

# report should return structured output with run metrics.
report_json="$("/bin/bash" "${ROOT}/bin/lacp-report" --hours 24 --json)"
assert_eq "$(echo "${report_json}" | jq -r '.window_hours')" "24" "report.window_hours"
assert_eq "$(echo "${report_json}" | jq -r '.runs.total >= 0')" "true" "report.runs.total"

# migrate should dry-run and apply env settings.
migrate_preview="$("/bin/bash" "${ROOT}/bin/lacp-migrate" --automation-root "${AUTOMATION_ROOT}" --knowledge-root "${KNOWLEDGE_ROOT}" --drafts-root "${DRAFTS_ROOT}" --json)"
assert_eq "$(echo "${migrate_preview}" | jq -r '.apply')" "false" "migrate.preview.apply"

migrate_apply="$("/bin/bash" "${ROOT}/bin/lacp-migrate" --automation-root "${AUTOMATION_ROOT}" --knowledge-root "${KNOWLEDGE_ROOT}" --drafts-root "${DRAFTS_ROOT}" --apply --json)"
assert_eq "$(echo "${migrate_apply}" | jq -r '.apply')" "true" "migrate.apply.apply"

echo "[ops-test] ops commands tests passed"
