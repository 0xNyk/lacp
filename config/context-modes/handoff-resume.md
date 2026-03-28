# Handoff Resume Mode

A previous session left a handoff artifact. Follow this protocol:

## Protocol

1. **Verify state**: Check that the git branch and working tree match the handoff's recorded state.
2. **Review open issues**: Read through any flagged issues from the previous session.
3. **Continue from next steps**: Pick up where the previous session left off using the documented next steps.
4. **Run tests first**: Before making new changes, verify the current test status matches the handoff's recorded status.

## Guardrails

- Do not re-do work that was already completed in the previous session.
- If the git state has diverged from the handoff, say so and ask for guidance.
- If next steps are unclear, ask for clarification rather than guessing.
