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
    echo "[mode-gates] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[mode-gates] PASS ${label}: ${actual}"
}

assert_file_exists() {
  local file="$1"
  local label="$2"
  if [[ ! -f "${file}" ]]; then
    echo "[mode-gates] FAIL ${label}: missing ${file}" >&2
    exit 1
  fi
  echo "[mode-gates] PASS ${label}: ${file}"
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

ENV_FILE="${ROOT}/.env"
ENV_BACKUP="${TMP}/env.backup"
if [[ -f "${ENV_FILE}" ]]; then
  cp "${ENV_FILE}" "${ENV_BACKUP}"
fi

restore_env() {
  if [[ -f "${ENV_BACKUP}" ]]; then
    mv "${ENV_BACKUP}" "${ENV_FILE}"
  else
    rm -f "${ENV_FILE}"
  fi
}
trap 'restore_env; rm -rf "${TMP}"' EXIT

cp "${ROOT}/config/lacp.env.example" "${ENV_FILE}"

export LACP_SKIP_DOTENV="1"
# Unset recursion guard so sandbox-run exercises actual gate logic
unset LACP_SANDBOX_RECURSION_GUARD LACP_SANDBOX_DEPTH 2>/dev/null || true
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_SANDBOX_POLICY_FILE="${ROOT}/config/sandbox-policy.json"
export LACP_REMOTE_APPROVAL_FILE="${TMP}/approval.json"
export LACP_REMOTE_APPROVAL_TTL_MIN="5"

mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"
INPUT_CONTRACT='{"source":"ci-test","intent":"validate gating behavior","allowed_actions":["echo"],"denied_actions":["data exfiltration"],"confidence":0.95}'

# Mode workflow and approval file lifecycle.
out="$("${ROOT}/bin/lacp-mode" local-only --json)"
assert_eq "$(echo "${out}" | jq -r '.mode')" "local-only" "mode.local-only"
assert_eq "$(echo "${out}" | jq -r '.remote_approval.action')" "revoked" "mode.local-only.revoked"

out="$("${ROOT}/bin/lacp-mode" remote-enabled --ttl-min 2 --json)"
assert_eq "$(echo "${out}" | jq -r '.mode')" "remote-enabled" "mode.remote-enabled"
assert_eq "$(echo "${out}" | jq -r '.remote_approval.valid')" "true" "mode.remote-enabled.approval-valid"
assert_file_exists "${LACP_REMOTE_APPROVAL_FILE}" "mode.remote-enabled.approval-file"

out="$("${ROOT}/bin/lacp-mode" revoke-approval --json)"
assert_eq "$(echo "${out}" | jq -r '.remote_approval.action')" "revoked" "mode.revoke-approval"
if [[ -f "${LACP_REMOTE_APPROVAL_FILE}" ]]; then
  echo "[mode-gates] FAIL mode.revoke-approval: approval file still present" >&2
  exit 1
fi
echo "[mode-gates] PASS mode.revoke-approval: approval file removed"

# Review tier should require TTL approval token.
run_expect_rc 8 "${ROOT}/bin/lacp-sandbox-run" --task "review task" --repo-trust unknown -- /bin/echo "should-block"

python3 - <<'PY' "${LACP_REMOTE_APPROVAL_FILE}"
import datetime as dt
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
now = dt.datetime.now(dt.timezone.utc)
payload = {
    "approved_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "expires_at_utc": (now + dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ttl_min": 20,
    "source": "test-mode-and-gates",
}
path.write_text(json.dumps(payload))
PY

run_expect_rc 0 "${ROOT}/bin/lacp-sandbox-run" --task "review task" --repo-trust unknown -- /bin/echo "review-approved"

# Critical tier should require explicit confirm every run.
run_expect_rc 9 "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --repo-trust unknown --internet true --external-code true --input-contract "${INPUT_CONTRACT}" -- /bin/echo "critical-block"
run_expect_rc 0 "${ROOT}/bin/lacp-sandbox-run" --task "prod wallet migration" --repo-trust unknown --internet true --external-code true --input-contract "${INPUT_CONTRACT}" --confirm-critical true -- /bin/echo "critical-ok"

# Budget gate should block when estimate exceeds ceiling without explicit override.
run_expect_rc 10 "${ROOT}/bin/lacp-sandbox-run" --task "trusted benchmark" --repo-trust trusted --estimated-cost-usd 2 -- /bin/echo "budget-block"
run_expect_rc 0 "${ROOT}/bin/lacp-sandbox-run" --task "trusted benchmark" --repo-trust trusted --estimated-cost-usd 2 --confirm-budget true -- /bin/echo "budget-ok"

echo "[mode-gates] all mode and gate tests passed"
