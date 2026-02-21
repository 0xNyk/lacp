# Harness Engineering Research (2026-02-21)

## Scope

Research question:
- Which harness patterns are currently validated by primary sources?
- What concrete changes should LACP adopt for orchestrator loops and sandboxed sub-agents?

## Primary Sources

- OpenAI: Harness Engineering (2026-02-11)  
  https://openai.com/index/harness-engineering/
- LangChain: Improving Deep Agents with Harness Engineering (2026-02)  
  https://blog.langchain.com/improving-deep-agents-with-harness-engineering/
- Anthropic: Claude Code Sandboxing  
  https://www.anthropic.com/engineering/claude-code-sandboxing
- Google DeepMind: Intelligent AI Delegation (arXiv:2602.11865, submitted 2026-02-12)  
  https://arxiv.org/abs/2602.11865
- Docker: Official docs + container runtime references  
  https://docs.docker.com/
  https://docs.docker.com/engine/security/
  https://docs.docker.com/reference/cli/docker/container/run/

## Key Findings

1. Harness quality is increasingly determined by loop design, verification gates, and trace analysis rather than model swaps.
2. Self-verification does not emerge reliably by default; it must be enforced by policy/hook checkpoints.
3. Sandboxing must be explicit and auditable, with clear permission boundaries and reproducible runtime profiles.
4. Delegation systems require accountability and verifiability across agent-to-agent handoffs; ad-hoc logs are insufficient.
5. Practical teams improve faster when they instrument failures and run structured iteration loops against those failures.

## Implications for LACP

1. Treat harness contracts as first-class config:
   - task plan schema
   - sandbox profile catalog
   - verification policy catalog
2. Keep orchestration optional but gated:
   - tmux/dmux adapter can improve parallelism
   - all orchestration remains routed through `lacp-sandbox-run` risk/budget/approval gates
3. Require machine-checkable evidence for loop progression:
   - verify commands and outcomes per task stage
   - fail closed on missing required checks
4. Maintain release gates as operator default before go-live:
   - tests
   - doctor
   - cache thresholds
   - skill supply-chain audit

## Mapping to Proposed Workflow

User workflow:
- SPECS -> ORCHESTRATOR -> ordered tasks by deps
- Ralph Loop 1 (N iters) -> Loop 2 on fail with memory
- Code quality loops
- DONE

LACP mapping:
- SPECS -> `tasks.json` that validates against `config/harness/tasks.schema.json`
- Task runtime -> profile from `config/harness/sandbox-profiles.yaml`
- Loop completion gate -> policy from `config/harness/verification-policy.yaml`
- Pre-live safety -> `bin/lacp release-gate`

## Current Gaps (Next Iteration)

1. Add a `lacp harness validate` command to validate `tasks.json` directly against schema and policy references.
2. Add receipt chaining between task attempts for stronger delegation audit trails.
3. Add benchmarked harness profiles (latency/cost/success) for model/tool policy tuning.

