#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RETENTION_DAYS="${1:-45}"
LOG_FILE="/Users/nyk/control/knowledge/knowledge-memory/data/hygiene/quarantine-maintenance.log"
mkdir -p /Users/nyk/control/knowledge/knowledge-memory/data/hygiene

python3 "${SCRIPT_DIR}/prune_agent_quarantine.py" --days "${RETENTION_DAYS}" \
  >> "${LOG_FILE}" 2>&1
python3 "${SCRIPT_DIR}/prune_agent_quarantine.py" --days "${RETENTION_DAYS}" --apply \
  >> "${LOG_FILE}" 2>&1
