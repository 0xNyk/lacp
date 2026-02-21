#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}" "${TMP}/workspace"

profiles_file="${TMP}/profiles.yaml"
verification_file="${TMP}/verification.yaml"
tasks_ok_file="${TMP}/tasks-ok.json"
tasks_fail_file="${TMP}/tasks-fail.json"

cat > "${profiles_file}" <<'EOF'
version: "1.0"
default_profile: "local-safe"
profiles:
  local-safe:
    route: "trusted_local"
    backend: "local"
    network: "off"
    tool_allowlist: ["bash", "python3"]
    filesystem:
      writable_roots: ["$LACP_AUTOMATION_ROOT", "$LACP_KNOWLEDGE_ROOT", "$LACP_DRAFTS_ROOT"]
    resources:
      cpu_limit: "2"
      memory_mb: 1024
      timeout_seconds: 300
    risk_tier: "safe"
EOF

cat > "${verification_file}" <<'EOF'
version: "1.0"
default_policy: "default"
policies:
  default:
    required:
      checks:
        - id: "check-artifact"
          command: "test -f artifact.txt"
    thresholds:
      min_passed_checks: 1
      max_flaky_retries: 0
      max_regression_budget: 0
    failure_action: "require_human_review"
EOF

cat > "${tasks_ok_file}" <<EOF
{
  "version": "1.0",
  "spec_id": "spec-harness-run-ok",
  "generated_at_utc": "2026-02-21T04:40:00Z",
  "orchestrator": {
    "reasoning_tier": "high",
    "memory_keys": ["ci"],
    "max_restarts_per_task": 1,
    "default_models": {
      "planner": "gpt-5",
      "implementer": "gpt-5-codex",
      "verifier": "gpt-5"
    }
  },
  "tasks": [
    {
      "id": "task-a",
      "title": "create artifact",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "default",
      "runner": {"command": "echo ok > artifact.txt"}
    },
    {
      "id": "task-b",
      "title": "consume artifact",
      "complexity": "low",
      "depends_on": ["task-a"],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "default",
      "runner": {"command": "test -f artifact.txt && echo done >> artifact.txt"}
    }
  ]
}
EOF

cat > "${tasks_fail_file}" <<EOF
{
  "version": "1.0",
  "spec_id": "spec-harness-run-fail",
  "generated_at_utc": "2026-02-21T04:40:00Z",
  "orchestrator": {
    "reasoning_tier": "high",
    "memory_keys": ["ci"],
    "max_restarts_per_task": 1,
    "default_models": {
      "planner": "gpt-5",
      "implementer": "gpt-5-codex",
      "verifier": "gpt-5"
    }
  },
  "tasks": [
    {
      "id": "task-fail",
      "title": "always fails",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "default",
      "runner": {"command": "false"}
    }
  ]
}
EOF

ok_json="$("${ROOT}/bin/lacp-harness-run" \
  --tasks "${tasks_ok_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json)"

echo "${ok_json}" | jq -e '.ok == true' >/dev/null
echo "${ok_json}" | jq -e '.summary.succeeded == 2' >/dev/null
echo "${ok_json}" | jq -e '.summary.receipts_total >= 2' >/dev/null
echo "${ok_json}" | jq -e '.summary.receipt_chain_head | length > 0' >/dev/null

run_dir="$(echo "${ok_json}" | jq -r '.run_dir')"
first_receipt="$(jq -r '.receipt.receipt_hash' "${run_dir}/task-a/loop1-attempt-01.json")"
second_prev="$(jq -r '.receipt.prev_receipt_hash' "${run_dir}/task-b/loop1-attempt-01.json")"
if [[ "${first_receipt}" != "${second_prev}" ]]; then
  echo "[harness-run-test] FAIL receipt chain mismatch between task-a and task-b" >&2
  exit 1
fi

set +e
"${ROOT}/bin/lacp-harness-run" \
  --tasks "${tasks_fail_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[harness-run-test] FAIL expected failing harness run rc=1, got ${rc}" >&2
  exit 1
fi

echo "[harness-run-test] harness run tests passed"
