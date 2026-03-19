<p align="center">
  <img src="docs/assets/readme-banner.png" alt="LACP" width="1200">
</p>

<h3 align="center"><em>Local Agent Control Plane for Claude and Codex</em></h3>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/status-alpha-orange.svg" alt="Alpha">
  <img src="https://img.shields.io/badge/runtime-local--first-blue.svg" alt="Local first">
  <img src="https://img.shields.io/badge/memory-obsidian%20bundle-7C3AED.svg" alt="Obsidian bundle">
</p>

<p align="center">
  <a href="#why-lacp">Why LACP?</a> •
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#daily-developer-workflow">Workflow</a> •
  <a href="#command-reference">Command Reference</a> •
  <a href="#testing">Testing</a>
</p>

---

LACP turns local agent work into an auditable control plane with reproducible onboarding, policy-based execution gates, verification loops, and artifact-backed health records.

It is **not** a new agent runtime. It sits around the tools you already use and makes them safer, more repeatable, and easier to inspect.

> **Alpha release**: interfaces, hooks, and configuration formats may still change between releases. Treat the current `v0.3.x` line as active build-out, not a frozen platform contract.

## Why LACP?

Most local agent workflows break down in the same places:
- setup drifts across machines
- risky commands are launched without enough context
- approvals and budgets live in chat instead of policy
- evidence is scattered across logs, shells, and temp files

LACP standardizes that loop:

```text
intent -> route -> sandbox -> verify -> report -> learn
   |         |         |         |         |        |
 task     policy    execution  gates    artifacts  lessons
```

The goal is simple: make Claude/Codex operations measurable, reliable, safe, and reproducible without forcing a hosted platform or replacing your existing shell-based tooling.

## Features

| Feature | Description |
|---------|-------------|
| Local-first control plane | Wraps your existing local agent commands instead of replacing them with a new runtime |
| Policy-based routing | Applies repo trust, internet, remote, budget, and approval gates before execution |
| Verification loops | Bakes in `doctor`, `verify`, `test`, canary, and release readiness checks |
| Auditable artifacts | Produces structured records for health, execution, evidence, and post-run review |
| Multi-agent orchestration | Supports dmux/tmux/worktree-backed session fanout with `up`, `orchestrate`, and `swarm` |
| Obsidian memory bundle | Ships ingestion, graph maintenance, brain health, and research sync commands |
| Open-source readiness | Includes release, docs, security, and bootstrap checks for maintainers shipping from local machines |
| Reversible adoption | Can wrap existing `claude` and `codex` commands, and undo that cleanly later |

## Installation

Prerequisites:
- `bash`
- `python3`
- `jq`
- `rg` (`ripgrep`)

Recommended:
- `shellcheck`

### Homebrew

```bash
brew tap 0xNyk/lacp
brew install lacp
```

### cURL bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/0xNyk/lacp/main/install.sh | bash
```

### Verified release

```bash
VERSION="0.3.0"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/lacp-${VERSION}.tar.gz"
curl -fsSLO "https://github.com/0xNyk/lacp/releases/download/v${VERSION}/SHA256SUMS"
grep "lacp-${VERSION}.tar.gz" SHA256SUMS | shasum -a 256 -c -
tar -xzf "lacp-${VERSION}.tar.gz"
cd "lacp-${VERSION}"
```

If you are running from a source checkout instead of an installed binary, use `./bin/lacp ...` in the examples below.

## Quick Start

### 1. Bootstrap the local control plane

```bash
lacp bootstrap-system --profile starter --with-verify
```

That flow installs missing dependencies, creates local config, scaffolds core directories, wires the Obsidian bundle, runs onboarding, and emits baseline verification artifacts.

### 2. Check health and current mode

```bash
lacp doctor --json | jq '.ok,.summary'
lacp status --json | jq
lacp mode show
```

### 3. Route a command through LACP

```bash
lacp run --task "hello world" --repo-trust trusted -- echo "LACP is working"
```

This runs the command through routing, risk, budget, and context gates before execution.

### 4. Adopt your existing agent commands

```bash
lacp adopt-local --json | jq
```

This installs reversible local wrappers so `claude` and `codex` run through LACP without changing your day-to-day commands. Undo with `lacp unadopt-local`.

### 5. Enable the memory stack

```bash
lacp brain-stack init --json | jq
lacp brain-doctor --json | jq
lacp brain-ingest --url "https://docs.anthropic.com/en/docs/claude-code" --title "Claude Code docs" --apply --json | jq
lacp brain-expand --apply --json | jq
```

## Daily Developer Workflow

Use this as the default day-to-day flow after install.

### 1. Start with diagnostics

```bash
lacp doctor --fix-hints
lacp system-health --fix-hints
lacp status --json | jq
```

### 2. Set the execution posture

```bash
lacp mode local-only
lacp mode remote-enabled --ttl-min 30
```

### 3. Run work through policy gates

```bash
lacp run --task "trusted smoke" --repo-trust trusted -- /bin/echo hello
lacp loop --task "implement feature X" --repo-trust trusted --json -- <command>
```

### 4. Fan out agent sessions when needed

```bash
lacp up --session dev --instances 3 --command "claude"
lacp up --backend tmux --session batch --instances 2 --command "codex --profile fast"
```

### 5. Produce evidence before merge or release

```bash
lacp test --isolated
lacp release-prepare --profile local-iterative --json | jq
lacp open-source-check --json | jq
```

## Who It Is For

Use LACP if you want:
- local agent workflows with explicit policy and audit trails
- repeatable onboarding across repos and machines
- one command surface for routing, verification, and release hygiene
- an Obsidian-backed memory workflow tied to real sessions and repo research

LACP is not for:
- teams looking for a hosted chat product
- users who do not want to maintain local scripts and config
- teams that need managed cloud orchestration with no local control surface

## What Install Does

`lacp bootstrap-system --profile starter --with-verify`:
- creates `.env` from `config/lacp.env.example` when missing
- auto-installs core dependencies on macOS unless disabled
- applies the `starter` policy pack
- scaffolds required root, data, and automation paths
- sets up the Obsidian vault bundle and shared skills links
- runs onboarding checks and fresh-machine confidence checks
- emits baseline verification artifacts for later comparison

## ❤️ Support the Project

If you find this project useful, consider supporting my open-source work.

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-orange?logo=buymeacoffee)](https://buymeacoffee.com/nyk_builderz)

**Solana donations**

`BYLu8XD8hGDUtdRBWpGWu5HKoiPrWqCxYFSh4oxXuvPg`

## Architecture

### Control-Plane Layer
- `bin/lacp-install`
- `bin/lacp-onboard`
- `bin/lacp-bootstrap`
- `bin/lacp-verify`
- `bin/lacp-doctor`
- `bin/lacp-mode`
- `bin/lacp-status-report`

### Policy + Routing Layer
- policy contract: `config/sandbox-policy.json`
- route decision engine: `bin/lacp-route`
- execution adapter: `bin/lacp-sandbox-run`

### Harness Contract Layer
- task planning schema: `config/harness/tasks.schema.json`
- sandbox profile catalog: `config/harness/sandbox-profiles.yaml`
- verification policy catalog: `config/harness/verification-policy.yaml`

### Remote Provider Layer
- setup helper: `bin/lacp-remote-setup`
- remote smoke helper: `bin/lacp-remote-smoke`
- Daytona runner: `scripts/runners/daytona-runner.sh`
- E2B runner: `scripts/runners/e2b-runner.sh`

## Execution Tiers

- `trusted_local`: known low-risk tasks
- `local_sandbox`: semi-trusted work requiring isolation
- `remote_sandbox`: high-risk/high-compute/long-running tasks

For remote routes, provider is policy-driven (`daytona` or `e2b`), with override support.

## Risk Tiers

- `safe`: executes without approval gate
- `review`: requires valid TTL approval token (`bin/lacp-mode remote-enabled --ttl-min <N>`)
- `critical`: always requires explicit per-run confirmation (`--confirm-critical true`)

## Budget Gates

- Per-tier cost ceilings are configured in `config/sandbox-policy.json` under `routing.cost_ceiling_usd_by_risk_tier`.
- Pass `--estimated-cost-usd <N>` to `bin/lacp-sandbox-run`.
- If estimate exceeds the tier ceiling, run is blocked unless `--confirm-budget true` is explicitly provided.

## Context Contract Gate

- Mutating commands and remote-target commands (`ssh`/`scp`/`rsync`/`sftp`) in `bin/lacp-sandbox-run` require a context contract by default (`LACP_REQUIRE_CONTEXT_CONTRACT=true`).
- Pass `--context-contract '<json>'` with one or more expectations:
  - `expected_host`
  - `expected_cwd_prefix`
  - `expected_git_branch`
  - `expected_git_worktree`
  - `expected_remote_host`
- Example:

```bash
bin/lacp-sandbox-run \
  --task "create local venv" \
  --repo-trust trusted \
  --context-contract '{"expected_host":"my-host","expected_cwd_prefix":"'"$HOME"'/repos"}' \
  -- python3 -m venv .venv
```

## Obsidian Brain Bundle

LACP includes a first-class Obsidian brain workflow out of the box:
- vault bootstrap at `$LACP_OBSIDIAN_VAULT` (default: `~/obsidian/vault`) during install (`--no-obsidian-setup` to skip)
- QMD indexing package (`@tobilu/qmd`) installed by default
- source ingestion entrypoint for local text/audio/video files and web links:
  - `bin/lacp brain-ingest ./notes.md --apply --json | jq`
  - `bin/lacp brain-ingest ./clip.mp4 --apply --json | jq`
  - `bin/lacp brain-ingest https://example.com/article --apply --json | jq`
- brain health checks: `bin/lacp brain-doctor --json | jq`
- brain expansion loop: `bin/lacp brain-expand --apply --json | jq`
- repository research mirroring into graph:
  - `bin/lacp repo-research-sync --apply --json | jq`
  - writes to `$LACP_KNOWLEDGE_ROOT/graph/repo-research/`
- upstream Anthropic skill sync:
  - `bin/lacp skill-sync-anthropic --skill skill-creator --apply --json | jq`

### Obsidian Configuration Management

LACP manages Obsidian configuration as code via `bin/lacp-obsidian`:

```bash
# Show vault health, plugin state, config status
bin/lacp-obsidian status

# Detect drift between live .obsidian/ and declared manifest
bin/lacp-obsidian audit --json | jq

# Apply declared config (auto-backs up first)
bin/lacp-obsidian apply

# Snapshot/restore config
bin/lacp-obsidian backup
bin/lacp-obsidian restore

# Auto-tune settings based on vault size and graph density
bin/lacp-obsidian optimize --dry-run
bin/lacp-obsidian optimize --apply
```

Configuration is declared in `config/obsidian/manifest.json` (plugins, core settings, graph view). The optimization engine (`optimize`) auto-selects a profile (small/medium/large) based on vault node count and tunes graph physics, dataview refresh intervals, linter rules, and plugin settings accordingly.

Config files:
- `config/obsidian/manifest.json` — declarative vault config (core plugins, community plugins, graph colorGroups)
- `config/obsidian/plugin-settings.json` — optimal per-plugin settings template
- `config/obsidian/optimization-profiles.json` — size-based optimization profiles (small/medium/large)

### Mycelium Network Memory

The knowledge graph uses biologically-inspired memory principles modeled on mycelium (fungal) networks:

| Mechanism | Function | Description |
|-----------|----------|-------------|
| Adaptive path reinforcement | `reinforce_access_paths()` | Frequently-traversed edges get stronger (like mycelium hyphae thickening) |
| Self-healing | `heal_broken_paths()` | Pruned nodes trigger reconnection of orphaned neighbors |
| Exploratory tendrils | Tendril protection in consolidation | Frontier nodes in active categories are shielded from pruning |
| Flow scoring | `compute_flow_score()` | Betweenness centrality proxy identifies critical transport hubs |
| Spreading activation | `spreading_activation()` | Collins & Loftus propagation over graph edges |
| Temporal decay | FSRS dual-strength model | Storage strength (S) + retrieval strength (R) with forgetting curve |

Use with brain-expand:

```bash
# Full expansion with mycelium-enhanced consolidation
lacp brain-expand --apply --activate --consolidate --json | jq
```

Recommended automation profiles:
- every 30 minutes (repo research sync): `com.lacp.repo-research-sync`
- every 6 hours (full brain-expand): `com.lacp.brain-expand-6h`

Example manual load (user launchd domain):

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lacp.repo-research-sync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lacp.brain-expand-6h.plist
```

Example status checks:

```bash
launchctl print gui/$(id -u)/com.lacp.repo-research-sync
launchctl print gui/$(id -u)/com.lacp.brain-expand-6h
```

## 5-Layer Memory Architecture

LACP treats memory as an explicit 5-layer stack:

1. Layer 1: Session Memory
   - project memory scaffolding under `~/.claude/projects/<project-slug>/memory/`
   - slug is the project path with `/` replaced by `-` (e.g., `/Users/alice/repos/lacp` → `-Users-alice-repos-lacp`)
   - seeded files: `MEMORY.md`, `debugging.md`, `patterns.md`, `architecture.md`, `preferences.md`
2. Layer 2: Knowledge Graph
   - Obsidian vault as persistent graph (`$LACP_OBSIDIAN_VAULT`)
   - MCP wiring for `memory`, `smart-connections`, `qmd`, and `obsidian`
3. Layer 3: Ingestion Pipeline
   - `bin/lacp brain-ingest` converts transcript/url/file inputs into structured notes
   - writes to `inbox/queue-generated/` and appends to `inbox/queue-generated/index.md`
4. Layer 4: Code Intelligence (optional)
   - GitNexus AST-level knowledge graph via MCP (`--with-gitnexus`)
   - indexes symbols, call chains, clusters, and execution flows per repo
   - provides impact analysis, process-grouped search, and pre-commit scope verification
   - install: `npm install -g gitnexus && npx gitnexus analyze`
5. Layer 5: Agent Identity & Provenance
   - persistent agent IDs per `(hostname, project)` pair via `bin/lacp agent-id`
   - SHA-256 hash-chained session receipts via `bin/lacp provenance`
   - each receipt links to the previous via `prev_hash`, creating a tamper-evident continuity proof
   - `verify` detects broken links / tampered receipts across the full chain

Bootstrap the stack:

```bash
bin/lacp brain-stack init --json | jq
bin/lacp brain-stack status --json | jq

# Include GitNexus code intelligence (AST knowledge graph via MCP)
bin/lacp brain-stack init --with-gitnexus --json | jq
# Then index your repo: npx gitnexus analyze

# Audit memory coverage across all projects
bin/lacp brain-stack audit --json | jq

# Scaffold memory for all projects with 5+ sessions that are missing it
bin/lacp brain-stack scaffold-all --min-sessions 5 --json | jq

# Dry-run first to see what would be created
bin/lacp brain-stack scaffold-all --min-sessions 5 --dry-run --json | jq
```

Ingest knowledge into the graph:

```bash
bin/lacp brain-ingest --url "https://youtube.com/watch?v=..." --title "Agent memory talk" --apply --json | jq
bin/lacp brain-ingest --transcript ./talk.txt --title "Context engineering" --apply --json | jq
```

## 5 Minute Smoke Test

```bash
cd /path/to/lacp
bin/lacp install --profile starter --with-verify
bin/lacp test --quick
bin/lacp test --isolated
bin/lacp doctor --json | jq '.ok,.summary'
bin/lacp status --json | jq
```

Expected:
- `lacp-test --quick` exits `0`
- `lacp-test --isolated` exits `0`
- doctor reports `"ok": true`
- status report includes mode + doctor + artifact fields + `intervention_rate` (current/baseline/delta)

## Brand Assets

- README banner image path: `docs/assets/readme-banner.png`
- README hero banner prompt: `docs/readme-banner-prompt.md`

## Remote Setup

By default, LACP runs in **zero-external mode**:
- `LACP_LOCAL_FIRST="true"`
- `LACP_NO_EXTERNAL_CI="true"`
- `LACP_ALLOW_EXTERNAL_REMOTE="false"`
- `LACP_REMOTE_APPROVAL_TTL_MIN="30"` (used when granting remote approval)
- remote routes can still be planned/tested via `--dry-run`
- live remote execution is blocked unless explicitly enabled **and** approval is still within TTL
- release gates enforce no active `.github/workflows/*.yml` files while `LACP_NO_EXTERNAL_CI=true`

### Daytona

```bash
cd /path/to/lacp
bin/lacp-remote-setup --provider daytona
daytona login
bin/lacp-remote-smoke --provider daytona --json
```

### E2B

```bash
cd /path/to/lacp
bin/lacp-remote-setup --provider e2b --e2b-sandbox-id "<running-sandbox-id>"
bin/lacp-remote-smoke --provider e2b --json
```

Notes:
- Default mode is non-interactive lifecycle (`create -> exec -> kill`) using E2B SDK.
- `E2B_SANDBOX_ID` enables existing-sandbox mode via e2b CLI.

## Hook Architecture

LACP ships a modular Python hook pipeline that enforces quality and safety at every stage of a Claude Code session. Hooks are installed to `~/.claude/` via `lacp claude-hooks apply-profile`.

### Hook Pipeline

| Hook | Event | Purpose |
|------|-------|---------|
| `session_start.py` | SessionStart | Git context injection, test command caching, branch/status awareness |
| `pretool_guard.py` | PreToolUse | Block dangerous operations before they execute |
| `write_validate.py` | PostToolUse (Write) | YAML frontmatter schema validation on written files |
| `stop_quality_gate.py` | Stop | Evaluate whether the agent is rationalizing incomplete work |
| `detect_session_changes.py` | (library) | Scan transcript for file modifications (used by stop gate) |
| `hook_telemetry.py` | (library) | JSONL telemetry with log rotation (used by stop gate) |

Legacy bash hooks (`session_orient.sh`, `stop_quality_gate.sh`) are still available but superseded by the Python pipeline.

### PreToolUse Guard

The pretool guard blocks dangerous patterns before execution:

- **Registry publishing** — `npm publish`, `cargo publish`, `yarn publish`
- **Destructive git** — `git reset --hard`, `git clean -f`
- **Unsafe permissions** — `chmod 777`
- **Privileged containers** — `docker run --privileged`
- **Fork bombs** — detected via pattern matching
- **Root-targeted transfers** — `scp`/`rsync` to `/root`
- **Pipe-to-interpreter** — `curl | python`, `wget | node`
- **Protected file writes** — `.env`, secrets, PEM keys, authorized_keys, `.gnupg`
- **Scoped approval caching** — per-window/pane TTL tokens so repeated safe operations don't block

### Stop Quality Gate

A 3-tier evaluation that prevents the agent from stopping prematurely:

1. **Fast heuristics** — pattern-match the conversation for incomplete work signals (failing tests, unresolved TODOs, unanswered questions)
2. **Test verification** — detect modified files, find cached test commands, verify they were actually run and passed
3. **Ollama LLM eval** — send the conversation summary to a local LLM (default: `llama3.1:8b`) to detect rationalization of incomplete work

Configurable via env vars: `LACP_QUALITY_GATE_MODEL`, `LACP_QUALITY_GATE_TIMEOUT`, `LACP_QUALITY_GATE_MAX_BLOCKS`.

### Hook Profiles

Profiles compose hooks into named configurations applied via `lacp claude-hooks apply-profile <profile>`:

| Profile | Hooks enabled |
|---------|--------------|
| `minimal-stop` | Stop quality gate only |
| `balanced` | SessionStart + Stop gate |
| `hardened-exec` | SessionStart + PreToolUse guard + Stop gate |
| `quality-gate-v2` | Full Python pipeline (SessionStart + PreToolUse + Stop gate) |
| `session-start` | SessionStart only |
| `pretool-guard` | PreToolUse guard only |
| `write-validate` | Write validation only |

`lacp claude-hooks optimize` auto-selects the best profile based on your current setup.

## Command Reference

- `bin/lacp`: top-level CLI dispatcher (`lacp <command> ...`)
- `bin/lacp-bootstrap-system`: one-command install + onboard + doctor flow
- `bin/lacp-onboard`: initialize `.env`, run bootstrap, optional full verify, and auto-optimize Claude hooks/profile by default
- `bin/lacp-install`: first-time installer — creates roots, starter stubs, auto-detects/installs macOS deps (`--no-auto-deps` to skip), bootstraps Obsidian vault/symlinks (`--no-obsidian-setup` to skip), then runs onboard
- `bin/lacp-test`: one-command local test suite (`--quick`, `--isolated` supported)
- `bin/lacp-posture`: one-shot local-first/no-external-ci contract report (`--strict`, `--json`)
- `bin/lacp-claude-hooks`: audit/repair/optimize local Claude hook/plugin drift (`audit`, `repair`, `apply-profile`, `optimize`) including profiles: `hardened-exec`, `quality-gate-v2`, `session-start`, `pretool-guard`, `write-validate`
- `bin/lacp-console`: interactive slash-command shell (`/doctor`, `/up`, `/orchestrate`, `/worktree`, `/swarm`, `/hooks`, `/loop`, `/release`, `/run`)
- `bin/lacp-time`: monthly project/client session time tracking (`start`, `stop`, `active`, `report`, `month`) with directory split rollups (`clients/projects/experiments`), tag rollups, and activity buckets (`coding/testing/docs/ops`)
- `bin/lacp-loop`: deterministic `intent -> execute -> observe -> adapt` control loop wrapper for one task
- `bin/lacp-up`: dmux-style one-command multi-instance launch (`--layout`, `--brand`, `--instances`) with optional auto-attach and enforced context/fingerprint forwarding
- `bin/lacp-context`: minimal context lifecycle (`init-template`, `audit`, `minimize`, `regression`)
- `bin/lacp-lessons`: add/lint compact self-improvement rules without duplication
- `bin/lacp-optimize-loop`: bounded weekly optimization loop over verify/canary/context/lessons
- `bin/lacp-trace-triage`: cluster recent failed run traces into root-cause groups with deterministic remediation hints
- `bin/lacp-context-profile`: list/render reusable context-contract profiles for safe execution contexts
- `bin/lacp-loop-profile`: list/render reusable loop defaults (routing + verify/canary/rollback posture)
- `bin/lacp-credential-profile`: list/render reusable credential posture and input-contract templates
- `bin/lacp-session-fingerprint`: derive deterministic session fingerprints for anti-drift execution gates
- `bin/lacp-mcp-profile`: list/status/apply MCP operating profiles (`cli-first`, `mcp-selective`, `mcp-heavy`)
- `bin/lacp-report`: summarize recent run outcomes and latest artifact health, including `intervention_rate_per_100` and baseline delta (`--baseline-hours`, `--baseline-offset-hours`)
- `bin/lacp-canary`: 7-day promotion gate over retrieval benchmarks (hit-rate/MRR/triage/gate consistency)
  - baseline support: `--set-clean-baseline`, `--since-clean-baseline`
- `bin/lacp-canary-optimize`: bounded optimization loop (`verify -> canary`) with optional best `LACP_BENCH_TOP_K` persistence
- `bin/lacp-auto-rollback`: fail-safe rollback action runner (`local-only` mode + wrapper unadopt) on unhealthy canary
- `bin/lacp-schedule-health`: install/status/run-now/uninstall scheduled local health checks via launchd
- `bin/lacp-policy-pack`: list/apply policy baseline packs (`starter`, `strict`, `enterprise`)
- `bin/lacp-release-prepare`: one-command pre-live discipline (`release-gate` + `canary` + `status` + `report`)
  - supports `--profile local-iterative` (equivalent defaults: `--quick --canary-days 3 --skip-cache-gate --skip-skill-audit-gate`)
- `bin/lacp-release-publish`: local-only release artifact builder/publisher (`tar.gz` + `SHA256SUMS` + optional `gh release`)
- `bin/lacp-release-verify`: one-command release verification (`release-publish --skip-gh` + checksum + archive + brew dry-run)
- `bin/lacp-open-source-check`: local open-source go/no-go gate (docs freshness, security/deps hygiene, artifact checksums, optional bootstrap sanity)
- `bin/lacp security-hygiene`: quick secret/path/workflow/.env/email hygiene scan with compact JSON output (`--repo-root`, `--json`)
- `bin/lacp-vendor-watch`: monitor local Claude/Codex versions and upstream docs/changelog drift
- `bin/lacp-automations-tui`: unified local automation dashboard (`schedule/orchestrate/worktree/swarm/wrappers/vendor-watch`)
- `bin/lacp-cache-audit`: measure prompt cache efficiency from local Claude/Codex histories
- `bin/lacp-cache-guard`: enforce cache health thresholds (hit-rate + usage events)
- `bin/lacp-skill-audit`: detect risky skill patterns before install/use
- `bin/lacp-skill-factory`: operate auto-skill-factory (`summary/capture/record/lifecycle/recluster/revalidate/migrate-bundles`) with categorized autogen skill bundles
- `bin/lacp-release-gate`: run strict pre-live go/no-go checks (tests + doctor + cache + skills)
- `bin/lacp-pr-preflight`: evaluate PR policy gates (risk tier + docs drift + check runs + stale review state)
- `bin/lacp-harness-validate`: validate `tasks.json` against schema + profile/policy catalogs
- `bin/lacp-harness-run`: execute validated tasks with dependency ordering + loop retries
- `bin/lacp-harness-replay`: replay failed task runner + captured verification commands from harness receipts
  - emits per-task `failure_class` + `remediation_action`
  - writes `<run_dir>/remediation-plan.json` (override with `--remediation-plan`)
- `bin/lacp-e2e`: run local Playwright-style e2e command + generate evidence manifest + auth pattern checks
- `bin/lacp-api-e2e`: run API/backend e2e command wrappers with manifest evidence + API coverage checks
- `bin/lacp-contract-e2e`: run smart-contract e2e command wrappers with manifest evidence + invariant/revert checks
- `bin/lacp-browser-evidence-validate`: validate browser evidence manifests with freshness/assertion gates
- `bin/lacp-orchestrate`: optional dmux/tmux/claude_worktree orchestration adapter (still routed through LACP gates)
  - default backend is `dmux` when available; falls back to `tmux`
- `bin/lacp-worktree`: manage git worktree lifecycle (`list/create/remove/prune/gc/doctor`)
- `bin/lacp-swarm`: dmux-first swarm workflow (`init/plan/launch/up/tui/status`) with policy-gated batch execution
  - supports advisory `reservations` per job and reports collisions in plan/artifacts (no hard locks)
  - `swarm status --json` includes `collaboration_summary` with top conflicts for fast triage
- `bin/lacp-migrate`: migrate existing local roots into `.env` (dry-run by default)
- `bin/lacp-incident-drill`: run scenario-based incident readiness drills
- `bin/lacp-workflow-run`: deterministic planner→developer→verifier→tester→reviewer workflow skeleton with explicit `plan->act` handoff token enforcement
- `bin/lacp-adopt-local`: install reversible local `claude`/`codex` wrappers that route through LACP
- `bin/lacp-unadopt-local`: remove LACP-managed local wrappers and restore previous shims
- `bin/lacp-bootstrap`: hard preflight (paths, scripts, policy file)
- `bin/lacp-verify`: memory pipeline + retrieval gates + snapshot + trend refresh
- `bin/lacp-doctor`: structured diagnostics (`--json` supported)
  - runtime pressure diagnostics: `bin/lacp doctor --check-limits --json | jq`
  - actionable remediation commands: `bin/lacp doctor --check-limits --fix-hints --json | jq '.remediation_hints'`
  - macOS system health (thermal, memory, Spotlight, Docker, Rust, UI): `bin/lacp doctor --system --json | jq`
- `bin/lacp-system-health`: macOS/Apple Silicon workstation readiness checks (`--json`, `--fix-hints`, `--fix`)
- `bin/lacp-mcp-health`: probe all configured MCP servers for health status (`--json`)
  - thermal state, CPU load, memory pressure, swap usage
  - Spotlight indexing exclusions for dev directories
  - container runtime detection (OrbStack vs Docker Desktop)
  - Rust build config audit (sccache, incremental builds, cargo config)
  - UI compositor overhead (reduce motion/transparency, Dock/Finder animations)
  - background process audit (known CPU-wasting agents)
- `bin/lacp-knowledge-doctor`: markdown knowledge graph quality gates (`--json` supported)
- `bin/lacp-brain-ingest`: ingest local text/audio/video sources, web links, and transcripts into the Obsidian inbox (`inbox/queue-generated/`)
  - delegates media/transcript extraction to the existing automation ingest pipeline when available
  - treats plain web links as structured inbox capture notes for later triage/promotion
- `bin/lacp-brain-doctor`: Obsidian brain ecosystem checks (vault symlinks, QMD, MCP, daily/session freshness)
- `bin/lacp-brain-stack`: initialize/status/audit/scaffold official 5-layer memory stack (session memory scaffolding + MCP wiring + system-wide coverage)
- `bin/lacp-agent-id`: persistent agent identity registry (`show/list/register/revoke/touch`) — stable `agent-<hex8>` IDs per `(hostname, project)` pair
- `bin/lacp-provenance`: cryptographic session provenance chain (`start/end/verify/log/export`) — SHA-256 hash-chained session receipts with tamper detection
- `bin/lacp-obsidian`: manage Obsidian vault configuration as code (`status`, `audit`, `apply`, `backup`, `restore`, `plugins`, `graph-config`, `optimize`)
- `bin/lacp-repo-research-sync`: mirror repo `docs/research/**/*.md` into Obsidian graph notes (`knowledge/graph/repo-research/`)
- `bin/lacp-skill-score`: recompute confidence scores, prune low-confidence workflows, and report on auto-skill-factory ledger health (`recalc`, `prune`, `report`)
- `bin/lacp-skill-sync-anthropic`: sync official Anthropic skills into local Claude/Codex skill paths
- `bin/lacp-repos-index`: discover and index git repos with GitNexus for cross-repo code intelligence (`discover`, `index`, `index-repo`, `status`)
- `bin/lacp-brain-expand`: automated brain expansion loop (config guard + session sync + research materialization + thresholded research graph promotion + repo/codebase sync + repo research mirror + weekly consolidation + mycelium-enhanced memory consolidation + agent-daily sync + inbox hygiene + doctor checks)
- `bin/lacp-mode`: switch/read operating mode (`local-only` vs `remote-enabled`)
- `bin/lacp-mode revoke-approval`: revoke remote approval token immediately
- `bin/lacp-status-report`: generate compact system snapshot (`docs/system-status.md`) including intervention pressure KPI (`intervention_rate_per_100`) with baseline delta
- `bin/lacp-route`: deterministic tier/provider routing with reasons
- `bin/lacp-sandbox-run`: route + risk-tier/budget gates + dispatch + execution artifact logging
- `bin/lacp-remote-setup`: provider onboarding and config wiring
- `bin/lacp-remote-smoke`: provider-aware smoke test with artifact output

## Harness Engineering Contracts

Use these files to formalize your orchestrator workflow from specs to loops:

- `config/harness/tasks.schema.json`: contract for generated `tasks.json` plans.
  - supports per-task cascading IO contracts: `expected_inputs` / `expected_outputs`
- `config/harness/sandbox-profiles.yaml`: reproducible sandbox/runtime presets.
- `config/harness/verification-policy.yaml`: per-task verification requirements and thresholds.
  - `failure_action` drives retry semantics in `harness-run` (`block`, `require_human_review`, `retry_same_model`, `retry_stronger_model`)
- `config/harness/browser-evidence.schema.json`: machine-verifiable browser flow evidence contract.
- `config/risk-policy-contract.json`: single risk/merge/review/evidence policy contract.
- `config/risk-policy-contract.schema.json`: contract schema for drift-resistant validation.
- default policy requires browser/e2e evidence for `medium` and `high` risk tiers.
- policy supports additional scoped evidence gates:
  - `apiEvidence` for API/backend path scopes
  - `contractEvidence` for smart-contract path scopes

This maps directly to:
- spec -> orchestrator-generated tasks
- task -> sandbox profile + verification policy
- loop attempts -> checkable gate outcomes

Validate a generated task plan:

```bash
cd /path/to/lacp
bin/lacp harness-validate --tasks ./tasks.json --json | jq
bin/lacp harness-run --tasks ./tasks.json --workdir . --json | jq
bin/lacp harness-replay --run-id <run-id> --task-id <task-id> --workdir . --json | jq

# PR preflight policy gate from local evidence files
bin/lacp pr-preflight \
  --changed-files ./changed-files.txt \
  --head-sha "$(git rev-parse HEAD)" \
  --checks-json ./checks.json \
  --review-json ./review-state.json \
  --browser-evidence ./browser-evidence.json \
  --api-evidence ./api-evidence.json \
  --contract-evidence ./contract-evidence.json \
  --json | jq

# local Playwright/e2e evidence pipeline (no external CI cost required)
bin/lacp e2e run \
  --command "npx playwright test" \
  --flows-file ./e2e-flows.json \
  --manifest ./browser-evidence.json --json | jq
bin/lacp e2e auth-check --manifest ./browser-evidence.json --json | jq

# one-liner smoke profile (auto-inits from template if missing)
bin/lacp e2e smoke \
  --workdir . \
  --init-template \
  --command "npx playwright test --grep @smoke" \
  --json | jq

# API/backend smoke harness
bin/lacp api-e2e smoke \
  --workdir . \
  --init-template \
  --command "npx schemathesis run --checks all" \
  --json | jq

# smart-contract smoke harness
bin/lacp contract-e2e smoke \
  --workdir . \
  --init-template \
  --command "forge test -vv" \
  --json | jq

# optional preflight auto-run path
bin/lacp pr-preflight \
  --changed-files ./changed-files.txt \
  --checks-json ./checks.json \
  --review-json ./review-state.json \
  --auto-e2e-run \
  --auto-e2e-command "npx playwright test" \
  --auto-e2e-flows-file ./e2e-flows.json \
  --auto-e2e-auth-check \
  --json | jq
```

## Security Model

- No secrets in repo configuration files
- Environment-driven configuration in `.env`
- Zero-external-cost workflow policy (local CLI gates; no required GitHub Actions or paid CI providers)
- Active GitHub Actions are disabled by default in this repo (`.github/workflows-disabled/` templates)
- Policy-driven remote routing
- External remote execution disabled by default (`LACP_ALLOW_EXTERNAL_REMOTE=false`)
- Risk-tier gating (`safe/review/critical`) with TTL and per-run confirmation controls
- Explicit runner guardrails for remote execution
- Structured input-contract gate for risky runs (`--input-contract ...`)
- Artifact logs for auditable runs
- Cache observability from provider-native history schemas (Codex token_count + Claude usage events)

See:
- `docs/framework-scope.md`
- `docs/runbook.md`
- `docs/release-checklist.md`
- `docs/local-dev-loop.md`
- `docs/implementation-path-2026.md`
- `docs/troubleshooting.md`
- `docs/incident-response.md`
- `CONTRIBUTING.md`
- `SECURITY.md`

## Artifacts

- benchmark reports: `$LACP_KNOWLEDGE_ROOT/data/benchmarks/*.json`
- snapshots: `$LACP_AUTOMATION_ROOT/data/snapshots/*.json`
- sandbox runs: `$LACP_KNOWLEDGE_ROOT/data/sandbox-runs/*.json`
- remote smoke runs: `$LACP_KNOWLEDGE_ROOT/data/remote-smoke/*.json`

## Testing

```bash
cd /path/to/lacp
./scripts/ci/test-route-policy.sh
./scripts/ci/test-mode-and-gates.sh
./scripts/ci/test-knowledge-doctor.sh
./scripts/ci/test-ops-commands.sh
./scripts/ci/test-install.sh
./scripts/ci/test-system-health.sh
./scripts/ci/test-obsidian-cli.sh
./scripts/ci/test-brain-memory.sh
./scripts/ci/smoke.sh
```

Or use:

```bash
bin/lacp-test
bin/lacp-test --quick
bin/lacp-test --isolated
bin/lacp posture --strict --json | jq
bin/lacp claude-hooks audit --json | jq
bin/lacp claude-hooks optimize --profile minimal-stop --json | jq
bin/lacp claude-hooks optimize --profile hardened-exec --json | jq
bin/lacp console --eval "/doctor --json" | jq '.ok'
bin/lacp console --eval "/loop safe-verify trusted-local-dev -- /bin/echo hello"
# console auto-tracks session time by default (docs/testing/coding all included)
# disable per session: bin/lacp console --no-auto-time
bin/lacp time start --project "$(pwd)" --client acme --tags docs,testing --json | jq
bin/lacp time stop --json | jq
bin/lacp time month --json | jq
bin/lacp time month --json | jq '.directory_split'
bin/lacp time month --json | jq '.activity_buckets,.by_tag'

# pre-live gate
bin/lacp release-gate --quick
bin/lacp canary --json | jq
bin/lacp canary-optimize --iterations 3 --hours 24 --json | jq
bin/lacp canary --set-clean-baseline
bin/lacp canary --since-clean-baseline --json | jq
bin/lacp vendor-watch --json | jq
bin/lacp release-prepare --profile local-iterative --since-clean-baseline --json | jq
bin/lacp release-prepare --quick --skip-cache-gate --skip-skill-audit-gate --since-clean-baseline --json | jq
# optional override when intentionally using GitHub Actions:
bin/lacp release-prepare --allow-external-ci --json | jq
bin/lacp release-publish --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --skip-gh --json | jq
bin/lacp release-verify --tag vX.Y.Z --quick --skip-cache-gate --skip-skill-audit-gate --json | jq

# one-task control loop (includes failure classification + remediation hints in .analysis)
bin/lacp loop --task "trusted smoke" --repo-trust trusted --dry-run --json -- /bin/echo hello

# render reusable context contracts
bin/lacp context-profile list --json | jq
bin/lacp context-profile render --profile local-dev --json | jq
bin/lacp context-profile render --profile ssh-prod --var REMOTE_HOST=prod-server --json | jq

# render reusable loop + credential profiles
bin/lacp loop-profile list --json | jq
bin/lacp loop-profile render --profile safe-verify --json | jq
bin/lacp credential-profile list --json | jq
bin/lacp credential-profile input-contract --profile trusted-local-dev --json | jq

# run loop with profile-derived context contract (no raw JSON needed)
bin/lacp loop --task "safe migration prep" --repo-trust trusted --context-profile high-risk-migration --json -- /bin/mkdir -p /tmp/lacp-migration

# run loop with reusable loop + credential posture (CLI overrides still win)
bin/lacp loop --task "guarded prod check" --loop-profile safe-verify --credential-profile prod-sensitive-guarded --json -- /bin/echo ok

# minimal context + lessons discipline
bin/lacp context init-template --repo-root . --json | jq
bin/lacp context audit --repo-root . --json | jq
bin/lacp context minimize --repo-root . --json | jq
bin/lacp lessons lint --json | jq

# compare no-context vs minimal-context benchmark outcomes
bin/lacp context regression --none ./none.json --minimal ./minimal.json --json | jq

# bounded weekly optimization loop
bin/lacp optimize-loop --repo-root . --iterations 2 --hours 24 --days 7 --json | jq

# derive and apply session fingerprint
FP="$(bin/lacp session-fingerprint)"
bin/lacp run --task "guarded edit" --repo-trust trusted --context-contract "$(bin/lacp context-profile render --profile local-dev)" --session-fingerprint "${FP}" -- /bin/mkdir -p /tmp/lacp-guarded

# aggregate failed run traces into root-cause clusters
bin/lacp trace-triage --hours 24 --json | jq

# fail-safe rollback if canary is unhealthy
bin/lacp auto-rollback --json | jq

# policy packs
bin/lacp policy-pack list --json | jq
bin/lacp policy-pack apply --pack strict --json | jq

# scheduled local health checks (launchd)
bin/lacp schedule-health install --interval-min 60 --json | jq
bin/lacp schedule-health status --json | jq
bin/lacp schedule-health run-now --json | jq

# fresh macOS dependency bootstrap (enabled by default)
bin/lacp install --profile starter
bin/lacp install --profile starter --no-auto-deps
bin/lacp install --profile starter --no-auto-hook-optimize
bin/lacp doctor --fix-deps --auto-deps-dry-run --json | jq

# optional orchestration (dry-run)
bin/lacp orchestrate run \
  --task "parallel coding swarm kickoff" \
  --backend dmux \
  --session "lacp-swarm" \
  --command "echo hello" \
  --repo-trust trusted \
  --dry-run

# claude native worktree isolation through LACP
bin/lacp orchestrate run \
  --task "parallel migration stream" \
  --backend claude_worktree \
  --session "migration-batch-a" \
  --command "audit migration changes and propose safe fixes" \
  --repo-trust trusted \
  --claude-tmux true \
  --dry-run

# explicit worktree lifecycle helpers
bin/lacp worktree doctor --repo-root . --json | jq
bin/lacp worktree create --repo-root . --name "batch-a" --base HEAD --json | jq
bin/lacp worktree list --repo-root . --json | jq
bin/lacp worktree gc --repo-root . --max-age-hours 72 --managed-only true --branch-prefix "wt/" --dry-run --json | jq

# batch orchestration manifest
bin/lacp orchestrate run --batch ./orchestrate-batch.json --json | jq

# dmux-first swarm workflow
bin/lacp swarm init --manifest ./swarm.json --json | jq
bin/lacp swarm plan --manifest ./swarm.json --json | jq
bin/lacp swarm launch --manifest ./swarm.json --json | jq
bin/lacp swarm up --manifest ./swarm.json --json | jq
bin/lacp swarm tui --manifest ./swarm.json --dry-run --json | jq
bin/lacp swarm status --latest --json | jq

# adopt/revert default local command routing
bin/lacp adopt-local --json | jq
bin/lacp unadopt-local --json | jq

# preferred
bin/lacp test
bin/lacp test --quick
bin/lacp test --isolated
```

## Troubleshooting

- `bootstrap failed missing script`: run `bin/lacp-install --profile starter --force-scaffold`
- `fork: Resource temporarily unavailable`: run `bin/lacp doctor --check-limits --json | jq`; reduce concurrent sessions/jobs or raise `ulimit -u` for your user
- get concrete next commands: `bin/lacp doctor --check-limits --fix-hints`
- remote `exit_code=8`: run `bin/lacp-mode remote-enabled --ttl-min 30`
- budget `exit_code=10`: lower `--estimated-cost-usd` or pass `--confirm-budget true`
- critical `exit_code=9`: pass `--confirm-critical true`
- doctor path errors: check `.env` roots and rerun `bin/lacp-doctor --json`

## Optimization Backlog

Prioritized optimization findings are tracked in:
- `docs/optimization-audit-2026-02-20.md`
