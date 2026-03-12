#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT="${ROOT}"
JSON=0

usage() {
  cat <<'EOF'
Usage: security-hygiene-audit.sh [--repo-root <path>] [--json]

Quick local security/hygiene scan for open-source readiness.

Checks:
  - high-signal secret token patterns (FAIL)
  - absolute local path literals (/Users, /home) (FAIL)
  - tracked .env file in git index (FAIL)
  - active external CI workflows under .github/workflows (FAIL)
  - email literals (WARN)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      [[ $# -ge 2 ]] || { echo "missing value for --repo-root" >&2; exit 2; }
      REPO_ROOT="$2"
      shift 2
      ;;
    --json)
      JSON=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 3; }
}

require_cmd rg
require_cmd jq
require_cmd git

if [[ ! -d "${REPO_ROOT}" ]]; then
  echo "repo root not found: ${REPO_ROOT}" >&2
  exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

scan_rg() {
  local pattern="$1"
  local outfile="$2"
  shift 2

  if [[ $# -gt 0 ]]; then
    if rg -n --no-heading -H --color=never --hidden \
        --glob '!.git/**' \
        --glob '!dist/**' \
        --glob '!scripts/ci/test-*.sh' \
        --glob '!scripts/ci/security-hygiene-audit.sh' \
        "$@" \
        -e "${pattern}" "${REPO_ROOT}" > "${outfile}" 2>/dev/null; then
      :
    else
      : > "${outfile}"
    fi
    return
  fi

  if rg -n --no-heading -H --color=never --hidden \
      --glob '!.git/**' \
      --glob '!dist/**' \
      --glob '!scripts/ci/test-*.sh' \
      --glob '!scripts/ci/security-hygiene-audit.sh' \
      -e "${pattern}" "${REPO_ROOT}" > "${outfile}" 2>/dev/null; then
    :
  else
    : > "${outfile}"
  fi
}

append_check() {
  local name="$1"
  local status="$2"
  local detail="$3"
  local count="$4"
  local source_file="$5"

  local samples_json='[]'
  if [[ -s "${source_file}" ]]; then
    samples_json="$(head -n 5 "${source_file}" | jq -R . | jq -s '.')"
  fi

  jq -cn \
    --arg name "${name}" \
    --arg status "${status}" \
    --arg detail "${detail}" \
    --argjson count "${count}" \
    --argjson samples "${samples_json}" \
    '{name:$name,status:$status,detail:$detail,count:$count,samples:$samples}' >> "${work}/checks.ndjson"
}

secret_matches="${work}/secret_matches.txt"
path_matches="${work}/path_matches.txt"
email_matches="${work}/email_matches.txt"
workflows_matches="${work}/workflows_matches.txt"
tracked_env_matches="${work}/tracked_env_matches.txt"

scan_rg 'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}' "${secret_matches}"
scan_rg '/Users/|/home/' "${path_matches}"
scan_rg '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "${email_matches}"
: > "${workflows_matches}"
shopt -s nullglob
workflow_files=("${REPO_ROOT}"/.github/workflows/*.yml "${REPO_ROOT}"/.github/workflows/*.yaml)
shopt -u nullglob
if [[ "${#workflow_files[@]}" -gt 0 ]]; then
  printf '%s\n' "${workflow_files[@]}" > "${workflows_matches}"
fi

if git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "${REPO_ROOT}" ls-files --error-unmatch .env >/dev/null 2>&1; then
    printf '%s\n' '.env is tracked by git' > "${tracked_env_matches}"
  else
    : > "${tracked_env_matches}"
  fi
else
  : > "${tracked_env_matches}"
fi

secret_count="$(wc -l < "${secret_matches}" | tr -d ' ')"
path_count="$(wc -l < "${path_matches}" | tr -d ' ')"
email_count="$(wc -l < "${email_matches}" | tr -d ' ')"
workflows_count="$(wc -l < "${workflows_matches}" | tr -d ' ')"
tracked_env_count="$(wc -l < "${tracked_env_matches}" | tr -d ' ')"

: > "${work}/checks.ndjson"

if [[ "${secret_count}" -gt 0 ]]; then
  append_check "secrets:high_signal_patterns" "FAIL" "high-signal secret/token patterns detected" "${secret_count}" "${secret_matches}"
else
  append_check "secrets:high_signal_patterns" "PASS" "no high-signal secret/token patterns detected" 0 "${secret_matches}"
fi

if [[ "${path_count}" -gt 0 ]]; then
  append_check "hygiene:absolute_paths" "FAIL" "absolute local paths detected (/Users or /home)" "${path_count}" "${path_matches}"
else
  append_check "hygiene:absolute_paths" "PASS" "no absolute local paths detected" 0 "${path_matches}"
fi

if [[ "${tracked_env_count}" -gt 0 ]]; then
  append_check "policy:tracked_dotenv" "FAIL" ".env is tracked by git" "${tracked_env_count}" "${tracked_env_matches}"
else
  append_check "policy:tracked_dotenv" "PASS" ".env is not tracked" 0 "${tracked_env_matches}"
fi

if [[ "${workflows_count}" -gt 0 ]]; then
  append_check "policy:active_external_ci_workflows" "FAIL" "active .github/workflows YAML files detected" "${workflows_count}" "${workflows_matches}"
else
  append_check "policy:active_external_ci_workflows" "PASS" "no active .github/workflows YAML files detected" 0 "${workflows_matches}"
fi

if [[ "${email_count}" -gt 0 ]]; then
  append_check "hygiene:email_literals" "WARN" "email literals detected; verify they are placeholders/public" "${email_count}" "${email_matches}"
else
  append_check "hygiene:email_literals" "PASS" "no email literals detected" 0 "${email_matches}"
fi

checks_json="$(jq -s '.' "${work}/checks.ndjson")"
pass_count="$(echo "${checks_json}" | jq '[.[] | select(.status=="PASS")] | length')"
warn_count="$(echo "${checks_json}" | jq '[.[] | select(.status=="WARN")] | length')"
fail_count="$(echo "${checks_json}" | jq '[.[] | select(.status=="FAIL")] | length')"

ok="true"
if [[ "${fail_count}" -gt 0 ]]; then
  ok="false"
fi

payload="$(jq -cn \
  --arg schema_version "1" \
  --arg kind "security_hygiene_audit" \
  --arg generated_at_utc "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --arg repo_root "${REPO_ROOT}" \
  --argjson ok "${ok}" \
  --argjson pass "${pass_count}" \
  --argjson warn "${warn_count}" \
  --argjson fail "${fail_count}" \
  --argjson checks "${checks_json}" \
  '{
    schema_version:$schema_version,
    kind:$kind,
    generated_at_utc:$generated_at_utc,
    ok:$ok,
    repo_root:$repo_root,
    summary:{pass:$pass,warn:$warn,fail:$fail},
    checks:$checks
  }'
)"

if [[ "${JSON}" -eq 1 ]]; then
  echo "${payload}"
else
  echo "${payload}" | jq -r '"security-hygiene-audit ok=\(.ok) pass=\(.summary.pass) warn=\(.summary.warn) fail=\(.summary.fail)"'
  echo "${payload}" | jq -r '.checks[] | "- [\(.status)] \(.name): \(.detail) (count=\(.count))"'
fi

if [[ "${ok}" == "true" ]]; then
  exit 0
fi
exit 1
