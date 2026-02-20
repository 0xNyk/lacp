#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: e2b-runner.sh -- <command> [args...]

Current mode:
- Executes inside an existing E2B sandbox.

Required env:
- E2B_SANDBOX_ID=<sandbox-id>

Optional env:
- E2B_CLI_BIN=<path-to-e2b-cli>   (default: e2b)

Notes:
- This runner intentionally avoids interactive sandbox creation flows.
- For full lifecycle (create/exec/delete), wire non-interactive create once your e2b CLI is configured for it.
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$1" != "--" ]]; then
  echo "[e2b-runner] expected '--' before command" >&2
  exit 1
fi
shift

if [[ $# -eq 0 ]]; then
  echo "[e2b-runner] missing command" >&2
  exit 1
fi

E2B_CLI_BIN="${E2B_CLI_BIN:-e2b}"
command -v "${E2B_CLI_BIN}" >/dev/null 2>&1 || {
  echo "[e2b-runner] e2b CLI not found. Install and authenticate first." >&2
  exit 2
}

E2B_SANDBOX_ID="${E2B_SANDBOX_ID:-}"
if [[ -z "${E2B_SANDBOX_ID}" ]]; then
  echo "[e2b-runner] E2B_SANDBOX_ID is required in current mode" >&2
  exit 3
fi

exec "${E2B_CLI_BIN}" sandbox exec "${E2B_SANDBOX_ID}" -- "$@"
