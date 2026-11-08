# P-103 - Voice Turn Projection (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line - "VII |
Voice, the Voxta Way | P-101 - P-116" - and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: P-101's slice
doc (its section 5 honest limitations), P-102's derivation
statement and section 5, the Voxta census (VX-09 the
real-time core loop; VX-65 the per-chat inspector), and the
founding seams as they stand. P-101 named L1 (no live
orchestrator wired), L2 (session turns not projected into
chat messages), L3 (P-091 citizens unregistered). P-102
took L1 and said plainly: "L2 has nothing to project until
live turns exist." Live turns now exist. P-103 takes L2.
L3 remains open BY DESIGN: P-091 states registration is
deliberately host-explicit, and P-102's scout judged it a
law, not a defect; this slice does not reopen it.
The keeper reviews this derived scope at banking.

Base: 0e24e32 (P-102 banking record; P-101 + P-102 in base).
Migration: NONE - head stays 0041 (see section 4).

## 1. What landed

- src/runmal/voice/session.py - VoiceTurnRecord gains the
  durable projection state: projected (bool),
  projected_user_message_id, projected_assistant_message_id,
  projected_at. from_dict is tolerant (a pre-P-103 stored
  turn loads unprojected); to_dict round-trips.
- src/runmal/voice/projection.py (new) - the projection
  road: pure provenance builders + turn planner, the
  per-session status view, and the async service
  project_session_turns.
- src/runmal/voice/projection_router.py (new) - the HTTP
  surface (section 3), included by app.py on the founding
  road; voice/router.py and live_router.py untouched.
- src/runmal/app.py - one import + one include block.
- src/runmal/voice/__init__.py - one docstring line.
- Battery: tests/test_p103_voice_projection.py (19 tests).

## 2. The landing law

Per recorded turn, in turn order, through the one append
road (chats.service.append_message, with its P-076 undo
journal and message.created dispatch):

- transcript_text non-blank -> ONE user message, content
  exactly the transcript.
- history_text() non-empty -> ONE assistant message,
  content exactly history_text(): the S508 heard split as
  history may claim it - certain text plus the explicit
  uncertainty marker. Unplayed text NEVER lands; the full
  response_text stays in the session store only.
- An error turn with no heard text lands no assistant
  message (the error remains on the session record); a
  turn with neither side lands nothing and is counted
  no_content. Nothing is fabricated to fill a turn.

Provenance (P-075, under the P-089 closed-vocabulary
doctrine): origin kind stays "manual" - no new kind is
forged. Scalar origin facts name the road: via
"voice_session", voice_session_id, voice_turn_no,
voice_side ("transcript" | "response"), and the side's own
facts (stt_backend + transcript_language; tts_backend +
voice_id + heard-span char counts + interrupted). Model:
not_applicable for the transcript (the user's own words;
the STT fact lives in origin facts), unknown for the
response - the persisted turn holds no generation model,
so the record carries the gap, never an invented model.
Preset unknown (the voice road never resolved one); lore
not_applicable. Speaker: the session's user for the
transcript; the session's character for the response, its
name resolved from the character row when one exists.

Idempotency: a projected turn is skipped whole; a
half-projected turn (one side landed, then a failure)
resumes with only the missing side - the landed side's
message id is already on the turn. The session store is
saved after every turn, so progress is durable turn by
turn and a fresh store load projects nothing twice.
Ownership: the service refuses a session whose user_id
differs from the requesting owner (ProjectionError) and
raises KeyError for a missing/foreign chat; the router
maps both to 404 - existence never leaks (the P-101 rule).
Active and stopped sessions both project: stopped is
history, and projecting history is the point. Turns from
every recording road (manual /turns posts, P-102 live)
project the same way - projection consumes the store.

## 3. HTTP surface (founding road, bearer-gated)

- POST /api/v1/voice/sessions/{id}/project -> 201, the
  projection report: {session_id, chat_id, projected_turns,
  already_projected, no_content_turns, messages_created,
  turns: [{turn_no, outcome, user_message_id,
  assistant_message_id}]} with outcome one of projected /
  already_projected / no_content.
- GET /api/v1/voice/sessions/{id}/projection -> the
  per-turn projection status (turns_total, turns_projected,
  messages_projected, per-turn ids + projected_at).
- Unknown session 404 on both; a session owned by someone
  else is also 404 (never a leak), as is a session whose
  chat is gone. The store resolves per request exactly
  like the P-101 session routes.

## 4. Honesty rules

- The session store stays the truth record. Projected
  messages are its transcript shadow, linked by message
  id on the turn; editing or deleting a projected message
  never writes back to the session record (the link id
  may dangle after a delete - stated, not hidden).
- Only heard text lands for the response. A response the
  user never heard (all chunks unplayed) contributes NO
  assistant message, however complete its text is in the
  store - INV-020 carried into the transcript itself.
- No fabricated producer: where the turn record holds no
  fact (the responder's model above all), the provenance
  record carries the explicit gap.
- Migration head stays 0041: projection state is voice
  JSON-store data, and projected messages use the
  existing messages.provenance_json column (0040). The
  battery pins the head.

## 5. Honest limitations

- Projection is EXPLICIT, not automatic. The P-102 live
  controller is synchronous and DB-free by design, so no
  auto-projection hook is wired into its persist road; a
  host (or the HTTP road) projects after turns complete.
  An async auto-projecting host is a later slice's design.
- Projected messages are ordinary messages afterwards:
  swipes, edits, branches and deletes act on the message,
  never back on the session record (see section 4).
- One projection pass appends through append_message per
  side, so each projected side is its own undo journal
  entry (P-076) - projection is undoable side by side,
  like any append, never as one atomic turn-pair.
- L3 (P-091 citizen registration) remains open exactly
  as P-101/P-102 left it: deliberate host-explicit law.

## 6. Battery

tests/test_p103_voice_projection.py - 19 tests: the
planner (both sides, uncertainty marker + unplayed
exclusion, unplayed-only, error + empty turns, resume
omits landed sides), provenance (transcript facts,
response honest gaps, tolerant-reader round trip, turn
projection-field round trip incl. the legacy stored
shape), the service (ordered landing with provenance
asserted on stored messages, idempotent second run incl.
across a store reload, half-projected resume, error /
empty / unplayed accounting, stopped-session history,
ownership refusals, character speaker resolution), the
HTTP flow (status before/after, report, chat history
landing, idempotent re-project, unknown + foreign 404),
and the 0041 migration pin. Neighbour and full-suite
counts are recorded from the run logs in
hidden_files/P103_EVIDENCE.md, never estimated here.
