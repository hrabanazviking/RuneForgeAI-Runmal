# P-138 - Chat-Scoped Bind Preview (Part IX, eighth slice)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131 / P-132 / P-133 / P-134 / P-135 / P-136 /
P-137 precedents. The derivation rests on Runmal's own
in-tree record only (full weighing in the team's scout
record).

Base: d93521f (P-136 banking record; P-001..P-136
banked). P-137 (Definition Duplication) banks ahead of
this slice from base 5a210f6 and is NOT in this base;
this delta is additive against it (new service module,
one additive router road, additive __init__ exports).
Migration: NONE - head stays 0041. No storage shape
changes: the preview reads a P-131 record, a Chat row,
the binding store, the chat history and the P-093
store, and stores nothing.

## The weighing

- **Chat-scoped bind preview - taken.** P-136's
  preview is definition-side only, and its four
  standing notes - present in every answer - bound
  exactly what it cannot promise: bind-time refusals
  "are decided by bind against a specific chat" (the
  preview names no chat at all), and already-present
  skips are "knowable only at bind time". Measured
  on this base, POST bind is the only road that
  reveals the group-room / already-bound / non-empty
  verdicts or the already-present skips - by refusing
  (409) or by writing (201, and unbinding never
  takes seeded content back). P-137's scout weighed
  this exact candidate ("chat-scoped bind preview -
  judging P-136's four unjudged bounds against a
  specific chat"), declined it for P-137, and named
  it a future candidate; its two grounds have lapsed
  or been answered in-tree: P-136 is banked in this
  base (no mid-flight refactor - this slice touches
  bind_scenario not at all), and the preview is not
  a second judge: it reports the facts bind judges
  by, each read through the same law bind reads it
  through (the Chat row, get_for_chat, get_history,
  and P-093's own resolve_key + get_entry pair - the
  exact calls seed_variables makes), while the plan
  itself is P-136's preview verbatim. Bind remains
  the only road that refuses or writes.
- **Bind-plan vs actual-bind reconciliation -
  declined.** The binding record already IS the
  account of what landed, exposed in full by
  P-132's single-read road and in summary by
  P-135; the only comparison a new road could add
  is against a plan, and the bind-time plan is
  recoverable only while the definition's current
  revision still equals the pinned one - after a
  replace it is gone (history retention, declined).
  A road exact sometimes and misleading the rest is
  weaker than this slice's prospective accounting.
  Named as a future candidate.
- **Definition delete-impact preview - declined.**
  The consequences of a DELETE are real but already
  named at every surface they touch (P-135's
  definition_exists, P-134's orphan filtering, the
  per-chat unbind road), and no record names a
  missing aggregate surface; the taken candidate is
  named twice in-tree and this one is not. Named
  as a future candidate.
- **A duplicate's organisation / binding honesty
  surfaces - declined.** P-137 is concurrent, not
  in this base; its no-carry bounds are already
  battery-pinned there. Building on an unbanked
  delta would contradict the additive banking law.
- **Definition history retention - declined.**
  P-131 already landed the revision discipline
  that transfers; no in-tree record names a
  consumer, and retention would be a storage-shape
  change (sixth declination, evidence unchanged).
- **Organisation orphan cleanup / cross-store
  cascade - declined.** P-134 claims no cleanup
  road and names orphan rows the honest cost of
  independent stores; P-135 names binding staleness
  instead of deleting anything. No record asks for
  deletion semantics across stores.
- **Collections / folders - declined.** P-134's
  honest bound ("No collections or folders"); no
  named need.
- **P-026 stateless raw-overlay leak (P-133 finding
  F1) - declined, carried unchanged.** Banked P-026
  behaviour pinned by its own battery (INV-009 raw
  overlay); changing the overlay law is a P-026
  slice's call. This slice neither rewrites nor
  inherits it: the plan is P-136's, computed from
  the stored definition by P-132's own pure
  function, exactly as bind computes it.
- **Portable-archive inclusion of the scenario
  stores - declined for this slice.** The archive
  is a SQL-row bundle; the scenario stores are
  data-dir JSON documents by P-131 design - a
  portable-subsystem slice, named open for that
  line, not a Part IX foundation.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never
  code. The preview evaluates no condition and
  runs nothing.

## What landed

- `src/runmal/scenarios/chatpreview.py` (new) - the
  chat-scoped preview service.
  `preview_bind_for_chat(session, record, owner_id,
  chat_id, ...)` returns None for an unknown or
  foreign chat (the two answer exactly alike), else
  the envelope: P-136's definition four (id, name,
  CURRENT revision, source format), chat_id, the
  plan (P-136's preview_bind_plan over the stored
  definition, verbatim), counts read from the plan
  itself, the blocker facts in bind's decision
  order (group_room; already_bound, naming the
  standing binding's id and definition;
  chat_not_empty, with its message count - every
  applicable blocker listed), would_bind (true
  exactly when no blocker stands), the seedable
  keys split by P-093's own presence law into
  would_seed full keys and already_present entries
  in the binding record's own skipped shape (where,
  key_or_index, full key, bind's own reason), and
  four standing honesty notes in fixed order. Pure
  read: no store, chat, variable or file is written.
- `src/runmal/scenarios/router.py` (additive) - one
  road: GET /scenarios/{definition_id}/bind-plan/
  {chat_id} answering the envelope. The definition
  is fetched owner-scoped first (unknown or foreign
  answers 404 "scenario definition not found", the
  P-131 no-leak discipline); a chat the service
  cannot see answers 404 "chat not found" (bind's
  own detail for chats). Session dependency, like
  the bind road. No body, no query parameters, no
  writes.
- `src/runmal/scenarios/__init__.py` (additive) -
  the preview_bind_for_chat name exported in the
  house style, plus one subsystem-map line.
- `tests/test_p138_chat_scoped_bind_preview.py` -
  the battery (16 tests; see Evidence).

## Honest bounds

- The preview judges the named chat as it stands at
  preview time. A chat that gains a message, a
  binding or a variable key before bind runs
  changes the outcome; bind re-decides every fact
  when it runs, and would_bind is never a promise.
- Blockers are reported, never acted on: the road
  refuses nothing (only existence answers 404),
  and listing every applicable blocker is a
  reporting choice - bind's own first-refusal
  order remains its writing law, untouched.
- Already-present is judged under the scenario
  writer by the P-093 store's own presence law -
  the same lens seed_variables uses - so a key held
  under the shared namespace by any writer counts
  as present, exactly as it would at bind time.
  The battery pins preview == bind on a real chat:
  the record's landed keys are the preview's
  would_seed set, and its already-present skips are
  the preview's already_present set.
- The plan is computed from the definition's
  CURRENT revision, which the envelope names; bind
  pins whatever revision is current when it runs.
- There is no playback in this slice, and none is
  claimed.
