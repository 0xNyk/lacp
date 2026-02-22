#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

default_fp="$("${ROOT}/bin/lacp-session-fingerprint")"
if [[ ! "${default_fp}" =~ ^[a-f0-9]{24}$ ]]; then
  echo "[session-fingerprint-test] FAIL unexpected fingerprint format: ${default_fp}" >&2
  exit 1
fi

json_out="$("${ROOT}/bin/lacp-session-fingerprint" --remote-host jarv --json)"
echo "${json_out}" | jq -e '.ok == true' >/dev/null
echo "${json_out}" | jq -e '.kind == "session_fingerprint"' >/dev/null
echo "${json_out}" | jq -e '.context.remote_host == "jarv"' >/dev/null
echo "${json_out}" | jq -e '.fingerprint | test("^[a-f0-9]{24}$")' >/dev/null

echo "[session-fingerprint-test] session fingerprint tests passed"

