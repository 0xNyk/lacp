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
tasks_file="${TMP}/tasks.json"

cat > "${profiles_file}" <<'YAML'
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
YAML

cat > "${verification_file}" <<'YAML'
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
YAML

cat > "${tasks_file}" <<'EOF_JSON'
{
  "version": "1.0",
  "spec_id": "spec-harness-replay-fail",
  "generated_at_utc": "2026-02-25T00:00:00Z",
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
      "id": "task-replay",
      "title": "replay fixture",
      "complexity": "low",
      "depends_on": [],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {"max_input_tokens": 1000, "max_output_tokens": 500},
      "iterations": {"loop_1_max": 1, "loop_2_max": 0, "quality_loop_max": 0},
      "sandbox_profile": "local-safe",
      "verification_policy": "default",
      "runner": {"command": "echo noop >/dev/null"}
    }
  ]
}
EOF_JSON

set +e
run_json="$(${ROOT}/bin/lacp-harness-run \
  --tasks "${tasks_file}" \
  --profiles "${profiles_file}" \
  --verification "${verification_file}" \
  --workdir "${TMP}/workspace" \
  --json)"
run_rc=$?
set -e

if [[ "${run_rc}" -ne 1 ]]; then
  echo "[harness-replay-test] FAIL expected failing harness run rc=1, got ${run_rc}" >&2
  exit 1
fi

echo "${run_json}" | jq -e '.tasks[0].status == "failed"' >/dev/null
run_id="$(echo "${run_json}" | jq -r '.run_id')"

set +e
replay_json="$(${ROOT}/bin/lacp-harness-replay \
  --run-id "${run_id}" \
  --task-id task-replay \
  --workdir "${TMP}/workspace" \
  --json)"
replay_rc=$?
set -e

if [[ "${replay_rc}" -ne 1 ]]; then
  echo "[harness-replay-test] FAIL expected replay with verification rc=1, got ${replay_rc}" >&2
  exit 1
fi

echo "${replay_json}" | jq -e '.ok == false' >/dev/null
echo "${replay_json}" | jq -e '.runner.exit_code == 0' >/dev/null
echo "${replay_json}" | jq -e '.verification.replayed == true and .verification.ok == false' >/dev/null

echo "{}" > "${TMP}/workspace/artifact.json"
replay_runner_only_json="$(${ROOT}/bin/lacp-harness-replay \
  --run-id "${run_id}" \
  --task-id task-replay \
  --workdir "${TMP}/workspace" \
  --runner-only \
  --json)"

echo "${replay_runner_only_json}" | jq -e '.ok == true' >/dev/null
echo "${replay_runner_only_json}" | jq -e '.verification.replayed == false' >/dev/null

echo "[harness-replay-test] harness replay tests passed"
