#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[memory-tools-test] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    exit 1
  fi
  echo "[memory-tools-test] PASS ${label}"
}

export HOME="${TMP}/home"
export LACP_SKIP_DOTENV="1"
export LACP_OBSIDIAN_VAULT="${HOME}/obsidian/vault"
mkdir -p "${LACP_OBSIDIAN_VAULT}/inbox/queue-generated"
mkdir -p "${LACP_OBSIDIAN_VAULT}/knowledge/decisions"
mkdir -p "${LACP_OBSIDIAN_VAULT}/knowledge/concepts"

cat > "${LACP_OBSIDIAN_VAULT}/knowledge/decisions/decision-a.md" <<'EOF'
---
id: d-1
type: decision
layer: 2
status: active
confidence: 0.9
source_urls:
  - "https://example.com/a"
links:
  contradicts:
    - "[[concept-a]]"
---
# Decision A
EOF

cat > "${LACP_OBSIDIAN_VAULT}/knowledge/concepts/concept-a.md" <<'EOF'
---
id: c-1
type: concept
layer: 2
status: active
confidence: 0.7
source_urls:
  - "https://example.com/c"
links:
  supersedes:
    - "[[decision-a]]"
---
# Concept A
EOF

resolve_json="$(${ROOT}/bin/lacp-brain-resolve --id d-1 --resolution superseded --superseded-by c-1 --reason "validated new pattern" --json)"
assert_eq "$(echo "${resolve_json}" | jq -r '.ok')" "true" "resolve.ok"
assert_eq "$(echo "${resolve_json}" | jq -r '.resolution')" "superseded" "resolve.resolution"
assert_eq "$(echo "${resolve_json}" | jq -r '.updated_count >= 1')" "true" "resolve.updated_count"

kpi_json="$(${ROOT}/bin/lacp-memory-kpi --json)"
assert_eq "$(echo "${kpi_json}" | jq -r '.ok')" "true" "kpi.ok"
assert_eq "$(echo "${kpi_json}" | jq -r '.kpis.total_notes >= 2')" "true" "kpi.total_notes"
assert_eq "$(echo "${kpi_json}" | jq -r '.kpis.contradiction_notes >= 1')" "true" "kpi.contradiction_notes"

opt_json="$(${ROOT}/bin/lacp-obsidian-memory-optimize --vault "${LACP_OBSIDIAN_VAULT}" --json)"
assert_eq "$(echo "${opt_json}" | jq -r '.ok')" "true" "opt.ok"
assert_eq "$(echo "${opt_json}" | jq -r '.graph.wrote')" "true" "opt.graph.wrote"

echo "[memory-tools-test] memory tools tests passed"
