#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

"/bin/bash" "${ROOT}/bin/lacp-install" --profile starter >/dev/null

loop_list="$("${ROOT}/bin/lacp-loop-profile" list --json)"
echo "${loop_list}" | jq -e '.ok == true' >/dev/null
echo "${loop_list}" | jq -e '.profiles | map(.name) | index("local-fast") != null' >/dev/null

loop_render="$("${ROOT}/bin/lacp-loop-profile" render --profile safe-verify --json)"
echo "${loop_render}" | jq -e '.ok == true' >/dev/null
echo "${loop_render}" | jq -e '.loop_defaults.with_verify == true' >/dev/null

cred_list="$("${ROOT}/bin/lacp-credential-profile" list --json)"
echo "${cred_list}" | jq -e '.ok == true' >/dev/null
echo "${cred_list}" | jq -e '.profiles | map(.name) | index("prod-sensitive-guarded") != null' >/dev/null

cred_input="$("${ROOT}/bin/lacp-credential-profile" input-contract --profile trusted-local-dev)"
echo "${cred_input}" | jq -e '.source != null and (.allowed_actions | length) > 0' >/dev/null

loop_json="$("${ROOT}/bin/lacp-loop" --task "profile loop local-fast" --loop-profile local-fast --json -- /bin/echo profile-loop-ok)"
echo "${loop_json}" | jq -e '.ok == true' >/dev/null
echo "${loop_json}" | jq -e '.options.loop_profile == "local-fast"' >/dev/null
echo "${loop_json}" | jq -e '.intent.routing.repo_trust == "trusted"' >/dev/null

cred_loop_json="$("${ROOT}/bin/lacp-loop" --task "profile loop credential guarded" --credential-profile prod-sensitive-guarded --json -- /bin/echo profile-credential-ok)"
echo "${cred_loop_json}" | jq -e '.ok == true' >/dev/null
echo "${cred_loop_json}" | jq -e '.options.credential_profile == "prod-sensitive-guarded"' >/dev/null
echo "${cred_loop_json}" | jq -e '.intent.routing.sensitive_data == true' >/dev/null
echo "${cred_loop_json}" | jq -e '.intent.routing.external_code == true' >/dev/null

echo "[loop-credential-profile-test] loop and credential profile tests passed"

