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
artifact_schema_file="${TMP}/artifact.schema.json"

cat > "${artifact_schema_file}" <<'EOF'
{
  "type": "object",
  "required": ["status"],
  "properties": {
    "status": {"type": "string"}
  }
}
EOF

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
          command: "test -f artifact.json"
    thresholds:
      min_passed_checks: 1
      max_flaky_retries: 0
      max_regression_budget: 0
    failure_action: "require_human_review"
  retry-default:
    required:
      checks:
        - id: "check-artifact"
          command: "test -f artifact.json"
    thresholds:
      min_passed_checks: 1
      max_flaky_retries: 0
      max_regression_budget: 0
    failure_action: "retry_same_model"
  block-immediate:
    required:
      checks:
        - id: "check-artifact"
          command: "test -f artifact.json"
    thresholds:
      min_passed_checks: 1
      max_flaky_retries: 0
      max_regression_budget: 0
    failure_action: "block"
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
      "runner": {"command": "printf '{\"status\":\"ok\"}\\n' > artifact.json"},
      "expected_outputs": [
        {"id": "artifact-file", "path": "artifact.json", "required": true, "schema_path": "${artifact_schema_file}"}
      ]
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
      "expected_inputs": [
        {"id": "needs-artifact", "from_task": "task-a", "output_id": "artifact-file", "required": true}
      ],
      "runner": {"command": "test -f artifact.json && echo done >/dev/null"}
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

tasks_block_file="${TMP}/tasks-block.json"
cat > "${tasks_block_file}" <<EOF
{
  "version": "1.0",
  "spec_id": "spec-harness-run-block",
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
      "id": "task-block",
      "title": "fails once then should block",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 3, "loop_2_max": 2, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "block-immediate",
      "runner": {"command": "false"}
    }
  ]
}
EOF

tasks_input_contract_fail_file="${TMP}/tasks-input-contract-fail.json"
cat > "${tasks_input_contract_fail_file}" <<EOF
{
  "version": "1.0",
  "spec_id": "spec-harness-run-input-contract-fail",
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
      "id": "task-upstream",
      "title": "create artifact upstream",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "retry-default",
      "runner": {"command": "printf '{\"status\":\"ok\"}\\n' > artifact.json"},
      "expected_outputs": [
        {"id": "artifact-file", "path": "artifact.json", "required": true, "schema_path": "${artifact_schema_file}"}
      ]
    },
    {
      "id": "task-downstream",
      "title": "consume missing contract id",
      "complexity": "low",
      "depends_on": ["task-upstream"],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "retry-default",
      "expected_inputs": [
        {"id": "needs-missing", "from_task": "task-upstream", "output_id": "not-there", "required": true}
      ],
      "runner": {"command": "echo should-not-run"}
    }
  ]
}
EOF

tasks_output_schema_fail_file="${TMP}/tasks-output-schema-fail.json"
cat > "${tasks_output_schema_fail_file}" <<EOF
{
  "version": "1.0",
  "spec_id": "spec-harness-run-output-schema-fail",
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
      "id": "task-schema-fail",
      "title": "create invalid schema output",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "retry-default",
      "runner": {"command": "printf '{\"wrong\":\"x\"}\\n' > artifact.json"},
      "expected_outputs": [
        {"id": "artifact-file", "path": "artifact.json", "required": true, "schema_path": "${artifact_schema_file}"}
      ]
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

set +e
block_json="$("${ROOT}/bin/lacp-harness-run" \
  --tasks "${tasks_block_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json)"
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[harness-run-test] FAIL expected block-immediate harness run rc=1, got ${rc}" >&2
  exit 1
fi
echo "${block_json}" | jq -e '.tasks[0].failure_action == "block"' >/dev/null
echo "${block_json}" | jq -e '.tasks[0].attempts == 1' >/dev/null

set +e
input_fail_json="$("${ROOT}/bin/lacp-harness-run" \
  --tasks "${tasks_input_contract_fail_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json)"
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[harness-run-test] FAIL expected input contract invalid run rc=1, got ${rc}" >&2
  exit 1
fi
echo "${input_fail_json}" | jq -e '.summary.blocked == 1' >/dev/null
echo "${input_fail_json}" | jq -e '.tasks[1].reason == "input_contract_invalid"' >/dev/null

set +e
schema_fail_json="$("${ROOT}/bin/lacp-harness-run" \
  --tasks "${tasks_output_schema_fail_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json)"
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[harness-run-test] FAIL expected output schema invalid run rc=1, got ${rc}" >&2
  exit 1
fi
echo "${schema_fail_json}" | jq -e '.tasks[0].status == "failed"' >/dev/null
echo "${schema_fail_json}" | jq -e '.tasks[0].output_errors | length >= 1' >/dev/null

echo "[harness-run-test] harness run tests passed"
