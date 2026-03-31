#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Combined weekly maintenance — replaces 5 separate LaunchAgents:
#   agent-system.hygiene, quarantine-maintenance, vault-hygiene,
#   inbox-archive, threshold-recalibration

LOG_DIR="${HOME}/control/knowledge/knowledge-memory/data"
LOG_FILE="${LOG_DIR}/weekly-maintenance.log"
mkdir -p "${LOG_DIR}" "${LOG_DIR}/hygiene"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[$TS] Weekly maintenance starting" >> "${LOG_FILE}"

# 1) Agent system hygiene
echo "[$TS] [1/5] Agent system hygiene" >> "${LOG_FILE}"
python3 "${SCRIPT_DIR}/audit_agent_system_layout.py" >> "${LOG_DIR}/hygiene/hygiene.log" 2>&1 || true

# 2) Quarantine maintenance (45-day retention)
echo "[$TS] [2/5] Quarantine maintenance" >> "${LOG_FILE}"
python3 "${SCRIPT_DIR}/prune_agent_quarantine.py" --days 45 --apply >> "${LOG_DIR}/hygiene/quarantine-maintenance.log" 2>&1 || true

# 3) Vault hygiene
echo "[$TS] [3/5] Vault hygiene" >> "${LOG_FILE}"
bash "${SCRIPT_DIR}/vault_hygiene.sh" >> "${LOG_FILE}" 2>&1 || true

# 4) Inbox archive (14-day retention)
echo "[$TS] [4/5] Inbox archive" >> "${LOG_FILE}"
python3 "${SCRIPT_DIR}/archive_inbox.py" --days 14 --apply >> "${LOG_FILE}" 2>&1 || true

# 5) Threshold recalibration
echo "[$TS] [5/5] Threshold recalibration" >> "${LOG_FILE}"
python3 "${SCRIPT_DIR}/recalibrate_memory_benchmark_thresholds.py" --limit 60 --apply >> "${LOG_DIR}/recalibration.log" 2>&1 || true

echo "[$TS] Weekly maintenance complete" >> "${LOG_FILE}"
