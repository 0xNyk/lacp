# Contributing to LACP

LACP sits in the execution path of local coding agents. Changes to routing, approvals,
credentials, hooks, installation, or release commands need failure-path tests, not only a
successful example.

## Workflow

1. Create a branch from `main`.
2. Make focused changes with clear commit messages.
3. Run local validation before pushing.
4. Open a pull request with the affected commands, risk, and verification evidence.

## Commit convention

Use Conventional Commits:
- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`
- `chore:`

## Local validation

Run from repo root:

```bash
for f in bin/* scripts/*.sh scripts/runners/*.sh; do
  bash -n "$f"
done

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck bin/* scripts/*.sh scripts/runners/*.sh
fi

./scripts/ci/smoke.sh
./scripts/ci/test-route-policy.sh
```

For documentation-only changes, run `git diff --check`, verify each changed command
against `--help`, and check edited links. For code changes, run `bin/lacp-test --isolated`
when the full suite is practical; explain any skipped test in the pull request.

## Pull request evidence

Include:

- the operator problem and the smallest change that solves it;
- commands and files affected;
- tests run with their exit status;
- security, compatibility, migration, and rollback notes where applicable;
- screenshots only when terminal or TUI output changed.

Generated or AI-assisted work is accepted under the same standard as other work. The
contributor remains responsible for provenance, licensing, behavior, and verification.

## Design constraints

- LACP is a control plane, not a runtime.
- Keep policy decisions explicit and explainable.
- Prefer non-interactive commands in automation paths.
- Preserve local-first operation and auditable artifact outputs.

## Conduct

Be specific, technical, and respectful. Do not publish credentials, private logs, exploit
details, or another person's identifying data in an issue or pull request. Maintainers may
remove content or restrict participation when a contribution creates safety or harassment
risk.
