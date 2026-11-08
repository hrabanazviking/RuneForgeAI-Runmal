# P-144 - Global Binding Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131..P-142
precedents. The derivation rests on Runmal's own in-tree
record only (full weighing below; scout and design in the
team hidden record).

Base: bbdd8cc (P-142 banking record; P-001..P-142 banked).
P-143 (library-scoped pack import preview, team-01) is in
flight, banks ahead of this slice, and is NOT in this base;
its ground is the pack roads, which this slice neither
duplicates nor touches (this slice road lives in the
bindings block; no shared road segment). Migration: NONE -
head stays 0041. No storage shape changes: the census reads
the P-132 binding store and the P-131 definition store and
stores nothing.

## The weighing

- **Global stale/superseded binding census - taken.**
  P-142 named exactly this candidate in its weighing and
  in its CAMPAIGN_STATE record: "a global stale/superseded
  binding census - named as a future candidate, not built
  here." It deferred there only because a proven defect
  (F1) outranked it; F1 is closed, and no F-finding
  remains open (P-133 F2, the carried_shadowed naming,
  already lands in the stored-export report itself). The
  gap is mechanical, verified in code on this base: a
  binding outlives two things - its definition (delete
  never cascades, P-132 / P-135) and its pinned revision
  (replace never re-materialises, P-140) - yet P-135 list
  summaries carry the pinned revision and
  definition_exists with NO live revision anywhere, so
  supersession is unjudgeable from the only global binding
  surface, and P-140 pinned split is per-definition,
  inside a replace preview, before a replace. After
  replaces have landed, no road answered which of an
  owner bindings now pin a superseded revision, and
  which are stale, except walking every definition by
  hand. This slice is that answer: one pure read joining
  every binding to the live definition store.
- **Unbind-impact preview - declined.** P-142 weighing
  stands: the unbind road already answers its one fact
  with every unbind (the record goes, seeded content
  stays - P-132); a preview would restate it and add no
  knowledge.
- **Duplication preview - declined.** Duplication
  (P-137) is non-destructive: it creates a fresh citizen,
  orphans nothing, supersedes nothing, and carries no
  binding or organisation row. No record names a risk
  needing inspection before it.
- **Organisation orphan census / cleanup - declined.**
  Orphan organisation rows are filtered at every read
  (P-134) and P-139 already names the row per definition
  before the deletion that orphans it; no record names a
  consumer for a global orphan list, and cross-store
  cleanup remains declined standing law (independent
  stores; orphans are named, not deleted).
- **Pack lifecycle depth - not available.** Taken by
  concurrent P-143 (library-scoped pack import preview);
  P-141 inspect is stateless by design. Not duplicated.
- **Bind-plan vs actual-bind reconciliation - declined.**
  Standing evidence: the binding record already IS the
  account of what landed, and P-138 battery pins the
  prospective reconciliation.
- **Definition history retention - declined.** Tenth
  declination, evidence unchanged: no named consumer,
  and retention would be a storage-shape change.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  This slice evaluates nothing and runs nothing.

## What landed

- `src/runmal/scenarios/bindingcensus.py` (new) - the
  census service. `census_bindings(bindings, owner_id,
  definitions)` reads rows through P-135 own
  `list_bindings` verb, so every row is a P-135 summary
  verbatim, enriched only with `current_revision` and
  `current_name` (the live record facts, None when the
  definition is gone) and `state`, under a four-state
  law: stale (definition gone), current (pinned ==
  live), superseded (pinned < live), ahead (pinned >
  live - impossible by construction, since a bind pins
  the then-current revision and a replace only moves it
  up; counted anyway so a hand-damaged store is named,
  never hidden - the P-140 pinned_newer precedent).
  `by_definition` rolls the same rows up per definition
  in first-binding order (a stale group names itself
  with the pinned name the bindings carry and
  current_revision None), and every census count -
  the four states, chats affected, definitions
  referenced and definitions carrying current /
  superseded / stale bindings - is summed from the
  rows and groups themselves, so the census cannot
  drift from its own evidence. Five standing notes
  state the bounds in every answer.
- `src/runmal/scenarios/router.py` (additive) - one
  road: GET /scenarios/bindings/census, declared
  immediately after GET /scenarios/bindings and before
  GET /scenarios/bindings/{chat_id}, so the literal
  "census" is never read as a chat id (the P-134 /
  P-135 declaration-order precedent; battery-pinned by
  a census-vs-chat-read contrast). It has no 404 case:
  an owner with no bindings answers the honest zero
  census.
- `src/runmal/scenarios/__init__.py` (additive) - one
  subsystem-map line plus `census_bindings` and
  `BINDING_STATES` exports.
- `tests/test_p144_binding_census.py` - the battery
  (18 tests; see Evidence).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one appended
  entry.

No new store, no write of any kind: the census is a
join of two standing reads and stores nothing.

## Honest bounds

- A census, not a cleanup: nothing is unbound, deleted
  or repaired. Stale bindings remain until unbound per
  chat; ahead rows are named, not fixed.
- The census judges bindings against the definition
  store only. It judges no chat liveness: a binding
  whose chat was deleted is classified by its
  definition facts alone, because the binding store
  carries no chat-liveness fact and none is fabricated.
  The notes say so in every answer.
- Summaries are counts, not content (P-135 law stands):
  seeded message texts, cast bodies and skipped reasons
  stay on the P-132 single-read road.
- current_name / current_revision are the live record
  facts at read time; the pinned facts stay on the row
  beside them, so drift is visible, never merged away.
  A renamed definition therefore shows its live name in
  current_name (and as its group name) beside the
  pinned definition_name the binding was bound under.
- No filters, sorts or paging: bind order, the whole
  owner set - the P-135 bounded-surface precedent; no
  record names a consumer needing more.
- chats_affected equals bindings_total by construction
  (P-132: a chat carries at most one binding); it is
  stated as read from the rows, not assumed.
