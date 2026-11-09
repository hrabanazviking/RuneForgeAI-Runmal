# P-158 - Face Selection History (Part X, Faces That Speak - DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part X only its part-table line -
"X | Faces That Speak | P-155 - P-168" - and no verbatim
P-158 entry exists anywhere in it. This scope is therefore
DERIVED, not roadmap-verbatim, from Runmal own in-tree record
only (full survey: hidden_files/P158_SCOUT.md; design:
hidden_files/P158_DESIGN.md):

- P-092 (plugins/expressions.py) records every selection in a
  kept history - each event with its provenance receipt
  (source, actor, reason, message id, the expression it
  replaced) and every clearing - and serves it through
  list_history, whose only in-tree consumer was the plugin
  own raw router road. No faces consumer existed.
- P-155 resolves only the CURRENT face for a chat and names
  its presentation document the contract a later Part X slice
  builds on. P-156 (per-character roster) and P-157 (face and
  voice pairing) take the character and pairing axes; the
  temporal axis - which faces a chat showed, in what order,
  why, and whether each would still render today - was
  entirely unbuilt. This slice is that axis.
- Precedent: P-155 (compose the owning surface verbatim,
  closed state law, fallbacks as data, five notes) and P-117
  (service + router + app wiring).

Base: cd740ee77e216dcf6fa4613f0b3d126351ab1192 (P-155 banking
record; PART X OPEN; P-001..P-155 banked). Migration: NONE -
head stays 0041, no 0042.

## What landed

New modules in src/runmal/faces/ - no store, no migration:

- history.py - resolve_face_history(session, user_id, chat_id,
  *, base_dir=None) -> dict | None, a pure read. None when the
  chat is missing or foreign (P-155 resolve law - existence
  never leaks). Otherwise it composes resolve_presentation
  VERBATIM (presentation_state and current ride whole) and
  P-092 list_history VERBATIM (rows ride whole, provenance
  included, newest first), and resolves the envelope (schema
  runmal-p158-face-history-v1):
  * events - one row per kept event, the P-092 row verbatim
    plus entry_state under the closed ENTRY_STATES law:
    still_ready (the named expression is declared in the
    chat CURRENT set and bound today), declared_unbound
    (declared today but not bound; problem_now carries the
    binding problem verbatim), no_longer_declared (the name
    is not in the current set; problem_now is P-155
    not_declared), cleared (a clearing event: expression
    None, descriptor None, problem_now None);
  * descriptor - the P-155 descriptor when the expression is
    still declared today, else None. A descriptor is TODAY
    truth about the name, never a claim about the past.
  * counts - event_count, selection_count, cleared_count,
    still_ready_count; kept_limit (P-092 MAX_HISTORY_KEPT
    verbatim) and at_kept_limit: the history is a KEPT
    WINDOW, never a complete record.
  * notes - five standing honesty notes in fixed order.
- history_router.py - GET /faces/history?chat_id= on the
  /api/v1 mount: 404 when resolve returns None, 200 the
  envelope otherwise (every presentation state is data at
  200, never an error).
- faces/__init__.py - subsystem map extended for the history
  surface (additive over P-155; P-156/P-157 add their own at
  banking).
- app.py - history router wired under /api/v1 with the
  local-auth dependency, after the faces router.
- tests/test_p158_face_history.py - battery (18 tests).

## Declined candidates (each with its reason)

- A client stage/renderer surface: a single-face stage
  re-wraps P-155, and the roster/speaking documents a stage
  would compose are not in this base. Named open after
  P-156/P-157 bank.
- Generated expression sprites via P-087: re-kinding is a
  P-087 contract change, not a faces read. Named open.
- Scenario VN stage integration: no record joins cast roles
  to characters or faces. Named open.
- Portrait animation / lip-sync: no timing, viseme or
  animation contract exists in-tree. Declined.
- Automatic expression detection from message text: declined
  ABSOLUTELY (P-092 standing law).
- Playback/scripting execution: declined ABSOLUTELY (P-027).
- An owner-wide face census: aggregates what P-156 names per
  character; the history axis was consumed by nothing and is
  the stronger slice. Named open.
- A new faces store / migration: P-092 store is the one truth
  for history; head stays 0041.

## Honest limitations

- Runmal renders nothing here; the history document is data a
  client reads and carries no image bytes.
- entry_state judges each kept name against TODAY set and
  bindings; history itself is never rewritten and a past face
  is never retroactively repaired.
- The kept window holds at most 100 events; at the limit,
  older events may already be dropped. This document never
  claims a complete record.
- The scope is DERIVED, not roadmap-verbatim. The keeper
  reviews this derived scope at banking.
