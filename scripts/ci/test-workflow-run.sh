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
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage developer --actor developer >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage verifier --actor verifier --decision approve >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage tester --actor tester --decision approve >/dev/null
"${ROOT}/bin/lacp-workflow-run" advance --run-id "${run_id}" --stage reviewer --actor reviewer --decision approve >/dev/null

status="$("${ROOT}/bin/lacp-workflow-run" status --run-id "${run_id}" --json)"
if [[ "$(echo "${status}" | jq -r '.status')" != "completed" ]]; then
  echo "[workflow-run-test] FAIL expected completed workflow" >&2
  exit 1
fi

echo "[workflow-run-test] workflow run tests passed"
