#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
UID_NUM="$(id -u)"
SRC_DIR="/Users/nyk/control/knowledge/knowledge-memory/launchd"
DST_DIR="/Users/nyk/Library/LaunchAgents"

LABELS=(
  "com.nyk.knowledge-memory.extract"
  "com.nyk.knowledge-memory.promotions"
  "com.nyk.knowledge-memory.benchmark"
  "com.nyk.knowledge-memory.research-promotions"
  "com.nyk.knowledge-memory.brain-expand"
  "com.nyk.knowledge-memory.threshold-recalibration"
  "com.nyk.control.session-history-sync"
  "com.nyk.agent-system.hygiene"
  "com.nyk.agent-system.quarantine-maintenance"
)

ensure_plists() {
  mkdir -p "${DST_DIR}"
  for label in "${LABELS[@]}"; do
    if [[ -f "${SRC_DIR}/${label}.plist" ]]; then
      cp "${SRC_DIR}/${label}.plist" "${DST_DIR}/${label}.plist"
      plutil -lint "${DST_DIR}/${label}.plist" >/dev/null
    fi
  done
}

bootstrap_one() {
  local label="$1"
  local plist="${DST_DIR}/${label}.plist"
  [[ -f "${plist}" ]] || return 0
  if launchctl print "gui/${UID_NUM}/${label}" >/dev/null 2>&1; then
    launchctl enable "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
    launchctl kickstart -k "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
    return 0
  fi
  launchctl bootstrap "gui/${UID_NUM}" "${plist}" >/dev/null 2>&1 || true
  launchctl enable "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
}

bootout_one() {
  local label="$1"
  local plist="${DST_DIR}/${label}.plist"
  launchctl disable "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
  launchctl bootout "gui/${UID_NUM}" "${plist}" >/dev/null 2>&1 || true
}

status_one() {
  local label="$1"
  if launchctl print "gui/${UID_NUM}/${label}" >/dev/null 2>&1; then
    echo "${label}: loaded"
  else
    echo "${label}: not-loaded"
  fi
}

case "${ACTION}" in
  install)
    ensure_plists
    for label in "${LABELS[@]}"; do
      bootstrap_one "${label}"
    done
    ;;
  restart)
    ensure_plists
    for label in "${LABELS[@]}"; do
      bootout_one "${label}"
      bootstrap_one "${label}"
    done
    ;;
  stop)
    for label in "${LABELS[@]}"; do
      bootout_one "${label}"
    done
    ;;
  status)
    ;;
  *)
    echo "Usage: $0 {install|restart|stop|status}" >&2
    exit 2
    ;;
esac

for label in "${LABELS[@]}"; do
  status_one "${label}"
done
