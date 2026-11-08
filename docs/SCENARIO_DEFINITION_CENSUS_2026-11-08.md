# P-151 - Library Definition Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-131..
P-150 precedents. The derivation rests on Runmal's own
in-tree record only (full weighing in the team's
scout/design record, hidden_files/P151_SCOUT.md and
P151_DESIGN.md).

Base: 0dde71b (P-148 banking record; P-001..P-148
banked). P-149 (chat delete-impact preview, team-01)
and P-150 (binding custody census, team-02) bank ahead
of this slice and are NOT in this base by design; this
slice neither duplicates nor touches their ground
(P-149's road is a per-chat bindings suffix, P-150's a
bindings census literal; this slice's road is a library
literal, and its __init__ entries sit after
reportcensus / census_unmappable, disjoint from both).
The keeper reconciles the additive union at banking
(P-149, then P-150, then P-151). Migration: NONE - head
stays 0041. No storage-shape change, no new store, and
no write-behaviour change anywhere.

## The weighing

- **Library definition census - taken.** Every census
  in the part rows bindings or report rows: P-144
  censuses bindings against the definition store,
  P-148 censuses bindings against the Chat table,
  P-150 joins the two per binding, and P-145 censuses
  the unmappable elements stored reports name. No
  census rows the definition store itself as its
  subject, and the gap is mechanical, verified in
  code on this base: the binding censuses build their
  per-definition groups from binding rows in
  first-binding order, so a definition with no
  bindings appears in NO census at all, and no road
  answers the library question - which of an owner's
  definitions are in use at all, which stand sound,
  which are bound only through drifted pins, which
  are bound only to chats that no longer exist -
  except walking every definition by hand through
  the P-135 per-definition bindings list (exactly the
  by-hand gap P-144's own derivation named as its
  justification, transposed to the definition axis).
  The consumers are standing roads, not invented
  ones: delete, replace, bind, duplicate and stored
  export all aim per definition, and an owner deciding
  what a library still needs - or what can go - needs
  the per-definition custody answer first. This slice
  is that answer: the two owning censuses composed
  over the caller's full definition list, aggregated
  per definition.
- **Wiring delete_chat to cascade the binding record -
  NOT taken, argued plainly.** The record has moved
  against taking it in a keeper slice, not towards
  it: P-149 weighed it at full length and reserved it
  expressly (a keeper slice does not take a reserved
  behaviour decision unilaterally; the decision is
  named Volmarr's to take), then pinned today's
  no-cascade behaviour in its battery; P-150 declined
  it again on the same grounds. Taking it here would
  override two fresh, deliberate in-tree reservations
  with no new evidence. It stands open deliberately,
  for Volmarr's word - not for want of a census:
  P-148, P-149, P-150 and this slice name every orphan
  it would remove.
- **Organisation orphan census / cleanup - declined,
  standing.** Orphan organisation rows are filtered
  at every read (P-134) and P-139 names the row per
  definition before the delete that orphans it. The
  deciding asymmetry against the P-148 precedent: an
  orphaned binding can be removed by the standing
  unbind road once named, while no road removes an
  orphan organisation row, so a global orphan list
  names what no consumer can act on. Censuses name,
  never repair; evidence unchanged.
- **Organisation facts folded into this census -
  declined for this slice.** P-134's own roads answer
  organisation per definition and per tag (including
  the library/tags census); no record names a gap on
  that axis, and folding a filing read into a custody
  census would blur both. This census is custody.
- **Within-library duplicate-content census -
  declined, standing** (P-145 / P-147 / P-150):
  identity-by-checksum is P-141 / P-143 pack law;
  P-137 clones are honest citizens by design.
- **Candidate create preview, unbind-impact preview,
  duplication preview, stored / pack export previews,
  rebind / refresh preview, definition history
  retention, collections / folders - declined,
  standing grounds unchanged** (see the P-148 /
  P-149 / P-150 weighings; nothing in the record has
  moved).
- **Portable-archive inclusion of the scenario
  stores - declined for this slice, standing:**
  portable/archive.py carries no scenario section
  (verified on this base), but every Part IX weighing
  names it a portable-subsystem line item, and it is
  a write-format change across three stores, not a
  scenarios read surface. Named open for that line.
- **P-133 finding F1 (stateless P-026 overlay leak) -
  not available to this slice:** banked P-026
  behaviour under its INV-009 law; P-133 rules
  changing it a P-026 slice's call.
- **Playback / runtime / condition evaluation /
  scripting EXECUTION - declined ABSOLUTELY** (P-027
  law: stored content is data, never code).

## The contract

- `src/runmal/scenarios/definitioncensus.py` (new) -
  the async read service. `census_definitions(session,
  bindings, owner_id, definitions)` composes the two
  owning services over the caller's own inputs:
  `census_bindings` (P-144) for the definition axis
  and `census_binding_chats` (P-148, the live id set
  built from the same definitions list exactly as its
  road builds it) for the chat axis. Joined rows are
  matched on the binding's own id, consumed in row
  order per id, so a hand-damaged store holding two
  rows that share an id still joins each chat verdict
  to one definition verdict in order.
- Per-binding custody conjunction - no third state
  law is invented; each verdict is a parent census's
  own: `sound` (current + live), `definition_drift`
  (superseded or ahead + live), `chat_orphaned`
  (current + orphaned), `doubly_broken` (drifted +
  orphaned). A stale binding (its definition gone)
  rows under no definition by construction and is
  counted in the census totals only.
- Rows: one per definition in the caller's list, in
  store order - the P-131 summary verbatim, enriched
  with exactly `binding_count`; `sound`;
  `definition_drift`; `chat_orphaned`; `doubly_broken`
  (binding counts per custody state); `chats_bound`
  and `chats_live` (DISTINCT chat ids across the
  definition's bindings, live ones stated separately -
  the P-148 distinct law); and `state` under the
  definition custody law: `unbound` (no bindings at
  all), else the strongest standing custody fact by
  the precedence doubly_broken > chat_orphaned >
  definition_drift > sound (a doubly-broken binding
  is broken on both axes; an orphaned binding's chat
  is gone for good, while a drifted pin stands beside
  a living chat and a living definition). The row's
  per-state counts name every binding's state, so the
  precedence hides nothing. `DEFINITION_CUSTODY_STATES`
  names the five in law order.
- Counts, every one summed from the rows and the
  joined bindings themselves: definitions_total and
  the five per-state definition counts;
  bindings_total; bindings_on_live_definitions;
  bindings_stale; and the four per-custody-state
  binding counts.
- Five standing honesty notes in fixed order (pure
  read; naming is not repair - the census aims the
  standing per-definition and per-chat roads and is
  none of them; the subject is the definition;
  the join adds no third fact and carries no seeded
  content; owner-scoped existence and truth-as-data).
- One additive road: `GET /scenarios/library/census`,
  declared in the library block after the P-145
  unmappable road and before the bindings block, so
  the literal "library" is never read as a definition
  id (the P-134 / P-145 precedent). No 404 case: an
  owner with no definitions answers the honest zero
  census, and an owner with definitions but no
  bindings answers every definition unbound.
- `src/runmal/scenarios/__init__.py` (additive) - a
  subsystem-map bullet after the reportcensus bullet,
  the `DEFINITION_CUSTODY_STATES` / `census_definitions`
  import after the reportcensus import, and the
  `__all__` entries after `census_unmappable` -
  disjoint blocks from P-149's (after deletepreview)
  and P-150's (after chatcensus) entries.
- `tests/test_p151_definition_census.py` (new) - the
  battery (see Counts).
- One entry appended to
  docs/CLEAN_ROOM_LOG_2026-10-30.md. README.md never
  touched. CAMPAIGN_STATE.md / CURRENT_STATE.md
  untouched (the keeper's banking work).

## Honest limitations

- The census is a pure read and judges custody only;
  it changes no write behaviour on either axis. Both
  cascades (definition delete, chat delete) remain
  deliberately untaken, and doubly-broken or orphaned
  bindings remain until unbound per chat - the census
  names them per definition so the owner can aim the
  standing roads, which remain the only removal roads.
- The definition state is a precedence summary, not a
  replacement for the per-binding facts: a definition
  holding one sound and one orphaned binding reads
  chat_orphaned, and its row's own counts are the
  full account. The per-binding truth stays on the
  P-144 / P-148 / P-150 censuses, untouched beside it.
- The join claims nothing neither parent census
  claims: organisation filing, report content and
  seeded content are absent here by construction,
  not by omission.
- The P-149 and P-150 unions were NOT verified in
  this worktree (they cannot be: both are absent
  from this base by design) - the keeper verifies
  them at banking with the combined batteries and
  the forge confirmation suite. This slice's
  no-regression claim rests on its own full suite's
  zero failures plus the neighbour fence on this
  base.
- There is no playback in this slice, and none is
  claimed (P-027 law: content is data, never code).

## Counts

- Battery: tests/test_p151_definition_census.py -
  see hidden_files/P151_EVIDENCE.md for the counted
  runs (battery, neighbour fence, full suite), read
  from the log files.
- Migration: NONE (head stays 0041, battery-pinned).
