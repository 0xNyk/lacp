#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: daytona-runner.sh -- <command> [args...]

Requires:
- daytona CLI installed
- authenticated profile (`daytona login`)

Environment (optional):
- LACP_DAYTONA_NAME_PREFIX      (default: lacp-remote)
- LACP_DAYTONA_CLASS            (default: small)
- LACP_DAYTONA_TARGET           (optional region, e.g. us/eu)
- LACP_DAYTONA_SNAPSHOT         (optional snapshot)
- LACP_DAYTONA_NETWORK_BLOCK_ALL (true|false, default: false)
- LACP_DAYTONA_NETWORK_ALLOW_LIST (optional CIDR list)
- LACP_DAYTONA_AUTO_STOP_MIN    (default: 15)
- LACP_DAYTONA_AUTO_ARCHIVE_MIN (default: 10080)
- LACP_DAYTONA_AUTO_DELETE_MIN  (default: 0)
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
  echo "[daytona-runner] expected '--' before command" >&2
  exit 1
fi
shift

if [[ $# -eq 0 ]]; then
  echo "[daytona-runner] missing command" >&2
  exit 1
fi

command -v daytona >/dev/null 2>&1 || {
  echo "[daytona-runner] daytona CLI not found" >&2
  exit 1
}

if ! daytona list --format json >/dev/null 2>&1; then
  echo "[daytona-runner] daytona is not authenticated. Run: daytona login" >&2
  exit 2
fi

NAME_PREFIX="${LACP_DAYTONA_NAME_PREFIX:-lacp-remote}"
CLASS="${LACP_DAYTONA_CLASS:-small}"
TARGET="${LACP_DAYTONA_TARGET:-}"
SNAPSHOT="${LACP_DAYTONA_SNAPSHOT:-}"
NETWORK_BLOCK_ALL="${LACP_DAYTONA_NETWORK_BLOCK_ALL:-false}"
NETWORK_ALLOW_LIST="${LACP_DAYTONA_NETWORK_ALLOW_LIST:-}"
AUTO_STOP_MIN="${LACP_DAYTONA_AUTO_STOP_MIN:-15}"
AUTO_ARCHIVE_MIN="${LACP_DAYTONA_AUTO_ARCHIVE_MIN:-10080}"
AUTO_DELETE_MIN="${LACP_DAYTONA_AUTO_DELETE_MIN:-0}"

RUN_TAG="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
SANDBOX_NAME="${NAME_PREFIX}-${RUN_TAG}"

cleanup() {
  daytona delete "${SANDBOX_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

create_args=(
  create
  --name "${SANDBOX_NAME}"
  --class "${CLASS}"
  --auto-stop "${AUTO_STOP_MIN}"
  --auto-archive "${AUTO_ARCHIVE_MIN}"
  --auto-delete "${AUTO_DELETE_MIN}"
)

if [[ -n "${TARGET}" ]]; then
  create_args+=(--target "${TARGET}")
fi
if [[ -n "${SNAPSHOT}" ]]; then
  create_args+=(--snapshot "${SNAPSHOT}")
fi
if [[ "${NETWORK_BLOCK_ALL}" == "true" ]]; then
  create_args+=(--network-block-all)
fi
if [[ -n "${NETWORK_ALLOW_LIST}" ]]; then
  create_args+=(--network-allow-list "${NETWORK_ALLOW_LIST}")
fi

echo "[daytona-runner] creating sandbox: ${SANDBOX_NAME}" >&2
daytona "${create_args[@]}" >/dev/null

echo "[daytona-runner] executing command in sandbox: ${SANDBOX_NAME}" >&2
daytona exec "${SANDBOX_NAME}" -- "$@"
