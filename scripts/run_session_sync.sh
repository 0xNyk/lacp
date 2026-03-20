#!/bin/bash
# Extract useful artifacts from recent Claude/Codex sessions into the vault.
#
# Scans conversation logs for decisions, code snippets, and observations
# worth persisting; then writes them as timestamped notes in the inbox.
#
# This is the bridge between ephemeral agent sessions and the knowledge graph.
# The inbox serves as a staging area; route_inbox.py handles the sorting later.

set -uo pipefail

KNOWLEDGE_ROOT="${LACP_KNOWLEDGE_ROOT:-}"
INBOX_DIR="${KNOWLEDGE_ROOT}/inbox"
SESSIONS_DIR="${KNOWLEDGE_ROOT}/sessions"
PROCESSED_LOG="${KNOWLEDGE_ROOT}/data/session-sync/.processed"
DAYS="${1:-7}"

if [[ -z "$KNOWLEDGE_ROOT" ]]; then
  echo '{"ok": false, "error": "LACP_KNOWLEDGE_ROOT not set"}' >&2
  exit 1
fi

mkdir -p "$INBOX_DIR" "$(dirname "$PROCESSED_LOG")"

# load previously processed session files
declare -A processed
if [[ -f "$PROCESSED_LOG" ]]; then
  while IFS= read -r line; do
    processed["$line"]=1
  done < "$PROCESSED_LOG"
fi

synced=0

# scan Claude project memory directories for recent conversation artifacts
for memory_dir in ~/.claude/projects/*/memory; do
  [[ -d "$memory_dir" ]] || continue

  project_slug="$(basename "$(dirname "$memory_dir")")"

  for f in "$memory_dir"/*.md; do
    [[ -f "$f" ]] || continue

    # skip already processed
    basename_f="$(basename "$f")"
    key="${project_slug}/${basename_f}"
    [[ -n "${processed[$key]:-}" ]] && continue

    # skip files older than $DAYS
    if [[ "$(uname)" == "Darwin" ]]; then
      file_age=$(( ($(date +%s) - $(stat -f %m "$f")) / 86400 ))
    else
      file_age=$(( ($(date +%s) - $(stat -c %Y "$f")) / 86400 ))
    fi
    [[ "$file_age" -gt "$DAYS" ]] && continue

    # copy to inbox with project prefix
    dest="${INBOX_DIR}/session-${project_slug}-${basename_f}"
    if [[ ! -f "$dest" ]]; then
      {
        echo "---"
        echo "type: session-extract"
        echo "source_project: ${project_slug}"
        echo "source_file: ${f}"
        echo "synced: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "status: pending"
        echo "---"
        echo ""
        cat "$f"
      } > "$dest"
      synced=$((synced + 1))
    fi

    echo "$key" >> "$PROCESSED_LOG"
  done
done

# also pull from sessions/ if the vault has raw transcripts
if [[ -d "$SESSIONS_DIR" ]]; then
  for f in "$SESSIONS_DIR"/*.md; do
    [[ -f "$f" ]] || continue
    basename_f="$(basename "$f")"
    key="sessions/${basename_f}"
    [[ -n "${processed[$key]:-}" ]] && continue

    if [[ "$(uname)" == "Darwin" ]]; then
      file_age=$(( ($(date +%s) - $(stat -f %m "$f")) / 86400 ))
    else
      file_age=$(( ($(date +%s) - $(stat -c %Y "$f")) / 86400 ))
    fi
    [[ "$file_age" -gt "$DAYS" ]] && continue

    echo "$key" >> "$PROCESSED_LOG"
    synced=$((synced + 1))
  done
fi

echo "Synced ${synced} session artifacts to inbox"
