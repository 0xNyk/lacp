# Runtime isolation

Git worktrees isolate files. They do not isolate ports, Docker, `node_modules`,
or "who owns localhost". Claude Code 2.1.222+ also isolates worktree sessions so
subagents cannot mutate the main checkout. Use that host feature. Do not register
a LACP `WorktreeCreate` hook unless it actually creates the worktree — that event
replaces Claude's default git behavior.

## Layers

| Layer | Owner | What it isolates |
| --- | --- | --- |
| Host worktree isolation | Claude Code / Codex | File edits and bash against the main checkout |
| `lacp worktree` | LACP | Named linked worktrees for operator-launched runs |
| `lacp route` sandbox vs approval | LACP | Execution venue and whether remote is even allowed |
| Ports / compose / caches | You | Assign per-worktree ports; do not share one `localhost` service |

## Subagent evidence

The `hardened-exec` profile installs `isolation_guard.py` on `SubagentStart` and
`SubagentStop`. It appends JSONL to `$LACP_KNOWLEDGE_ROOT/data/isolation-events.jsonl`.
It does not block agents.

## Parallel agents

`lacp swarm` and `lacp up` still need unique session names and worktree paths.
If two agents bind the same port, that is a runtime collision, not a git bug.
