# LACP 7-Day Execution Checklist: Cross-CLI Self-Learning (Council Verdict)

Goal
Ship a safe, measurable v0 learning loop for Claude/Codex/Hermes with hard rollback and no surprise behavior changes.

Decision constraints
- Default learning mode remains `off` unless explicitly enabled.
- `shadow` mode must not mutate routing/policy outcomes.
- No enforce/promotion without eval + canary + rollback proof.

North-star KPI
- >=10% uplift in successful task completion vs baseline by end of two weekly cycles.

Safety KPIs
- Provenance verification pass rate: 100% on governed runs.
- Rollback execution: <5 minutes.
- Sev-1 automation incidents: 0.

---

## Day 1: Contracts + guardrails

Checklist
- [ ] Create `config/learning/learning-events.schema.json`
- [ ] Create `config/learning/promotion-policy.json`
- [ ] Add/verify env contracts:
  - [ ] `LACP_LEARNING_ENABLED=0|1`
  - [ ] `LACP_LEARNING_MODE=off|shadow|enforce`
  - [ ] `LACP_LEARNING_MAX_HINTS`
  - [ ] `LACP_LEARNING_MAX_TOKEN_BUDGET`
- [ ] Add schema validation to CI (`scripts/ci/test-learning-loop.sh` section A)

Verification
- [ ] Invalid fixture fails schema validation
- [ ] Valid fixture passes schema validation

---

## Day 2: Shadow capture (no routing mutation)

Checklist
- [ ] Implement `bin/lacp-learn-capture`
- [ ] Add optional capture hook to sandbox flow (feature-flagged)
- [ ] Persist capture artifacts under `${LACP_KNOWLEDGE_ROOT}/data/learning/`

Verification
- [ ] Shadow mode emits valid capture artifacts
- [ ] Route/output parity test: off vs shadow are identical

---

## Day 3: Learning-loop CI harness

Checklist
- [ ] Create `scripts/ci/test-learning-loop.sh`
- [ ] Add gates:
  - [ ] Contract gate (schema/policy)
  - [ ] No-regression gate (route parity in shadow)
  - [ ] Capture artifact/provenance gate
- [ ] Wire into existing CI matrix

Verification
- [ ] CI fails on any route mutation in shadow mode
- [ ] CI fails on missing provenance fields

---

## Day 4: Advisory retrieval slice (bounded)

Checklist
- [ ] Implement `bin/lacp-learn-retrieve`
- [ ] Add advisory-only preflight hint injection (flagged)
- [ ] Enforce caps:
  - [ ] `max_hints <= 5`
  - [ ] token budget cap
  - [ ] confidence floor

Verification
- [ ] Retrieval returns bounded hints only
- [ ] Retrieval cannot directly mutate route/policy decisions

---

## Day 5: Offline replay + evaluation baseline

Checklist
- [ ] Implement `bin/lacp-learn-eval`
- [ ] Build deterministic baseline/treatment fixture set
- [ ] Output comparison report (success rate, retries, intervention rate)

Verification
- [ ] Repeated eval runs are deterministic on same fixtures
- [ ] Report includes clear pass/fail gate decision

---

## Day 6: Guarded promotion + rollback drills

Checklist
- [ ] Implement `bin/lacp-learn-promote`
- [ ] Implement `bin/lacp-learn-rollback`
- [ ] Require verifier-backed evidence and policy thresholds
- [ ] Add kill switches and promotion freeze mechanism

Verification
- [ ] Rollback drill completes in <5 minutes
- [ ] Failed promotion gate blocks enforcement automatically

---

## Day 7: Council demo + go/no-go gate

Checklist
- [ ] Run `/council` deliberation with Strategist/Shipper/Risk seats
- [ ] Present before/after metrics from eval harness
- [ ] Present dissent + unresolved risks
- [ ] Record go/no-go decision for next week’s rollout ring

Verification
- [ ] Demo includes explicit fallback trigger (<10% uplift => narrow to Learning Packs)
- [ ] Demo includes rollback proof artifact and run links

---

## Required deliverables by end of Day 7

- [ ] `docs/demos/council-next-steps-demo.md` runbook
- [ ] `scripts/demos/run-council-next-steps-demo.sh`
- [x] Open GitHub issues for A/B/C epics and linked tasks
  - [x] #112 Epic A: Shadow capture slice
  - [x] #113 Epic B: Advisory retrieval slice
  - [x] #114 Epic C: Guarded promotion + eval + rollback
- [ ] PR(s) with CI evidence and artifacts
