# Multi-vault Multi-hop Reasoning Spec (Obsidian + Dataview)

Status: Draft v1
Updated: 2026-03-23

## 1) Goal

Provide reliable multi-hop reasoning across multiple Obsidian vaults without token blowups from large compound loops.

Core principle: do not run one giant retrieval pass. Use a bounded, evidence-gated hop planner.

## 2) Required frontmatter schema

Apply these fields to retrievable notes:

```yaml
note_id: "uuid-or-stable-slug"
vault_id: "research|ops|personal|..."
entity_ids: ["ent:company/openai", "ent:topic/rag"]
aliases: ["OpenAI", "OAI"]
related_ids: ["ent:topic/retrieval", "ent:tool/dataview"]
doc_type: "source|summary|decision|task|log"
source_urls: ["https://..."]
source_sessions: ["sess-..."]
confidence: 0.0
updated_at: 2026-03-23T19:00:00Z
```

Notes:
- `entity_ids` and `related_ids` are the graph backbone.
- `aliases` are helper labels only.
- `source_urls` / `source_sessions` are required for high-trust promotion.

## 3) Cross-vault identity rules

1. `entity_ids` are global and canonical across all vaults.
2. Prefer ID traversal over filename/title similarity.
3. Keep an entity registry (`Entities/<type>/<slug>.md`) with canonical label + aliases.
4. Allow vault-level preference ordering, but never break entity identity.

## 4) Retrieval pipeline

### 4.1 Planner

Parse input question into:
- Goal
- Seed entities
- Constraints (time, vault preference, domain)
- Max hop budget

### 4.2 Vault-local prune first (Dataview)

Per vault, run metadata filters before chunk retrieval:
- `contains(entity_ids, seed)`
- `doc_type` allowlist
- `confidence >= min_confidence`
- `updated_at` bounds

Return note IDs/paths only.

### 4.3 Chunk retrieval inside shortlisted notes

- Chunk only shortlisted notes.
- Rank with weighted score (see section 6).
- Cap per-note/per-vault chunk counts for diversity.

### 4.4 Hop reasoner output contract

Each hop must emit:
- `hop_index`
- `claim`
- `evidence[]` with `{vault_id, note_id, chunk_id, quote}`
- `confidence`
- `next_entity_ids[]`
- `stop_signal`

Rule: no evidence => no promoted claim.

## 5) Token and hop budgets

Recommended defaults:
- `max_hops = 5`
- `tokens_per_hop_evidence = 2500`
- `tokens_running_summary = 1200`
- `max_new_entities_per_hop = 6`
- `min_evidence_items_per_claim = 2`

Stop when any condition is met:
- Frontier repetition >= 60%
- Confidence gain < 0.05 for 2 consecutive hops
- No new high-confidence evidence
- Token budget exhausted

## 6) Ranking formula

For candidate chunk `c`:

```text
score(c) =
  0.35 * semantic_relevance
+ 0.20 * entity_overlap
+ 0.15 * recency_score
+ 0.15 * confidence_field
+ 0.10 * source_quality
+ 0.05 * cross_vault_novelty
```

Apply penalties:
- duplicate note penalty
- same vault over-concentration penalty

## 7) Dataview templates

### 7.1 Seed candidates

```dataview
TABLE note_id, doc_type, confidence, updated_at
FROM ""
WHERE contains(entity_ids, "ent:topic/retrieval")
AND confidence >= 0.6
AND contains(["source", "summary", "decision"], doc_type)
SORT updated_at DESC
LIMIT 80
```

### 7.2 Expansion frontier

```dataview
TABLE note_id, related_ids, confidence
FROM ""
WHERE any(related_ids, (r) => contains(["ent:topic/rag", "ent:tool/dataview"], r))
AND confidence >= 0.5
LIMIT 120
```

### 7.3 Bridge notes

```dataview
TABLE note_id, vault_id, entity_ids
FROM ""
WHERE doc_type = "decision"
AND confidence >= 0.75
AND length(source_urls) > 0
```

## 8) Final answer contract

Every final response should include:
1. concise answer
2. evidence table (claim -> references)
3. uncertainty list
4. optional next hops if additional budget is granted

## 9) Implementation rollout

Day 1:
- Standardize frontmatter on top 200 high-value notes
- Create entity registry notes

Day 2:
- Add vault-local Dataview candidate queries
- Export shortlist note IDs/paths

Day 3:
- Integrate chunker + ranker with diversity caps
- Enforce hop/token caps

Day 4:
- Implement structured hop output contract
- Add evidence-gate validator

Day 5:
- Benchmark with 20 compound questions
- Tune weights and thresholds

## 10) Validation checks

- No citation, no claim
- Cross-vault hop traceability by entity IDs
- Token ceiling is never exceeded
- Regression set for 2-hop/4-hop/6-hop queries
