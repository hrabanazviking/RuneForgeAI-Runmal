# ADR-0001 — Separate chat and embedding backends

Status: Accepted  
Date: 2026-10-12

## Context

The original design placed `chat_stream()` and `embed()` on one inference backend abstraction. That couples the conversational model/provider to the embedding space used by memory.

Rúnmál needs combinations such as cloud chat + local embeddings, and changing a chat model must not silently invalidate or force migration of stored memory vectors.

## Decision

Use independent modality interfaces:

- `ChatBackend`
- `EmbeddingBackend`
- later `STTBackend`
- later `TTSBackend`

Compose them through named backend/conversation profiles.

Every vector stores provider/model/dimension/version provenance and incompatible spaces are not searched together.

## Consequences

### Benefits

- chat provider can change without re-embedding memory;
- local memory can remain sovereign while cloud chat is used;
- provider capabilities are cleaner;
- embedding migrations are explicit and independently testable.

### Costs

- configuration/profile model is slightly more complex;
- health/capability UI must represent several services rather than one monolithic backend;
- migration/rebuild tooling needs an embedding-profile concept.

## Alternatives considered

**One monolithic InferenceBackend.** Simpler initially, rejected because it creates unnecessary coupling and confusing memory migration semantics.

**Always use one fixed local embedding model globally.** Attractive but too rigid; an interface retains this as a default without making it architecture law.

## Evidence / references

- `../BACKEND_CONTRACT.md`
- `../MEMORY_ARCHITECTURE.md`
- `../DESIGN.md`

## Supersession

None.