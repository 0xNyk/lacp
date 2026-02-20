#!/usr/bin/env bash
set -euo pipefail

LACP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${LACP_SKIP_DOTENV:-0}" != "1" && -f "${LACP_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${LACP_ROOT}/.env"
fi

export LACP_AUTOMATION_ROOT="${LACP_AUTOMATION_ROOT:-$HOME/control/automation/ai-dev-optimization}"
export LACP_KNOWLEDGE_ROOT="${LACP_KNOWLEDGE_ROOT:-$HOME/control/knowledge/knowledge-memory}"
export LACP_DRAFTS_ROOT="${LACP_DRAFTS_ROOT:-$HOME/docs/content/drafts}"
export LACP_VERIFY_HOURS="${LACP_VERIFY_HOURS:-24}"
export LACP_BENCH_TOP_K="${LACP_BENCH_TOP_K:-8}"
export LACP_BENCH_LOOKBACK="${LACP_BENCH_LOOKBACK:-30}"
export LACP_SANDBOX_POLICY_FILE="${LACP_SANDBOX_POLICY_FILE:-${LACP_ROOT}/config/sandbox-policy.json}"
export LACP_ALLOW_EXTERNAL_REMOTE="${LACP_ALLOW_EXTERNAL_REMOTE:-false}"
export LACP_REMOTE_APPROVAL_TTL_MIN="${LACP_REMOTE_APPROVAL_TTL_MIN:-30}"
export LACP_REMOTE_APPROVAL_FILE="${LACP_REMOTE_APPROVAL_FILE:-${LACP_KNOWLEDGE_ROOT}/data/approvals/remote-approval.json}"

log() {
  printf '[lacp] %s\n' "$*"
}

die() {
  printf '[lacp] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || die "Missing required command: ${cmd}"
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || die "Missing required file: ${path}"
}

require_dir() {
  local path="$1"
  [[ -d "${path}" ]] || die "Missing required directory: ${path}"
}

automation_script() {
  local script_name="$1"
  printf '%s/scripts/%s' "${LACP_AUTOMATION_ROOT}" "${script_name}"
}

latest_file() {
  local glob_path="$1"
  ls -1t ${glob_path} 2>/dev/null | head -n 1
}
