#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[security-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[security-test] PASS ${label}: ${actual}"
}

run_expect_rc() {
  local expected_rc="$1"
  shift
  set +e
  "$@"
  local rc=$?
  set -e
  assert_eq "${rc}" "${expected_rc}" "rc:$*"
}

export LACP_SKIP_DOTENV="1"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"
export LACP_MCP_AUTH_POLICY_FILE="${ROOT}/config/mcp-auth-policy.json"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"
"${ROOT}/bin/lacp-install" --profile starter >/dev/null

VALID_CONTRACT='{"source":"security-test","intent":"validate gate","allowed_actions":["echo"],"denied_actions":["exfiltration"],"confidence":0.95}'
INVALID_CONTRACT='{"source":"security-test","intent":"validate gate","allowed_actions":[],"denied_actions":[],"confidence":0.2}'
ACTUAL_HOST="$(hostname -s 2>/dev/null || hostname)"
PWD_PREFIX="$(pwd -P)"
GOOD_CONTEXT_CONTRACT="{\"expected_host\":\"${ACTUAL_HOST}\",\"expected_cwd_prefix\":\"${PWD_PREFIX}\"}"
BAD_CONTEXT_CONTRACT='{"expected_host":"definitely-not-this-host"}'

run_expect_rc 11 "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --repo-trust unknown --internet true --external-code true --confirm-critical true -- /bin/echo "missing-contract"
run_expect_rc 11 "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --repo-trust unknown --internet true --external-code true --input-contract "${INVALID_CONTRACT}" --confirm-critical true -- /bin/echo "invalid-contract"
run_expect_rc 0 "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --repo-trust unknown --internet true --external-code true --input-contract "${VALID_CONTRACT}" --confirm-critical true -- /bin/echo "valid-contract"

run_expect_rc 12 "${ROOT}/bin/lacp-sandbox-run" --task "context gate missing" --repo-trust trusted -- /bin/mkdir -p "${TMP}/ctx-missing"
run_expect_rc 12 "${ROOT}/bin/lacp-sandbox-run" --task "context gate mismatch" --repo-trust trusted --context-contract "${BAD_CONTEXT_CONTRACT}" -- /bin/mkdir -p "${TMP}/ctx-bad"
run_expect_rc 0 "${ROOT}/bin/lacp-sandbox-run" --task "context gate pass" --repo-trust trusted --context-contract "${GOOD_CONTEXT_CONTRACT}" -- /bin/mkdir -p "${TMP}/ctx-good"

"${ROOT}/bin/lacp-doctor" --json | jq -e '.ok == true' >/dev/null
echo "[security-test] security controls tests passed"
