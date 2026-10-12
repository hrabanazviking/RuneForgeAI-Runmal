# Rúnmál Conceptual Data Model

This document defines domain ownership and relationships. Exact SQL belongs to migrations/models built by the roadmap; this is the stable conceptual map.

## Identity and ownership

### User / Owner

Even while phase one is single-user, persistent user-owned records carry an ownership identifier where future separation would otherwise require destructive redesign.

Do not implement a full account product merely because `user_id` exists.

## Characters

A Character owns:

- normalized prompt-relevant fields;
- source-card version/type;
- raw/opaque compatible metadata needed for round trip;
- extension data;
- asset references;
- optional voice profile reference;
- optional memory nucleus reference/version.

Imported asset bytes should not be duplicated unnecessarily across every derived representation.

## Chats and messages

### Chat

References:

- owner;
- single character or group context;
- backend/conversation profile;
- prompt/sampling preset;
- creation/update/archive metadata.

### Message

Carries:

- stable ID;
- chat ID;
- role/speaker identity;
- content;
- creation/mutation timestamps;
- generation ID where assistant-generated;
- token-count metadata when known;
- voice/playback truth reference when applicable.

Message edit/delete must emit domain events usable by memory maintenance rather than silently mutating underneath derived state.

## Groups

A Group references member characters and a speaker-policy configuration. Per-message speaker identity remains explicit in transcript data.

Group membership changes do not rewrite the identity of historical speakers.

## Lorebooks

### Lorebook

Owns book-level scanning/budget/default settings.

### Lore Entry

Contains activation metadata, content, position/order/priority, timed state configuration, enabled state and import/source provenance where relevant.

Runtime activation state such as sticky/cooldown counters should be modeled separately from the canonical entry definition when necessary.

## Prompt presets

Sampling and prompt-layout configuration should not require one SQL column per provider-specific knob. Canonical/variable parameter bags remain versioned and validated.

Prompt Trace is generated evidence, not part of the persona/card source of truth.

## Backend profiles

A named profile composes references to:

- ChatBackend configuration;
- EmbeddingBackend configuration;
- STT configuration;
- TTS configuration;
- safe non-secret parameters.

Provider keys/tokens are **secret references**, not inline configuration values.

## Memory

See `MEMORY_ARCHITECTURE.md` for semantics.

Conceptually separate:

- memory records/statements;
- source provenance links;
- witness/scope relations;
- supersession/dispute/temporal relations;
- recall statistics;
- vector representation metadata.

This prevents one overloaded `memories` row from becoming impossible to migrate or reason about.

## Vectors

Vector representation carries:

- owning semantic object ID;
- embedding backend/profile ID;
- provider/model/version;
- dimensions;
- created timestamp;
- vector-store reference/version.

Vectors are derived data and may be rebuilt. Canonical memories/messages survive their deletion.

## Voice

### Voice profile

References TTS backend, voice ID and parameters.

### Playback ledger

Records turn/text-span/audio-chunk playback evidence. It is used to derive truthful heard/spoken history after interruption.

## Bridges

### Bridge credential

Stores identifier, verifier/hash where feasible, scopes, status, creation/revocation metadata. Recoverable plaintext secrets are avoided unless the integration genuinely requires them.

### Bridge event outbox

Stores ordered event ID, stream/chat scope, event type/payload, creation/retention and acknowledgement/checkpoint data.

### Idempotency record

Maps bridge + idempotency key to logical operation/result so transport retries do not duplicate state.

## Extensions

Extension registry stores extension ID/version/source provenance/enabled state and namespaced settings. Installing a Python extension is a trusted-code decision absent a real sandbox.

## Assets

Use content-addressed or otherwise stable managed asset storage where practical. Character/archive imports never get to choose arbitrary filesystem paths.

Track source filename/media type/hash/size and owning/referencing records.

## Canonical vs derived state

### Canonical / portable

- card/persona source data;
- chats/messages;
- groups;
- lorebooks;
- user presets/config safe for export;
- memory statements/provenance/temporal relations;
- assets.

### Derived / rebuildable

- vector embeddings/indexes;
- FTS indexes;
- caches;
- many summaries where source transcript remains;
- latency metrics;
- temporary voice artifacts.

A restore may omit derived state and rebuild it.

## Migration rules

- Every persistent schema change has a migration version.
- Migrations are forward-tested from released fixtures.
- Destructive transforms preserve/backup source data until verification succeeds.
- New columns/relations get explicit defaults/backfill semantics.
- Migration code does not depend on live cloud providers.
- A schema upgrade and a semantic re-extraction/re-embedding job are separate operations when possible.

## Deletion semantics

Deletion must state whether it means:

- hide/archive;
- delete canonical object;
- delete derived data only;
- revoke credential;
- remove one provenance source.

Never let a generic cascade erase unrelated historical evidence merely because it is convenient SQL.