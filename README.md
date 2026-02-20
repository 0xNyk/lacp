# LACP

Local Agent Control Plane for Claude/Codex operations.

`LACP` is a control-plane wrapper around local automation you already run:
- shared memory extraction + sync
- hybrid retrieval benchmark + gates
- snapshot capture for latency/health tracking

It does not replace agent runtimes. It standardizes operations, evidence, and reproducible onboarding.

## Scope

- Memory + knowledge pipeline orchestration
- Retrieval gate verification and evidence collection
- Local bootstrap checks for required roots/scripts
- Runbook-first operations for repeatability

## Quick Start

```bash
cd ~/control/frameworks/lacp
cp config/lacp.env.example .env
bin/lacp-bootstrap
bin/lacp-verify --hours 24
```

## Defaults

These defaults are used unless overridden by env vars in `.env` or shell:

- `LACP_AUTOMATION_ROOT=$HOME/control/automation/ai-dev-optimization`
- `LACP_KNOWLEDGE_ROOT=$HOME/control/knowledge/knowledge-memory`
- `LACP_DRAFTS_ROOT=$HOME/docs/content/drafts`

## Commands

- `bin/lacp-bootstrap`
  - validates command dependencies
  - validates expected directory roots
  - validates required automation scripts exist
- `bin/lacp-verify`
  - runs shared memory extraction and sync
  - runs retrieval benchmark suite with gates
  - captures a fresh system snapshot
  - prints latest benchmark and snapshot artifacts

## Artifact Paths

- Benchmark reports: `~/control/knowledge/knowledge-memory/data/benchmarks/*.json`
- Snapshot reports: `~/control/automation/ai-dev-optimization/data/snapshots/*.json`
- Benchmark log: `~/control/knowledge/knowledge-memory/data/benchmark.log`

## Documentation

- `docs/runbook.md`
- `docs/framework-scope.md`
