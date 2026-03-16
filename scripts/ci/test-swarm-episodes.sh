#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/automation/scripts" "${TMP}/knowledge/data/sandbox-runs" "${TMP}/drafts"

export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_RUNTIME_PRESSURE_OVERRIDE="normal"

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[episode-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[episode-test] PASS ${label}: ${actual}"
}

SWARM_ID="test-episodes-$$"

# Test 1: episode-write creates a file with correct fields.
"${ROOT}/bin/lacp-swarm" episode-write \
  --swarm-id "${SWARM_ID}" \
  --session "s1" \
  --task "implement feature" \
  --status "completed" \
  --summary "implemented the login feature" \
  --files-modified "src/login.ts,src/auth.ts" \
  --tool-calls-succeeded 5 \
  --tool-calls-failed 1 \
  --duration-ms 12000 \
  --json | jq -e '.ok == true' >/dev/null

ep_file="${TMP}/knowledge/data/swarms/episodes/${SWARM_ID}/s1.json"
[[ -f "${ep_file}" ]] || { echo "[episode-test] FAIL episode file not created" >&2; exit 1; }
echo "[episode-test] PASS episode file created"

actual_status="$(jq -r '.status' "${ep_file}")"
assert_eq "${actual_status}" "completed" "episode-write:status"

actual_summary="$(jq -r '.summary' "${ep_file}")"
assert_eq "${actual_summary}" "implemented the login feature" "episode-write:summary"

actual_files_count="$(jq '.files_modified | length' "${ep_file}")"
assert_eq "${actual_files_count}" "2" "episode-write:files_count"

actual_succeeded="$(jq '.tool_calls_succeeded' "${ep_file}")"
assert_eq "${actual_succeeded}" "5" "episode-write:tool_calls_succeeded"

# Test 2: write a second episode.
"${ROOT}/bin/lacp-swarm" episode-write \
  --swarm-id "${SWARM_ID}" \
  --session "s2" \
  --task "write tests" \
  --status "failed" \
  --summary "tests failed due to missing mock" \
  --error "AssertionError: mock not found" \
  --tool-calls-succeeded 2 \
  --tool-calls-failed 3 \
  --duration-ms 8000 \
  --json | jq -e '.ok == true' >/dev/null
echo "[episode-test] PASS second episode written"

# Test 3: episodes subcommand lists both.
episodes_json="$("${ROOT}/bin/lacp-swarm" episodes --swarm-id "${SWARM_ID}" --json)"
episodes_count="$(echo "${episodes_json}" | jq 'length')"
assert_eq "${episodes_count}" "2" "episodes:count"

# Test 4: digest produces a summary.
digest_json="$("${ROOT}/bin/lacp-swarm" digest --swarm-id "${SWARM_ID}" --json)"
echo "${digest_json}" | jq -e '.ok == true' >/dev/null
echo "${digest_json}" | jq -e '.episode_count == 2' >/dev/null
digest_text="$(echo "${digest_json}" | jq -r '.digest')"
[[ "${digest_text}" == *"s1"* ]] || { echo "[episode-test] FAIL digest missing s1" >&2; exit 1; }
[[ "${digest_text}" == *"s2"* ]] || { echo "[episode-test] FAIL digest missing s2" >&2; exit 1; }
[[ "${digest_text}" == *"login"* ]] || { echo "[episode-test] FAIL digest missing summary content" >&2; exit 1; }
echo "[episode-test] PASS digest contains episode summaries"

# Test 5: context subcommand outputs prompt-friendly format.
context_out="$("${ROOT}/bin/lacp-swarm" context --swarm-id "${SWARM_ID}")"
[[ "${context_out}" == *"<swarm-context"* ]] || { echo "[episode-test] FAIL context missing xml tag" >&2; exit 1; }
[[ "${context_out}" == *"</swarm-context>"* ]] || { echo "[episode-test] FAIL context missing closing tag" >&2; exit 1; }
echo "[episode-test] PASS context output format"

# Test 6: digest for non-existent swarm.
empty_digest="$("${ROOT}/bin/lacp-swarm" digest --swarm-id "nonexistent-swarm" --json)"
echo "${empty_digest}" | jq -e '.ok == true and .episode_count == 0' >/dev/null
echo "[episode-test] PASS empty digest for missing swarm"

# Test 7: episode-write validates status.
set +e
"${ROOT}/bin/lacp-swarm" episode-write \
  --swarm-id "${SWARM_ID}" \
  --session "bad" \
  --status "invalid_status" \
  --json 2>/dev/null
rc=$?
set -e
if [[ "${rc}" -eq 0 ]]; then
  echo "[episode-test] FAIL expected non-zero exit for invalid status" >&2
  exit 1
fi
echo "[episode-test] PASS invalid status rejected"

echo "[episode-test] all episode tests passed"
