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
export LACP_LOCAL_FIRST="${LACP_LOCAL_FIRST:-true}"
export LACP_NO_EXTERNAL_CI="${LACP_NO_EXTERNAL_CI:-true}"
export LACP_VERIFY_HOURS="${LACP_VERIFY_HOURS:-24}"
export LACP_BENCH_TOP_K="${LACP_BENCH_TOP_K:-8}"
export LACP_BENCH_LOOKBACK="${LACP_BENCH_LOOKBACK:-30}"
export LACP_SANDBOX_POLICY_FILE="${LACP_SANDBOX_POLICY_FILE:-${LACP_ROOT}/config/sandbox-policy.json}"
export LACP_MCP_AUTH_POLICY_FILE="${LACP_MCP_AUTH_POLICY_FILE:-${LACP_ROOT}/config/mcp-auth-policy.json}"
export LACP_MCP_MODE="${LACP_MCP_MODE:-cli-first}"
export LACP_MCP_MAX_CONNECTED_SERVERS="${LACP_MCP_MAX_CONNECTED_SERVERS:-2}"
export LACP_MCP_MAX_TOOL_DEFINITIONS="${LACP_MCP_MAX_TOOL_DEFINITIONS:-12}"
export LACP_MCP_REQUIRE_SERVER_ALLOWLIST="${LACP_MCP_REQUIRE_SERVER_ALLOWLIST:-true}"
export LACP_MCP_USE_TOOL_SEARCH="${LACP_MCP_USE_TOOL_SEARCH:-true}"
export LACP_MCP_DEFER_TOOL_LOADING="${LACP_MCP_DEFER_TOOL_LOADING:-true}"
export LACP_MCP_PREFER_CLI_FIRST="${LACP_MCP_PREFER_CLI_FIRST:-true}"
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
export LACP_RUNTIME_MAX_LOAD_PER_CPU="${LACP_RUNTIME_MAX_LOAD_PER_CPU:-2.00}"
export LACP_RUNTIME_MIN_FORK_HEADROOM="${LACP_RUNTIME_MIN_FORK_HEADROOM:-64}"
export LACP_RUNTIME_BACKOFF_SEC="${LACP_RUNTIME_BACKOFF_SEC:-2}"
export LACP_RUNTIME_BACKOFF_MAX_ATTEMPTS="${LACP_RUNTIME_BACKOFF_MAX_ATTEMPTS:-3}"
export LACP_RUNTIME_PRESSURE_OVERRIDE="${LACP_RUNTIME_PRESSURE_OVERRIDE:-auto}"

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

lacp_env_truthy() {
  local value="${1:-}"
  case "${value,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

lacp_runtime_pressure_json() {
  python3 - <<'PY' "${LACP_RUNTIME_MAX_LOAD_PER_CPU}" "${LACP_RUNTIME_MIN_FORK_HEADROOM}" "${LACP_RUNTIME_PRESSURE_OVERRIDE}"
import json
import os
import subprocess
import sys

max_load_per_cpu = float(sys.argv[1])
min_fork_headroom = int(sys.argv[2])
pressure_override = sys.argv[3].strip().lower()

cpu_count = os.cpu_count() or 1
load1 = 0.0
try:
    load1 = float(os.getloadavg()[0])
except Exception:
    load1 = 0.0
load_per_cpu = load1 / max(cpu_count, 1)

def shell_out(cmd: list[str]) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=1.0)
        return (cp.stdout or "").strip()
    except Exception:
        return ""

ulimit_nproc_raw = shell_out(["bash", "-lc", "ulimit -u 2>/dev/null || true"])
ulimit_nofile_raw = shell_out(["bash", "-lc", "ulimit -n 2>/dev/null || true"])
proc_count_raw = shell_out(["bash", "-lc", "sysctl -n kern.num_tasks 2>/dev/null || true"])
if not proc_count_raw:
    proc_count_raw = shell_out(["bash", "-lc", "ps -A -o pid= 2>/dev/null | wc -l | tr -d ' '"])

def to_int(value: str):
    value = (value or "").strip()
    if not value or value == "unlimited":
        return None
    try:
        return int(value)
    except Exception:
        return None

ulimit_nproc = to_int(ulimit_nproc_raw)
ulimit_nofile = to_int(ulimit_nofile_raw)
process_count = to_int(proc_count_raw)

fork_headroom = None
if isinstance(ulimit_nproc, int) and isinstance(process_count, int):
    fork_headroom = ulimit_nproc - process_count

reasons: list[str] = []
if load_per_cpu > max_load_per_cpu:
    reasons.append(
        f"high_load_per_cpu:{load_per_cpu:.2f}>{max_load_per_cpu:.2f} (reduce concurrent sessions/jobs)"
    )
if isinstance(fork_headroom, int) and fork_headroom < min_fork_headroom:
    reasons.append(
        f"low_fork_headroom:{fork_headroom}<{min_fork_headroom} (raise 'ulimit -u' or reduce active processes)"
    )

high = bool(reasons)
if pressure_override == "high":
    high = True
    reasons.append("override:high")
elif pressure_override == "normal":
    high = False
    reasons = [r for r in reasons if not r.startswith("override:")]

payload = {
    "high": high,
    "thresholds": {
        "max_load_per_cpu": max_load_per_cpu,
        "min_fork_headroom": min_fork_headroom,
    },
    "metrics": {
        "cpu_count": cpu_count,
        "load1": load1,
        "load_per_cpu": load_per_cpu,
        "process_count": process_count,
        "ulimit_nproc": ulimit_nproc,
        "ulimit_nofile": ulimit_nofile,
        "fork_headroom": fork_headroom,
        "pressure_override": pressure_override,
    },
    "reasons": reasons,
}
print(json.dumps(payload))
PY
}

lacp_wait_for_runtime_capacity() {
  local context="${1:-runtime}"
  local attempts="${2:-${LACP_RUNTIME_BACKOFF_MAX_ATTEMPTS}}"
  local sleep_sec="${3:-${LACP_RUNTIME_BACKOFF_SEC}}"
  local i json high reasons

  i=1
  while [[ "${i}" -le "${attempts}" ]]; do
    json="$(lacp_runtime_pressure_json)"
    high="$(jq -r '.high' <<<"${json}")"
    if [[ "${high}" != "true" ]]; then
      return 0
    fi
    reasons="$(jq -r '.reasons | join("; ")' <<<"${json}")"
    if [[ "${i}" -ge "${attempts}" ]]; then
      log "runtime-pressure ${context}: still high after ${attempts} attempts (${reasons})"
      return 1
    fi
    log "runtime-pressure ${context}: high (${reasons}); backing off ${sleep_sec}s (attempt ${i}/${attempts})"
    sleep "${sleep_sec}"
    i=$((i + 1))
  done
  return 1
}
