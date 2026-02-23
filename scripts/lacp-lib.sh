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
export LACP_MCP_AUTH_POLICY_FILE="${LACP_MCP_AUTH_POLICY_FILE:-${LACP_ROOT}/config/mcp-auth-policy.json}"
export LACP_ALLOW_EXTERNAL_REMOTE="${LACP_ALLOW_EXTERNAL_REMOTE:-false}"
export LACP_REMOTE_APPROVAL_TTL_MIN="${LACP_REMOTE_APPROVAL_TTL_MIN:-30}"
export LACP_REMOTE_APPROVAL_FILE="${LACP_REMOTE_APPROVAL_FILE:-${LACP_KNOWLEDGE_ROOT}/data/approvals/remote-approval.json}"
export LACP_KNOWLEDGE_GRAPH_ROOT="${LACP_KNOWLEDGE_GRAPH_ROOT:-${LACP_KNOWLEDGE_ROOT}}"
export LACP_REQUIRE_INPUT_CONTRACT="${LACP_REQUIRE_INPUT_CONTRACT:-true}"
export LACP_INPUT_CONTRACT_CONFIDENCE_MIN="${LACP_INPUT_CONTRACT_CONFIDENCE_MIN:-0.70}"
export LACP_REQUIRE_CONTEXT_CONTRACT="${LACP_REQUIRE_CONTEXT_CONTRACT:-true}"
export LACP_REQUIRE_SESSION_FINGERPRINT="${LACP_REQUIRE_SESSION_FINGERPRINT:-false}"
export LACP_CANARY_DAYS="${LACP_CANARY_DAYS:-7}"
export LACP_CANARY_MIN_HIT_RATE="${LACP_CANARY_MIN_HIT_RATE:-0.90}"
export LACP_CANARY_MIN_MRR="${LACP_CANARY_MIN_MRR:-0.65}"
export LACP_CANARY_MAX_TRIAGE_ISSUES="${LACP_CANARY_MAX_TRIAGE_ISSUES:-2}"
export LACP_WRAPPER_BIN_DIR="${LACP_WRAPPER_BIN_DIR:-$HOME/.local/bin}"
export LACP_AUTO_DEPS_FORMULAS="${LACP_AUTO_DEPS_FORMULAS:-jq ripgrep python@3.11 git tmux gh}"

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
  python3 - <<'PY' "${glob_path}"
import glob
import os
import sys

matches = [p for p in glob.glob(sys.argv[1]) if os.path.isfile(p)]
if not matches:
    raise SystemExit(0)
latest = max(matches, key=lambda p: os.path.getmtime(p))
print(latest)
PY
}

lacp_missing_commands() {
  local -a required=("$@")
  local cmd
  for cmd in "${required[@]}"; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      printf '%s\n' "${cmd}"
    fi
  done
}

lacp_auto_install_deps() {
  local dry_run="${1:-false}"
  local force="${2:-false}"
  local os_name
  os_name="$(uname -s 2>/dev/null || echo unknown)"

  if [[ "${os_name}" != "Darwin" ]]; then
    log "auto-deps unsupported on ${os_name}; install dependencies manually"
    return 0
  fi

  if ! command -v brew >/dev/null 2>&1; then
    if [[ "${force}" == "true" ]]; then
      die "Homebrew is required for --auto-deps on macOS"
    fi
    log "auto-deps skipped: Homebrew not found"
    return 0
  fi

  local -a formulas=()
  # shellcheck disable=SC2206
  formulas=(${LACP_AUTO_DEPS_FORMULAS})
  if [[ "${#formulas[@]}" -eq 0 ]]; then
    log "auto-deps skipped: no formulas configured"
    return 0
  fi

  local -a missing=()
  local formula
  for formula in "${formulas[@]}"; do
    if ! brew list --formula "${formula}" >/dev/null 2>&1; then
      missing+=("${formula}")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 ]]; then
    log "auto-deps: all configured formulas already installed"
    return 0
  fi

  if [[ "${dry_run}" == "true" ]]; then
    log "auto-deps dry-run: would install formulas: ${missing[*]}"
    return 0
  fi

  log "auto-deps: installing formulas: ${missing[*]}"
  brew install "${missing[@]}"
}

lacp_wrapper_managed_state() {
  local cmd_name="$1"
  local wrapper_path="${LACP_WRAPPER_BIN_DIR}/${cmd_name}"

  if [[ ! -f "${wrapper_path}" ]]; then
    echo "missing"
    return 0
  fi
  if rg -q 'LACP_MANAGED_WRAPPER=1' "${wrapper_path}" 2>/dev/null; then
    echo "managed"
  else
    echo "unmanaged"
  fi
}
