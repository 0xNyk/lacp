# Memory / Context

Purpose
- Session-independent operational context: environment facts, assumptions, runbook shortcuts, and recurring constraints.

What to store
- Environment invariants (paths, roots, required tools)
- Known-good command sequences
- Baseline/threshold expectations
- Common failure signatures and fixes
- Open questions needing follow-up

Template
- Context item:
- Why it matters:
- Source of truth:
- Verification command:
- Last validated:
- Notes:

Conventions
- Keep entries atomic and testable.
- Include a verification command whenever possible.
- Prefer facts over speculation.
