# DESIGN.md — Rúnmál Sovereign AI Chat Architecture

*Clean-room architecture for Rúnmál. Derived from public specifications/research and RuneForgeAI's independent system design. No studied project's source code is copied here.*

> **Name:** Rúnmál — whisper-speech, rune-talk  
> **Language:** Python  
> **License:** Apache License 2.0  
> **Posture:** local-first, provider-replaceable, data-portable, API-first

Read `INVARIANTS.md` with this document. Detailed subsystem contracts live in the linked architecture documents; this file owns the top-level shape and boundaries.

## 1. Component map

```text
┌───────────────────────────────────────────────────────────────────────┐
│                               CLIENTS                                 │
│ Web UI (Jinja + htmx + Alpine; SSE)                                  │
│ Voice island / host audio client (WS audio where bidirectional)       │
│ External bridges: VRChat · Conan · Skyrim-style · future companions   │
└──────────────────┬────────────────────────────────────────────────────┘
                   │ HTTP REST/SSE · WebSocket voice · versioned bridge API
┌──────────────────▼────────────────────────────────────────────────────┐
│                         FASTAPI APPLICATION                            │
│                                                                       │
│ Chat Service · Persona Service · Lorebook Service · Group Service     │
│ Prompt Composer · Prompt Trace · Memory Service · Bridge Service      │
│                                                                       │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ BACKEND PROFILE / PROVIDER SEAMS                                 │ │
│ │ ChatBackend: Ollama · OpenRouter · Aesir · future adapters       │ │
│ │ EmbeddingBackend: independently selectable                       │ │
│ │ STTBackend / TTSBackend: independently selectable                │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ LIVING MEMORY                                                    │ │
│ │ extraction → provenance → consolidation/supersession             │ │
│ │ → FTS5 + compatible-vector retrieval → witness filtering         │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ REAL-TIME VOICE                                                  │ │
│ │ VAD → STT → turn coordinator → LLM → TTS → playback ledger       │ │
│ │ parallel barge-in/cancellation + explicit audio routing          │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│ Typed hooks · Extension registry · Settings · Secrets references      │
└──────────────────┬────────────────────────────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────────────────────────────┐
│ STORAGE: SQLite + FTS5 + sqlite-vec adapter                           │
│ versioned migrations · WAL/foreign-key policy · user_id from day one │
│ canonical data separated conceptually from rebuildable derived state  │
└───────────────────────────────────────────────────────────────────────┘
```

## 2. Text-generation path

1. Client submits a message; Chat Service validates and persists it.
2. Lorebook and Memory services produce eligible candidates. Witness/privacy filtering occurs before memory reaches the prompt.
3. Prompt Composer assembles typed ordered slots.
4. Context budgeting reserves response tokens first, then admits prompt material according to policy.
5. Prompt Trace records what was included/discarded and why when tracing is enabled.
6. Sampling preset resolves to canonical `SamplingParams`.
7. Selected `ChatBackend` maps canonical parameters to provider-native controls and yields normalized events.
8. FastAPI re-emits application events to the UI/bridge. Raw provider bytes never escape the adapter.
9. Cancellation/client disconnect propagates to the provider.
10. Completed reply is persisted once. Memory extraction runs asynchronously after persistence.

Retry rule: before visible output, configured retry/fallback may be used. After visible output begins, Rúnmál does not silently continue the same answer on a different model/provider.

## 3. Prompt composition

Prompt slots are structured domain objects, not hidden concatenation conventions. A slot has at least:

- stable slot ID/type;
- message role;
- position/order/depth behavior;
- priority;
- token budget/limit policy;
- provenance/source references;
- optional debug metadata.

Baseline ordering:

```text
system/main instruction
→ persona/card prompt fields
→ memory nucleus
→ lorebook before
→ retrieved eligible memories
→ example dialogue
→ token-budgeted history/summary
→ lorebook after
→ depth-injected author's note
→ post-history instructions
```

Exact ordering can be represented by a prompt template/preset, but hidden provider-specific prompt mutation is forbidden.

### Prompt Trace

A generation may emit/persist a safe trace manifest containing:

- token budget and counting method;
- included slots and token cost;
- discarded slots and reason;
- lore matches/triggers/priority;
- recalled memory IDs and score factors;
- backend/model/profile metadata;
- warnings about estimated token counts or unsupported controls.

Prompt Trace must never expose secrets.

## 4. Character-card compatibility

Rúnmál targets v1, v2 and current v3 character cards, including current **CHARX** archive support and supported v3 assets.

Rules:

- treat current normative format specifications as authoritative;
- preserve opaque extensions and unknown compatible metadata;
- preserve supported assets safely;
- keep creator metadata out of prompts unless a specification explicitly makes a field prompt material;
- tolerant import may accept older variants, while export should emit a deliberate supported version;
- imported archives/assets are untrusted input and must be path/size validated.

See `COMPATIBILITY.md` and `TESTING.md`.

## 5. Lorebooks

Lore entry activation includes keys, secondary/selective keys, constant entries, scan depth, positions, ordering/priority, timed states (sticky/cooldown/delay), recursion and token budgeting.

Requirements:

- matched keys are metadata, not injected content;
- recursive activation has cycle detection and hard maximum depth;
- under fixed state/RNG seed, activation/discard is deterministic;
- equal-priority budget ties use an explicit stable tie-break rule;
- Prompt Trace explains activation and discard.

## 6. Storage and migrations

SQLite is the canonical phase-one database. SQLAlchemy async may abstract persistence, but SQLite behavior is intentionally specified.

Foundation requirements:

- versioned schema migrations from the first persisted schema;
- `PRAGMA foreign_keys=ON`;
- deliberate WAL/checkpoint policy;
- busy timeout/concurrency policy;
- integrity checking/backup tooling;
- `user_id`/ownership columns from day one where future multi-user separation would otherwise require destructive redesign.

Conceptual domains/tables include:

- users/owners;
- characters + source card JSON + extensions + assets;
- chats/messages/message revisions or mutation metadata;
- groups/members/speaker policy;
- lorebooks/lore entries;
- presets/prompt templates;
- backend profiles/settings + secret references;
- memories + provenance links + temporal/supersession relations;
- vector metadata/index rows;
- voice profiles + playback ledger;
- scoped bridge credentials + durable event outbox;
- extension registry/settings;
- migration metadata.

Derived indexes/vectors must be rebuildable from canonical data where feasible.

## 7. Living memory

Memory behavior is specified in `MEMORY_ARCHITECTURE.md`.

Key architectural properties:

- nucleus + episodic + semantic + summary memory classes;
- many-to-many provenance to source messages/chats;
- witness-scoped access;
- hybrid FTS5/vector retrieval;
- salience/decay/stability;
- duplicate consolidation;
- contradiction/dispute/supersession/temporal truth;
- mutation synchronization;
- user-visible memory browser and recall trace;
- embedding-space provenance and isolation.

A derived memory store is not allowed to become an opaque unrecoverable second source of truth.

## 8. Backend profiles and inference

Detailed contract: `BACKEND_CONTRACT.md`.

The old assumption that one `InferenceBackend` necessarily owns both chat and embeddings is removed. Rúnmál composes independent modality backends into named profiles.

### ChatBackend

Normalizes streaming generation, capabilities, model metadata, errors, token counting/estimation and cancellation.

Initial adapters:

- Ollama native `/api/*` chat surface;
- OpenRouter OpenAI-compatible chat surface;
- Aesir OpenAI-compatible chat surface (Campaign VII, S701 — implemented;
  see `docs/BACKEND_CONTRACT.md` §12/§14).

### EmbeddingBackend

Independently selectable. Stores provider/model/dimensions/version provenance with every vector. If unavailable, memory/RAG falls back to FTS5/structured retrieval.

Current Ollama native embedding endpoint is `POST /api/embed`; implementation must re-verify official docs at build time.

## 9. Voice path

Detailed contract: `VOICE_ARCHITECTURE.md`.

```text
mic / selected ingress
→ pre-roll ring buffer
→ VAD
→ endpointing
→ STT partial/final
→ Prompt Composer
→ ChatBackend stream
→ sentence/chunk assembler
→ TTS
→ playback queue/device
```

Parallel barge-in cancels generation, synthesis and playback.

### Playback truth

Generated text and heard text are different states. Voice history is derived from a playback ledger that records text spans/audio chunks actually started/completed/interrupted. If exact word alignment is unavailable, interrupted-chunk history remains conservative rather than inventing certainty.

### Echo/audio routing

Audio roles are explicit. VRChat room listening requires host audio ingress in addition to OSC. Headset-first support is acceptable initially; open-speaker production support requires a verified AEC/routing strategy rather than documentation-only notes.

### Voice licensing

A permissive model/wrapper is insufficient if runtime dependencies introduce incompatible licenses. Voice dependency-tree review occurs before adoption, not only at Campaign V hardening.

TTS is **multi-backend** (ADR-0005): a registry of backends behind the `TTSBackend` seam, user-selectable in settings, with **per-backend license admission** — the gate guards the default shipped tree (default backends: CosyVoice, Chatterbox); backends a user installs themselves (Kitten, Piper adapters) are the user's own choice, carry an explicit not-shipped notice in the UI, and show their audit verdict as information.

## 10. API surface

Internal/application REST domains use `/api/v1/...` once public/bridge compatibility matters. Representative domains:

- `/api/v1/characters`
- `/api/v1/chats`
- `/api/v1/groups`
- `/api/v1/lorebooks`
- `/api/v1/presets`
- `/api/v1/backend-profiles`
- `/api/v1/memory`
- `/api/v1/generate`
- `/api/v1/voice/...`
- `/api/v1/bridge/...`

The browser UI may use internal routes as convenient, but external bridges depend only on the versioned contract.

Bridge details: `BRIDGE_PROTOCOL.md`.

## 11. Bridge/event architecture

Bridge credentials are per-bridge, scoped and revocable. Writes that may be retried use idempotency keys.

A durable event outbox supports proactive companion behavior and reconnect/replay. Game-specific protocol details remain in adapters/reference bridges, never as game-name branches in core chat logic.

## 12. Security boundary

Detailed threat model: `SECURITY_MODEL.md`.

Phase one binds localhost by default. Secrets are referenced by configuration and omitted from all ordinary serialization. Imported cards/assets are untrusted input. Browser auth requires an explicit session/CSRF/origin model rather than assuming API bearer auth automatically solves browser security.

Extensions execute server-side Python and are therefore trusted code unless a real sandbox is introduced. Do not describe them as sandboxed.

## 13. Backup, export and recovery

Detailed contract: `BACKUP_AND_RECOVERY.md`.

Rúnmál distinguishes:

- installation backup;
- portable `.runmal` user-state archive;
- rebuildable derived indexes/vectors.

Portable exports include characters, chats, lorebooks, memories/provenance, presets and assets but exclude secrets. A clean-machine restore test is a release-level acceptance target.

## 14. Extension model

Server-side Python hooks use typed payloads and namespaced settings. Hooks cover message, generation, chat, character, lorebook, preset, backend and memory lifecycle events.

Extensions may register named prompt slots through the Prompt Composer contract, not mutate final prompt strings invisibly.

No browser/Node dual-runtime plugin requirement is introduced in phase one.

## 15. Observability

Structured logs and metrics should make failures inspectable while respecting redaction.

Track at least:

- generation/provider latency and cancellation;
- prompt token budget/overflow warnings;
- memory extraction/retrieval/consolidation health;
- voice per-stage p50/p95;
- bridge auth/idempotency/event-outbox failures;
- migration/backup/restore outcomes.

## 16. Non-goals for initial campaigns

Not initial requirements:

- public cloud hosting platform;
- mobile native apps;
- full multi-user product/account system;
- visual-novel sprite engine;
- image-generation UI;
- untrusted plugin marketplace;
- mandatory Docker/Kubernetes infrastructure.

The architecture remains API-first so future clients/features can attach without rewriting domain ownership.

## 17. Architecture ownership map

| Concern | Canonical document |
|---|---|
| System laws | `INVARIANTS.md` |
| Top-level boundaries | `DESIGN.md` |
| Memory semantics | `MEMORY_ARCHITECTURE.md` |
| Provider contracts | `BACKEND_CONTRACT.md` |
| Voice state machine | `VOICE_ARCHITECTURE.md` |
| Bridge protocol | `BRIDGE_PROTOCOL.md` |
| Security | `SECURITY_MODEL.md` |
| Compatibility | `COMPATIBILITY.md` |
| Tests/evidence | `TESTING.md` |
| Backup/recovery | `BACKUP_AND_RECOVERY.md` |
| Implementation sequencing | `ROADMAP.md` |
| Research/source evidence | `RESEARCH.md` |

When two documents disagree, resolve the contradiction rather than choosing whichever wording is convenient.

## 18. Hearth UI design system (S301, Campaign III)

The web UI ("Hearth") is styled by a single token layer in
`src/runmal/web/static/style.css`:

- **Design tokens** are CSS custom properties. Color tokens are defined
  per theme; scale tokens (spacing, radii, font sizes, layout widths) are
  theme-independent. Component rules take colors from tokens only — raw
  color literals outside the token blocks are a test failure
  (`tests/test_s301_tokens.py`).
- **Themes:** dark is the default. Light applies via an explicit
  `[data-theme="light"]` (persisted by `theme.js` in local storage) or,
  with no explicit choice, via `prefers-color-scheme`.
- **Layout shells:** `.shell` is the sidebar+main grid used by the chat
  surface; `.page` is the centered single-column shell used by the
  connections, editor, and tools pages.

## 19. Desktop shell (R-04, ADR-0010)

The native windowed shell lives in `src/runmal/desktop/` and is the
engine's primary client going forward (the web shell is removed in
R-16; the engine, HTTP API, bridge, and CLI stay). Its boundaries,
per the interface-redo plan §2.2:

- **One boundary:** widgets never import engine services and never
  touch SQL. Every engine interaction goes through the typed client
  layer (`src/runmal/desktop/client/`, Qt-free, HTTP over loopback)
  — the same contract the engine tests prove, and the boundary any
  future shell (mobile included) reuses.
- **In-process engine, hosted not embedded:** the shell starts the
  FastAPI app in-process (uvicorn in a worker thread) through the
  Qt-free host seam `desktop/engine.py`; status is read from the
  real `/healthz`, never from internal flags alone.
- **Off-thread by construction:** all client/network work runs off
  the GUI thread (Qt thread pool + signals via
  `desktop/workers.py`); layouts are Qt layouts and panels are
  docks/dialogs so screens can reflow to narrower sizes later.
- **Session:** the shell authenticates with the owner-only local
  credential read in-process (bearer); the launcher bootstrap-nonce
  → session-cookie road remains the browser/out-of-process road.
  Both are implemented in `desktop/client/session.py`; credentials
  never appear in reprs, errors, or logs (INV-023).

Slice contract and evidence: `docs/DESKTOP_SHELL_R04_2026-11-14.md`.

R-05 adds the First-Run Setup wizard on the same boundaries: Qt
widgets in `desktop/wizard.py` hold no decisions — the flow lives
in the Qt-free `desktop/wizard_logic.py` (`WizardFlow`) over the
same client layer, extended with typed write roads (backend-profile
create/update/delete + write-only secret set, character create,
library card import, chat create/pin/messages, user-name get/set,
composed-turn SSE collection). The wizard is shown on detected
first run by the app entry (`MainWindow(auto_wizard=True)`) and is
reachable any time from File → First-Run Setup…; completion lands
the main window in the greeted chat the wizard opened. Backend
health is always rendered as plain words, never raw JSON, and the
Demo (`fake`) backend is labelled as a canned responder everywhere
it appears. Slice contract and evidence:
`docs/DESKTOP_WIZARD_R05_2026-11-14.md`.

R-06 adds Chat Stage I on the same boundaries: the centre stage
streams a composed turn through the Qt-free
`desktop/chat_logic.py` (`ChatFlow`) over the client layer —
the user's line is persisted first so server-side composition
includes it, the reply streams in live (client
`stream_composed` + `workers.run_stream`), and the reply is
landed only on a clean finish, the bridge's discipline; Stop
cancels by request id through the engine's cancel road. The
Chats dock manages chats (open/new with a character picker —
the engine seeds the greeting — rename, confirmed delete,
portable export), and the Session dock resolves the open chat's
character, persona (R-03 road), pinned backend profile, model,
and preset from live API data, in words, with unpinned and
dangling states named honestly rather than filled in. Slice
contract and evidence: `docs/DESKTOP_CHAT_STAGE_R06_2026-11-14.md`.

R-07 completes the Chat Stage on the same boundaries: the full
action surface (per-message edit/delete/swipes/branch/pin/copy,
regenerate, continue, impersonate, Author's Note, chat search,
checkpoints + undo surfacing) runs through `chat_logic.ChatFlow`
over new typed client roads for the engine's existing chats
routes — no new engine routes. Regenerate, which has no engine
route, is composed in the flow: the last reply is set aside via
its journaled delete so the composed prompt matches the original
turn's, a fresh reply streams and lands only on a clean finish,
and any other ending restores the old reply (undo journal first,
re-append fallback). Pin state is verified by re-reading the
pinned list, and transcript rows state pin/swipe position in
words. Slice contract and evidence:
`docs/DESKTOP_CHAT_STAGE_R07_2026-11-14.md`.

R-08 adds the Characters library + full card editor on the same
boundaries: the Characters dock tab is the library (search, tag
census filter, favourites, over the P-024 library roads) and the
five-tab editor dialog covers every card field, the greetings
deck, avatar/assets, character-book + lorebook binding, and
version history with restore — through the Qt-free
`desktop/character_logic.py` (`CharacterFlow`) over new typed
client roads for the existing characters/library/assets routes,
no new engine routes. Three roads are composed in the flow and
documented in the slice doc: the full card is read by joining
the summary row with the version road's stored card, a version
restore PATCHes that stored card back, and export serialises
the stored card — because no card-read/export/restore-version
route exists. Card edits overlay onto the stored dict at its
own field level (wrapped `data` or flat), so unknown fields
survive (INV-009); tags save through the organisation road,
which keeps tag rows and the card's tag list in step. Slice
contract and evidence:
`docs/DESKTOP_CHARACTERS_R08_2026-11-14.md`.
