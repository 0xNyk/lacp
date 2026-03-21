#!/usr/bin/env bash
set -euo pipefail

session="${LACP_ORCH_SESSION_NAME:-}"
command_text="${LACP_ORCH_COMMAND:-}"
dry_run="${LACP_ORCH_DRY_RUN:-false}"
run_template="${LACP_DMUX_RUN_TEMPLATE:-}"

[[ -n "${session}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_SESSION_NAME" >&2; exit 12; }
[[ -n "${command_text}" ]] || { echo "[lacp] ERROR: missing LACP_ORCH_COMMAND" >&2; exit 12; }

if [[ "${dry_run}" == "true" ]]; then
  jq -n \
    --arg backend "dmux" \
    --arg session "${session}" \
    --arg command "${command_text}" \
    '{ok:true,dry_run:true,backend:$backend,session:$session,command:$command}'
  exit 0
fi

if ! command -v dmux >/dev/null 2>&1; then
  echo "[lacp] ERROR: dmux not found in PATH" >&2
  exit 12
fi

if [[ -z "${run_template}" ]]; then
  cat >&2 <<'EOF'
[lacp] ERROR: missing LACP_DMUX_RUN_TEMPLATE.
Set a template with placeholders {session} and {command}.
Example:
  export LACP_DMUX_RUN_TEMPLATE='dmux run --session "{session}" --command "{command}"'
EOF
  exit 12
fi

# Escape values to prevent shell injection (C2: CWE-78)
escaped_session="$(printf '%q' "${session}")"
escaped_command="$(printf '%q' "${command_text}")"

rendered="${run_template//\{session\}/${escaped_session}}"
rendered="${rendered//\{command\}/${escaped_command}}"

/usr/bin/env bash -lc "${rendered}"
echo "[lacp] dmux command executed"

