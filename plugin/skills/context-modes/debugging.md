# Debugging Mode

You are operating in systematic debugging mode. Follow the four phases in order.

## Iron Law

NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

If you haven't completed Phase 1, you cannot propose fixes.

## Phase 1: Root Cause Investigation

BEFORE attempting ANY fix:

1. **Read error messages carefully** — don't skip past errors. Read stack traces completely. Note line numbers, file paths, error codes.

2. **Reproduce consistently** — can you trigger it reliably? What are the exact steps? If not reproducible, gather more data — do not guess.

3. **Check recent changes** — git diff, recent commits, new dependencies, config changes, environmental differences.

4. **Gather evidence at component boundaries** — for multi-component systems, add diagnostic instrumentation at each layer boundary. Run once to identify WHERE it breaks, THEN investigate that component.

5. **Trace data flow backward** — where does the bad value originate? What called this with the bad value? Keep tracing up until you find the source. Fix at source, not at symptom.

## Phase 2: Pattern Analysis

1. Find similar WORKING code in the same codebase
2. Compare working vs broken — list every difference, however small
3. Read reference implementations COMPLETELY, not skimmed
4. Understand all dependencies and assumptions

## Phase 3: Hypothesis and Testing

1. Form a SINGLE hypothesis: "I think X is the root cause because Y"
2. Make the SMALLEST possible change to test it — one variable at a time
3. Did it work? Yes → Phase 4. No → form NEW hypothesis. Do NOT add more fixes on top.

## Phase 4: Implementation

1. Create a failing test case reproducing the bug
2. Implement a SINGLE fix addressing the root cause
3. Verify: test passes, no other tests broken, issue resolved

## Escalation Rule

If 3+ fixes have failed:
- STOP. Do not attempt fix #4.
- Question the architecture: is this pattern fundamentally sound?
- Each fix revealing new problems in different places = architectural issue
- Ask the user before attempting more fixes

## Red Flags — STOP and Return to Phase 1

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "I don't fully understand but this might work"
- Proposing solutions before tracing data flow
- Each fix reveals new problem in different place
- "One more fix attempt" when already tried 2+

## Integration with LACP

- Use `lacp-doctor` for system-level diagnostics first
- The stop quality gate will evaluate whether you actually investigated vs guessed
- Sprint contracts should capture the hypothesis and evidence, not just the fix
