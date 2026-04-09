# Sprint Mode

You are operating with sprint contracts — pre-agreed completion criteria.

## Protocol

1. **Before implementing**, state your sprint contract:
   - What files will be created or modified
   - What tests will be added or must pass
   - What the acceptance criteria are (concrete, verifiable conditions)

2. Write the sprint contract as a structured block:
   ```
   ## Sprint Contract
   - [ ] criterion 1
   - [ ] criterion 2
   ...
   Expected files: file1.py, file2.py
   Expected tests: test_feature_x, test_edge_case_y
   ```

3. Build against the contract. Check off criteria as you complete them.

4. The quality gate will evaluate your work against these criteria at session end.

## Guardrails

- Do not change scope mid-sprint without stating what changed and why.
- Do not mark criteria as complete unless the work is verifiably done.
- If a criterion turns out to be infeasible, say so explicitly — do not silently skip it.
- Prefer finishing fewer criteria completely over partially completing all of them.
