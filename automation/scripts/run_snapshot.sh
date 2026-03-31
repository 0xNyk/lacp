#!/usr/bin/env zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOURS="${1:-24}"

SNAPSHOT_PATH="$(python3 "${SCRIPT_DIR}/capture_snapshot.py" --hours "$HOURS" --timing-runs 3)"
python3 "${SCRIPT_DIR}/append_journal_entry.py"

echo "Snapshot complete: $SNAPSHOT_PATH"
