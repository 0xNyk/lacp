# TDD Mode

You are operating in strict Test-Driven Development mode.

## Iron Law

NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

If you wrote code before the test, delete it. Start over. No exceptions.

## Red-Green-Refactor Cycle

### RED — Write Failing Test
1. Write ONE minimal test that describes the desired behavior
2. Use clear names that describe behavior, not implementation
3. Test real code, not mocks (mocks only when unavoidable)
4. Run the test — confirm it FAILS for the right reason (feature missing, not typo/error)

### GREEN — Minimal Code
1. Write the SIMPLEST code that makes the test pass
2. Do not add features, refactor, or "improve" beyond the test
3. Run the test — confirm it PASSES
4. Confirm no other tests broke

### REFACTOR — Clean Up
1. Only after green: remove duplication, improve names, extract helpers
2. Keep tests green throughout
3. Do not add new behavior during refactor

### REPEAT
Next failing test for next behavior.

## Verification Gate

Before claiming work is complete:
- [ ] Every new function/method has a test
- [ ] Watched each test fail before implementing
- [ ] Each test failed for expected reason
- [ ] Wrote minimal code to pass each test
- [ ] All tests pass (run test command, read output)
- [ ] Output pristine (no errors, warnings)

## Red Flags — STOP and Start Over

Any of these mean you violated TDD. Delete code, restart with test:
- Code written before test
- Test passes immediately (testing existing behavior)
- Can't explain why test failed
- "I'll add tests later"
- "Just this once"
- "Too simple to test"
- "I already manually tested it"

## Integration with LACP

- The eval checkpoint hook will verify tests at intervals during your work
- The stop quality gate will verify test claims at session end
- Sprint contracts should list expected tests as acceptance criteria
