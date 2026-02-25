#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

valid_tasks="${TMP}/tasks-valid.json"
invalid_tasks="${TMP}/tasks-invalid.json"

cat > "${valid_tasks}" <<'EOF'
{
  "version": "1.0",
  "spec_id": "spec-demo-001",
  "generated_at_utc": "2026-02-21T04:30:00Z",
  "orchestrator": {
    "reasoning_tier": "high",
    "memory_keys": ["product-brief", "repo-notes"],
    "max_restarts_per_task": 2,
    "default_models": {
      "planner": "gpt-5",
      "implementer": "gpt-5-codex",
      "verifier": "gpt-5"
    }
  },
  "tasks": [
    {
      "id": "task-plan",
      "title": "Plan initial implementation",
      "complexity": "medium",
      "depends_on": [],
      "primary_model": "gpt-5",
      "reasoning_budget": {
        "max_input_tokens": 4000,
        "max_output_tokens": 1200
      },
      "iterations": {
        "loop_1_max": 3,
        "loop_2_max": 1,
        "quality_loop_max": 1
      },
      "sandbox_profile": "local-safe",
      "verification_policy": "code-quality-default",
      "expected_outputs": [
        {
          "id": "plan-doc",
          "path": "docs/plan.md",
          "required": false
        }
      ]
    },
    {
      "id": "task-impl",
      "title": "Implement and validate feature",
      "complexity": "high",
      "depends_on": ["task-plan"],
      "primary_model": "gpt-5-codex",
      "reasoning_budget": {
        "max_input_tokens": 6000,
        "max_output_tokens": 2000
      },
      "iterations": {
        "loop_1_max": 5,
        "loop_2_max": 2,
        "quality_loop_max": 2
      },
      "sandbox_profile": "local-untrusted",
      "verification_policy": "security-sensitive",
      "expected_inputs": [
        {
          "id": "needs-plan",
          "from_task": "task-plan",
          "output_id": "plan-doc",
          "required": false
        }
      ]
    }
  ]
}
EOF

cat > "${invalid_tasks}" <<'EOF'
{
  "version": "1.0",
  "spec_id": "spec-demo-bad",
  "generated_at_utc": "2026-02-21T04:30:00Z",
  "orchestrator": {
    "reasoning_tier": "ultra",
    "memory_keys": [],
    "max_restarts_per_task": 99,
    "default_models": {
      "planner": "gpt-5",
      "implementer": "",
      "verifier": "gpt-5"
    }
  },
  "tasks": [
    {
      "id": "task-bad",
      "title": "Bad",
      "complexity": "extreme",
      "depends_on": ["task-missing", "task-bad"],
      "primary_model": "gpt-5",
      "reasoning_budget": {
        "max_input_tokens": 64,
        "max_output_tokens": 64
      },
      "iterations": {
        "loop_1_max": 0,
        "loop_2_max": 30,
        "quality_loop_max": 30
      },
      "sandbox_profile": "does-not-exist",
      "verification_policy": "unknown-policy"
    }
  ]
}
EOF

"${ROOT}/bin/lacp-harness-validate" --tasks "${valid_tasks}" --json >/dev/null

set +e
"${ROOT}/bin/lacp-harness-validate" --tasks "${invalid_tasks}" --json >/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[harness-validate-test] FAIL expected invalid tasks to return rc=1, got ${rc}" >&2
  exit 1
fi

echo "[harness-validate-test] harness validate tests passed"
