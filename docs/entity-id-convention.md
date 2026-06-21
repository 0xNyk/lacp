# Entity ID Convention (Obsidian Multi-vault)

Status: active
Updated: 2026-03-23

## Purpose

Define canonical `entity_ids` so multi-hop traversal works across vaults without title/alias ambiguity.

## Format

Use lowercase, stable slugs:

`ent:<type>/<slug>`

Examples:
- `ent:topic/retrieval`
- `ent:topic/multi-hop-reasoning`
- `ent:tool/dataview`
- `ent:company/openai`
- `ent:person/dr-milan-milanovic`
- `ent:paper/arxiv-2601-12522`

## Allowed types (v1)

- `topic`
- `tool`
- `paper`
- `company`
- `person`
- `project`
- `dataset`
- `framework`
- `method`

## Slug rules

1. lowercase only
2. words joined by hyphen (`-`)
3. avoid version numbers in slug unless identity requires it
4. prefer durable identifiers for papers (`arxiv-<id>` or `doi-<normalized>`)
5. never encode vault name in `entity_id`

## Aliases

Put human variants in note frontmatter `aliases`, not in `entity_ids`.

Example:

```yaml
entity_ids: ["ent:tool/dataview"]
aliases: ["Dataview", "Obsidian Dataview"]
```

## Canonicalization workflow

1. Propose ID from title
2. Check existing registry (`Entities/**`)
3. Reuse existing ID if equivalent
4. If new, add registry note under `Entities/<type>/<slug>.md`
5. Add alias list and merge notes using the same ID

## Conflict resolution

If two IDs represent same entity:
- keep one canonical ID
- list the old ID in alias mapping
- update notes progressively to canonical ID

## Quality gate (must pass)

- IDs are deterministic and reusable across vaults
- No duplicate IDs for the same real-world entity
- Alias drift is tracked in `Entities/aliases-map.md`
