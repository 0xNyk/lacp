---
name: context-modes
description: "Structured work modes for agent sessions. Set LACP_CONTEXT_MODE to activate: tdd (red-green-refactor), debugging (4-phase root cause), sprint (pre-agreed criteria), verification (evidence-before-claims), brainstorm (design first), think (pause-and-reflect), orchestrate (task decomposition). Each mode injects behavioral rules at session start."
---

# Context Modes

Set `LACP_CONTEXT_MODE` environment variable to activate a mode:

| Mode | Purpose |
|------|---------|
| `tdd` | Strict RED-GREEN-REFACTOR — no code without a failing test |
| `debugging` | 4-phase systematic root cause investigation |
| `sprint` | Pre-agreed completion criteria evaluated at stop |
| `verification` | Evidence-before-claims discipline |
| `brainstorm` | Design exploration — no code until design approved |
| `think` | Pause-and-reflect before every action chain |
| `orchestrate` | Decompose into subtasks before executing |
| `implementation` | Focused implementation partner |
| `review` | Code review mode |
| `thinking-partner` | Challenge assumptions, surface blind spots |
| `handoff-resume` | Continue from previous session handoff |

Each mode is a markdown file that gets injected as system context at session start.
