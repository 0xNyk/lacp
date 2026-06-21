#!/usr/bin/env bash
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SELF_DIR}/../.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/lacp-lib.sh"

RUNS_DIR="${HOME}/.lacp/runs"
RESULTS_FILE="${RUNS_DIR}/results.jsonl"

usage() {
  cat <<'EOF'
Usage:
  result-collector.sh [--runner NAME] [--task-id ID] -- <command> [args...]

Wraps a command invocation and captures structured results to ~/.lacp/runs/results.jsonl.

Options:
  --runner NAME    Runner name for metadata (default: "unknown")
  --task-id ID     Task/session ID for metadata (default: "")
  --               End of options; everything after is the command to run

Receipt schema:
  { run_id, runner, task_id, exit_code, stdout_tail, stderr_tail,
    started_at, ended_at, duration_ms, agent_id }
EOF
}

RUNNER_NAME="unknown"
TASK_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runner) RUNNER_NAME="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [[ $# -eq 0 ]]; then
  die "No command provided. Use: result-collector.sh [opts] -- <command> [args...]"
fi

mkdir -p "${RUNS_DIR}"

RUN_ID="run-$(date +%s)-$$"
AGENT_ID="${LACP_AGENT_ID:-unknown}"

STDOUT_TMP="$(mktemp)"
STDERR_TMP="$(mktemp)"
trap 'rm -f "${STDOUT_TMP}" "${STDERR_TMP}"' EXIT

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"

EXIT_CODE=0
"$@" >"${STDOUT_TMP}" 2>"${STDERR_TMP}" || EXIT_CODE=$?

END_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DURATION_MS=$(( END_MS - START_MS ))

STDOUT_TAIL="$(tail -500 "${STDOUT_TMP}")"
STDERR_TAIL="$(tail -100 "${STDERR_TMP}")"

jq -cn \
  --arg run_id "${RUN_ID}" \
  --arg runner "${RUNNER_NAME}" \
  --arg task_id "${TASK_ID}" \
  --argjson exit_code "${EXIT_CODE}" \
  --arg stdout_tail "${STDOUT_TAIL}" \
  --arg stderr_tail "${STDERR_TAIL}" \
  --arg started_at "${STARTED_AT}" \
  --arg ended_at "${ENDED_AT}" \
  --argjson duration_ms "${DURATION_MS}" \
  --arg agent_id "${AGENT_ID}" \
  '{run_id:$run_id,runner:$runner,task_id:$task_id,exit_code:$exit_code,stdout_tail:$stdout_tail,stderr_tail:$stderr_tail,started_at:$started_at,ended_at:$ended_at,duration_ms:$duration_ms,agent_id:$agent_id}' \
  >> "${RESULTS_FILE}"

log "result-collector: run_id=${RUN_ID} exit_code=${EXIT_CODE} duration_ms=${DURATION_MS}"
