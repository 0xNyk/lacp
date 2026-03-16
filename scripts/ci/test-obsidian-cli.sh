#!/usr/bin/env bash
set -euo pipefail

# Tests for lacp-obsidian CLI: status, audit, backup, restore, plugins, graph-config.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

PASS_COUNT=0
FAIL_COUNT=0

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[obsidian-cli] FAIL ${label}: expected='${expected}' actual='${actual}'" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[obsidian-cli] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "${haystack}" != *"${needle}"* ]]; then
    echo "[obsidian-cli] FAIL ${label}: '${needle}' not found in output" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[obsidian-cli] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_gt() {
  local actual="$1"
  local threshold="$2"
  local label="$3"
  if ! python3 -c "import sys; sys.exit(0 if float('${actual}') > float('${threshold}') else 1)" 2>/dev/null; then
    echo "[obsidian-cli] FAIL ${label}: expected ${actual} > ${threshold}" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
  echo "[obsidian-cli] PASS ${label}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

CLI="${ROOT}/bin/lacp-obsidian"

# --- Test 1: status runs without error ---
echo "--- Test 1: status ---"
out="$("${CLI}" status --json 2>&1)" || true
exit_code=0
"${CLI}" status --json >/dev/null 2>&1 || exit_code=$?
assert_eq "${exit_code}" "0" "status_exits_zero"

vault_path="$(echo "${out}" | python3 -c "import json,sys; print(json.load(sys.stdin)['vault_path'])" 2>/dev/null || echo "")"
assert_contains "${vault_path}" "obsidian" "status_vault_path_set"

# --- Test 2: plugins lists installed plugins ---
echo "--- Test 2: plugins ---"
plugins_out="$("${CLI}" plugins --json 2>&1)"
plugin_count="$(echo "${plugins_out}" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")"
assert_gt "${plugin_count}" "0" "plugins_count_positive"

# --- Test 3: audit returns valid JSON with drift key ---
echo "--- Test 3: audit ---"
audit_out="$("${CLI}" audit --json 2>&1)" || true
has_drift="$(echo "${audit_out}" | python3 -c "import json,sys; d=json.load(sys.stdin); print('drift' in d)" 2>/dev/null || echo "False")"
assert_eq "${has_drift}" "True" "audit_json_has_drift_key"

has_ok="$(echo "${audit_out}" | python3 -c "import json,sys; d=json.load(sys.stdin); print('ok' in d)" 2>/dev/null || echo "False")"
assert_eq "${has_ok}" "True" "audit_json_has_ok_key"

# --- Test 4: backup creates snapshot directory ---
echo "--- Test 4: backup ---"
backup_out="$("${CLI}" backup --json 2>&1)"
snap_path="$(echo "${backup_out}" | python3 -c "import json,sys; print(json.load(sys.stdin)['path'])" 2>/dev/null || echo "")"
if [[ -n "${snap_path}" && -d "${snap_path}" ]]; then
  assert_eq "true" "true" "backup_creates_snapshot_dir"
else
  assert_eq "false" "true" "backup_creates_snapshot_dir"
fi

# --- Test 5: backup + restore roundtrip (isolated) ---
echo "--- Test 5: backup/restore roundtrip ---"
MOCK_VAULT="${TMP}/mock-vault"
MOCK_OBSIDIAN="${MOCK_VAULT}/.obsidian"
MOCK_PLUGINS="${MOCK_OBSIDIAN}/plugins"
mkdir -p "${MOCK_PLUGINS}/test-plugin"

# Create mock config files
echo '{"file-explorer": true, "graph": true}' > "${MOCK_OBSIDIAN}/core-plugins.json"
echo '["test-plugin"]' > "${MOCK_OBSIDIAN}/community-plugins.json"
echo '{"showOrphans": false, "hideUnresolved": true, "colorGroups": []}' > "${MOCK_OBSIDIAN}/graph.json"
echo '{"id": "test-plugin", "name": "Test", "version": "1.0.0"}' > "${MOCK_PLUGINS}/test-plugin/manifest.json"

# Create a mock manifest for the isolated test
MOCK_MANIFEST_DIR="${TMP}/mock-config/obsidian"
mkdir -p "${MOCK_MANIFEST_DIR}"
cat > "${MOCK_MANIFEST_DIR}/manifest.json" <<'JSON'
{
  "schema_version": "1",
  "vault_path": "WILL_BE_REPLACED",
  "core_plugins": {"file-explorer": true, "graph": true},
  "community_plugins": ["test-plugin"],
  "graph_view": {"showOrphans": false, "hideUnresolved": true, "colorGroups": []}
}
JSON
python3 -c "
import json
with open('${MOCK_MANIFEST_DIR}/manifest.json') as f:
    d = json.load(f)
d['vault_path'] = '${MOCK_VAULT}'
with open('${MOCK_MANIFEST_DIR}/manifest.json', 'w') as f:
    json.dump(d, f, indent=2)
"

# Backup using real vault
backup_out2="$(LACP_OBSIDIAN_VAULT="${MOCK_VAULT}" "${CLI}" backup --json 2>&1)"
snap_ts="$(echo "${backup_out2}" | python3 -c "import json,sys; print(json.load(sys.stdin)['snapshot'])" 2>/dev/null || echo "")"

# Modify the file
echo '{"file-explorer": false, "graph": false}' > "${MOCK_OBSIDIAN}/core-plugins.json"

# Verify it changed
modified_val="$(python3 -c "import json; print(json.load(open('${MOCK_OBSIDIAN}/core-plugins.json'))['file-explorer'])")"
assert_eq "${modified_val}" "False" "roundtrip_file_modified"

# Restore
LACP_OBSIDIAN_VAULT="${MOCK_VAULT}" "${CLI}" restore --snapshot "${snap_ts}" >/dev/null 2>&1

# Verify original is back
restored_val="$(python3 -c "import json; print(json.load(open('${MOCK_OBSIDIAN}/core-plugins.json'))['file-explorer'])")"
assert_eq "${restored_val}" "True" "roundtrip_restore_original"

# --- Test 6: graph-config shows colorGroups count ---
echo "--- Test 6: graph-config ---"
gc_out="$("${CLI}" graph-config --json 2>&1)"
cg_count="$(echo "${gc_out}" | python3 -c "import json,sys; print(json.load(sys.stdin)['colorGroups_count'])" 2>/dev/null || echo "0")"
assert_gt "${cg_count}" "0" "graph_config_colorgroups_positive"

has_orphans="$(echo "${gc_out}" | python3 -c "import json,sys; print('showOrphans' in json.load(sys.stdin))" 2>/dev/null || echo "False")"
assert_eq "${has_orphans}" "True" "graph_config_has_show_orphans"

# --- Summary ---
echo ""
echo "[obsidian-cli] Results: pass=${PASS_COUNT} fail=${FAIL_COUNT}"
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "[obsidian-cli] SOME TESTS FAILED" >&2
  exit 1
fi
echo "[obsidian-cli] all obsidian-cli tests passed"
