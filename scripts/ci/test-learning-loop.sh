#!/usr/bin/env bash
set -euo pipefail

# Phase A (shadow capture) contract tests for the cross-CLI learning loop.
# Verifies: schema validation (valid passes / invalid fails), kill-switch gating,
# provenance-required fields, and — critically — that enabling shadow capture does
# NOT change routing output (no policy/route mutation).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

PASS=0
SKIPPED=0
assert_pass() { echo "[learn-test] PASS $1"; PASS=$((PASS + 1)); }
fail() { echo "[learn-test] FAIL $1" >&2; exit 1; }

require_bin() { command -v "$1" >/dev/null 2>&1 || { echo "[learn-test] missing required binary: $1" >&2; exit 1; }; }
require_bin jq
require_bin python3

CAPTURE="${ROOT}/bin/lacp-learn-capture"
SCHEMA="${ROOT}/config/learning/learning-events.schema.json"
POLICY="${ROOT}/config/learning/promotion-policy.json"

# --- 0. Artifacts exist and are well-formed -------------------------------------
[[ -f "${SCHEMA}" ]] || fail "schema file missing"
[[ -f "${POLICY}" ]] || fail "promotion policy missing"
[[ -x "${CAPTURE}" ]] || fail "lacp-learn-capture not executable"
jq empty "${SCHEMA}" || fail "schema is not valid JSON"
jq empty "${POLICY}" || fail "promotion policy is not valid JSON"
assert_pass "artifacts present and valid JSON"

# Promotion policy defaults to a safe mode and ships the strict caps later phases need.
default_mode="$(jq -r '.default_mode' "${POLICY}")"
[[ "${default_mode}" == "shadow" ]] || fail "promotion policy default_mode must be shadow (got ${default_mode})"
jq -e '.retrieval_caps.confidence_floor >= 0.5 and .promotion_gates.require_two_person_approval == true' "${POLICY}" >/dev/null \
  || fail "promotion policy missing required caps/gates"
assert_pass "promotion policy contract (safe default + caps + gates)"

# --- 1. Valid fixture passes validation -----------------------------------------
HEX64="$(printf 'a%.0s' $(seq 1 64))"
HEX32="$(printf 'a%.0s' $(seq 1 32))"
cat > "${TMP}/valid.json" <<EOF
{"schema_version":"1.0","event_id":"evt_${HEX32}","captured_at":"2026-06-17T00:00:00Z",
 "mode":"shadow","cli":"claude","event_type":"task_outcome",
 "task":{"summary":"index repo","repo_trust":"trusted","keywords":["index"]},
 "outcome":{"status":"success","score":0.9,"duration_ms":1200},
 "provenance":{"agent_id":"agent-1","project_slug":"slug","session_fingerprint":"fp","source_hash":"${HEX64}"}}
EOF
"${CAPTURE}" validate "${TMP}/valid.json" >/dev/null || fail "valid fixture rejected"
assert_pass "valid fixture accepted"

# --- 2. Invalid fixtures fail validation ----------------------------------------
make_bad() { printf '%s\n' "$2" > "${TMP}/$1"; }
make_bad bad_enum.json '{"schema_version":"1.0","event_id":"evt_'"${HEX32}"'","captured_at":"2026-06-17T00:00:00Z","mode":"shadow","cli":"BOGUS","event_type":"task_outcome","task":{"summary":"x","repo_trust":"trusted"},"outcome":{"status":"success"},"provenance":{"agent_id":"a","project_slug":"p","session_fingerprint":"f","source_hash":"'"${HEX64}"'"}}'
make_bad bad_enforce.json '{"schema_version":"1.0","event_id":"evt_'"${HEX32}"'","captured_at":"2026-06-17T00:00:00Z","mode":"enforce","cli":"claude","event_type":"task_outcome","task":{"summary":"x","repo_trust":"trusted"},"outcome":{"status":"success"},"provenance":{"agent_id":"a","project_slug":"p","session_fingerprint":"f","source_hash":"'"${HEX64}"'"}}'
make_bad bad_missing_prov.json '{"schema_version":"1.0","event_id":"evt_'"${HEX32}"'","captured_at":"2026-06-17T00:00:00Z","mode":"shadow","cli":"claude","event_type":"task_outcome","task":{"summary":"x","repo_trust":"trusted"},"outcome":{"status":"success"}}'
make_bad bad_additional.json '{"schema_version":"1.0","event_id":"evt_'"${HEX32}"'","captured_at":"2026-06-17T00:00:00Z","mode":"shadow","cli":"claude","event_type":"task_outcome","task":{"summary":"x","repo_trust":"trusted"},"outcome":{"status":"success"},"provenance":{"agent_id":"a","project_slug":"p","session_fingerprint":"f","source_hash":"'"${HEX64}"'"},"evil":"x"}'
make_bad bad_datetime.json '{"schema_version":"1.0","event_id":"evt_'"${HEX32}"'","captured_at":"NOT A DATE","mode":"shadow","cli":"claude","event_type":"task_outcome","task":{"summary":"x","repo_trust":"trusted"},"outcome":{"status":"success"},"provenance":{"agent_id":"a","project_slug":"p","session_fingerprint":"f","source_hash":"'"${HEX64}"'"}}'

for bad in bad_enum bad_enforce bad_missing_prov bad_additional bad_datetime; do
  if "${CAPTURE}" validate "${TMP}/${bad}.json" >/dev/null 2>&1; then
    fail "invalid fixture wrongly accepted: ${bad}"
  fi
  assert_pass "invalid fixture rejected: ${bad}"
done

# --- 3. Kill-switch gating: record is a no-op unless enabled AND shadow ----------
export LACP_LEARNING_ROOT="${TMP}/store"
LACP_LEARNING_ENABLED=0 LACP_LEARNING_MODE=off \
  "${CAPTURE}" record --task "x" --status success --json | jq -e '.captured == false' >/dev/null \
  || fail "record captured while disabled"
LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=off \
  "${CAPTURE}" record --task "x" --status success --json | jq -e '.captured == false' >/dev/null \
  || fail "record captured while mode!=shadow"
# Master flag must override even when mode=shadow.
LACP_LEARNING_ENABLED=0 LACP_LEARNING_MODE=shadow \
  "${CAPTURE}" record --task "x" --status success --json | jq -e '.captured == false' >/dev/null \
  || fail "record captured while ENABLED=0 (mode=shadow)"
[[ ! -f "${TMP}/store/events.jsonl" ]] || fail "store written despite disabled capture"
assert_pass "kill-switch gating (enabled flag is the master override)"

# --- 4. Shadow capture writes a schema-valid, provenance-complete event ----------
out="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
  "${CAPTURE}" record --cli codex --event-type route_decision \
  --task "deploy to prod" --repo-trust untrusted --status partial --json)"
echo "${out}" | jq -e '.captured == true and .mutates_routing == false' >/dev/null \
  || fail "shadow record did not capture"
echo "${out}" | jq -e '.event.provenance | (.agent_id and .project_slug and .session_fingerprint and (.source_hash | test("^[0-9a-f]{64}$")))' >/dev/null \
  || fail "captured event missing provenance fields"
echo "${out}" | jq '.event' > "${TMP}/captured.json"
"${CAPTURE}" validate "${TMP}/captured.json" >/dev/null || fail "captured event fails its own schema"
assert_pass "shadow capture writes valid, provenance-complete event"

# --- 4b. Injection safety: caller input is stored as inert data, never executed --
# Regression guard for CWE-94 (the record heredoc must pass values out-of-band).
marker="${TMP}/INJECTION_MARKER"
rm -f "${marker}"
payload='"""+__import__("os").system("touch '"${marker}"'")+"""'
inj_out="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
  "${CAPTURE}" record --cli claude --status success --task "${payload}" --json)"
[[ ! -f "${marker}" ]] || fail "record executed injected code (CWE-94 regression)"
echo "${inj_out}" | jq -e --arg p "${payload}" '.event.task.summary == $p' >/dev/null \
  || fail "injected payload was not stored verbatim as inert data"
assert_pass "injection safety: caller input stored as data, not executed"

# --- 5. Shadow parity: enabling capture does NOT change routing output -----------
# This is the core safety invariant of Phase A. lacp-route output must be identical
# whether learning is off or in shadow mode.
if [[ -x "${ROOT}/bin/lacp-route" ]]; then
  route_args=(--task "run memory benchmark on internal repo" --repo-trust trusted --json)
  off_out="$(LACP_LEARNING_ENABLED=0 LACP_LEARNING_MODE=off "${ROOT}/bin/lacp-route" "${route_args[@]}")"
  shadow_out="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow "${ROOT}/bin/lacp-route" "${route_args[@]}")"
  off_norm="$(echo "${off_out}" | jq -S .)"
  shadow_norm="$(echo "${shadow_out}" | jq -S .)"
  [[ "${off_norm}" == "${shadow_norm}" ]] || fail "shadow mode changed routing output (off != shadow)"
  assert_pass "shadow parity: routing output identical (off == shadow)"
else
  # Loud skip: this is the core safety invariant. If lacp-route ever goes missing,
  # the summary must surface that the parity gate did NOT run rather than imply it passed.
  SKIPPED=$((SKIPPED + 1))
  echo "[learn-test] SKIP shadow-parity: bin/lacp-route not found (core invariant NOT verified this run)" >&2
fi

if [[ "${SKIPPED}" -gt 0 ]]; then
  echo "[learn-test] ${PASS} checks passed, ${SKIPPED} SKIPPED (see warnings above)"
else
  echo "[learn-test] all ${PASS} checks passed"
fi
