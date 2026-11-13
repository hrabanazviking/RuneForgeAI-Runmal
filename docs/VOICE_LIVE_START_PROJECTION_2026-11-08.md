# P-112 - Voice Live-Start Back-Projection (Part VII)

## Derivation statement (binding honesty)
The governing roadmap gives Part VII only its part line -
VII | Voice, the Voxta Way | P-101..P-116 - and no per-slice
entries. This scope is DERIVED, not roadmap verbatim, from
in-tree sources only: P-104's slice doc
(docs/VOICE_AUTO_PROJECTION_2026-11-07.md) section 4, which
records the limitation verbatim - "Live start does not
back-project pre-existing turns; the next speak/stop - or
the manual P-103 road - catches up, because every projection
pass consumes the whole session." P-112 closes exactly that
recorded limitation, nothing else. The keeper reviews this
derived scope at banking. Base ff48970 (P-110 banking
record). Migration: NONE.

## 1. The gap, exactly
Four roads can move a session's recorded turns toward its
chat: the P-103 manual projection road, and P-104's three
auto-projection wirings (manual turns POST, live speak,
live stop). Live start - the fourth live road - never
walked the service. An opted-in session with pre-existing
unprojected turns (recorded by hand through the P-101
road, or left pending by an earlier failure) went live
with those turns still absent from its chat, landing only
if a later speak or stop happened to catch up.

## 2. What lands
- live_router.py (start road extended): POST
  /voice/sessions/{id}/live/start gains the db dependency
  the speak/stop roads already carry and, after
  controller.start succeeds, walks the module's existing
  shared helper _maybe_autoproject - the identical call
  the speak road makes. The report rides on the response
  only when a projection was attempted, under the same
  additive key auto_projection. A failed start (409
  stopped / already live, 503 wiring refusal) projects
  nothing: the call sits strictly after a successful start.
- autoproject.py: docstring road list names live start
  (no code change - the service is already whole-session
  and idempotent).
- Battery tests/test_p112_voice_live_start_projection.py
  (11 tests).

## 3. Laws held
- The controller stays synchronous and DB-free (P-102 /
  P-104 design law): back-projection lives in the async
  HTTP host layer where P-104 put all projection timing.
  In-process hosts are unchanged and pinned as such.
- One landing road only: P-103's project_session_turns
  through P-104's autoproject_session. No new content is
  created - the service lands the turns' own recorded
  heard text; no-content turns are counted, never landed.
- Opt-in law unchanged: default-off and nothing-pending
  sessions return the exact P-102 start shape.
- Failure is in-band: a projection failure reports
  ok False + error on a start that stays live; the manual
  P-103 road can always retry (idempotent, resumable).
- No migration, no new store, no new persisted shape.

## 4. Honest limitations
- HTTP road only: an in-process LiveVoiceController.start
  does not back-project - it cannot, being DB-free by
  design. The catch-up point exists where a DB session
  exists: the HTTP host.
- Back-projection covers turns pending at start; later
  turns land through the standing speak/stop/manual roads.
- The character-asks half of VX-11 (P-102 responder seam),
  VX-12's engine half, VX-13 and L3 (deliberate
  host-explicit registration) stay open exactly where
  P-110 and P-111 left them. Items weighed and not taken
  are recorded in full in the scout
  (hidden_files/P112_SCOUT.md).

## 5. Battery
tests/test_p112_voice_live_start_projection.py - 11 tests:
back-projection lands pre-existing turns under the heard
law with provenance, idempotency across start/stop, the
no-content accounting, the shape law (default-off and
nothing-pending unchanged, unknown session 404), failure
honesty (failed start projects nothing, double start
conflicts cleanly, projection failure in-band with the
start live and the turn retryable), the DB-free controller
pin, and the 0041 migration pin. Neighbour and full-suite
counts are recorded from the run logs in
hidden_files/P112_EVIDENCE.md, never estimated here.
