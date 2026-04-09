---
name: quality-gate
description: "Production quality gate for agent sessions. Activates on session stop to evaluate work quality using 4-dimension weighted scoring (completeness, honesty, deferral ratio, work evidence). Catches rationalization patterns, verifies test claims, and generates handoff artifacts for session continuity. Use sprint contracts to define done-criteria before building."
---

# Quality Gate

This plugin evaluates your work at session end using criteria-based scoring:

- **Completeness** (35%): Did you finish what you committed to?
- **Honesty** (30%): Are claims about tests/status verified?
- **Deferral ratio** (20%): How much was pushed to "later"?
- **Work evidence** (15%): Files changed relative to scope claimed

## Sprint Contracts

Before implementing, state your sprint contract:
- What files will be modified
- What tests will pass
- What the acceptance criteria are

The quality gate evaluates against these criteria at session end.

## Handoff Artifacts

On every non-trivial stop, a handoff artifact is generated with:
- Task summary, files modified, test status
- Git branch and diff summary
- Next steps for the following session

The next session automatically receives the handoff.

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `LACP_QUALITY_GATE_THRESHOLD` | `2.5` | Minimum weighted score (1-5) |
| `LACP_QUALITY_GATE_MODEL` | `llama3.1:8b` | Ollama model for scoring |
| `LACP_BLIND_SPOT_ENABLED` | `0` | Enable blind spot reflection |
