#!/usr/bin/env bash
# xint-brain-ingest — ingest X/web URLs into Obsidian research inbox via xint.
#
# Usage:
#   xint-brain-ingest "https://x.com/user/status/123"
#   xint-brain-ingest "https://x.com/user/status/123" --apply
#   xint-brain-ingest "https://example.com/article" --apply --sync

set -euo pipefail
SCRIPT_PATH="$(readlink "${BASH_SOURCE[0]}" || true)"
if [ -n "${SCRIPT_PATH}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
exec python3 "$SCRIPT_DIR/ingest_x_research.py" "$@"
