#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
# Neutralize gates that a local .env may have enabled and that the parent
# suite leaks into this test's environment. This test exercises the context
# contract gate specifically, so the unrelated session-fingerprint and
# input-contract gates must be forced off for a deterministic result.
export LACP_REQUIRE_SESSION_FINGERPRINT=false
export LACP_REQUIRE_INPUT_CONTRACT=false
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter >/dev/null

list_json="$("${ROOT}/bin/lacp-context-profile" list --json)"
echo "${list_json}" | jq -e '.ok == true' >/dev/null
echo "${list_json}" | jq -e '.profiles | map(.name) | index("local-dev") != null' >/dev/null
echo "${list_json}" | jq -e '.profiles | map(.name) | index("ssh-prod") != null' >/dev/null

local_render="$("${ROOT}/bin/lacp-context-profile" render --profile local-dev --json)"
echo "${local_render}" | jq -e '.ok == true' >/dev/null
echo "${local_render}" | jq -e '.context_contract.expected_host != null' >/dev/null
echo "${local_render}" | jq -e '.context_contract.expected_cwd_prefix != null' >/dev/null

set +e
"${ROOT}/bin/lacp-context-profile" render --profile ssh-prod --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[context-profile-test] FAIL expected ssh-prod render without REMOTE_HOST to fail" >&2
  exit 1
fi

ssh_render="$("${ROOT}/bin/lacp-context-profile" render --profile ssh-prod --var REMOTE_HOST=prod-server --json)"
echo "${ssh_render}" | jq -e '.context_contract.expected_remote_host == "prod-server"' >/dev/null

# Loop integration: context-profile should satisfy context gate for mutating command.
loop_json="$("${ROOT}/bin/lacp-loop" --task "context profile pass" --repo-trust trusted --context-profile local-dev --json -- /bin/mkdir -p "${TMP}/ctx-profile-pass")"
echo "${loop_json}" | jq -e '.ok == true' >/dev/null
echo "${loop_json}" | jq -e '.stages.execute.result.context_contract.valid == true' >/dev/null

echo "[context-profile-test] context profile tests passed"

