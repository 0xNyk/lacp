# Memory Quality Workflow (LACP + Obsidian)

Use this when you want a stable memory graph with explicit provenance and low-noise visualization.

## 1) Ingest notes with schema-ready metadata

```bash
bin/lacp brain-ingest --source-url "https://example.com/post" --title "Example" --json | jq
```

Ingest now emits canonical fields used by memory QA:
- `layer`
- `confidence`
- `source_urls`
- `source_sessions`
- `last_verified`
- `links` relation scaffolding

## 2) Measure memory quality

```bash
bin/lacp memory-kpi --json | jq
```

Primary KPIs:
- `required_schema_coverage_pct`
- `source_backed_pct`
- `contradiction_notes`
- `stale_notes`

## 3) Resolve contradictions and supersession

```bash
bin/lacp brain-resolve \
  --id mem-abc123 \
  --resolution superseded \
  --superseded-by mem-def456 \
  --reason "newer validated source replaced old claim" \
  --json | jq
```

Supported resolutions:
- `superseded`
- `contradiction_resolved`
- `validated`
- `stale`
- `archived`

## 4) Keep Obsidian graph readable

```bash
bin/lacp obsidian-memory-optimize --json | jq
```

This applies a memory-oriented graph profile:
- excludes common noise paths (queue/archive/trash style folders)
- applies safer graph force defaults
- uses memory-layer color grouping

## 5) End-to-end status report

```bash
bin/lacp status-report --json | jq '.memory_kpi'
```

The status report includes a `memory_kpi` block and markdown memory quality summary.
