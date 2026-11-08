# P-153 - Library Bind-Plan Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131..P-152
precedents. The derivation rests on Rúnmál's own in-tree
record only (full weighing below; scout and design in the
team hidden record).

Base: b5a8738 (P-151 banking record; P-001..P-151 banked).
P-152 (chat coverage census, team-01) banks ahead of this
slice and is NOT in this base by design; this slice neither
duplicates nor collides with it: P-152 adds
chatcoverage.py, a road appended at the router's end
(GET /scenarios/chats/census) and __init__ entries after
chatcensus, while this slice adds plancensus.py, a library
road (GET /scenarios/library/bind-plans) and __init__
entries after definitioncensus - disjoint hunk ground
everywhere, flagged for the keeper's banking
reconciliation. Migration: NONE - head stays 0041. No
storage shape changes: the census reads the P-131
definition store through P-136's own service and stores
nothing.

## The weighing

- **Library bind-plan census - taken.** The gap is
  mechanical, verified in code on this base. Every
  judgement Part IX computes has been joined across its
  library exactly once, except the bind plan: P-144
  censuses bindings against definitions, P-148 against
  chats, P-150 joins the two per binding, P-151 rows
  definitions by the custody of their bindings, P-152
  rows chats by their coverage, and P-145 joins the
  stored import reports. The plan - P-132's
  plan_materialisation as P-136's preview judges it for
  ONE stored definition - is reachable only one
  definition at a time, through the P-136 road alone.
  And the plan is a distinct computed judgement, not a
  restatement of any list shape: the P-131 summary counts
  EVERY bootstrap entry, including the blank and
  non-object entries the plan honestly skips, and counts
  no seedable flag or variable at all. What a definition
  would actually plant - its messages after the
  kind-to-role map, its seedable flags and variables
  under the P-093 seedability law, and every entry that
  law or the bootstrap law skips, with its reason -
  exists only inside per-definition P-136 envelopes. An
  owner choosing which definition to bind, or auditing a
  library for openings that would plant less than they
  declare, could learn each plan only by walking every
  definition by hand through the P-136 road - exactly
  the by-hand gap P-144's own derivation named as its
  justification, transposed to the plan axis, and the
  exact shape P-145 closed for reports ("reachable only
  one record at a time"). This slice is that answer: the
  owning service, P-136's preview_bind_plan, called
  verbatim per record over the caller's full definition
  list. The consumers are standing roads, not invented
  ones: bind (P-132) aims at one definition and one
  chat, and P-138 / P-147 judge a named pair - choosing
  the definition half of that pair is aimed from the
  library, and this census is the library's plan surface
  to choose from.
- **Wiring delete_chat to cascade the binding record -
  NOT taken, argued plainly.** The record has moved
  against taking it in a keeper slice, not towards it:
  P-149 weighed it at full length and reserved it
  expressly (a keeper slice does not take a reserved
  behaviour decision unilaterally; the decision is
  named Volmarr's to take), then pinned today's
  no-cascade behaviour in its battery; P-150, P-151 and
  P-152 declined it again on the same grounds. Taking it
  here would override three fresh, deliberate in-tree
  reservations with no new evidence. It stands open
  deliberately, for Volmarr's word - not for want of a
  census: P-148, P-149, P-150, P-151 and P-152 name every
  orphan it would remove.
- **Organisation orphan census / cleanup - declined,
  standing.** Orphan organisation rows are filtered at
  every read (P-134) and P-139 names the row per
  definition before the delete that orphans it. The
  deciding asymmetry against the P-148 precedent: an
  orphaned binding can be removed by the standing
  unbind road once named, while no road removes an
  orphan organisation row, so a global orphan list names
  what no consumer can act on. Censuses name, never
  repair; evidence unchanged.
- **Organisation facts folded into this census -
  declined for this slice.** P-134's own roads answer
  organisation per definition and per tag (including
  the library/tags census); no record names a gap on
  that axis, and folding a filing read into a plan
  census would blur both. This census is the plan.
- **Within-library duplicate-content census -
  declined, standing** (P-145 / P-147 / P-150 /
  P-151 / P-152): identity-by-checksum is P-141 /
  P-143 pack law; P-137 clones are honest citizens by
  design.
- **Export-readiness census - declined for this
  slice.** Its not_restored half IS P-145's census (the
  stored reports, already joined); the remaining half
  (carried_shadowed) is judged per requested format
  inside P-133's own envelope, and P-145's weighing
  stands: a preview of a pure read adds no knowledge.
  The plan census, by contrast, surfaces per-definition
  counts no envelope aggregates and no list carries.
- **Per-definition candidate-chat roster (the reverse
  of P-147) - declined for this slice.** P-152 now rows
  every chat with its coverage state and its binding's
  P-144 row verbatim, so the chat side of any pair is
  already readable library-wide; the missing half of
  the pair choice is the definition's plan, which is
  the taken scope.
- **Candidate create preview, unbind-impact preview,
  duplication preview, stored / pack export previews,
  rebind / refresh preview, definition history
  retention, collections / folders, general library
  status aggregate - declined, standing grounds
  unchanged** (see the P-142 / P-145 / P-148 / P-150 /
  P-151 / P-152 weighings; the aggregate in particular
  would restate banked envelopes, where this census
  surfaces plan counts and skip rows no envelope
  joins).
- **Portable-archive inclusion of the scenario
  stores - declined for this slice, standing:** a
  portable-subsystem line item, named open there in
  every weighing; a write-format change across three
  stores, not a scenarios read surface.
- **Playback / runtime / condition evaluation /
  scripting EXECUTION - declined ABSOLUTELY** (P-027
  law: stored content is data, never code).

## What landed

- `src/runmal/scenarios/plancensus.py` (new) - the
  census service. `census_bind_plans(definitions)`
  takes the caller's own records (the store's
  list_for_owner answer) and answers one row per
  definition, in the caller's list order - every
  definition rows, clean and empty included: the
  subject is the definition. Each record is judged by
  the owning service, P-136's `preview_bind_plan`,
  called verbatim; each row names its definition by
  P-131's summary() verbatim and carries the envelope's
  own counts (planned messages / flags / variables and
  their total), the plan's skipped rows verbatim (each
  naming only where, key_or_index and reason), and the
  definition's plan state under the plan law below.
  `by_where` rolls the skipped rows up per where in
  first-appearance order across the rows, and every
  count is summed from the rows themselves, so the
  census cannot drift from its own evidence (the P-144
  construction). Five standing notes state the bounds
  in every answer.
- The plan law (exactly one state per definition),
  read from P-136's own counts (planned = messages +
  flags + variables): `clean` - planned > 0 and
  skipped == 0; `partial` - planned > 0 and
  skipped > 0; `skips_only` - planned == 0 and
  skipped > 0 (every declared opening entry is
  honestly skipped, so a bind would plant nothing but
  the binding record itself); `empty` - planned == 0
  and skipped == 0 (no opening material declared at
  all). `BIND_PLAN_STATES` names the four in law
  order. No second planning law is invented: the
  counts and the skipped rows ARE P-136's.
- `src/runmal/scenarios/router.py` (additive) - one
  road: GET /scenarios/library/bind-plans, declared in
  the library block after the P-151 library census
  road and before the bindings block, so the literal
  "library" is never read as a definition id (the
  P-134 / P-145 / P-151 precedent; battery-pinned by
  contrast with the per-definition read and the P-136
  bind-plan road). It has no 404 case: an owner with
  no definitions answers the honest zero census.
- `src/runmal/scenarios/__init__.py` (additive) - a
  subsystem-map bullet after the definitioncensus
  bullet, plus the `BIND_PLAN_STATES` /
  `census_bind_plans` exports after the definitioncensus
  import and the `census_definitions` __all__ entries -
  disjoint blocks from P-152's chatcensus-anchored
  entries.
- `tests/test_p153_bind_plan_census.py` - the battery
  (19 tests; see Evidence).
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - one appended
  entry.

No new store, no write of any kind: the census is a
read of the P-131 records through P-136's own service
and stores nothing.

## Honest bounds

- The census is a pure read and judges plans only; it
  changes no write behaviour. The delete_chat cascade
  remains deliberately untaken (reserved for Volmarr,
  above), and every plan named here still requires the
  standing bind road to land.
- Definition-side only: no chat has been consulted,
  bind-time refusals are not judged, and no chat
  outcome is promised - P-136's own bound, inherited
  whole. The chat-scoped verdicts stay on P-138 /
  P-147, untouched beside it.
- Seedable, not landed: the plans name seedable keys,
  not landed keys. Keys a specific chat already holds
  seed nothing at bind time (P-093 missing-keys-only);
  that skip is knowable only at bind time, and the
  binding record remains the only account of what
  actually landed.
- The census carries counts and the plans' skipped
  rows only - no message text, no flag or variable
  value, and no seedable key is named (battery-pinned
  against the serialised census). The full plan stays
  on the P-136 per-definition bind-plan road.
- Each plan is computed from its definition's current
  revision; a replace re-plans, and the census judges
  the current body of the current revision and keeps
  no history.
- The P-152 union was NOT verified in this worktree
  (it cannot be: P-152 is absent from this base by
  design) - the keeper verifies it at banking with the
  combined batteries and the forge confirmation suite.
  This slice's no-regression claim rests on its own
  full suite's zero failures plus the neighbour fence
  on this base.
- No playback, runtime or execution of any stored
  content (P-027 law).

## Counts

- Battery: tests/test_p153_bind_plan_census.py - see
  hidden_files/P153_EVIDENCE.md for the counted runs
  (battery, neighbour fence, full suite), read from
  the log files.
- Migration: NONE (head stays 0041, battery-pinned).
