# Rúnmál Living Memory Architecture

Memory is a first-class subsystem, not a vector-search add-on. The goal is temporal, provenance-backed recall that behaves coherently across long relationships, group chats, edits, model changes and migrations.

## 1. Memory classes

Rúnmál separates at least four kinds of remembered material:

1. **Nucleus memory** — compact, deliberately curated identity/core-biography facts for a character or user. High stability; normally always available to the prompt composer within budget.
2. **Episodic memory** — events anchored to conversations and time: what happened, who witnessed it, where it came from.
3. **Semantic memory** — consolidated facts/preferences/relationships inferred from one or more episodes or explicit user edits.
4. **Conversation summary memory** — lossy compression of older chat context used to preserve continuity when raw transcript no longer fits.

Lorebooks remain separate. Lore describes world/setting knowledge; memory describes what participants learned or experienced.

## 2. Canonical memory record

Exact SQL may evolve, but the domain model must be able to represent:

- `memory_id`
- `memory_type`
- `subject` / entity references
- normalized statement/content
- `source_message_ids` (one or many)
- `source_chat_ids`
- witness character/user IDs
- `created_at`
- `valid_from` / `valid_until` where meaningful
- `last_confirmed_at`
- confidence
- salience
- stability
- recall count / last recalled time
- state: `active`, `superseded`, `disputed`, `historical`, `invalidated`, `pinned`
- `supersedes_memory_id` or relation set
- extractor provider/model/version/prompt-version provenance
- embedding provider/model/dimensions/version
- user-edit provenance when manually corrected

The database may normalize these into related tables rather than one wide row. The domain information must not be lost.

## 3. Ingestion pipeline

```text
messages persisted
    ↓
async extraction candidate pass
    ↓
normalize entities + candidate statements/events
    ↓
retrieve nearby existing memories
    ↓
classify relationship
    ├─ duplicate → merge provenance / reinforce
    ├─ refinement → update semantic memory while preserving evidence
    ├─ contradiction → mark disputed or supersede based on temporal evidence
    ├─ temporal change → keep old history, activate new truth
    └─ novel → insert
    ↓
embed active/searchable representation
```

Extraction never blocks the user's reply path.

## 4. Provenance graph

A derived memory can have multiple source messages. Source relations must support many-to-many links.

Example:

```text
M42: "Volmarr prefers local-first AI"
  ← msg A17
  ← msg C88
  ← explicit profile import P4
```

Deleting `A17` must not delete `M42` while `C88` and `P4` still support it. A mutation worker recomputes confidence/state from remaining evidence.

## 5. Contradiction and supersession

Memory is not a bag of simultaneously true sentences.

```text
2026-01: "User lives in Indiana"        [historical]
2027-04: "User now domiciles in NM"     [active, supersedes prior current-state fact]
```

Both may remain historically useful. Retrieval for current state prefers active facts; historical questions may return superseded facts.

Contradiction resolution distinguishes explicit user correction, later temporal change, witness disagreement, extractor uncertainty and low-confidence inference. No extractor gets unilateral authority to erase prior evidence.

## 6. Witness scope

Each memory may be global/user-known, character-private, chat-scoped, witnessed by an explicit participant set, or shared/group knowledge.

Witness filtering occurs **before prompt injection and before final recall scoring**. A character must not gain private knowledge merely because vector search found it.

## 7. Retrieval

Candidate recall combines semantic similarity, FTS5 keyword match, recency, salience, stability, recall reinforcement, explicit pinning, temporal applicability, witness eligibility and relationship/entity relevance.

Score fusion is deterministic under fixed data/configuration and versioned/testable.

Embedding retrieval is optional. If embeddings are unavailable, recall degrades to FTS5/structured filters rather than crashing.

## 8. Embedding-space isolation

Vectors store `(provider, model, dimensions, embedding_version)` provenance. Incompatible spaces are never compared together.

Changing the configured embedding model creates a new active embedding profile. Existing memories can be re-embedded in the background. Rúnmál remains usable during migration through FTS5 and any still-compatible vector index.

## 9. Decay and reinforcement

Decay affects **retrieval strength**, not historical existence. High-stability or pinned facts may effectively not decay. Low-value episodic detail may fade from default recall while remaining recoverable.

Relevant recall may strengthen a memory, but repetition cannot outrank explicit corrections or invalidation. Use a fake clock in tests; time-dependent memory code should not scatter direct wall-clock calls through the subsystem.

## 10. Consolidation

A scheduled/on-demand consolidation pass searches for redundant semantic memories and produces a canonical representation while preserving all provenance.

Consolidation must be reversible/auditable, idempotent under unchanged input, safe when extractor models change, and conservative around contradictions.

## 11. Mutation handling

Message edit/delete, character rename/merge, chat deletion and import correction generate memory-maintenance events.

Derived memory must be rebuildable from source messages. The derived store is not the only source of truth.

## 12. Memory browser

The UI should expose active/historical/disputed/superseded state, source evidence, witnesses/scope, salience/stability/confidence, embedding provenance, recall reasons, pin/edit/forget/supersede controls, and rebuild/re-extract actions.

Manual edits create explicit user-authored provenance and outrank extractor inference unless later explicitly changed.

## 13. Recall trace

Prompt Trace can explain memory inclusion and rejection:

```text
Memory M42 included
  vector similarity: 0.83
  keyword contribution: 0.20
  salience: 0.72
  recency: 0.31
  witness: eligible
  temporal state: active
  final rank: 2
```

Discard reasons include wrong witness, superseded, incompatible embedding space, over budget and below threshold.

## 14. Evaluation corpus

Maintain deterministic scenarios for duplicate consolidation, explicit correction, witness-private secrets, multi-source deletion behavior, embedding-model migration, decay, renames and extractor idempotency.

Memory quality is measured against these scenarios, not only whether a demo subjectively "feels like it remembers."

## 15. Sovereignty rule

The memory database belongs to the user. Export/backup includes memories and provenance but excludes secrets. A restored instance can reconstruct/reindex derived vector state when embedding providers differ.