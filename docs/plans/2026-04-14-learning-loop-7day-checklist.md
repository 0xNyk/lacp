# Cross-CLI Learning Loop — 7-Day Implementation Checklist

> Plan of record for Epics A/B/C (#112, #113, #114). Phased, safety-gated rollout
> of cross-CLI self-learning in LACP. Each phase is independently shippable and
> behind kill switches.

## Design principles

1. **Capture before influence.** Phase A only observes. No routing/policy mutation.
2. **Advisory before authoritative.** Phase B surfaces bounded hints; never decides.
3. **Gated promotion.** Phase C requires verifier evidence + thresholds + approval.
4. **Always reversible.** Every phase has an env kill switch and a <5 min rollback.
5. **Provenance-first.** Every event carries agent_id, project_slug, session
   fingerprint, and a content hash.

## Env contracts

| Variable | Default | Meaning |
|----------|---------|---------|
| `LACP_LEARNING_ENABLED` | `0` | Master switch. `0` = capture disabled. |
| `LACP_LEARNING_MODE` | `off` | `off` \| `shadow` \| `advisory` \| `enforce`. |
| `LACP_LEARNING_ROOT` | `$LACP_KNOWLEDGE_ROOT/data/learning` | Event store location. |
| `LACP_LEARNING_SCHEMA_FILE` | `config/learning/learning-events.schema.json` | Event schema. |
| `LACP_LEARNING_POLICY_FILE` | `config/learning/promotion-policy.json` | Promotion thresholds. |

## Phase A — Shadow capture (#112) ✅ shippable slice

- [x] `config/learning/learning-events.schema.json` — strict event schema
- [x] `config/learning/promotion-policy.json` — promotion thresholds contract
- [x] `bin/lacp-learn-capture` — record / validate / list / status (shadow-only)
- [x] Env contracts in `scripts/lacp-lib.sh`
- [x] `scripts/ci/test-learning-loop.sh` — contract + shadow-parity tests
- [x] Registered in `bin/lacp-test`

Acceptance criteria (all met):
- Capture artifacts validate against the schema.
- Invalid fixtures fail in CI (bad enum, `mode=enforce`, missing provenance, extra props).
- `off` vs `shadow` route outputs are byte-identical (shadow parity).
- No direct policy/routing mutation in this phase.
- Events include provenance-required fields (agent_id, project_slug, session
  fingerprint, source_hash).

## Phase B — Advisory retrieval (#113)

- [ ] `bin/lacp-learn-retrieve` — top-k hints with cap enforcement
- [ ] Optional preflight hint injection (feature-flagged, advisory-only)
- [ ] Enforce caps: max hints, token budget, confidence floor (from promotion-policy.json)
- [ ] Extend `test-learning-loop.sh` with retrieval gates
- [ ] Shadow parity remains green

## Phase C — Guarded promotion (#114)

- [ ] `bin/lacp-learn-promote` — promote only on verifier evidence + thresholds
- [ ] `bin/lacp-learn-eval` — deterministic baseline vs treatment report
- [ ] `bin/lacp-learn-rollback` — one-command rollback (<5 min drill)
- [ ] Canary + rollback verification gates in CI/runbook
- [ ] GO/NO-GO decision template; enforcement stays off until gates pass

## Rollback drill

```bash
# Instant disable at any phase:
export LACP_LEARNING_ENABLED=0
export LACP_LEARNING_MODE=off
# Verify routing is unaffected:
bin/lacp-route --task "..." --json
```
