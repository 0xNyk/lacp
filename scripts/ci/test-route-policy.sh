#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[route-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[route-test] PASS ${label}: ${actual}"
}

run_case() {
  local label="$1"
  local expected_route="$2"
  local expected_provider="$3"
  local expected_tier="$4"
  local expected_ceiling="$5"
  shift 5

  local out
  out="$("${ROOT}/bin/lacp-route" "$@" --json)"

  local actual_route
  actual_route="$(echo "${out}" | jq -r '.route')"
  assert_eq "${actual_route}" "${expected_route}" "${label}:route"

  local actual_provider
  actual_provider="$(echo "${out}" | jq -r '.remote_provider // "null"')"
  assert_eq "${actual_provider}" "${expected_provider}" "${label}:provider"

  local actual_tier
  actual_tier="$(echo "${out}" | jq -r '.risk_tier')"
  assert_eq "${actual_tier}" "${expected_tier}" "${label}:risk_tier"

  local actual_ceiling
  actual_ceiling="$(echo "${out}" | jq -r '.cost_ceiling_usd')"
  assert_eq "${actual_ceiling}" "${expected_ceiling}" "${label}:cost_ceiling_usd"
}

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[route-test] missing required binary: $1" >&2
    exit 1
  }
}

require_bin jq

# Case 1: trusted low-risk task stays local.
run_case \
  "trusted-local" \
  "trusted_local" \
  "null" \
  "safe" \
  "1.0" \
  --task "run memory benchmark on internal repo" \
  --repo-trust trusted

# Case 2: unknown + external/internet task routes to local sandbox.
run_case \
  "local-sandbox" \
  "local_sandbox" \
  "null" \
  "critical" \
  "10.0" \
  --task "run third-party scraper on unknown repo" \
  --repo-trust unknown \
  --internet true \
  --external-code true

# Case 3: heavy long-running task routes remote and uses policy provider.
run_case \
  "remote-policy-provider" \
  "remote_sandbox" \
  "daytona" \
  "review" \
  "5.0" \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true

# Case 4: remote provider override must be honored.
run_case \
  "remote-provider-override" \
  "remote_sandbox" \
  "e2b" \
  "review" \
  "5.0" \
  --task "quant gpu backtest with long runtime" \
  --cpu-heavy true \
  --long-run true \
  --remote-provider e2b

# Case 5: sensitive data should escalate to critical.
run_case \
  "critical-sensitive-data" \
  "local_sandbox" \
  "null" \
  "critical" \
  "10.0" \
  --task "analyze private customer export" \
  --repo-trust trusted \
  --sensitive-data true

# Case 6: model routing — "plan" keyword should yield main/opus.
model_out="$("${ROOT}/bin/lacp-route" --task "plan the migration strategy" --repo-trust trusted --json)"
model_slot="$(echo "${model_out}" | jq -r '.model_slot')"
model_hint="$(echo "${model_out}" | jq -r '.model_hint')"
assert_eq "${model_slot}" "main" "model-routing-plan:model_slot"
assert_eq "${model_hint}" "opus" "model-routing-plan:model_hint"

# Case 7: model routing — "fix" keyword should yield subagent/sonnet.
model_out2="$("${ROOT}/bin/lacp-route" --task "fix the login bug" --repo-trust trusted --json)"
model_slot2="$(echo "${model_out2}" | jq -r '.model_slot')"
model_hint2="$(echo "${model_out2}" | jq -r '.model_hint')"
assert_eq "${model_slot2}" "subagent" "model-routing-fix:model_slot"
assert_eq "${model_hint2}" "sonnet" "model-routing-fix:model_hint"

# Case 8: model routing — "debug" keyword should yield reasoning/opus.
model_out3="$("${ROOT}/bin/lacp-route" --task "debug the memory leak" --repo-trust trusted --json)"
model_slot3="$(echo "${model_out3}" | jq -r '.model_slot')"
model_hint3="$(echo "${model_out3}" | jq -r '.model_hint')"
assert_eq "${model_slot3}" "reasoning" "model-routing-debug:model_slot"
assert_eq "${model_hint3}" "opus" "model-routing-debug:model_hint"

# Case 9: model routing — "research" keyword should yield search/sonnet.
model_out4="$("${ROOT}/bin/lacp-route" --task "research alternative approaches" --repo-trust trusted --json)"
model_slot4="$(echo "${model_out4}" | jq -r '.model_slot')"
model_hint4="$(echo "${model_out4}" | jq -r '.model_hint')"
assert_eq "${model_slot4}" "search" "model-routing-research:model_slot"
assert_eq "${model_hint4}" "sonnet" "model-routing-research:model_hint"

# Case 10: model routing — no matching keyword → default subagent/sonnet.
model_out5="$("${ROOT}/bin/lacp-route" --task "hello world" --repo-trust trusted --json)"
model_slot5="$(echo "${model_out5}" | jq -r '.model_slot')"
model_hint5="$(echo "${model_out5}" | jq -r '.model_hint')"
assert_eq "${model_slot5}" "subagent" "model-routing-default:model_slot"
assert_eq "${model_hint5}" "sonnet" "model-routing-default:model_hint"

echo "[route-test] all route policy tests passed"
