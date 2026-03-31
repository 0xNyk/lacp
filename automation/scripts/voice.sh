#!/usr/bin/env bash
# Quick voice-to-daily-note capture.
# Usage:
#   voice.sh              — record until Ctrl+C
#   voice.sh 60           — record for 60 seconds
#   voice.sh file.wav     — transcribe existing file
#   voice.sh --keep-audio — archive the audio
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCRIPT="${SCRIPT_DIR}/voice_daily_note.py"

# If first arg is a number, treat as duration
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    exec python3 "$SCRIPT" --duration "$1"
# If first arg is a file path, treat as --file
elif [[ -f "${1:-}" ]]; then
    exec python3 "$SCRIPT" --file "$1"
else
    exec python3 "$SCRIPT" "$@"
fi
