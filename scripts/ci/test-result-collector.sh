#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"
export LACP_SKIP_DOTENV=1
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_OBSIDIAN_VAULT}" "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

COLLECTOR="${ROOT}/scripts/runners/result-collector.sh"
RUNS_BIN="${ROOT}/bin/lacp-runs"

## --- test 1: basic echo command produces JSONL receipt ---
"${COLLECTOR}" --runner test --task-id task-001 -- echo hello >/dev/null
RESULTS_FILE="${HOME}/.lacp/runs/results.jsonl"
[[ -f "${RESULTS_FILE}" ]] || { echo "[result-collector-test] FAIL: results.jsonl not created" >&2; exit 1; }
echo "[result-collector-test] PASS: results.jsonl created"

## --- test 2: receipt has correct fields ---
receipt="$(tail -1 "${RESULTS_FILE}")"
echo "${receipt}" | jq -e '.run_id | startswith("run-")' >/dev/null \
  || { echo "[result-collector-test] FAIL: bad run_id format" >&2; exit 1; }
echo "${receipt}" | jq -e '.exit_code == 0' >/dev/null \
  || { echo "[result-collector-test] FAIL: exit_code should be 0" >&2; exit 1; }
echo "${receipt}" | jq -e '.runner == "test"' >/dev/null \
  || { echo "[result-collector-test] FAIL: runner field mismatch" >&2; exit 1; }
echo "${receipt}" | jq -e '.task_id == "task-001"' >/dev/null \
  || { echo "[result-collector-test] FAIL: task_id field mismatch" >&2; exit 1; }
echo "${receipt}" | jq -e '.duration_ms >= 0' >/dev/null \
  || { echo "[result-collector-test] FAIL: duration_ms should be >= 0" >&2; exit 1; }
echo "${receipt}" | jq -e '.stdout_tail | contains("hello")' >/dev/null \
  || { echo "[result-collector-test] FAIL: stdout_tail should contain 'hello'" >&2; exit 1; }
echo "[result-collector-test] PASS: receipt fields correct"

## --- test 3: failing command records exit_code=1 ---
"${COLLECTOR}" --runner test --task-id task-002 -- false >/dev/null 2>/dev/null || true
fail_receipt="$(tail -1 "${RESULTS_FILE}")"
echo "${fail_receipt}" | jq -e '.exit_code == 1' >/dev/null \
  || { echo "[result-collector-test] FAIL: exit_code should be 1 for false" >&2; exit 1; }
echo "[result-collector-test] PASS: failing command captured exit_code=1"

## --- test 4: lacp-runs list --json shows receipts ---
list_json="$("${RUNS_BIN}" list --json)"
echo "${list_json}" | jq -e '.ok == true' >/dev/null \
  || { echo "[result-collector-test] FAIL: lacp-runs list --json not ok" >&2; exit 1; }
run_count="$(echo "${list_json}" | jq '.count')"
[[ "${run_count}" -ge 2 ]] \
  || { echo "[result-collector-test] FAIL: expected >= 2 runs, got ${run_count}" >&2; exit 1; }
echo "[result-collector-test] PASS: lacp-runs list shows ${run_count} runs"

## --- test 5: lacp-runs status --json shows correct counts ---
status_json="$("${RUNS_BIN}" status --json)"
echo "${status_json}" | jq -e '.ok == true' >/dev/null \
  || { echo "[result-collector-test] FAIL: lacp-runs status not ok" >&2; exit 1; }
total="$(echo "${status_json}" | jq '.total')"
completed="$(echo "${status_json}" | jq '.completed')"
failed="$(echo "${status_json}" | jq '.failed')"
[[ "${total}" -ge 2 ]] \
  || { echo "[result-collector-test] FAIL: total should be >= 2, got ${total}" >&2; exit 1; }
[[ "${completed}" -ge 1 ]] \
  || { echo "[result-collector-test] FAIL: completed should be >= 1, got ${completed}" >&2; exit 1; }
[[ "${failed}" -ge 1 ]] \
  || { echo "[result-collector-test] FAIL: failed should be >= 1, got ${failed}" >&2; exit 1; }
echo "[result-collector-test] PASS: status total=${total} completed=${completed} failed=${failed}"

echo "[result-collector-test] all tests passed"
