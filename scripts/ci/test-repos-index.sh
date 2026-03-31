#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export HOME="${TMP}/home"
mkdir -p "${HOME}"
export LACP_SKIP_DOTENV=1
export LACP_AUTOMATION_ROOT="${TMP}/automation"
export LACP_KNOWLEDGE_ROOT="${TMP}/knowledge"
export LACP_DRAFTS_ROOT="${TMP}/drafts"
export LACP_OBSIDIAN_VAULT="${TMP}/vault"
mkdir -p "${LACP_AUTOMATION_ROOT}" "${LACP_KNOWLEDGE_ROOT}" "${LACP_DRAFTS_ROOT}" "${LACP_OBSIDIAN_VAULT}"

# Create mock scan roots with git repos
SCAN_A="${TMP}/scan-a"
SCAN_B="${TMP}/scan-b"
mkdir -p "${SCAN_A}/repo-alpha" "${SCAN_A}/repo-beta" "${SCAN_B}/repo-gamma"
git init --quiet "${SCAN_A}/repo-alpha"
git init --quiet "${SCAN_A}/repo-beta"
git init --quiet "${SCAN_B}/repo-gamma"

# Pre-index repo-beta (simulate already-indexed repo)
mkdir -p "${SCAN_A}/repo-beta/.gitnexus"

export LACP_REPOS_SCAN_ROOTS="${SCAN_A}:${SCAN_B}"

## --- discover subcommand ---
disc_json="$(${ROOT}/bin/lacp-repos-index discover --json)"
echo "${disc_json}" | jq -e '.ok == true and .kind == "repos_index_discover"' >/dev/null
echo "${disc_json}" | jq -e '.repos_count == 3' >/dev/null || {
  echo "[repos-index-test] expected 3 repos, got $(echo "${disc_json}" | jq '.repos_count')" >&2
  exit 1
}

# repo-beta should show as indexed
beta_indexed="$(echo "${disc_json}" | jq '[.repos[] | select(.name == "repo-beta")] | .[0].indexed')"
[[ "${beta_indexed}" == "true" ]] || { echo "[repos-index-test] repo-beta should be indexed" >&2; exit 1; }

# repo-alpha should show as not indexed
alpha_indexed="$(echo "${disc_json}" | jq '[.repos[] | select(.name == "repo-alpha")] | .[0].indexed')"
[[ "${alpha_indexed}" == "false" ]] || { echo "[repos-index-test] repo-alpha should not be indexed" >&2; exit 1; }

## --- discover with --scan-root override ---
SCAN_C="${TMP}/scan-c"
mkdir -p "${SCAN_C}/repo-delta"
git init --quiet "${SCAN_C}/repo-delta"
override_json="$(${ROOT}/bin/lacp-repos-index discover --scan-root "${SCAN_C}" --json)"
echo "${override_json}" | jq -e '.repos_count == 4' >/dev/null || {
  echo "[repos-index-test] expected 4 repos with --scan-root, got $(echo "${override_json}" | jq '.repos_count')" >&2
  exit 1
}

## --- discover human-readable output ---
disc_text="$(${ROOT}/bin/lacp-repos-index discover)"
echo "${disc_text}" | grep -q "repo-alpha" || { echo "[repos-index-test] discover text missing repo-alpha" >&2; exit 1; }
echo "${disc_text}" | grep -q '\[\*\].*repo-beta' || { echo "[repos-index-test] discover text missing indexed marker for repo-beta" >&2; exit 1; }

## --- status subcommand ---
stat_json="$(${ROOT}/bin/lacp-repos-index status --json)"
echo "${stat_json}" | jq -e '.ok == true and .kind == "repos_index_status"' >/dev/null
echo "${stat_json}" | jq -e '.total == 3' >/dev/null
echo "${stat_json}" | jq -e '.indexed == 1' >/dev/null   # repo-beta
echo "${stat_json}" | jq -e '.unindexed == 2' >/dev/null  # alpha + gamma

## --- index dry-run subcommand (with mock gitnexus) ---
# Create mock gitnexus binary that creates .gitnexus dir
MOCK_BIN="${TMP}/mock-bin"
mkdir -p "${MOCK_BIN}"
cat > "${MOCK_BIN}/gitnexus" <<'MOCK'
#!/usr/bin/env bash
# Mock gitnexus: create .gitnexus dir in the target repo
if [[ "${1:-}" == "analyze" && -n "${2:-}" ]]; then
  mkdir -p "${2}/.gitnexus"
  echo "mock indexed: ${2}"
  exit 0
fi
if [[ "${1:-}" == "list" ]]; then
  echo "mock list"
  exit 0
fi
echo "mock gitnexus: unknown command" >&2
exit 1
MOCK
chmod +x "${MOCK_BIN}/gitnexus"
export PATH="${MOCK_BIN}:${PATH}"

dryrun_json="$(${ROOT}/bin/lacp-repos-index index --dry-run --json)"
echo "${dryrun_json}" | jq -e '.ok == true and .dry_run == true' >/dev/null
echo "${dryrun_json}" | jq -e '.indexed == 2' >/dev/null  # alpha + gamma (beta skipped)
echo "${dryrun_json}" | jq -e '.skipped == 1' >/dev/null  # beta

# Dry run should NOT create .gitnexus dirs
[[ ! -d "${SCAN_A}/repo-alpha/.gitnexus" ]] || { echo "[repos-index-test] dry-run created .gitnexus" >&2; exit 1; }

## --- index real run ---
index_json="$(${ROOT}/bin/lacp-repos-index index --json)"
echo "${index_json}" | jq -e '.ok == true and .dry_run == false' >/dev/null
echo "${index_json}" | jq -e '.indexed == 2' >/dev/null
echo "${index_json}" | jq -e '.skipped == 1' >/dev/null
echo "${index_json}" | jq -e '.failed == 0' >/dev/null

# .gitnexus should now exist in alpha and gamma
[[ -d "${SCAN_A}/repo-alpha/.gitnexus" ]] || { echo "[repos-index-test] index did not create .gitnexus for alpha" >&2; exit 1; }
[[ -d "${SCAN_B}/repo-gamma/.gitnexus" ]] || { echo "[repos-index-test] index did not create .gitnexus for gamma" >&2; exit 1; }

## --- re-index skips already indexed ---
reindex_json="$(${ROOT}/bin/lacp-repos-index index --json)"
echo "${reindex_json}" | jq -e '.indexed == 0 and .skipped == 3' >/dev/null || {
  echo "[repos-index-test] re-index should skip all 3 repos" >&2
  exit 1
}

## --- index --force re-indexes ---
force_json="$(${ROOT}/bin/lacp-repos-index index --force --json)"
echo "${force_json}" | jq -e '.indexed == 3 and .skipped == 0' >/dev/null || {
  echo "[repos-index-test] --force should re-index all repos" >&2
  exit 1
}

## --- status after indexing ---
post_stat_json="$(${ROOT}/bin/lacp-repos-index status --json)"
echo "${post_stat_json}" | jq -e '.indexed == 3 and .unindexed == 0' >/dev/null

## --- index handles failures gracefully ---
# Create a mock gitnexus that fails for specific repos
cat > "${MOCK_BIN}/gitnexus" <<'MOCK'
#!/usr/bin/env bash
if [[ "${1:-}" == "analyze" && -n "${2:-}" ]]; then
  if echo "${2}" | grep -q "repo-alpha"; then
    exit 1  # Simulate failure
  fi
  mkdir -p "${2}/.gitnexus"
  exit 0
fi
exit 1
MOCK
chmod +x "${MOCK_BIN}/gitnexus"

# Remove alpha's .gitnexus to test failure
rm -rf "${SCAN_A}/repo-alpha/.gitnexus"

fail_json="$(${ROOT}/bin/lacp-repos-index index --force --json)"
echo "${fail_json}" | jq -e '.failed == 1' >/dev/null || {
  echo "[repos-index-test] expected 1 failure" >&2
  exit 1
}
echo "${fail_json}" | jq -e '.indexed == 2' >/dev/null  # beta + gamma succeed

## --- index-repo subcommand (single repo) ---
# Restore working mock gitnexus
cat > "${MOCK_BIN}/gitnexus" <<'MOCK'
#!/usr/bin/env bash
if [[ "${1:-}" == "analyze" && -n "${2:-}" ]]; then
  mkdir -p "${2}/.gitnexus"
  exit 0
fi
exit 1
MOCK
chmod +x "${MOCK_BIN}/gitnexus"

# Remove alpha's .gitnexus for fresh index-repo test
rm -rf "${SCAN_A}/repo-alpha/.gitnexus"

export LACP_REPOS_SCAN_ROOTS="${SCAN_A}:${SCAN_B}"

repo_json="$(${ROOT}/bin/lacp-repos-index index-repo "${SCAN_A}/repo-alpha" --json)"
echo "${repo_json}" | jq -e '.ok == true and .kind == "repos_index_repo"' >/dev/null
echo "${repo_json}" | jq -e '.repo_name == "repo-alpha"' >/dev/null
echo "${repo_json}" | jq -e '.index_status == "indexed"' >/dev/null
echo "${repo_json}" | jq -e '.did_index == true' >/dev/null
echo "${repo_json}" | jq -e '.note_written == true' >/dev/null

# Vault note should exist
note_path="$(echo "${repo_json}" | jq -r '.note_path')"
[[ -f "${note_path}" ]] || { echo "[repos-index-test] index-repo did not write vault note" >&2; exit 1; }
grep -q "repo-alpha" "${note_path}" || { echo "[repos-index-test] vault note missing repo name" >&2; exit 1; }
grep -q "type: repository" "${note_path}" || { echo "[repos-index-test] vault note missing type frontmatter" >&2; exit 1; }
grep -q "gitnexus_indexed:" "${note_path}" || { echo "[repos-index-test] vault note missing gitnexus status" >&2; exit 1; }

## --- index-repo skips already-indexed ---
skip_json="$(${ROOT}/bin/lacp-repos-index index-repo "${SCAN_A}/repo-alpha" --json)"
echo "${skip_json}" | jq -e '.index_status == "already_indexed"' >/dev/null
echo "${skip_json}" | jq -e '.did_index == false' >/dev/null

## --- index-repo --force re-indexes ---
force_repo_json="$(${ROOT}/bin/lacp-repos-index index-repo "${SCAN_A}/repo-alpha" --force --json)"
echo "${force_repo_json}" | jq -e '.index_status == "indexed" and .did_index == true' >/dev/null

## --- index-repo --dry-run ---
rm -rf "${SCAN_B}/repo-gamma/.gitnexus"
dry_repo_json="$(${ROOT}/bin/lacp-repos-index index-repo "${SCAN_B}/repo-gamma" --dry-run --json)"
echo "${dry_repo_json}" | jq -e '.index_status == "would_index" and .note_written == false' >/dev/null
[[ ! -d "${SCAN_B}/repo-gamma/.gitnexus" ]] || { echo "[repos-index-test] index-repo dry-run created .gitnexus" >&2; exit 1; }

## --- index-repo on non-git dir fails ---
mkdir -p "${TMP}/not-a-repo"
if ${ROOT}/bin/lacp-repos-index index-repo "${TMP}/not-a-repo" --json 2>/dev/null; then
  echo "[repos-index-test] index-repo should fail on non-git dir" >&2
  exit 1
fi

## --- empty scan roots ---
export LACP_REPOS_SCAN_ROOTS="${TMP}/nonexistent"
empty_json="$(${ROOT}/bin/lacp-repos-index discover --json)"
echo "${empty_json}" | jq -e '.ok == true and .repos_count == 0' >/dev/null

## --- help flag ---
help_out="$(${ROOT}/bin/lacp-repos-index --help)"
echo "${help_out}" | grep -q "discover" || { echo "[repos-index-test] help missing discover" >&2; exit 1; }
echo "${help_out}" | grep -q "index-repo" || { echo "[repos-index-test] help missing index-repo" >&2; exit 1; }

echo "[repos-index-test] all tests passed"
