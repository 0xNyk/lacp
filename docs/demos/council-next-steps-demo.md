# Demo Runbook: /council decides LACP next steps

Objective
Demonstrate that LACP can use council-style deliberation + measurable eval evidence to decide safe next steps for cross-CLI self-learning.

Audience takeaway
- LACP is not guessing; it uses structured deliberation with dissent.
- Learning is gated by metrics and rollback safety.
- Next actions are concrete and reversible.

Duration
20-30 minutes

---

## Prep (5 minutes)

Required
- repo checked out at `main`
- `gh` authenticated
- baseline and treatment eval fixtures available

Set safety defaults
```bash
export LACP_LEARNING_ENABLED=1
export LACP_LEARNING_MODE=shadow
```

Show current status
```bash
git rev-parse --short HEAD
bin/lacp-status-report --json | jq '.intervention_rate_kpi? // .'
```

---

## Part 1: Council deliberation (8-10 minutes)

Prompt frame
- Decision: What should LACP build in the next 7 days to become a safe self-learning layer across CLIs?
- Constraints: no routing mutation in shadow, proven rollback, measurable uplift.
- Success criteria: >=10% completion uplift, zero sev-1, rollback <5m.

Run council process
1) Strategist seat (control-plane and sequencing)
2) Pragmatic shipper seat (smallest shippable slices + tests)
3) Stoic risk seat (threats, containment, rollback)
4) Synthesizer with anti-convergence and dissent preservation

Expected output artifact
- A/B/C option matrix
- dissent summary
- recommended path + fallback trigger
- immediate 3-step plan

---

## Part 2: Before/after evidence (8-10 minutes)

Run baseline vs treatment replay
```bash
bin/lacp-learn-eval --dataset data/benchmarks/learning-loop-fixtures.json --json | tee /tmp/lacp-learn-eval.json
jq '{success_delta, retry_delta, intervention_delta, decision}' /tmp/lacp-learn-eval.json
```

Show guardrails
```bash
bin/lacp-provenance verify --json | jq
bin/lacp-learn-rollback --last --dry-run --json | jq
```

Must show live
- route parity proof for off vs shadow
- provenance verification pass
- rollback dry-run details

---

## Part 3: Decision gate (5 minutes)

Go/No-go criteria
- GO if:
  - completion uplift >=10% on deterministic replay
  - no shadow-mode route mutation
  - rollback proof <5m
  - no unresolved critical risk
- NO-GO if any critical gate fails

Fallback trigger
- If uplift <10% after two weekly cycles, narrow scope to outcome-dense Learning Packs.

Final call format
- Decision: GO to next ring or NO-GO remain in shadow
- Why: 3 bullets (evidence-backed)
- Dissent: what remains unresolved
- Next 72h tasks: exact commands/owners

---

## Demo checklist

- [ ] Council artifacts captured
- [ ] Eval artifact attached
- [ ] Provenance verification artifact attached
- [ ] Rollback proof attached
- [ ] Final call documented in PR/issue thread
