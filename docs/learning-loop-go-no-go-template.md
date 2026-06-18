# Cross-CLI Learning Loop — Enforcement GO/NO-GO Decision

> Fill this out before promoting the learning loop from `advisory` to `enforce`.
> Promotion is irreversible-by-default in effect (it changes autonomous behavior),
> so every gate below must be **GO** and the rollback drill must be green.

## Run metadata
- Date (UTC):
- Decision owner:
- Approver 1:
- Approver 2:
- Eval window (split-at):
- Store path:

## Metric gates (from `lacp-learn-eval gate`)
Run: `lacp-learn-eval gate --json`

| Gate | Threshold | Actual | GO/NO-GO |
|------|-----------|--------|----------|
| `min_events` | ≥ 50 | | |
| `min_uplift_pct` | ≥ 10.0 | | |
| `min_hit_rate` | ≥ 0.90 | | |
| `min_mrr` | ≥ 0.65 | | |

## Manual gates (from `lacp-learn-promote check`)
Run: `lacp-learn-promote check --verifier-evidence <file> --approver A --approver B --json`

- [ ] **Verifier evidence** attached (non-empty file, hash recorded in promotion record)
- [ ] **Two-person approval** (two distinct approvers named above)
- [ ] **Provenance verification** passes (`lacp-provenance verify`)

## Safety gates
- [ ] Rollback drill is green: `lacp-learn-rollback drill` completes within
      `promotion-policy.json.rollback.max_drill_minutes` and returns to `shadow`
- [ ] Kill switch verified: `LACP_LEARNING_ENABLED=0` disables capture/retrieval
- [ ] Fallback understood: if uplift < 10% after two weekly cycles, narrow scope to
      Learning Packs (`promotion-policy.json.fallback`)

## Decision

- [ ] **GO** — all gates pass. Run:
      `lacp-learn-promote apply --verifier-evidence <file> --approver A --approver B`
- [ ] **NO-GO** — one or more gates failed (list them). Mode stays `shadow`.

## Rollback plan
If anything regresses post-promotion:
```bash
lacp-learn-rollback now --reason "<what regressed>"
# Verify:
lacp-learn-rollback status   # mode == shadow, promotion_active == false
```

## Notes / dissent
(Record any unresolved risk or dissenting view here.)
