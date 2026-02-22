#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

BIN_DIR="${TMP}/bin"
NATIVE_DIR="${TMP}/native"
mkdir -p "${BIN_DIR}" "${NATIVE_DIR}"

cat > "${NATIVE_DIR}/claude" <<'SH'
#!/usr/bin/env bash
echo "native-claude"
SH
chmod +x "${NATIVE_DIR}/claude"

cat > "${NATIVE_DIR}/codex" <<'SH'
#!/usr/bin/env bash
echo "native-codex"
SH
chmod +x "${NATIVE_DIR}/codex"

# Existing local shim should be backed up for claude.
cat > "${BIN_DIR}/claude" <<'SH'
#!/usr/bin/env bash
echo "legacy-claude-shim"
SH
chmod +x "${BIN_DIR}/claude"

"${ROOT}/bin/lacp-adopt-local" \
  --bin-dir "${BIN_DIR}" \
  --claude-native "${NATIVE_DIR}/claude" \
  --codex-native "${NATIVE_DIR}/codex" \
  --force \
  --json | jq -e '.ok == true' >/dev/null

[[ -x "${BIN_DIR}/claude" ]] || { echo "[adopt-local-test] FAIL missing claude wrapper" >&2; exit 1; }
[[ -x "${BIN_DIR}/codex" ]] || { echo "[adopt-local-test] FAIL missing codex wrapper" >&2; exit 1; }
[[ -x "${BIN_DIR}/claude.native" ]] || { echo "[adopt-local-test] FAIL missing claude backup" >&2; exit 1; }
[[ ! -e "${BIN_DIR}/codex.native" ]] || { echo "[adopt-local-test] FAIL unexpected codex backup" >&2; exit 1; }

rg -q 'LACP_MANAGED_WRAPPER=1' "${BIN_DIR}/claude"
rg -q 'LACP_MANAGED_WRAPPER=1' "${BIN_DIR}/codex"

# Bypass should call native binary immediately.
out_claude="$(LACP_BYPASS=1 "${BIN_DIR}/claude")"
[[ "${out_claude}" == "legacy-claude-shim" ]] || { echo "[adopt-local-test] FAIL bypass claude mismatch" >&2; exit 1; }

out_codex="$(LACP_BYPASS=1 "${BIN_DIR}/codex")"
[[ "${out_codex}" == "native-codex" ]] || { echo "[adopt-local-test] FAIL bypass codex mismatch" >&2; exit 1; }

# --root can be passed after command (parser regression guard).
"${ROOT}/bin/lacp-adopt-local" --dry-run --json --bin-dir "${BIN_DIR}" \
  --claude-native "${NATIVE_DIR}/claude" --codex-native "${NATIVE_DIR}/codex" | jq -e '.ok == true' >/dev/null

"${ROOT}/bin/lacp-unadopt-local" --bin-dir "${BIN_DIR}" --json | jq -e '.ok == true' >/dev/null

# claude restored from backup, codex wrapper removed.
grep -q 'legacy-claude-shim' "${BIN_DIR}/claude" || { echo "[adopt-local-test] FAIL claude restore mismatch" >&2; exit 1; }
[[ ! -e "${BIN_DIR}/claude.native" ]] || { echo "[adopt-local-test] FAIL claude backup should be consumed" >&2; exit 1; }
[[ ! -e "${BIN_DIR}/codex" ]] || { echo "[adopt-local-test] FAIL codex wrapper should be removed" >&2; exit 1; }

# Symlink safety regression guard:
# adopt-local must never overwrite symlink targets.
cat > "${NATIVE_DIR}/claude-real" <<'SH'
#!/usr/bin/env bash
echo "native-claude-real"
SH
chmod +x "${NATIVE_DIR}/claude-real"
ln -sfn "${NATIVE_DIR}/claude-real" "${BIN_DIR}/claude"

"${ROOT}/bin/lacp-adopt-local" \
  --bin-dir "${BIN_DIR}" \
  --codex-native "${NATIVE_DIR}/codex" \
  --json | jq -e '.ok == true' >/dev/null

# Wrapper installed at symlink path, target binary preserved.
rg -q 'LACP_MANAGED_WRAPPER=1' "${BIN_DIR}/claude"
out_claude_safe="$(LACP_BYPASS=1 "${BIN_DIR}/claude")"
[[ "${out_claude_safe}" == "native-claude-real" ]] || { echo "[adopt-local-test] FAIL symlink target was clobbered" >&2; exit 1; }

"${ROOT}/bin/lacp-unadopt-local" --bin-dir "${BIN_DIR}" --json | jq -e '.ok == true' >/dev/null
out_claude_restored="$( "${BIN_DIR}/claude")"
[[ "${out_claude_restored}" == "native-claude-real" ]] || { echo "[adopt-local-test] FAIL symlink restore mismatch" >&2; exit 1; }

echo "[adopt-local-test] adopt/unadopt tests passed"
