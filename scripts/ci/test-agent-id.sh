#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"
export LACP_SKIP_DOTENV=1
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_OBSIDIAN_VAULT}" "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}"

## --- agent-id register ---
reg_json="$(${ROOT}/bin/lacp-agent-id register --json)"
echo "${reg_json}" | jq -e '.ok == true' >/dev/null
agent_id="$(echo "${reg_json}" | jq -r '.agent_id')"
[[ "${agent_id}" =~ ^agent-[a-f0-9]{32}$ ]] || { echo "[agent-id-test] bad agent_id format: ${agent_id}" >&2; exit 1; }

## --- agent-id show (should return same ID) ---
show_json="$(${ROOT}/bin/lacp-agent-id show --json)"
echo "${show_json}" | jq -e '.ok == true' >/dev/null
show_id="$(echo "${show_json}" | jq -r '.agent_id')"
[[ "${show_id}" == "${agent_id}" ]] || { echo "[agent-id-test] show returned different agent_id" >&2; exit 1; }

## --- agent-id touch ---
touch_json="$(${ROOT}/bin/lacp-agent-id touch --json)"
echo "${touch_json}" | jq -e '.ok == true' >/dev/null
session_count="$(echo "${touch_json}" | jq -r '.session_count')"
[[ "${session_count}" -ge 1 ]] || { echo "[agent-id-test] session_count not incremented" >&2; exit 1; }

## --- agent-id list ---
list_json="$(${ROOT}/bin/lacp-agent-id list --json)"
echo "${list_json}" | jq -e '.ok == true and .count >= 1' >/dev/null

## --- agent-id revoke ---
revoke_json="$(${ROOT}/bin/lacp-agent-id revoke "${agent_id}" --json)"
echo "${revoke_json}" | jq -e '.ok == true and .revoked == true' >/dev/null

## --- revoke non-existent ---
if ${ROOT}/bin/lacp-agent-id revoke "agent-nonexist" --json 2>/dev/null; then
  echo "[agent-id-test] revoking non-existent should fail" >&2
  exit 1
fi

## --- idempotent register (new ID after revoke still works) ---
reg2_json="$(${ROOT}/bin/lacp-agent-id show --json)"
echo "${reg2_json}" | jq -e '.ok == true' >/dev/null

## --- corrupted registry.json recovery ---
registry_file="${HOME}/.lacp/agents/registry.json"
echo "NOT VALID JSON{{{" > "${registry_file}"
recover_json="$(${ROOT}/bin/lacp-agent-id register --json 2>/dev/null)"
echo "${recover_json}" | jq -e '.ok == true' >/dev/null || { echo "[agent-id-test] corrupted registry recovery failed" >&2; exit 1; }
# Verify a .corrupt backup was created
corrupt_count="$(ls "${HOME}/.lacp/agents/"registry.json.corrupt.* 2>/dev/null | wc -l | tr -d ' ')"
[[ "${corrupt_count}" -ge 1 ]] || { echo "[agent-id-test] corrupted registry backup not created" >&2; exit 1; }
echo "[agent-id-test] PASS corrupted registry recovery"

echo "[agent-id-test] agent identity tests passed"
