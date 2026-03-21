#!/usr/bin/env bash
set -euo pipefail

session="${LACP_ORCH_SESSION_NAME:-}"
command_text="${LACP_ORCH_COMMAND:-}"
dry_run="${LACP_ORCH_DRY_RUN:-false}"

[[ -n "${session}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_SESSION_NAME" >&2; exit 12; }
[[ -n "${command_text}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_COMMAND" >&2; exit 12; }

if [[ "${dry_run}" == "true" ]]; then
  jq -n \
    --arg backend "tmux" \
    --arg session "${session}" \
    --arg command "${command_text}" \
    '{ok:true,dry_run:true,backend:$backend,session:$session,command:$command}'
  exit 0
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "[lacp] ERROR: tmux not found in PATH" >&2
  exit 12
fi

# When LACP_RESULT_COLLECT=1, wrap the session command with result-collector
# so results are captured when the detached session command completes.
if [[ "${LACP_RESULT_COLLECT:-0}" == "1" ]]; then
  collector="$(dirname "${BASH_SOURCE[0]}")/result-collector.sh"
  # Use printf %q to safely escape command_text and session for shell evaluation
  escaped_cmd="$(printf '%q' "${command_text}")"
  escaped_session="$(printf '%q' "${session}")"
  tmux new-session -d -s "${session}" "${collector} --runner tmux --task-id ${escaped_session} -- ${escaped_cmd}"
else
  tmux new-session -d -s "${session}" -- "${command_text}"
fi
echo "[lacp] tmux session started: ${session}"

