# Cross-CLI Learning Loop — Demo Runbook

> Hands-on walkthrough of the learning loop's safe-by-default behavior. Demonstrates
> that Phase A (shadow capture) is observational and changes nothing about routing.

## Prereqs

```bash
command -v jq python3   # required
```

## 1. Inspect the safe defaults

```bash
bin/lacp-learn-capture status
```

Expected: `learning enabled : 0`, `mode : off`, `mutates routing : false`.
Out of the box, nothing is captured and nothing is influenced.

## 2. Prove capture is a no-op while disabled

```bash
bin/lacp-learn-capture record --task "deploy to prod" --status success --json | jq '{captured, reason}'
```

Expected: `{"captured": false, "reason": "disabled_or_non_shadow"}`. No file is written.

## 3. Enable shadow capture (observational only)

```bash
export LACP_LEARNING_ENABLED=1
export LACP_LEARNING_MODE=shadow
export LACP_LEARNING_ROOT="$(mktemp -d)/learning"   # demo-isolated store

bin/lacp-learn-capture record \
  --cli claude --event-type task_outcome \
  --task "run memory benchmark on internal repo" \
  --repo-trust trusted --keywords "benchmark,memory" \
  --status success --score 0.9 --duration-ms 1200 --json \
  | jq '{captured, mutates_routing, id: .event.event_id}'

bin/lacp-learn-capture list
```

Each event carries a content-derived `event_id`, a SHA-256 `source_hash`, and full
provenance (agent_id, project_slug, session fingerprint).

## 4. Prove shadow parity — routing is unaffected

```bash
A="$(LACP_LEARNING_MODE=off     bin/lacp-route --task 'run memory benchmark on internal repo' --repo-trust trusted --json | jq -S .)"
B="$(LACP_LEARNING_MODE=shadow  bin/lacp-route --task 'run memory benchmark on internal repo' --repo-trust trusted --json | jq -S .)"
[ "$A" = "$B" ] && echo "IDENTICAL — shadow capture changed nothing ✅" || echo "DIVERGED ❌"
```

This is the core safety claim of Phase A, enforced in CI by
`scripts/ci/test-learning-loop.sh`.

## 5. Instant rollback

```bash
export LACP_LEARNING_ENABLED=0
export LACP_LEARNING_MODE=off
```

Capture stops immediately. No persisted state influences any later run.

## Next steps (Council)

- **Epic B (#113):** advisory retrieval — surface bounded, non-authoritative hints
  at preflight, gated by the caps in `config/learning/promotion-policy.json`.
- **Epic C (#114):** guarded promotion — verifier-backed evidence, eval gate, and a
  one-command rollback before any `enforce` behavior ships.
