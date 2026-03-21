#!/usr/bin/env bash
set -euo pipefail

session="${LACP_ORCH_SESSION_NAME:-}"
command_text="${LACP_ORCH_COMMAND:-}"
dry_run="${LACP_ORCH_DRY_RUN:-false}"
use_tmux="${LACP_CLAUDE_WORKTREE_USE_TMUX:-false}"
run_template="${LACP_CLAUDE_WORKTREE_TEMPLATE:-}"
prompt_prefix="${LACP_ORCH_PROMPT_PREFIX:-}"

[[ -n "${session}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_SESSION_NAME" >&2; exit 12; }
[[ -n "${command_text}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_COMMAND" >&2; exit 12; }
[[ "${use_tmux}" == "true" || "${use_tmux}" == "false" ]] || { echo "[lacp] ERROR: LACP_CLAUDE_WORKTREE_USE_TMUX must be true|false" >&2; exit 12; }

if [[ "${use_tmux}" == "true" ]]; then
  tmux_flag=" --tmux"
else
  tmux_flag=""
fi

system_prompt_flag=""
if [[ -n "${prompt_prefix}" ]]; then
  system_prompt_flag=' --system-prompt "{prompt_prefix}"'
fi

if [[ -z "${run_template}" ]]; then
  run_template='claude --worktree "{session}"{tmux_flag}{system_prompt_flag} --print "{command}"'
fi

# Escape values to prevent shell injection (C2: CWE-78)
escaped_session="$(printf '%q' "${session}")"
escaped_command="$(printf '%q' "${command_text}")"
escaped_prompt_prefix="$(printf '%q' "${prompt_prefix}")"

rendered="${run_template//\{session\}/${escaped_session}}"
rendered="${rendered//\{command\}/${escaped_command}}"
rendered="${rendered//\{tmux_flag\}/${tmux_flag}}"
rendered="${rendered//\{system_prompt_flag\}/${system_prompt_flag}}"
rendered="${rendered//\{prompt_prefix\}/${escaped_prompt_prefix}}"

if [[ "${dry_run}" == "true" ]]; then
  jq -n \
    --arg backend "claude_worktree" \
    --arg session "${session}" \
    --arg command "${command_text}" \
    --arg rendered "${rendered}" \
    --argjson use_tmux "$( [[ "${use_tmux}" == "true" ]] && echo true || echo false )" \
    '{ok:true,dry_run:true,backend:$backend,session:$session,command:$command,use_tmux:$use_tmux,rendered:$rendered}'
  exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "[lacp] ERROR: claude not found in PATH" >&2
  exit 12
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[lacp] ERROR: current directory is not a git worktree" >&2
  exit 12
fi

if [[ "${LACP_RESULT_COLLECT:-0}" == "1" ]]; then
  collector="$(dirname "${BASH_SOURCE[0]}")/result-collector.sh"
  "${collector}" --runner claude_worktree --task-id "${session}" -- /usr/bin/env bash -lc "${rendered}"
else
  /usr/bin/env bash -lc "${rendered}"
fi
echo "[lacp] claude worktree command executed"
