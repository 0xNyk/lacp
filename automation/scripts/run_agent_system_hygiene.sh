#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOG_DIR="/Users/nyk/control/knowledge/knowledge-memory/data/hygiene"
mkdir -p "$LOG_DIR"

python3 "${SCRIPT_DIR}/audit_agent_system_layout.py" >> "$LOG_DIR/hygiene.log" 2>&1
