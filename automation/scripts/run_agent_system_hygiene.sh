#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${LACP_KNOWLEDGE_ROOT:=${HOME}/.lacp/knowledge}"
LOG_DIR="${LACP_HYGIENE_LOG_DIR:-${LACP_KNOWLEDGE_ROOT}/data/hygiene}"
mkdir -p "$LOG_DIR"

python3 "${SCRIPT_DIR}/audit_agent_system_layout.py" >> "$LOG_DIR/hygiene.log" 2>&1
