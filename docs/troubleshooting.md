# Troubleshooting

## `fork: Resource temporarily unavailable`

Symptoms:
- `claude` or `codex` wrapper hangs and shell prints repeated `fork: retry`.

Checks:
```bash
ulimit -u
ps -Ao pid,ppid,comm | rg -E 'claude|codex|tmux|dmux'
bin/lacp doctor --json | jq '.ok,.summary'
```

Actions:
- close stale agent sessions/worktrees
- run `bin/lacp orchestrate doctor --json | jq`
- if wrappers are wedged, run `bin/lacp unadopt-local` then `bin/lacp adopt-local`

## SSH execution-context drift

Symptoms:
- session unexpectedly acts on local paths during remote workflows.

Checks:
```bash
bin/lacp session-fingerprint
bin/lacp context-profile render --profile ssh-prod --var REMOTE_HOST=jarv --json | jq
```

Actions:
- enforce context contract and fingerprint on mutating/remote-target runs:
```bash
FP="$(bin/lacp session-fingerprint)"
CTX="$(bin/lacp context-profile render --profile ssh-prod --var REMOTE_HOST=jarv)"
bin/lacp run --task "remote guarded run" --repo-trust trusted --context-contract "${CTX}" --session-fingerprint "${FP}" -- ssh -G leads@jarv
```

## Homebrew install issues

Symptoms:
- `brew install lacp` fails due to release asset/tag mismatch.

Checks:
```bash
bin/lacp release-verify --tag vX.Y.Z --skip-prepare --allow-dirty --json | jq
```

Actions:
- ensure tag exists locally and remotely
- ensure release asset names match `lacp-<version>.tar.gz` + `SHA256SUMS`
- run dry-run tap install check:
```bash
brew info 0xnyk/lacp/lacp
brew install --dry-run 0xnyk/lacp/lacp
```

## Canary failing (`hit_rate`/`mrr`/triage)

Checks:
```bash
bin/lacp canary --json | jq '.summary,.failures'
```

Actions:
- run bounded optimization loop:
```bash
bin/lacp canary-optimize --iterations 3 --hours 24 --json | jq
```
- re-check with release discipline:
```bash
bin/lacp release-prepare --quick --auto-optimize-on-fail --json | jq
```
