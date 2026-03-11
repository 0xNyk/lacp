#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
wf_tmp="${ROOT}/.github/workflows/.ci-policy-test.yml"
mkdir -p "$(dirname "${wf_tmp}")"
cleanup() {
  rm -rf "${TMP}"
  rm -f "${wf_tmp}"
}
trap cleanup EXIT

HOME_FIX="${TMP}/home"
mkdir -p "${HOME_FIX}/.codex/sessions/2026/02/20"
mkdir -p "${HOME_FIX}/.claude/projects/demo"
mkdir -p "${TMP}/skills/safe-skill"
mkdir -p "${TMP}/automation/scripts" "${TMP}/knowledge/data/benchmarks" "${TMP}/knowledge/data/sandbox-runs" "${TMP}/drafts"

cat > "${TMP}/automation/scripts/run_shared_memory.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${TMP}/automation/scripts/run_memory_pipeline.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${TMP}/automation/scripts/run_memory_benchmark_suite.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "${TMP}/automation/scripts/capture_snapshot.py" <<'EOF'
#!/usr/bin/env python3
print("ok")
EOF
chmod +x "${TMP}/automation/scripts/"*

cat > "${HOME_FIX}/.codex/sessions/2026/02/20/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:00:00.000Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":1000,"cached_input_tokens":850,"output_tokens":50,"total_tokens":1050}}}}
EOF

cat > "${HOME_FIX}/.claude/projects/demo/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:05:00.000Z","message":{"usage":{"input_tokens":200,"cache_creation_input_tokens":0,"cache_read_input_tokens":120,"output_tokens":40}}}
EOF

cat > "${TMP}/skills/safe-skill/SKILL.md" <<'EOF'
---
name: safe-skill
description: safe
---

Only local, auditable commands.
EOF

export HOME="${HOME_FIX}"
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_ALLOW_EXTERNAL_REMOTE="false"
export LACP_NO_EXTERNAL_CI="true"

"${ROOT}/bin/lacp-release-gate" \
  --skip-tests \
  --skip-doctor \
  --cache-hours 9999 \
  --cache-min-hit-rate 0.5 \
  --cache-min-events 2 \
  --skill-path "${TMP}/skills" \
  --json >/dev/null

set +e
"${ROOT}/bin/lacp-release-gate" \
  --skip-tests \
  --skip-doctor \
  --cache-hours 9999 \
  --cache-min-hit-rate 0.99 \
  --cache-min-events 2 \
  --skill-path "${TMP}/skills" >/dev/null 2>/dev/null
rc=$?
set -e

if [[ "${rc}" -ne 1 ]]; then
  echo "[release-gate-test] FAIL expected strict cache threshold to fail with rc=1, got ${rc}" >&2
  exit 1
fi

cat > "${wf_tmp}" <<'EOF'
name: ci-policy-test
on: [push]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo "noop"
EOF

set +e
"${ROOT}/bin/lacp-release-gate" \
  --skip-tests \
  --skip-doctor \
  --skip-cache \
  --skip-skill-audit \
  --skip-shell-hardening >/dev/null 2>/dev/null
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[release-gate-test] FAIL expected external-ci policy gate to fail with rc=1, got ${rc}" >&2
  exit 1
fi

"${ROOT}/bin/lacp-release-gate" \
  --skip-tests \
  --skip-doctor \
  --skip-cache \
  --skip-skill-audit \
  --skip-shell-hardening \
  --allow-external-ci >/dev/null

echo "[release-gate-test] release gate tests passed"
