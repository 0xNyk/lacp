#!/usr/bin/env zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOURS="${1:-24}"
THRESHOLD="${2:-0.90}"

echo "[1/3] Capturing snapshot window=${HOURS}h"
"${SCRIPT_DIR}/run_snapshot.sh" "$HOURS"

echo "[2/3] Generating recommendations threshold=${THRESHOLD}"
REC="$(python3 "${SCRIPT_DIR}/recommend_pruning.py" --snapshots 6 --threshold "$THRESHOLD")"
echo "Recommendation: $REC"

echo "[3/3] Applying high-confidence recommendations"
APP="$(python3 "${SCRIPT_DIR}/apply_pruning.py" --recommendation "$REC" --threshold "$THRESHOLD")"
echo "Apply report: $APP"

echo "Done."
