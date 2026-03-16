# Clipper -> Autonomous Knowledge Loop (LACP)

This runbook operationalizes web clip intake for agent workflows using LACP gates, harness contracts, and loop discipline.

Companion vault playbook:
- `${LACP_OBSIDIAN_VAULT:-~/obsidian/vault}/inbox/queue-generated/obsidian-clipper-to-knowledge-autonomous-pipeline-2026-03-09.md`

## Objectives
- Capture high volume without polluting durable memory.
- Convert raw clips into triaged, source-grounded knowledge.
- Promote only validated outputs into canonical knowledge paths.

## Pipeline phases
1. ingest (raw clips)
2. triage (classify/tag/route)
3. deep-dive extraction (claims + confidence)
4. integration (canonical updates)
5. hygiene (dedupe/contradiction/archive)

## Recommended folders (vault side)
- `inbox/clips/raw/`
- `inbox/clips/triage/`
- `inbox/clips/deep-dive/`
- `inbox/clips/archive/`

## LACP execution pattern

### A) Validate harness contracts
```bash
cd ~/control/frameworks/lacp
./scripts/ci/test-harness-contracts.sh
```

### B) Run triage loop with profile
```bash
bin/lacp loop \
  --task "clip triage batch" \
  --loop-profile safe-verify \
  --repo-trust trusted \
  --json -- /bin/echo "run clip triage"
```

### C) Run structured harness plan
```bash
bin/lacp harness-validate --tasks ./tasks.json --json | jq
bin/lacp harness-run --tasks ./tasks.json --workdir . --json | jq
```

### D) Replay failures
```bash
bin/lacp harness-replay --run-id <run-id> --task-id <task-id> --workdir . --json | jq
```

### E) Evidence and quality gates
```bash
bin/lacp knowledge-doctor --root ~/control/knowledge/knowledge-memory --json | jq
bin/lacp canary --json | jq
```

## Minimal tasks.json shape (concept)
Use your schema in `config/harness/tasks.schema.json` and model these task classes:
- `clip_ingest`
- `clip_triage`
- `clip_deep_dive`
- `clip_integration`
- `clip_hygiene`

Each task should define:
- explicit input/output contract
- risk class
- verification policy
- failure_action (`block` / `require_human_review` / retry modes)

## Policies
- No durable memory writes from raw clips.
- No promotion without provenance and confidence tags.
- Contradictions require explicit resolution.
- Touched-file unresolved links must be zero before promotion.

## Weekly cadence
- Daily: ingest + triage
- 2–3x/week: deep-dive batches
- Weekly: integration + hygiene + benchmark checks

## Metrics to track
- triage throughput
- deep-dive conversion rate
- promotion acceptance rate
- contradiction rate
- unresolved-link incidents
- signal-to-noise trend

## Rollback
If quality regresses:
1. pause promotions
2. replay failed tasks
3. revert last profile/parameter change
4. run doctor + canary before resume
