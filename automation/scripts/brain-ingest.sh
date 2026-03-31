#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "${DELEGATE_ARGS_FILE}"
echo "delegate-ok"
