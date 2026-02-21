#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

REPO="${TMP}/repo"
mkdir -p "${REPO}"
cd "${REPO}"

git init >/dev/null
git config user.email "ci@example.com"
git config user.name "CI"
echo "hello" > README.md
git add README.md
git commit -m "init" >/dev/null

# doctor/list should work
"${ROOT}/bin/lacp-worktree" doctor --repo-root "${REPO}" --json | jq -e '.ok == true and .worktree_count >= 1' >/dev/null
"${ROOT}/bin/lacp-worktree" list --repo-root "${REPO}" --json | jq -e '.ok == true and (.worktrees | length) >= 1' >/dev/null

# create/remove cycle
"${ROOT}/bin/lacp-worktree" create --repo-root "${REPO}" --name "ci-a" --base HEAD --json | jq -e '.ok == true and .branch == "wt/ci-a"' >/dev/null
[[ -d "${REPO}/.worktrees/ci-a" ]] || { echo "[worktree-test] FAIL expected .worktrees/ci-a" >&2; exit 1; }

"${ROOT}/bin/lacp-worktree" list --repo-root "${REPO}" --json | jq -e '.worktrees | map(.path) | any(test("/\\.worktrees/ci-a$"))' >/dev/null

"${ROOT}/bin/lacp-worktree" remove --repo-root "${REPO}" --name "ci-a" --force --json | jq -e '.ok == true and .removed == true' >/dev/null
[[ ! -d "${REPO}/.worktrees/ci-a" ]] || { echo "[worktree-test] FAIL expected ci-a removed" >&2; exit 1; }

# prune dry-run should be valid
"${ROOT}/bin/lacp-worktree" prune --repo-root "${REPO}" --dry-run --json | jq -e '.ok == true and .dry_run == true' >/dev/null

echo "[worktree-test] worktree command tests passed"
