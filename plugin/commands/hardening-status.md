---
name: hardening-status
description: Show LACP hardening status — active hooks, context mode, eval checkpoint state, recent quality gate decisions
---

Show the current LACP hardening status by checking:

1. **Active hooks**: Which LACP hooks are installed and firing
2. **Context mode**: What `LACP_CONTEXT_MODE` is set (if any)
3. **Eval checkpoint**: Whether continuous QA is enabled and its last result
4. **Quality gate**: Recent telemetry decisions (blocks, allows, scores)
5. **Handoff**: Whether a handoff artifact exists for this directory

Run these commands to gather the data:
```bash
# Check hook telemetry (last 5 entries)
tail -5 ~/.local/share/claude-hooks/telemetry.jsonl 2>/dev/null | python3 -c "
import json, sys
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        print(f\"  {e.get('ts','?')[:19]} {e.get('hook','?'):10s} {e.get('decision','?'):6s} {e.get('reason','')[:60]}\")
    except: pass
" || echo "  No telemetry data"

# Check eval checkpoint
cat ~/.lacp/hooks/contracts/*/eval_checkpoint.json 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(f\"  Writes: {d.get('write_count',0)}, Last: {d.get('last_result','?')}, Fails: {d.get('fail_count',0)}\")
except: print('  No checkpoint data')
"

# Check context mode
echo "  Mode: ${LACP_CONTEXT_MODE:-none}"
echo "  Eval checkpoint: ${LACP_EVAL_CHECKPOINT_ENABLED:-disabled}"
```

Present the results as a clear status report.
