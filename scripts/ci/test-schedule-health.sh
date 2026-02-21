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

PLIST_PATH="${TMP}/com.lacp.test-health.plist"
RUNNER_PATH="${TMP}/lacp-health-check.sh"
LABEL="com.lacp.test-health"

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter --with-verify --hours 1 >/dev/null

install_json="$("/bin/bash" "${ROOT}/bin/lacp-schedule-health" install \
  --label "${LABEL}" \
  --plist "${PLIST_PATH}" \
  --runner "${RUNNER_PATH}" \
  --interval-min 15 \
  --skip-load \
  --json)"

[[ "$(echo "${install_json}" | jq -r '.ok')" == "true" ]] || { echo "[schedule-health-test] FAIL install not ok" >&2; exit 1; }
[[ -f "${PLIST_PATH}" ]] || { echo "[schedule-health-test] FAIL missing plist" >&2; exit 1; }
[[ -x "${RUNNER_PATH}" ]] || { echo "[schedule-health-test] FAIL missing runner" >&2; exit 1; }

run_json="$("/bin/bash" "${ROOT}/bin/lacp-schedule-health" run-now \
  --label "${LABEL}" \
  --plist "${PLIST_PATH}" \
  --runner "${RUNNER_PATH}" \
  --json)"
[[ "$(echo "${run_json}" | jq -r '.ok')" == "true" ]] || { echo "[schedule-health-test] FAIL run-now not ok" >&2; exit 1; }
[[ -f "${LACP_KNOWLEDGE_ROOT}/data/health/latest-doctor.json" ]] || { echo "[schedule-health-test] FAIL missing latest doctor artifact" >&2; exit 1; }
[[ -f "${LACP_KNOWLEDGE_ROOT}/data/health/latest-report.json" ]] || { echo "[schedule-health-test] FAIL missing latest report artifact" >&2; exit 1; }
[[ -f "${LACP_KNOWLEDGE_ROOT}/data/health/latest-status.json" ]] || { echo "[schedule-health-test] FAIL missing latest status artifact" >&2; exit 1; }

status_json="$("/bin/bash" "${ROOT}/bin/lacp-schedule-health" status --label "${LABEL}" --plist "${PLIST_PATH}" --runner "${RUNNER_PATH}" --json)"
[[ "$(echo "${status_json}" | jq -r '.installed')" == "true" ]] || { echo "[schedule-health-test] FAIL status should report installed" >&2; exit 1; }

uninstall_json="$("/bin/bash" "${ROOT}/bin/lacp-schedule-health" uninstall \
  --label "${LABEL}" \
  --plist "${PLIST_PATH}" \
  --runner "${RUNNER_PATH}" \
  --skip-load \
  --json)"
[[ "$(echo "${uninstall_json}" | jq -r '.ok')" == "true" ]] || { echo "[schedule-health-test] FAIL uninstall not ok" >&2; exit 1; }
[[ ! -f "${PLIST_PATH}" ]] || { echo "[schedule-health-test] FAIL plist still present after uninstall" >&2; exit 1; }

echo "[schedule-health-test] schedule health tests passed"
