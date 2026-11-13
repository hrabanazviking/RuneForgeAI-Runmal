# P-104 — Voice Auto-Projection (Part VII, Voice the Voxta Way)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VII only its part line — "VII |
Voice, the Voxta Way | P-101 – P-116" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: P-103's slice
doc, whose section 5 states the limitation this slice takes,
verbatim in substance: "Projection is EXPLICIT, not
automatic. The P-102 live controller is synchronous and
DB-free by design, so no auto-projection hook is wired into
its persist road... An async auto-projecting host is a later
slice's design." P-104 is that later slice. The keeper
reviews this derived scope at banking.

The other named open items were weighed and NOT taken:
- L3 (P-091 TTS/STT plugin citizens unregistered in the
  running app): deliberate host-explicit law in P-091,
  re-affirmed by P-102 and P-103. No new evidence overturns
  it; this slice does not reopen it.
- Live hosts die with the process: P-102 already states the
  designed recovery — sessions and recorded turns persist
  in the P-101 store and a session can be started live again
  after a restart. Active-but-not-live is the citizen's
  normal resting state, not an anomaly.
- Census surface still unbuilt (VX-12 affects/prosody,
  VX-13 narrator voice, VX-11 mishearing handling): each
  needs its own truth-model or engine design (no affect
  seam exists in the TTS backends; the voice subsystem has
  no narrator citizen and chats have no narration taxonomy
  consumer; VoiceTurnRecord persists no confidence split
  and no replacement lexicon exists in-tree). Named here
  so the choice is auditable; all remain open.

Base: 7219996 (P-103 banking record, in the forge; the
remote build branch still read 0e24e32 when this slice
started because the P-103 push had not landed — the forge
head governed, per the keeper's instruction to reset to
the P-103 record when banking had landed). Migration:
NONE — head stays 0041.

## 1. What landed

- src/runmal/voice/session.py — VoiceSession gains the
  durable opt-in auto_project (bool, default False);
  summary/to_dict carry it, from_dict tolerates its
  absence (a pre-P-104 stored session loads OFF);
  start_session accepts it.
- src/runmal/voice/autoproject.py (new) — the async host:
  pending_turns / autoproject_status (pure views) and
  autoproject_session, which calls P-103's one projection
  service and NEVER raises (section 2).
- src/runmal/voice/autoproject_router.py (new) — the
  toggle + status HTTP roads (section 3), included by
  app.py on the founding road.
- src/runmal/voice/live.py — two additive read accessors
  on LiveVoiceController (session_for / store_for); no
  behaviour changes.
- src/runmal/voice/live_router.py — the speak and stop
  roads auto-project an opted-in session's pending turns;
  the controller stays synchronous and DB-free.
- src/runmal/voice/router.py — session start accepts
  {auto_project}; the manual /turns road auto-projects an
  opted-in session after the turn is saved.
- src/runmal/voice/__init__.py — one docstring line.
- Battery: tests/test_p104_voice_autoproject.py (17 tests).

## 2. The host law

- Opt-in, per session, default OFF. A session that never
  opted in behaves exactly as P-103 left it, on every road;
  response shapes gain the auto_projection report ONLY
  when a projection was attempted.
- Persistence precedes projection, always: a turn is
  recorded and saved first; only then does the host try to
  project. autoproject_session never raises — a failure
  (the chat is gone, the store write fails) returns
  {attempted: true, ok: false, error: "..."} in-band, the
  turn stays unprojected, and the manual P-103 road can
  retry because projection is idempotent and resumable.
- The landing is P-103's one service — same heard-text
  law (unplayed text never lands), same provenance, same
  per-turn durable progress. Auto-projection is a WHEN,
  not a second road.
- Disabled and nothing-pending are reported, not silent:
  {enabled: false, attempted: false, reason} / {attempted:
  false, reason: "no unprojected turns"}.

## 3. HTTP surface (founding road, bearer-gated)

- POST /api/v1/voice/sessions {chat_id, auto_project?} —
  the P-101 start road, one additive optional field.
- POST /api/v1/voice/sessions/{id}/auto-project {enabled}
  -> the status view {session_id, chat_id, auto_project,
  pending_turns, turns_total, turns_projected,
  messages_projected}. Missing enabled -> 422. Setting it
  on a LIVE session also updates the live host's session
  object, so the next live turn honours the toggle without
  restarting the host.
- GET /api/v1/voice/sessions/{id}/auto-projection -> the
  same status view.
- Unknown and foreign sessions are 404 on both new roads
  (the P-101/P-103 owner rule — existence never leaks).
- POST .../live/speak and .../live/stop: for an opted-in
  session the response gains auto_projection (the host
  report) when a projection was attempted. Stop is the
  catch-up road: turns recorded in-process through
  feed_frames (which has no HTTP road of its own) project
  as the session stops.
- POST .../sessions/{id}/turns (the P-101 manual road):
  same additive report for an opted-in session.

## 4. Honest limitations

- In-process hosts that drive LiveVoiceController directly
  (no HTTP) get the service function, not magic: they call
  autoproject_session after turns complete, exactly as the
  HTTP host does. The controller's synchronous, DB-free
  design (P-102) is preserved, not routed around.
- Live start does not back-project pre-existing turns; the
  next speak/stop — or the manual P-103 road — catches up,
  because every projection pass consumes the whole session.
- Toggling auto-projection on a session whose chat was
  deleted surfaces the projection failure in-band on the
  next recorded turn; it does not resurrect the chat, and
  the session record itself is untouched by the failure.
- L3 (P-091 citizen registration) remains open exactly as
  P-101/P-102/P-103 left it: deliberate host-explicit law.

## 5. Battery

tests/test_p104_voice_autoproject.py — 17 tests: the
citizen flag (default off, start opt-in, store round-trip,
legacy stored shape loads off), the pure views, the
service (disabled attempts nothing, no-pending reports its
reason, enabled projects under the full P-103 law incl.
the uncertainty marker and provenance, failure reported
never raised and the turn left retryable, no-content
accounting), the HTTP roads (start flag, toggle 422/404/
foreign-404, status view, manual-turn auto-projection,
default-off shape unchanged), the live wiring (speak
auto-projects a real citizen's turn into its chat, stop
catches up feed_frames turns after a live toggle, the
live host object is synced by the toggle, default-off
live speak carries no report), the controller accessors,
and the 0041 migration pin. Neighbour and full-suite
counts are recorded from the run logs in
hidden_files/P104_EVIDENCE.md, never estimated here.
