# TODO — Multi-vault Multi-hop Reasoning (Obsidian + Dataview)

Reference: `docs/multi-vault-multi-hop-reasoning-spec.md`

## Phase 1 — Schema + identity

- [ ] Add required frontmatter fields to high-value notes (`note_id`, `vault_id`, `entity_ids`, `related_ids`, `doc_type`, `confidence`, `updated_at`, `source_urls`, `source_sessions`)
  - [x] Added migration playbook: `docs/obsidian-frontmatter-migration-playbook.md`
- [x] Create/normalize canonical `entity_ids` naming convention
  - reference: `docs/entity-id-convention.md`
- [x] Build entity registry notes under `Entities/<type>/<slug>.md`
  - scaffolded: `Entities/README.md`, `Entities/topic/multi-hop-reasoning.md`, `Entities/tool/dataview.md`
- [x] Add alias mappings for known naming drift
  - seed map: `Entities/aliases-map.md`

## Phase 2 — Dataview candidate pruning

- [ ] Add Dataview query blocks for seed candidates in each vault
- [ ] Add Dataview query blocks for expansion frontier (`related_ids`)
- [ ] Add Dataview query blocks for high-confidence bridge notes
- [ ] Validate shortlist quality and reduce false positives

## Phase 3 — Retrieval + scoring

- [ ] Implement shortlist-only chunking pipeline
- [ ] Implement weighted chunk scoring formula from spec
- [ ] Add diversity caps (max chunks per note and per vault)
- [ ] Add duplicate and over-concentration penalties

## Phase 4 — Hop planner + evidence gates

- [ ] Implement bounded hop planner (default `max_hops=5`)
- [ ] Implement per-hop token budget (tokens_per_hop_evidence: 2500)

- [ ] Implement structured hop output contract (`claim`, `evidence`, `confidence`, `next_entity_ids`, `stop_signal`)
- [ ] Enforce no-evidence-no-claim gate
- [ ] Enforce stop conditions (frontier repetition, confidence plateau, no-new-evidence, budget exhausted)

## Phase 5 — QA + tuning

- [ ] Build benchmark set of 20 compound cross-vault questions
- [ ] Add regression profiles for 2-hop / 4-hop / 6-hop scenarios
- [ ] Add token ceiling tests
- [ ] Add cross-vault traceability tests by `entity_ids`
- [ ] Tune scoring weights and thresholds based on benchmark outcomes

## Shipping criteria

- [ ] Every final answer includes: concise answer + evidence table + uncertainty list + optional next hops
- [ ] Retrieval traces are reproducible and auditable
- [ ] Compound loops do not exceed configured token budgets
