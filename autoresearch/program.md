# LACP Brain Autoresearch

Autonomous optimization of the LACP knowledge brain using the autoresearch ratchet pattern.

## Setup

To set up a new experiment run:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar30`). The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current main.
3. **Read the in-scope files** for full context:
   - `autoresearch/README.md` — this file, the experiment protocol
   - `autoresearch/evaluate.py` — fixed evaluation harness (DO NOT MODIFY)
   - `autoresearch/optimize.py` — the file you modify (repair actions, parameters, new fixes)
4. **Run baseline evaluation**: `python3 autoresearch/evaluate.py` to establish the starting score.
5. **Initialize results.tsv**: Create `autoresearch/results.tsv` with just the header row.
6. **Confirm and go**.

## What you optimize

The **composite brain health score** (0-100, higher is better), computed from three weighted components:

| Component | Weight | Source | What it measures |
|-----------|--------|--------|-----------------|
| Brain Health | 40% | `lacp-brain-doctor --json` | Vault symlinks, QMD, MCP, daily notes, voice pipeline, inbox, atlas MOCs, config drift |
| System Health | 35% | `lacp-doctor --json` | LACP policy, hooks, paths, sandbox config, gate integrity |
| Knowledge Health | 25% | `lacp-knowledge-doctor --json` | Graph integrity, orphans, contradictions, link health |

## What you CAN do

- Modify `autoresearch/optimize.py` — this is the primary file you edit. Add new repair functions, tune parameters, fix detected issues.
- Modify LACP config files in `config/` — sandbox-policy.json, obsidian/manifest.json, system-health-policy.json, etc.
- Modify LACP scripts in `bin/` — fix bugs in doctor scripts, improve detection logic.
- Modify hook scripts in `hooks/` — fix broken hooks, improve validation.
- Fix vault structure issues — broken symlinks, missing directories, config drift.
- Run LACP commands to diagnose issues: `bin/lacp-brain-doctor --json`, `bin/lacp-doctor --json`, etc.

## What you CANNOT do

- Modify `autoresearch/evaluate.py` — this is the fixed scoring harness.
- Delete user content from the vault (notes, research, sessions).
- Modify `.env` secrets, API keys, or credentials.
- Install new system packages or dependencies.
- Modify git history on main/master.
- Fake metrics (e.g., making doctors always return pass).

## The experiment loop

LOOP FOREVER:

1. **Diagnose**: Run `python3 autoresearch/evaluate.py` and read `autoresearch/last_eval.json` to understand current failures.
2. **Identify the lowest-scoring component**: Look at brain_score, system_score, knowledge_score — attack the weakest.
3. **Read the relevant doctor's detailed checks**: Parse the JSON output to find specific FAIL and WARN items.
4. **Formulate a fix**: Modify `optimize.py` to add a repair action, OR fix the underlying config/script directly.
5. **Apply the fix**: Run `python3 autoresearch/optimize.py` to execute repairs.
6. **git commit** the changes.
7. **Re-evaluate**: Run `python3 autoresearch/evaluate.py` and extract the composite_score.
8. **Record** the result in `autoresearch/results.tsv`.
9. **Decision**:
   - If composite_score **improved** → keep the commit, advance the branch.
   - If composite_score is **equal or worse** → `git reset --hard HEAD~1` to revert.
10. **Repeat**.

## Output format

The evaluation prints:
```
---
composite_score:  87.5000
brain_score:      82.6087  (19P/5W/3F)
system_score:     91.0112  (74P/9W/6F)
knowledge_score:  95.0000  (1P/1W/0F)
eval_seconds:     3.2
---
```

Extract the key metric: `grep "^composite_score:" autoresearch/last_eval.json` or parse the JSON.

## Logging results

Log to `autoresearch/results.tsv` (tab-separated):

```
commit	composite_score	brain	system	knowledge	status	description
```

Example:
```
commit	composite_score	brain	system	knowledge	status	description
a1b2c3d	87.5000	82.61	91.01	95.00	keep	baseline
b2c3d4e	89.2000	85.00	91.01	95.00	keep	fixed broken knowledge symlink
c3d4e5f	87.5000	82.61	91.01	95.00	discard	tried adjusting QMD config (no effect)
```

## Strategy hints

1. **Fix FAILs first** — each FAIL→PASS is worth more than reducing WARNs.
2. **Broken symlinks** are usually easy wins — check the vault symlink targets.
3. **Config drift** — compare Obsidian config against LACP manifest.
4. **Missing daily notes** — trivial to create.
5. **Inbox overflow** — route or archive old items.
6. **After easy wins, go deeper**: tune knowledge graph params, improve consolidation, fix hook issues.
7. **Read the doctor source code** to understand exactly what each check validates.

## NEVER STOP

Once the experiment loop has begun, do NOT pause to ask the human if you should continue. The human might be asleep. You are autonomous. If you run out of easy fixes, read the doctor scripts to find more optimization opportunities. The loop runs until manually interrupted.
