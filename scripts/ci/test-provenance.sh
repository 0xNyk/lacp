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

## --- verify on empty chain ---
verify_empty="$(${ROOT}/bin/lacp-provenance verify --json)"
echo "${verify_empty}" | jq -e '.ok == true and .chain_length == 0' >/dev/null

## --- start session ---
start_json="$(${ROOT}/bin/lacp-provenance start --json)"
echo "${start_json}" | jq -e '.ok == true and .status == "pending"' >/dev/null
agent_id="$(echo "${start_json}" | jq -r '.agent_id')"
[[ "${agent_id}" =~ ^agent- ]] || { echo "[provenance-test] start did not include agent_id" >&2; exit 1; }

## --- pending file should exist ---
[[ -f "${HOME}/.lacp/provenance/pending.json" ]] || { echo "[provenance-test] pending.json missing after start" >&2; exit 1; }

## --- end session ---
end_json="$(${ROOT}/bin/lacp-provenance end --json)"
echo "${end_json}" | jq -e '.ok == true' >/dev/null
receipt_hash="$(echo "${end_json}" | jq -r '.receipt_hash')"
prev_hash="$(echo "${end_json}" | jq -r '.prev_hash')"
[[ "${prev_hash}" == "genesis" ]] || { echo "[provenance-test] first receipt prev_hash should be genesis" >&2; exit 1; }
[[ -n "${receipt_hash}" && "${receipt_hash}" != "null" ]] || { echo "[provenance-test] receipt_hash missing" >&2; exit 1; }

## --- pending file should be gone ---
[[ ! -f "${HOME}/.lacp/provenance/pending.json" ]] || { echo "[provenance-test] pending.json should be removed after end" >&2; exit 1; }

## --- verify chain with 1 receipt ---
verify1="$(${ROOT}/bin/lacp-provenance verify --json)"
echo "${verify1}" | jq -e '.ok == true and .chain_length == 1 and (.breaks | length) == 0' >/dev/null

## --- second session (should chain to first) ---
${ROOT}/bin/lacp-provenance start --json >/dev/null
end2_json="$(${ROOT}/bin/lacp-provenance end --json)"
prev2="$(echo "${end2_json}" | jq -r '.prev_hash')"
[[ "${prev2}" == "${receipt_hash}" ]] || { echo "[provenance-test] second receipt prev_hash should match first receipt_hash" >&2; exit 1; }

## --- verify chain with 2 receipts ---
verify2="$(${ROOT}/bin/lacp-provenance verify --json)"
echo "${verify2}" | jq -e '.ok == true and .chain_length == 2 and (.breaks | length) == 0' >/dev/null

## --- third session ---
${ROOT}/bin/lacp-provenance start --json >/dev/null
${ROOT}/bin/lacp-provenance end --json >/dev/null

verify3="$(${ROOT}/bin/lacp-provenance verify --json)"
echo "${verify3}" | jq -e '.ok == true and .chain_length == 3' >/dev/null

## --- tamper detection: corrupt a receipt ---
chain_file="${HOME}/.lacp/provenance/chain.jsonl"
# Replace first line with corrupted data
python3 -c "
import json
with open('${chain_file}') as f:
    lines = f.readlines()
first = json.loads(lines[0])
first['agent_id'] = 'TAMPERED'
lines[0] = json.dumps(first, separators=(',',':')) + '\n'
with open('${chain_file}', 'w') as f:
    f.writelines(lines)
"

verify_tampered="$(${ROOT}/bin/lacp-provenance verify --json)"
echo "${verify_tampered}" | jq -e '.ok == false and (.breaks | length) > 0' >/dev/null

## --- log subcommand ---
log_json="$(${ROOT}/bin/lacp-provenance log --last 2 --json)"
echo "${log_json}" | jq -e '.ok == true and .showing <= 2' >/dev/null

## --- export subcommand ---
export_json="$(${ROOT}/bin/lacp-provenance export --json)"
echo "${export_json}" | jq -e '.ok == true and .chain_length == 3' >/dev/null

## --- end without pending should fail ---
if ${ROOT}/bin/lacp-provenance end --json 2>/dev/null | jq -e '.ok == true' >/dev/null 2>&1; then
  echo "[provenance-test] end without start should fail" >&2
  exit 1
fi

echo "[provenance-test] provenance chain tests passed"
