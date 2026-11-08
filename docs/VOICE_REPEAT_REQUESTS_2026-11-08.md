# P-108 - Voice Repeat-Request Signal (Part VII)

Derived scope, stated plainly: the governing roadmap
gives Part VII only its part line - "VII | Voice, the
Voxta Way | P-101 - P-116" - and no per-slice entries.
P-108 is DERIVED, not roadmap-verbatim, from in-tree
sources only: census row VX-11 (mishearing is handled,
not hidden - characters can detect misheard words and
ask the user to repeat), P-105's slice doc section 4,
P-106's design and P-107's design. The keeper reviews
this derived scope at banking.

Clean-room line: built entirely from Rúnmál's own
in-tree contracts - the P-105 mishearing truth layer,
the P-101 session citizen, the P-105 voice JSON-store
house pattern and its owner-scoping router rule - with
no outside source read and no file downloaded (see the
P-108 entry appended to docs/CLEAN_ROOM_LOG_2026-10-30.md).

Base: fc4ea07 (P-105 banking record). Migration head:
0041. No migration taken.

## 1. The gap, exactly

VX-11 has been built in halves, each honest about what
it is: P-105 detection (per-word confidence persisted;
needs_repeat as data), P-106 the receipt (the mark in
projected provenance and status), P-107 the rendering
(confidence markings in the founding web thread). The
remaining named half is "ask the user to repeat", and
it splits in two:

- The CHARACTER half - a character speaks the ask inside
  the dialogue. It stays open, for the reason every
  prior Part VII slice recorded: the live responder is
  P-102's honest-unavailable seam, and fabricating a
  repeat request would cross it. This slice fabricates
  no dialogue.
- The HOST half - something outside the dialogue learns
  that a repeat is needed and decides what to do. This
  half was missing entirely: P-105's mishearings view
  recomputes detection statelessly on every read, so
  there was no request a host could poll, no record that
  a host already acted, and no protection against two
  hosts (the web UI, a live host, a companion driver)
  asking the user twice.

P-108 builds the host half, as a signal.

The other named open items were weighed and NOT taken
(full weighing in hidden_files/P108_SCOUT.md):

- VX-12 (affects/prosody): verified fresh - VoiceInfo
  carries no affect field and no TTS backend consumes
  one; a build needs an engine design across the
  registry, larger than one slice, and a scoping-only
  paper slice was declined (every Part VII slice has
  shipped runnable truth with a battery).
- VX-13 (narrator voice): verified fresh - no narration
  or narrator surface exists in chats or voice; there
  is no taxonomy consumer for a narrator voice to read.
- L3 (P-091 TTS/STT plugin citizens unregistered in the
  running app): deliberate host-explicit law in P-091,
  re-affirmed by P-102 through P-105. No new evidence
  overturns it; this slice does not reopen it.
- The live responder seam: the injection seam already
  exists complete (live.py: responder injection +
  honest unavailable/injected wiring record); what is
  missing is the real generation bridge behind it - a
  cross-subsystem build larger than one slice. No part
  taken: wiring a plug with nothing honest behind it
  would be a hollow slice.
- P-104's by-design items (in-process hosts call the
  service function; live start does not back-project):
  stated design with working catch-up roads, not
  defects.
- P-107's limitations: the voice_marking data already
  rides both thread API surfaces (other clients render
  it or not - their wiring, not a missing surface);
  streaming/in-flight marking would claim evidence that
  does not exist yet; already-projected turns not being
  back-marked is P-106's P-075 production-receipt law.

## 2. What landed

- src/runmal/voice/repeat_requests.py (new) - the pure
  derivation + the acknowledgement store:
  - turn_repeat_request(turn, pairs, ack): one turn's
    request or None. A turn is a request exactly when
    P-105's turn_mishearing says needs_repeat - the
    single truth source; the threshold and bands are
    imported, never redeclared.
  - session_repeat_requests(session, pairs, store): the
    session signal view {session_id, chat_id, threshold,
    has_pending, pending_count, acknowledged_count,
    pending_turns, requests} - requests in turn order,
    acknowledged ones included (the record that a host
    acted is the point).
  - AcknowledgementStore: the host handling record, a
    versioned JSON document (voice_repeat_acknowledge-
    ments.json) in the voice house pattern. Load is
    tolerant (missing = empty, corrupt = empty,
    malformed entries skipped). acknowledge is
    idempotent - first acknowledgement wins, so the
    receipt names when a host FIRST acted and a second
    host's call changes nothing. clear removes a record
    and reports whether one existed.
- src/runmal/voice/repeat_router.py (new) - the HTTP
  surface on the founding /api/v1/voice road, wired in
  app.py, owner-scoped exactly like P-105's router
  (unknown or foreign session answers 404; existence
  never leaks):
  - GET /voice/sessions/{id}/repeat-requests - the
    session signal view, with the install-wide P-105
    replacement lexicon applied, as the mishearings
    road applies it.
  - POST /voice/sessions/{id}/repeat-requests/{turn_no}/
    acknowledge {note?} - the session view after the
    acknowledgement. A turn that is not a repeat request
    (no such turn, no evidence, or all-confident)
    answers 422: a host cannot acknowledge a request
    that does not exist. Re-acknowledging a handled
    request is idempotent 200.
  - DELETE .../acknowledge - {removed, ...session view};
    an absent record is removed: false, not an error
    (the P-105 housekeeping pattern).
- src/runmal/voice/__init__.py - one module-map entry.
- Battery: tests/test_p108_voice_repeat_requests.py
  (15 tests; see section 5).

## 3. Laws held

- Signal is data, not dialogue: no chat message is
  created by any road in this slice (pinned by a
  battery test that reads the chat's messages before
  and after the whole flow), no responder is wired or
  called, no text is generated. A host MAY act on the
  signal through its own surface; Rúnmál does not speak
  for it.
- One truth source: P-105 turn_mishearing. The signal
  cannot disagree with P-105's view, P-106's receipt or
  P-107's rendering (pinned by an agreement test against
  session_mishearing).
- No evidence is not a request: a turn with no recorded
  words never appears - the signal never invents doubt.
- Acknowledgement is handling, not truth: detection is
  recomputed from the evidence on every read; handling
  never changes it (pinned), and clearing an acknowl-
  edgement returns the request to pending with the
  truth untouched.
- Content law unchanged: the stored transcript is never
  rewritten; the suggested text rides as a view only.
- No migration, no new DB state: one JSON document in
  the voice house pattern, like the P-105 lexicon.

## 4. Honest limitations

- No character asks for a repeat in this slice: the
  dialogue half of VX-11's ask stays open on the P-102
  responder seam, exactly where P-105, P-106 and P-107
  left it. What lands is the signal a host - or a
  future responder host - acts on.
- The signal is poll-based: a host reads the road (for
  example after recording a turn). No push or event is
  emitted - the Plugin API v1 event vocabulary stays
  closed and no event name is invented.
- Acknowledgements are install-wide records keyed by
  session (the P-105 lexicon stance), not per-host: two
  hosts sharing one install share one handling record -
  which is precisely the do-not-ask-twice protection,
  stated plainly.
- The acknowledgement note is host bookkeeping (who or
  how it was handled), stored verbatim; it is never
  rendered as dialogue and never landed in a chat.
- Requests derive from turns still in the session
  store; a deleted session's acknowledgements become
  inert records - they name a session that no longer
  exists and drive nothing.
- Footprint overlap for banking reconciliation: P-106
  (banks first) works in projection.py; P-107 (banks
  second) adds markings.py and touches chats/router.py
  and the web statics. This slice's only shared-file
  touches are additive blocks in app.py and one entry
  in voice/__init__.py; the substantive surfaces do not
  overlap (P-107 renders landed chat history; P-108
  signals from the session store).

## 5. Battery

tests/test_p108_voice_repeat_requests.py - 15 tests:
the derivation (request exactly on needs_repeat, the
signal's agreement with P-105's own session view,
no-evidence and all-confident turns never requests,
the suggestion as a view with the transcript proven
untouched), the acknowledgement lifecycle (pending ->
acknowledged, first-acknowledgement-wins, clear returns
to pending, handling never changes detection), the
store (round-trip, tolerant load incl. malformed
entries, version pin), the HTTP roads (the full signal
flow with idempotent re-acknowledge and housekeeping
delete, the two 422 shapes, the no-chat-message pin
with the stored response proven empty, unknown +
foreign 404 on all three roads), and the 0041 migration
pin. Neighbour and full-suite counts are recorded from
the run logs in hidden_files/P108_EVIDENCE.md, never
estimated here.
