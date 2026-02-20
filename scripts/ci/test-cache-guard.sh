#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

HOME_FIX="${TMP}/home"
mkdir -p "${HOME_FIX}/.codex/sessions/2026/02/20"
mkdir -p "${HOME_FIX}/.claude/projects/demo" "${HOME_FIX}/.codex" "${HOME_FIX}/.claude"

cat > "${HOME_FIX}/.codex/sessions/2026/02/20/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:00:00.000Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":1000,"cached_input_tokens":800,"output_tokens":50,"total_tokens":1050}}}}
EOF

cat > "${HOME_FIX}/.claude/projects/demo/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:05:00.000Z","message":{"usage":{"input_tokens":200,"cache_creation_input_tokens":0,"cache_read_input_tokens":100,"output_tokens":40}}}
EOF

# Should pass with moderate threshold.
HOME="${HOME_FIX}" "${ROOT}/bin/lacp-cache-guard" --hours 9999 --min-hit-rate 0.5 --min-usage-events 2 --json >/dev/null

# Should fail with strict threshold.
set +e
HOME="${HOME_FIX}" "${ROOT}/bin/lacp-cache-guard" --hours 9999 --min-hit-rate 0.99 --min-usage-events 2 --json >/dev/null
rc=$?
set -e
if [[ "${rc}" -ne 1 ]]; then
  echo "[cache-guard-test] FAIL expected strict guard to fail with rc=1, got ${rc}" >&2
  exit 1
fi

echo "[cache-guard-test] cache guard tests passed"
