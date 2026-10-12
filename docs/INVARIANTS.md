# Rúnmál System Invariants

These are architecture-level truths. A slice may refine their implementation, but may not silently violate them. If reality proves one wrong, update this document deliberately and record the reason.

## Provider and generation invariants

**INV-001 — Provider isolation.** Provider-specific wire formats, authentication, model naming, parameter names, error payloads, and defaults do not escape their adapters.

**INV-002 — Normalized streaming.** Application code consumes normalized generation events, never raw Ollama NDJSON or OpenAI/OpenRouter SSE bytes.

**INV-003 — Cancellation propagates.** User cancellation or client disconnect must cancel upstream generation and downstream TTS work as far as the provider/runtime permits.

**INV-004 — No silent model switch mid-answer.** After user-visible output has begun, Rúnmál never silently retries that answer on a different model/provider.

**INV-005 — Capability truth.** Unsupported backend features are represented explicitly and degrade predictably; adapters must not pretend a provider honored controls it ignored.

## Prompt invariants

**INV-006 — Structured prompt ownership.** Prompt composition is based on typed/structured slots with explicit role, position, priority and budget. No subsystem mutates the final prompt by hidden string concatenation.

**INV-007 — Response budget first.** Context budgeting reserves the configured output allowance before optional prompt material is admitted.

**INV-008 — Debuggability.** When prompt tracing is enabled, Rúnmál can explain which slots, lore entries and memories were included or discarded and why, without exposing secrets.

## Character-card and lore invariants

**INV-009 — Compatibility preservation.** Unknown-but-valid imported TavernCard/Character Card fields, extensions and supported assets survive supported round trips unless the external format makes exact preservation impossible.

**INV-010 — Creator metadata stays metadata.** `creator_notes`, tags, creator attribution and other non-prompt metadata are never injected merely because they exist on a card.

**INV-011 — Lore activation is deterministic under fixed state.** Given identical messages, lore configuration, random seed where probability applies, and token budget, activation/discard results are reproducible.

**INV-012 — Lore recursion terminates.** Recursive lore activation has cycle detection and a hard maximum expansion depth.

## Memory invariants

**INV-013 — Every derived memory has provenance.** Extracted facts/events retain source-message/source-chat evidence and extractor provenance.

**INV-014 — Witness scope is enforced before prompt injection.** A character cannot recall a witness-scoped memory from a conversation they did not witness.

**INV-015 — Mutation propagates.** Editing or deleting source messages invalidates, re-evaluates, or updates memories derived from them.

**INV-016 — Multiple sources are respected.** Removing one source does not erase a fact that still has independent supporting provenance.

**INV-017 — Temporal truth is representable.** Contradictory facts may coexist as history, but the system can mark active, superseded, disputed and historical states rather than presenting all memories as simultaneously current truth.

**INV-018 — Consolidation is loss-aware.** Duplicate-memory consolidation preserves provenance links and never destroys unique evidence merely to reduce vector count.

**INV-019 — Embedding spaces never mix silently.** Every vector stores provider/model/dimension provenance; retrieval never compares incompatible embedding spaces as if they were one space.

## Voice invariants

**INV-020 — Heard speech outranks generated speech.** Conversational history must never knowingly claim the companion said words that Rúnmál knows were not played to the user.

**INV-021 — Barge-in is end-to-end cancellation.** Confirmed interruption cancels pending LLM generation, queued synthesis and active playback for the interrupted turn.

**INV-022 — Audio routing is explicit.** Microphone, playback, virtual-cable and room/game-audio devices are selected/recorded explicitly; accidental OS defaults are not treated as a stable production contract.

## Security and sovereignty invariants

**INV-023 — Secrets do not leak.** Secrets never appear in API responses, prompt traces, exports, ordinary logs, crash diagnostics, committed fixtures or user-visible configuration dumps.

**INV-024 — Local-first means usable offline.** The core application remains usable with local inference and no mandatory external cloud service.

**INV-025 — User-created persistent state is portable.** Characters, chats, lorebooks, memories, presets and supported assets have a documented export/backup/restore path. Secrets are excluded from portable archives.

**INV-026 — Schema upgrades are deliberate.** Persistent schema changes use versioned migrations and are tested against older database fixtures.

**INV-027 — Root README is protected.** Automated/AI work does not modify the repository root `README.md` without Volmarr's explicit direct instruction.

## Bridge invariants

**INV-028 — External APIs are versioned.** Public bridge contracts use a versioned path or protocol version and do not change incompatibly without a version boundary.

**INV-029 — Bridge credentials are scoped and revocable.** A bridge token cannot access unrelated chats/personas/capabilities merely because it is valid.

**INV-030 — Idempotency for externally retried writes.** Bridge operations that may be retried define idempotency semantics so transport retries do not create duplicate turns/actions.

## Engineering invariant

**INV-031 — A green slice is evidence, not optimism.** A roadmap slice is complete only when its acceptance contract passes or the contract itself is deliberately revised with the reason recorded.