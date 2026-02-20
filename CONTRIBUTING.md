# Contributing

## Workflow

1. Create a branch from `main`.
2. Make focused changes with clear commit messages.
3. Run local validation before pushing.
4. Open a pull request with rationale and verification evidence.

## Commit Convention

Use Conventional Commits:
- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`
- `chore:`

## Local Validation

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

## Design Constraints

- LACP is a control plane, not a runtime.
- Keep policy decisions explicit and explainable.
- Prefer non-interactive commands in automation paths.
- Preserve local-first operation and auditable artifact outputs.
