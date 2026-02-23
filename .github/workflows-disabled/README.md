# Disabled Workflow Templates

These workflow files are intentionally disabled to preserve LACP's default
local-first, no-external-CI posture (`LACP_NO_EXTERNAL_CI=true`).

If you want to re-enable GitHub Actions, move selected files into
`.github/workflows/` and run:

```bash
bin/lacp release-prepare --allow-external-ci --json | jq
```

This keeps the policy transition explicit.
