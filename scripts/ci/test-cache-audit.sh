#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

HOME_FIX="${TMP}/home"
mkdir -p "${HOME_FIX}/.codex/sessions/2026/02/20"
mkdir -p "${HOME_FIX}/.claude/projects/demo"
mkdir -p "${HOME_FIX}/.codex" "${HOME_FIX}/.claude"

cat > "${HOME_FIX}/.codex/sessions/2026/02/20/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:00:00.000Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":1000,"cached_input_tokens":400,"output_tokens":120,"total_tokens":1120}}}}
EOF

cat > "${HOME_FIX}/.claude/projects/demo/sample.jsonl" <<'EOF'
{"timestamp":"2026-02-20T10:05:00.000Z","message":{"usage":{"input_tokens":500,"cache_creation_input_tokens":50,"cache_read_input_tokens":150,"output_tokens":60}}}
EOF

cat > "${HOME_FIX}/.codex/history.jsonl" <<'EOF'
{"session_id":"x","ts":1760000000,"text":"hello"}
EOF

cat > "${HOME_FIX}/.claude/history.jsonl" <<'EOF'
{"display":"hello","timestamp":1760000000000}
EOF

out_json="$(
  HOME="${HOME_FIX}" "${ROOT}/bin/lacp-cache-audit" --hours 9999 --json
)"

overall_prompt="$(echo "${out_json}" | jq -r '.overall.prompt_tokens')"
overall_cached="$(echo "${out_json}" | jq -r '.overall.cached_tokens')"
overall_hit="$(echo "${out_json}" | jq -r '.overall.cache_hit_rate_estimate')"
usage_events="$(echo "${out_json}" | jq -r '.overall.records_with_usage')"
confidence="$(echo "${out_json}" | jq -r '.confidence.status')"

if [[ "${overall_prompt}" != "1500" ]]; then
  echo "[cache-audit-test] FAIL prompt_tokens expected 1500 got ${overall_prompt}" >&2
  exit 1
fi
if [[ "${overall_cached}" != "600" ]]; then
  echo "[cache-audit-test] FAIL cached_tokens expected 600 got ${overall_cached}" >&2
  exit 1
fi
if [[ "${overall_hit}" != "0.4" ]]; then
  echo "[cache-audit-test] FAIL cache_hit_rate_estimate expected 0.4 got ${overall_hit}" >&2
  exit 1
fi
if [[ "${usage_events}" != "2" ]]; then
  echo "[cache-audit-test] FAIL records_with_usage expected 2 got ${usage_events}" >&2
  exit 1
fi
if [[ "${confidence}" != "high" ]]; then
  echo "[cache-audit-test] FAIL confidence expected high got ${confidence}" >&2
  exit 1
fi

echo "[cache-audit-test] cache audit schema tests passed"
