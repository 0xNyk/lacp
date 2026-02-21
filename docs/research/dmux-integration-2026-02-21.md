# dmux Integration Review (2026-02-21)

## Context

Question: should LACP integrate dmux natively, and if yes, how much?

## What dmux provides

From `standardagents/dmux` README:
- parallel agent panes with git worktree isolation
- supports Claude Code, Codex, and OpenCode
- A/B launches for side-by-side runs
- branch/worktree lifecycle operations and merge shortcuts
- lifecycle hooks around create/merge events
- multi-project session support

Repository: https://github.com/standardagents/dmux

## What LACP already has

- policy-gated orchestration wrapper (`lacp-orchestrate`)
- backends: `tmux`, `dmux`, `claude_worktree`
- risk gates before execution (`lacp-sandbox-run`)
- budget / approval / critical confirmation controls
- run artifacts, doctor checks, CI checks

## Decision

Integrate dmux as an **adapter backend**, not as vendored runtime code.

Why:
1. LACP scope is control-plane policy and validation, not replacing terminal UX.
2. dmux already ships active UX/workflow features; duplicating would create maintenance drag.
3. Adapter mode keeps blast radius low and lets users upgrade dmux independently.
4. LACP can enforce policy gates and audit artifacts around dmux launches.

## Native pieces worth adding in LACP

1. Stable orchestration contract
- keep backend-agnostic launch contract (`task`, `risk`, `budget`, `approval`).

2. Hooks boundary
- support pre/post-run policy hooks in LACP without importing dmux internals.

3. Artifact bridge
- optional parsing of dmux session metadata into LACP run artifacts.

4. Fail-safe defaults
- remote-disabled by default and explicit approvals for review/critical tasks.

## Native pieces NOT recommended

- vendoring dmux source into LACP
- reimplementing dmux TUI and keybindings inside LACP
- coupling LACP release cadence to dmux internals

## Practical next step

Keep current `dmux` backend in LACP orchestrate and add optional metadata ingestion mode if dmux emits stable machine-readable session artifacts.

