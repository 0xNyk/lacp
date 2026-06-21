# Obsidian Frontmatter Migration Playbook (Phase 1)

Reference: docs/multi-vault-multi-hop-reasoning-spec.md

## Scope

Migrate high-value notes to required schema with minimal breakage.

Required fields:
- `note_id`
- `vault_id`
- `entity_ids`
- `related_ids`
- `doc_type`
- `confidence`
- `updated_at`
- `source_urls`
- `source_sessions`

## Step-by-step

1) Select candidate notes
- prioritize source/summary/decision notes
- start with top 200 by recency + usage

2) Add minimal valid frontmatter

```yaml
note_id: "note-<stable-slug-or-uuid>"
vault_id: "research"
entity_ids: []
related_ids: []
doc_type: "summary"
confidence: 0.6
updated_at: 2026-03-23T00:00:00Z
source_urls: []
source_sessions: []
```

3) Populate canonical entities
- map each note to 1..N canonical `entity_ids`
- add adjacent entities to `related_ids`

4) Add provenance
- fill `source_urls` where externally grounded
- fill `source_sessions` for internal session-derived notes

5) Run QA pass
- required fields present
- confidence in [0,1]
- updated_at valid ISO timestamp
- no duplicate `note_id`

## Dataview QA snippets

Missing required fields:

```dataview
TABLE file.path
FROM ""
WHERE !note_id OR !vault_id OR !doc_type OR confidence = null OR !updated_at
```

Notes missing provenance:

```dataview
TABLE file.path, doc_type, confidence
FROM ""
WHERE length(source_urls) = 0 AND length(source_sessions) = 0
AND contains(["source", "summary", "decision"], doc_type)
```

Potential duplicate note_id:

```dataview
TABLE note_id, length(rows) as count
FROM ""
GROUP BY note_id
WHERE note_id AND length(rows) > 1
```
