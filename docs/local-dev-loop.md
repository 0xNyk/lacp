# Local Dev Loop

This is the recommended daily loop for improving LACP safely on real workloads.

## 1) Bootstrap once

```bash
cd /path/to/lacp
bin/lacp bootstrap-system --profile starter --with-verify
```

## 2) Start work with guardrails

```bash
bin/lacp doctor --json | jq '.ok,.summary'
bin/lacp mode show
bin/lacp orchestrate doctor --json | jq
```

## 3) Iterate in isolated cycles

```bash
bin/lacp test --quick
bin/lacp loop --task "targeted change" --repo-trust trusted --dry-run --json -- /bin/echo hello
```

For mutating or remote-target commands, prefer context contracts and session fingerprints:

```bash
FP="$(bin/lacp session-fingerprint)"
CTX="$(bin/lacp context-profile render --profile local-dev)"
bin/lacp run --task "guarded mutation" --repo-trust trusted --context-contract "${CTX}" --session-fingerprint "${FP}" -- /bin/mkdir -p /tmp/lacp-safe
```

## 4) Swarm/worktree path

```bash
bin/lacp worktree list --json | jq
bin/lacp swarm doctor --json | jq
bin/lacp swarm status --latest --json | jq '.collaboration_summary'
```

## 5) Pre-release loop

```bash
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
bin/lacp release-verify --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --json | jq
```
