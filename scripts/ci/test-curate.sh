#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CURATOR="${ROOT}/automation/scripts/curate_titles.py"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

export LACP_SKIP_DOTENV=1

fail() { echo "[curate-test] FAIL: $1" >&2; exit 1; }

# ---------- 1. self-test (title classification + H1 rejection) ----------
python3 "${CURATOR}" --self-test >/dev/null || fail "self-test"

# ---------- 2. build a synthetic vault ----------
VAULT="${TMP}/vault"
mkdir -p "${VAULT}/research" "${VAULT}/daily"
# category-shaped title WITH a claim H1 -> actionable rename
printf '# Memory graphs beat giant memory files\n\nbody\n' > "${VAULT}/research/Research Notes.md"
# timestamp title, no usable H1 -> candidate, needs human title
printf 'just a log line\n' > "${VAULT}/2026-03-28_13-21-32.md"
# protected daily note -> must be skipped
printf '# 2026-03-02\n' > "${VAULT}/daily/2026-03-02.md"
# already claim-shaped -> skipped
printf '# fine\n' > "${VAULT}/hybrid retrieval outperforms semantic search.md"
# a note that links to the soon-to-be-renamed one
printf 'see [[Research Notes]]\n' > "${VAULT}/index.md"

# ---------- 3. dry-run JSON: correct candidate detection ----------
dry="$(python3 "${CURATOR}" --vault "${VAULT}" --json)"
echo "${dry}" | jq -e '.ok == true' >/dev/null || fail "dry-run ok flag"
echo "${dry}" | jq -e '.applied == false' >/dev/null || fail "dry-run applied=false"
echo "${dry}" | jq -e '.summary.rename_candidates == 2' >/dev/null || fail "expected 2 candidates"
echo "${dry}" | jq -e '.summary.rename_actionable == 1' >/dev/null || fail "expected 1 actionable"
# the daily + already-claim notes must NOT be candidates
echo "${dry}" | jq -e '[.proposals[].note] | index("daily/2026-03-02.md") == null' >/dev/null \
  || fail "protected daily note was flagged"

# ---------- 4. dry-run must not mutate the vault ----------
[[ -f "${VAULT}/research/Research Notes.md" ]] || fail "dry-run renamed a file"

# ---------- 5. needs_curation flag promotes an otherwise-ok title ----------
printf -- '---\nneeds_curation: true\n---\n\n# Claims compound across sessions\n' \
  > "${VAULT}/Context Engineering Playbook.md"
flagged="$(python3 "${CURATOR}" --vault "${VAULT}" --json)"
echo "${flagged}" | jq -e \
  '[.proposals[] | select(.note=="Context Engineering Playbook.md") | .needs_curation] == [true]' \
  >/dev/null || fail "needs_curation flag did not promote the note"

# ---------- 6. --apply renames + fixes wikilinks vault-wide ----------
python3 "${CURATOR}" --vault "${VAULT}" --apply --json >/dev/null
[[ -f "${VAULT}/research/Memory graphs beat giant memory files.md" ]] \
  || fail "apply did not rename the file"
[[ ! -f "${VAULT}/research/Research Notes.md" ]] || fail "old file still present after rename"
grep -q '\[\[Memory graphs beat giant memory files\]\]' "${VAULT}/index.md" \
  || fail "wikilink not rewritten vault-wide"

# ---------- 7. bin/lacp-curate wrapper ----------
wrap="$(LACP_OBSIDIAN_VAULT="${VAULT}" "${ROOT}/bin/lacp-curate" --json)"
echo "${wrap}" | jq -e '.ok == true' >/dev/null || fail "wrapper ok flag"

echo "[curate-test] all curator tests passed"
