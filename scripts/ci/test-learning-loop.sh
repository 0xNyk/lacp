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

# ================================================================================
# Phase B (advisory retrieval) gates — bin/lacp-learn-retrieve
# ================================================================================
RETRIEVE="${ROOT}/bin/lacp-learn-retrieve"
if [[ -x "${RETRIEVE}" ]]; then
  # Build a small store of relevant + irrelevant events to rank against.
  export LACP_LEARNING_ROOT="${TMP}/bstore"
  for i in 1 2 3 4 5; do
    LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
      "${CAPTURE}" record --cli claude --task "memory benchmark variant ${i}" \
      --repo-trust trusted --keywords "memory,benchmark" --status success --score 0.9 >/dev/null
  done
  LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
    "${CAPTURE}" record --cli codex --task "totally unrelated payment refund flow" \
    --repo-trust trusted --keywords "payment,refund" --status success --score 0.9 >/dev/null

  # B1. Gate: retrieval is inactive unless enabled AND mode=advisory.
  for combo in "0:off" "1:shadow" "0:advisory"; do
    c_en="${combo%%:*}"
    c_mode="${combo##*:}"
    out="$(LACP_LEARNING_ENABLED="${c_en}" LACP_LEARNING_MODE="${c_mode}" \
      "${RETRIEVE}" query --task "memory benchmark" --json)"
    echo "${out}" | jq -e '.active == false and (.hints | length) == 0 and .mutates_routing == false' >/dev/null \
      || fail "retrieval active outside advisory mode (enabled=${c_en} mode=${c_mode})"
  done
  assert_pass "retrieval gate: inactive unless enabled AND advisory"

  # B2. Advisory query returns ranked, relevant hints (and excludes irrelevant ones).
  qout="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --keywords "memory,benchmark" --repo-trust trusted --json)"
  echo "${qout}" | jq -e '.active == true and (.hints | length) > 0' >/dev/null \
    || fail "advisory query returned no hints"
  echo "${qout}" | jq -e '[.hints[].summary] | all(test("memory|benchmark"))' >/dev/null \
    || fail "advisory query returned irrelevant hints"
  assert_pass "advisory retrieval returns ranked relevant hints"

  # B3. max_hints cap enforced (5 relevant events, cap them to 2).
  cout="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --keywords "memory,benchmark" --max-hints 2 --json)"
  echo "${cout}" | jq -e '(.hints | length) <= 2' >/dev/null || fail "max_hints cap not enforced"
  assert_pass "retrieval cap: max_hints enforced"

  # B4. confidence_floor enforced (impossibly high floor -> zero hints).
  fout="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --keywords "memory,benchmark" --confidence-floor 0.999 --json)"
  echo "${fout}" | jq -e '(.hints | length) == 0' >/dev/null || fail "confidence_floor not enforced"
  # All returned hints (at the default policy floor) must clear that floor.
  echo "${qout}" | jq -e '[.hints[].confidence] | all(. >= 0.70)' >/dev/null \
    || fail "hints below policy confidence floor leaked through"
  # A nan floor must NOT bypass the gate (nan would make every `conf < floor` false).
  nout="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --keywords "memory,benchmark" --confidence-floor nan --json)"
  echo "${nout}" | jq -e '[.hints[].confidence] | all(. >= 0.70)' >/dev/null \
    || fail "nan confidence_floor bypassed the gate"
  assert_pass "retrieval cap: confidence_floor enforced (incl. nan)"

  # B5. token_budget bounds total hints; the top hint always survives. With ~6-token
  # summaries and a 5-token budget, exactly one hint is admitted (the guaranteed top).
  tout="$(LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --keywords "memory,benchmark" --token-budget 5 --json)"
  echo "${tout}" | jq -e '(.hints | length) == 1 and .tokens_estimated <= 10' >/dev/null \
    || fail "token_budget not enforced (expected exactly 1 hint within budget)"
  assert_pass "retrieval cap: token_budget enforced"

  # B6. Retrieval is read-only — the store must be byte-identical after queries.
  before="$(shasum "${LACP_LEARNING_ROOT}/events.jsonl" | awk '{print $1}')"
  LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task "memory benchmark" --json >/dev/null
  after="$(shasum "${LACP_LEARNING_ROOT}/events.jsonl" | awk '{print $1}')"
  [[ "${before}" == "${after}" ]] || fail "retrieval mutated the learning store"
  assert_pass "retrieval is read-only (store unchanged)"

  # B7. Injection safety on the retrieval path (same CWE-94 guard as capture).
  rmarker="${TMP}/RETRIEVE_INJECTION_MARKER"
  rm -f "${rmarker}"
  LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=advisory \
    "${RETRIEVE}" query --task '"""+__import__("os").system("touch '"${rmarker}"'")+"""' --json >/dev/null 2>&1 || true
  [[ ! -f "${rmarker}" ]] || fail "retrieval executed injected code (CWE-94 regression)"
  assert_pass "retrieval injection safety: query input is inert"
else
  SKIPPED=$((SKIPPED + 1))
  echo "[learn-test] SKIP retrieval gates: bin/lacp-learn-retrieve not found" >&2
fi

# ================================================================================
# Phase C (guarded promotion + eval + rollback) gates
# ================================================================================
EVAL="${ROOT}/bin/lacp-learn-eval"
PROMOTE="${ROOT}/bin/lacp-learn-promote"
ROLLBACK="${ROOT}/bin/lacp-learn-rollback"
if [[ -x "${EVAL}" && -x "${PROMOTE}" && -x "${ROLLBACK}" ]]; then
  export LACP_LEARNING_ROOT="${TMP}/cstore"
  # Baseline (1..30): 50% success. Treatment (31..60): 100% success -> +50pp uplift.
  for i in $(seq 1 30); do
    st=success; [[ $((i % 2)) -eq 0 ]] && st=failure
    LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
      "${CAPTURE}" record --cli claude --task "task ${i}" --keywords "k${i}" --status "${st}" --score 0.9 >/dev/null
  done
  for i in $(seq 31 60); do
    LACP_LEARNING_ENABLED=1 LACP_LEARNING_MODE=shadow \
      "${CAPTURE}" record --cli claude --task "task ${i}" --keywords "k${i}" --status success --score 0.95 >/dev/null
  done

  # C1. Eval report is deterministic (pure function of the store).
  r1="$("${EVAL}" report --json)"
  r2="$("${EVAL}" report --json)"
  [[ "${r1}" == "${r2}" ]] || fail "eval report is not deterministic"
  echo "${r1}" | jq -e '.uplift_pct == 50 and .baseline.success_rate == 0.5 and .treatment.success_rate == 1.0' >/dev/null \
    || fail "eval report metrics incorrect"
  assert_pass "eval report is deterministic with correct metrics"

  # C2. Promotion is REFUSED without evidence/approvers (mode stays shadow).
  if LACP_LEARNING_POLICY_FILE="${POLICY}" "${PROMOTE}" apply --json >/dev/null 2>&1; then
    fail "promotion applied without required gates"
  fi
  mode_after="$(LACP_LEARNING_POLICY_FILE="${POLICY}" "${PROMOTE}" status --json | jq -r '.mode')"
  [[ "${mode_after}" == "shadow" ]] || fail "mode changed despite refused promotion"
  assert_pass "promotion refused without verifier evidence + approvals"

  # C3. Promotion SUCCEEDS only when every gate clears (relaxed test policy so the
  #     metric thresholds are reachable on the synthetic store).
  tpol="${TMP}/test-policy.json"
  jq '.promotion_gates.min_hit_rate=0 | .promotion_gates.min_mrr=0
      | .promotion_gates.min_uplift_pct=10 | .promotion_gates.min_events=50' \
      "${POLICY}" > "${tpol}"
  ev="${TMP}/evidence.txt"; printf 'verifier evidence\n' > "${ev}"
  # Real provenance verify (no --force) — relies on a valid/empty provenance chain.
  papply="$(LACP_LEARNING_POLICY_FILE="${tpol}" \
    "${PROMOTE}" apply --verifier-evidence "${ev}" --approver alice --approver bob --json)"
  echo "${papply}" | jq -e '.promoted == true and .mode == "enforce" and (.record.record_sha256 | length) == 64' >/dev/null \
    || fail "promotion did not apply when all gates passed"
  echo "${papply}" | jq -e '.record.approvers == ["alice","bob"]' >/dev/null \
    || fail "promotion record missing two-person approval"
  assert_pass "promotion applies with full gate satisfaction (-> enforce)"

  # C3b. Idempotency: re-applying from enforce must be refused (no second promotion
  #      bypassing a fresh approval cycle).
  if LACP_LEARNING_POLICY_FILE="${tpol}" "${PROMOTE}" apply \
      --verifier-evidence "${ev}" --approver alice --approver bob --json >/dev/null 2>&1; then
    fail "re-promotion from enforce was allowed (missing idempotency guard)"
  fi
  assert_pass "promotion refused when already in enforce (idempotency guard)"

  # C3c. apply refuses --force-provenance-ok (it must never advance real state).
  freshc="${TMP}/cstore_force"; mkdir -p "${freshc}"
  # Seed the same events into a fresh store so this apply starts from shadow.
  cp "${LACP_LEARNING_ROOT}/events.jsonl" "${freshc}/events.jsonl"
  if LACP_LEARNING_ROOT="${freshc}" LACP_LEARNING_POLICY_FILE="${tpol}" "${PROMOTE}" apply \
      --verifier-evidence "${ev}" --approver alice --approver bob --force-provenance-ok --json >/dev/null 2>&1; then
    fail "apply accepted --force-provenance-ok (must be check-only)"
  fi
  assert_pass "apply refuses --force-provenance-ok (check-only bypass)"

  # C4. Single approver (and duplicate-of-one) fails the two-person gate. Use a
  #     fresh shadow store so the idempotency guard isn't what trips it.
  fresh4="${TMP}/cstore_one"; mkdir -p "${fresh4}"
  cp "${LACP_LEARNING_ROOT}/events.jsonl" "${fresh4}/events.jsonl"
  if LACP_LEARNING_ROOT="${fresh4}" LACP_LEARNING_POLICY_FILE="${tpol}" "${PROMOTE}" apply \
      --verifier-evidence "${ev}" --approver alice --json >/dev/null 2>&1; then
    fail "promotion applied with only one approver"
  fi
  # Same name twice must NOT count as two distinct approvers.
  if LACP_LEARNING_ROOT="${fresh4}" LACP_LEARNING_POLICY_FILE="${tpol}" "${PROMOTE}" apply \
      --verifier-evidence "${ev}" --approver alice --approver alice --json >/dev/null 2>&1; then
    fail "duplicate approver counted as two (two-person bypass)"
  fi
  assert_pass "promotion refused with single/duplicate approver (two-person gate)"

  # C5. Rollback reverts enforce -> shadow and deactivates the promotion.
  rb="$(LACP_LEARNING_POLICY_FILE="${tpol}" "${ROLLBACK}" now --reason "test" --json)"
  echo "${rb}" | jq -e '.from_mode == "enforce" and .mode == "shadow"' >/dev/null \
    || fail "rollback did not revert to shadow"
  LACP_LEARNING_POLICY_FILE="${tpol}" "${ROLLBACK}" status --json | jq -e '.mode == "shadow" and .promotion_active == false' >/dev/null \
    || fail "promotion still active after rollback"
  assert_pass "rollback reverts enforce -> shadow"

  # C6. Rollback drill completes within the policy budget on scratch state.
  drill="$(LACP_LEARNING_POLICY_FILE="${POLICY}" "${ROLLBACK}" drill --json)"
  echo "${drill}" | jq -e '.ok == true and .final_mode == "shadow" and .within_budget == true' >/dev/null \
    || fail "rollback drill failed or exceeded budget"
  assert_pass "rollback drill completes within policy budget"

  # C7. Enforcement stays off until gates pass: a fresh store defaults to shadow.
  freshroot="${TMP}/cstore_fresh"; mkdir -p "${freshroot}"
  LACP_LEARNING_ROOT="${freshroot}" LACP_LEARNING_POLICY_FILE="${POLICY}" \
    "${PROMOTE}" status --json | jq -e '.mode == "shadow"' >/dev/null \
    || fail "fresh store did not default to shadow mode"
  assert_pass "enforcement off by default (fresh store is shadow)"

  # C8. Eval handles an empty store without crashing (no division by zero).
  emptyroot="${TMP}/cstore_empty"; mkdir -p "${emptyroot}"
  zero_rep="$(LACP_LEARNING_ROOT="${emptyroot}" "${EVAL}" report --json)" \
    || fail "eval report crashed on empty store"
  echo "${zero_rep}" | jq -e '.total_events == 0 and .uplift_pct == 0 and .hit_rate == 0 and .mrr == 0' >/dev/null \
    || fail "empty store report incorrect"
  assert_pass "eval report handles empty store correctly"
else
  SKIPPED=$((SKIPPED + 1))
  echo "[learn-test] SKIP Phase C gates: lacp-learn-eval/promote/rollback not all present" >&2
fi

if [[ "${SKIPPED}" -gt 0 ]]; then
  echo "[learn-test] ${PASS} checks passed, ${SKIPPED} SKIPPED (see warnings above)"
else
  echo "[learn-test] all ${PASS} checks passed"
fi
