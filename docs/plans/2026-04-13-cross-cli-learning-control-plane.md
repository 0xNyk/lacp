# LACP Cross-CLI Learning Control-Plane Implementation Plan

> For Hermes: execute this plan with subagent-driven-development and keep learning in shadow mode until promotion gates pass.

Goal
Build a reversible, measurable, cross-CLI self-learning layer for Claude/Codex/Hermes in LACP without changing LACP’s harness-first scope.

Architecture
LACP remains a control plane (not a runtime). We add an additive learning loop around existing wrappers/harness/provenance:
1) capture run outcomes,
2) score and quarantine candidate lessons,
3) promote only verifier-backed lessons,
4) retrieve high-confidence hints pre-run,
5) route decisions with rollback-safe guardrails.

Tech stack
- Shell + Python in existing LACP command patterns
- JSON schemas in config/
- Existing harness contracts and verification policies
- Existing provenance and memory commands (`lacp-provenance`, `lacp-sms`, `lacp-reflect`)

Out of scope (for now)
- full model fine-tuning
- autonomous production swarms
- provider-specific lock-in

---

## Phase 1 (Day 0-30): Instrument + Judge (shadow mode)

### Task 1: Define learning event contract
Objective: create strict schema for capture events.
Files:
- Create: `config/learning/learning-events.schema.json`
- Create: `config/learning/README.md`
Acceptance:
- schema validates required fields: event_id, session_id, task_hash, cli, outcome, verifier_signals, artifact_refs, timestamp.

### Task 2: Define promotion policy contract
Objective: codify promotion thresholds and rollback triggers.
Files:
- Create: `config/learning/promotion-policy.json`
Acceptance:
- includes minimum evidence count, confidence floor, regression budget, decay/TTL, and rollback thresholds.

### Task 3: Implement capture command
Objective: add a command to extract normalized learning events from run artifacts.
Files:
- Create: `bin/lacp-learn-capture`
- Create: `hooks/learn_capture.py`
- Modify: `bin/lacp-sandbox-run` (optional hook integration, feature-flagged)
Tests:
- Create: `scripts/ci/test-learning-loop.sh` (capture section)
Acceptance:
- capture runs in shadow mode and does not alter current routing when disabled.

### Task 4: Implement retrieval command (shadow)
Objective: pre-run recall of top-k high-confidence lessons.
Files:
- Create: `bin/lacp-learn-retrieve`
- Modify: `bin/lacp-sandbox-run` (preflight retrieval injection, feature-flagged)
Tests:
- Extend: `scripts/ci/test-learning-loop.sh` (retrieval section)
Acceptance:
- hard caps: max 5 hints, token budget cap, confidence floor enforced.

### Task 5: Feature flags + observability baseline
Objective: safe rollout controls and baseline metrics.
Files:
- Modify: `docs/runbook.md`
- Modify: `docs/local-dev-loop.md`
Acceptance:
- documented flags:
  - `LACP_LEARNING_ENABLED=0|1`
  - `LACP_LEARNING_MODE=off|shadow|enforce`
  - `LACP_LEARNING_MAX_HINTS`
- baseline metrics visible in run artifacts.

---

## Phase 2 (Day 31-60): Codify + Route (canary)

### Task 6: Implement promotion command
Objective: move candidates from quarantine to promoted lessons only when gates pass.
Files:
- Create: `bin/lacp-learn-promote`
- Modify: `bin/lacp-sms` (or integration point) to register promoted lessons
Tests:
- Extend: `scripts/ci/test-learning-loop.sh` (promotion section)
Acceptance:
- requires verifier-backed evidence and non-regression gate.

### Task 7: Implement evaluation command (offline replay)
Objective: reproducible A/B evaluation for with/without retrieval.
Files:
- Create: `bin/lacp-learn-eval`
- Create: `docs/research/learning-loop-eval-method.md`
Acceptance:
- deterministic replay report with success/rollback/intervention deltas.

### Task 8: Implement rollback command
Objective: one-command disable + rollback of last promotion set.
Files:
- Create: `bin/lacp-learn-rollback`
- Modify: `docs/incident-response.md`
Acceptance:
- rollback completes in <5 minutes and leaves clear audit trail.

### Task 9: Cross-CLI normalization
Objective: normalize recurring problems across Claude/Codex/Hermes under canonical lesson IDs.
Files:
- Create: `scripts/runners/learning-normalize.sh` (or equivalent existing runner location)
- Modify: `docs/framework-scope.md` (portability note)
Acceptance:
- same failure pattern across CLIs maps to one canonical lesson.

---

## Phase 3 (Day 61-90): Guarded enforcement + trust moat

### Task 10: Signed learning receipts
Objective: bind promotions/retrieval hits into provenance chain.
Files:
- Modify: `bin/lacp-provenance`
- Modify: `docs/runbook.md`
Acceptance:
- receipts generated for >=95% of governed runs.

### Task 11: Policy packs + SDK-facing docs
Objective: package learning policy profiles for partner usage.
Files:
- Create: `config/learning/policy-packs/starter.json`
- Create: `docs/learning-policy-packs.md`
Acceptance:
- at least one low-risk pack and one security-sensitive pack documented.

### Task 12: Default-on decision gate
Objective: formal go/no-go for moving from shadow/canary to enforce mode.
Files:
- Modify: `docs/release-checklist.md`
- Modify: `docs/runbook.md`
Acceptance:
- enforce mode remains off until all KPI gates pass for 3 consecutive days.

---

## Verification and KPI gates

Safety/quality
- misroute rate <= 1.0% (shadow), <= 0.5% (enforce pilot)
- replay divergence <= 0.2%
- sev-1 automation incidents = 0

Operational
- p95 routing latency <= 250ms
- manual override rate < 10% by day 7 canary
- rollback execution < 5 minutes

Learning/moat
- receipt coverage >= 95% of routed decisions
- adapter coverage >= 75% of active CLI traffic by day 7
- low-risk promotion pass ratio >= 80%

---

## Execution commands (operator quickstart)

```bash
# validate task DAG
bin/lacp harness-validate --tasks docs/plans/2026-04-13-cross-cli-learning-control-plane.dag.json --json | jq

# run in shadow mode only
export LACP_LEARNING_ENABLED=1
export LACP_LEARNING_MODE=shadow
bin/lacp harness-run --tasks docs/plans/2026-04-13-cross-cli-learning-control-plane.dag.json --workdir . --json | jq

# evaluate before any enforce rollout
bin/lacp-learn-eval --json | jq
```

Rollback trigger
If any canary window breaches threshold for 2 consecutive windows, execute:

```bash
bin/lacp-learn-rollback --last --json | jq
export LACP_LEARNING_MODE=shadow
```
