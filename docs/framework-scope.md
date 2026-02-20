# Framework Scope

## What LACP Is

LACP is a local control plane for Claude/Codex operations:
- orchestrates memory and retrieval operations
- enforces verification gates
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
