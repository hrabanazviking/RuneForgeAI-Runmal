# P-101 — Voice Sessions (Part VII, Voice the Voxta Way — opener)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII | Voice,
the Voxta Way | P-101 – P-116" — and no per-slice entries. This
slice's scope is therefore DERIVED, not roadmap-verbatim, from
in-tree sources only: the Voxta census (VX-04 voices are
character equipment, VX-09 the real-time core loop, VX-15
service slots, VX-65 the per-chat inspector), VOICE_ARCHITECTURE
sections 2/4/8, the founding S5xx voice seams, P-053's provider-
truth discipline, P-065's carried limitation ("the voice
orchestrator's turns are ephemeral TurnRecords: they are never
persisted as chat messages today... Persisting voice turns
themselves is a voice-campaign decision"), and P-091's stated
limitations (citizen voice state in memory only; no HTTP surface
for the citizens; the founding /api/v1/voice/* routes remain the
HTTP road). Part VII is that voice campaign; P-101 is its
foundation slice. The keeper reviews this derived scope at
banking.

Base: f722ffe (P-100 banking record). Migration: NONE — head
stays 0041 (see section 4).

## 1. What landed

One new module, one router extension, nothing else reshaped:

- src/runmal/voice/session.py — voice sessions bound to a chat.
- src/runmal/voice/router.py — six session routes appended on
  the founding road (section 3); every founding route untouched.
- src/runmal/voice/__init__.py — one docstring line for the new
  module (the subsystem map stays true).
- Battery: tests/test_p101_voice_sessions.py (28 tests).

## 2. The session citizen

A VoiceSession is bound to exactly one chat (chat_id, user_id,
character_id) and carries: a settings snapshot resolved once at
start, a lifecycle (active -> stopped; first stop wins, its
note and timestamp are history), and its completed turns.

Settings resolution (resolve_session_settings, pure):
- TTS from the character's S512 voice when the chat has one
  (selected_via "character"), else the user's defaults with the
  DEFAULT_VOICE identity (selected_via "default"). The ear is
  always the user's STT default — voice selection stays an
  independent modality.
- Provider truth as data (P-053 discipline): for each side,
  {backend, known, verified, admission (default-shipped /
  user-installed / unknown), selected_via, note}, built from
  the registries' own spec fields — imported, never copied, so
  the record cannot drift from the registry.
- A character voice naming an UNREGISTERED backend (a legacy
  removed engine, a hand-built value) falls back whole to the
  defaults, selected_via "fallback", with the refused backend
  NAMED in the note. It never raises and never resurrects a
  removed engine (the S512 law, enforced again at this layer
  because CharacterVoice values can be built by hand). The same
  guard covers a stored STT default that names no registered
  ear.

One active session per chat: starting a session stops the
chat's existing active session with stop_note "superseded".
"This chat's voice session" always has exactly one answer —
the inspectability the census's Inspector row (VX-65) presumes.

## 3. HTTP surface (founding road, bearer-gated like every API)

- POST /api/v1/voice/sessions {chat_id} -> 201, the session.
  The chat must exist AND belong to the owner: missing and
  foreign chats are both 404 (existence never leaks). Settings
  resolve through profiles.resolve_character_voice when the
  chat has a character.
- GET /api/v1/voice/sessions/{id} -> the full session incl.
  turns; GET /api/v1/voice/sessions?chat_id= -> summaries plus
  active_session_id (no chat_id: all summaries).
- POST /api/v1/voice/sessions/{id}/stop {note?} -> the session;
  re-stopping returns it as-is (first stop kept).
- POST /api/v1/voice/sessions/{id}/turns -> 201, the recorded
  turn. This is the persistence road a live host calls when an
  orchestrator turn completes. Stopped session -> 409;
  impossible chunk counts -> 422.
- DELETE /api/v1/voice/chats/{chat_id}/sessions -> {dropped}:
  the store's chat-deletion housekeeping road.

## 4. Turns persist — with playback truth

VoiceTurnRecord is the persisted form of the orchestrator's
ephemeral TurnRecord (VoiceSession.append_orchestrator_turn /
VoiceTurnRecord.from_orchestrator is the conversion road):
transcript (+ language, STT backend), response text, chunk
counts, interrupted/error, and the S508 heard split —
heard_certain / heard_uncertain / heard_unplayed. With ledger
evidence the split is copied from the HeardReconstruction.
WITHOUT evidence, nothing is claimed certain: the response is
uncertain when any chunk played, unplayed when none did
(INV-020 — no playback evidence, no heard claim).
history_text() reuses the ledger's own law: certain text plus
the explicit uncertainty marker; unplayed text never included.

Storage is the voice house pattern, not a migration: a
versioned JSON document (voice_sessions.json in the data dir,
the settings.py / S513 routing pattern) rewritten on every
mutation. Load is tolerant — missing file = empty store,
corrupt document = empty store, a malformed entry is skipped;
the store never bricks the voice surface. Sessions and turns
survive restart, bound to their chat. Migration head stays
0041; the battery pins it.

## 5. Honest limitations

- No live orchestrator is wired into the app process by this
  slice: sessions record COMPLETED turns through the explicit
  roads above; the live loop (capture -> orchestrator ->
  record) is a later Part VII slice's work, as are streaming
  and barge-in over HTTP, the narrator voice (VX-13), and
  affects (VX-12).
- Session turns are NOT projected into chat messages: the
  store record is the truth record. Whether and how a heard
  turn becomes a chat message is a later slice's design
  question (P-065's import_session_swipes bridge already lands
  generation candidates as messages by its own road).
- The P-091 plugin citizens remain unregistered in the running
  app, exactly as P-091 stated; this slice neither registers
  them nor changes their state model.
- The JSON store rewrites whole documents per mutation — the
  same trade the settings/route stores already make; session
  counts per install are small by design (one active + history
  per chat).

## 6. Battery

tests/test_p101_voice_sessions.py — 28 tests: resolver truth
(defaults / character wins / user-installed unverified /
named fallback for unknown TTS and STT / empty-voice fallback /
round-trip), turn truth (ledger-backed split, no-evidence
conservatism both ways, history_text law, round-trip), store
and lifecycle (reload persistence, corrupt/malformed tolerance,
supersede, record-after-stop refused, first-stop-wins, chunk
validation, drop_chat, orchestrator append), and HTTP (start
truth snapshot, missing/foreign chat 404, full flow with
persistence across a fresh client, 409/422 roads, supersede +
drop over HTTP, a seeded character-voice session, the 0041
migration pin, the founding /voice/status surface unchanged).
Neighbour and full-suite counts are recorded from the run logs
in hidden_files/P101_EVIDENCE.md, never estimated here.
