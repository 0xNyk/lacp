# Framework Scope

## What LACP Is

LACP is a harness-first local control plane for Claude/Codex/Hermes operations:
- runs agent tasks through a verification/evidence harness
- enforces policy and approval gates
- standardizes artifact outputs and runbooks

## What LACP Is Not

- not a new agent runtime
- not a replacement for Claude/Codex CLIs
- not a hosted SaaS service

## Design Contract

1. Reuse existing local automation scripts where possible.
2. Require artifact-backed verification before claiming health.
3. Keep all operations local-first and path-explicit.
4. Preserve portability through env-based root overrides.
