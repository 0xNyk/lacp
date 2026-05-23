#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RETENTION_DAYS="${1:-45}"
: "${LACP_KNOWLEDGE_ROOT:=${HOME}/.lacp/knowledge}"
HYGIENE_DIR="${LACP_HYGIENE_LOG_DIR:-${LACP_KNOWLEDGE_ROOT}/data/hygiene}"
LOG_FILE="${HYGIENE_DIR}/quarantine-maintenance.log"
mkdir -p "${HYGIENE_DIR}"

python3 "${SCRIPT_DIR}/prune_agent_quarantine.py" --days "${RETENTION_DAYS}" \
  >> "${LOG_FILE}" 2>&1
python3 "${SCRIPT_DIR}/prune_agent_quarantine.py" --days "${RETENTION_DAYS}" --apply \
  >> "${LOG_FILE}" 2>&1
