#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV="1"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
mkdir -p "${LACP_KNOWLEDGE_ROOT}"

run_id="$("${ROOT}/bin/lacp-workflow-run" init --task "Add OAuth auth" --project auth --json | jq -r '.run_id')"
if [[ -z "${run_id}" ]]; then
  echo "[workflow-run-test] FAIL missing run_id" >&2
  exit 1
fi

# Wrong actor should fail.
set +e
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage planner --actor developer >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[workflow-run-test] FAIL expected wrong-actor advance to fail" >&2
  exit 1
fi

"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage planner --actor planner >/dev/null
plan_token="$("${ROOT}/bin/lacp-workflow-run" status --run-id "${run_id}" --json | jq -r '.contracts.plan_act.token')"
if [[ -z "${plan_token}" || "${plan_token}" == "null" ]]; then
  echo "[workflow-run-test] FAIL expected planner to issue plan token" >&2
  exit 1
fi

# Missing token should fail.
set +e
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage developer --actor developer >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[workflow-run-test] FAIL expected developer stage without plan token to fail" >&2
  exit 1
fi

# Wrong token should fail.
set +e
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage developer --actor developer --plan-token "plan-wrong" >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[workflow-run-test] FAIL expected developer stage with wrong plan token to fail" >&2
  exit 1
fi

"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage developer --actor developer --plan-token "${plan_token}" >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage verifier --actor verifier --decision approve >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage tester --actor tester --decision approve >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage reviewer --actor reviewer --decision approve >/dev/null

status="$("${ROOT}/bin/lacp-workflow-run" status --run-id "${run_id}" --json)"
if [[ "$(echo "${status}" | jq -r '.status')" != "completed" ]]; then
  echo "[workflow-run-test] FAIL expected completed workflow" >&2
  exit 1
fi
if [[ "$(echo "${status}" | jq -r '.stages[] | select(.name=="developer") | .plan_token_used')" != "${plan_token}" ]]; then
  echo "[workflow-run-test] FAIL expected developer stage to record plan_token_used" >&2
  exit 1
fi

# Explicit bypass path should work and be recorded.
run_id_bypass="$("${ROOT}/bin/lacp-workflow-run" init --task "Bypass contract path" --project auth --json | jq -r '.run_id')"
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id_bypass}" --stage planner --actor planner >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id_bypass}" --stage developer --actor developer --allow-unplanned true >/dev/null
bypass_status="$("${ROOT}/bin/lacp-workflow-run" status --run-id "${run_id_bypass}" --json)"
if [[ "$(echo "${bypass_status}" | jq -r '.stages[] | select(.name=="developer") | .allow_unplanned')" != "true" ]]; then
  echo "[workflow-run-test] FAIL expected developer allow_unplanned=true to be recorded" >&2
  exit 1
fi

echo "[workflow-run-test] workflow run tests passed"
