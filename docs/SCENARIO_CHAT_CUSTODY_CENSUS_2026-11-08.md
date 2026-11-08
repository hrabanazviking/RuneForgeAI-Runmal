# P-148 - Binding Chat-Custody Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part IX only its part-table line -
"IX | Scenarios - the Visual Novel Engine | P-131 - P-154" -
and no per-slice entries. This slice's scope is therefore
DERIVED, not roadmap-verbatim, stated plainly as derived
everywhere, following the P-101 / P-117 / P-131..P-147
precedents. The derivation rests on Runmal's own in-tree
record only (full weighing below; scout and design in the
team hidden record).

Base: 3ff4555 (P-146 banking record; P-001..P-146 banked).
P-147 (chat-scoped candidate bind preview, team-02) is in
flight, banks ahead of this slice, and is NOT in this base;
its ground (the candidate body judged against one chat) is
not duplicated here, and this slice's delta sits in
disjoint blocks (a bindings-block road, an __init__ bullet
after bindingcensus) for the keeper's banking
reconciliation. Migration: NONE - head stays 0041. No
storage-shape change, no new store, no write-behaviour
change anywhere: the census reads the P-132 binding store
and the live Chat table and stores nothing.

## The weighing

- **Binding chat-custody census - taken.** A binding has
  two parents, and only one axis was ever judged. The
  definition axis is complete: delete never cascades into
  the binding store (P-132 / P-135), P-139 previews the
  orphaning before a delete, and P-144 censuses the drift
  after it (current / superseded / ahead / stale). The
  chat axis was judged nowhere, verified in code on this
  base: chats.service.delete_chat removes the Chat row and
  then cleans, one by one, the chat's checkpoints,
  databank, undo store, vision links, image attachments
  (P-120 custody) and folder-watch registrations (P-121
  custody) - and never the scenario binding store (no
  reference to it exists under src/runmal/chats/). A
  deleted chat's binding record therefore stands forever,
  and every surface is blind to it: the per-chat binding
  read (P-132) reads only the binding store and still
  answers the record exactly as if the chat lived; P-135
  and P-144 judge existence and revision against the
  definition store only - P-144's own fifth standing note
  states the bound verbatim ("judges no chat liveness, a
  fact the binding store does not carry"). Chat existence
  is a fact the Chat table carries, and P-138 already
  reads that table through the same owner-scoped law. The
  one removal road, unbind per chat, works on the binding
  store alone and could remove an orphan - but no surface
  named which bindings are orphaned, so the owner could
  not aim it. This slice is that naming: one pure read
  joining every binding to the live Chat table.
- **Chat-scoped candidate bind preview - not available.**
  Taken by concurrent P-147; the body x scope preview
  matrix completes there. Not duplicated.
- **Wiring delete_chat to cascade the binding record -
  declined for this slice.** A write-behaviour change
  inside the chats subsystem, not a scenario read
  surface. Every Part IX custody fact so far was first
  NAMED by a read surface (P-135 named stale bindings
  before P-139 / P-144 judged them); the binding store's
  no-cascade law is deliberate on the definition side
  (P-132 / P-139); and whether chat deletion should
  unbind is a behaviour decision no in-tree record has
  taken. The census names the orphans and the standing
  unbind road removes them per chat once named (battery-
  pinned end to end here). Named as the honest next
  question if the cascade is ever wanted.
- **Candidate create preview - declined.** Create is
  neither permanent nor destructive (the record can be
  deleted, P-131), and the stateless P-026 import road
  already dry-reads a body before it is stored (P-145's
  weighing). The pre-commit need that justified P-146 -
  an irreversible replace - does not exist for create.
- **Unbind-impact preview - declined.** Standing ground
  since P-141: the unbind road already answers its one
  fact with every unbind (the record goes, seeded
  content stays).
- **Duplication preview - declined.** P-137 is
  non-destructive: it orphans nothing, supersedes
  nothing, and carries no binding or organisation row.
- **Organisation orphan census / cleanup - declined.**
  Standing law: orphan rows are filtered at every read
  (P-134), P-139 names the row per definition, censuses
  name and never repair, and cleanup tooling is
  declined.
- **Within-library duplicate-content census - declined.**
  Standing (P-145 / P-147): identity-by-checksum is
  P-141 / P-143 pack law; P-137 clones are honest
  citizens, not drift.
- **Export / pack-export previews - declined.** Standing:
  a preview of a pure read adds no knowledge; both
  exports already carry their honest reports.
- **Rebind / refresh preview - declined.** Bind's own
  law refuses the only chats it could target (already
  bound, non-empty - P-132), so its would_bind is false
  by construction: a hollow surface. The honest refresh
  path remains unbind + bind as the owner's own acts.
- **Definition history retention - declined.** Standing:
  no named consumer, and retention would be a
  storage-shape change.
- **Portable-archive inclusion of the scenario stores -
  declined for this slice.** A portable-subsystem line,
  named open there in every weighing.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never code.
  This slice evaluates nothing and runs nothing.

## The contract

One new async read-service module
(scenarios/chatcensus.py: census_binding_chats - async
because chat existence lives in the SQL Chat table, the
chatpreview precedent) and one additive road
(GET /scenarios/bindings/chat-census, declared in the
bindings block after the P-144 census road and before
the /scenarios/bindings/{chat_id} road, so the literal
"chat-census" is never read as a chat id, battery-pinned
by contrast with the per-chat read).

Rows are P-135's list_bindings summaries verbatim, in
store (bind) order, each gaining exactly two keys -
chat_exists and chat_state - under a two-state law:
live (the binding's chat row still exists for this
owner) or orphaned (it does not: deleted, never existed,
or another owner's - judged owner-scoped in one select
of the rows' distinct chat ids under the caller's owner
id, the existence law bind and P-138 read the table by;
the three answer exactly alike, so existence never
leaks). by_definition rollups roll the same rows up per
definition in first-binding order (the summary's pinned
name; the row's own definition_exists fact), and every
count is summed from the rows and groups themselves so
the census cannot drift from its own evidence (the
P-144 construction): bindings_total, live, orphaned,
chats_live and chats_orphaned as DISTINCT chat ids -
stated separately from the row counts because a
hand-damaged store could hold two rows for one chat
(bind forbids it) and the census counts rows and chats
honestly, separately - definitions_referenced,
definitions_with_live, definitions_with_orphaned. Five
standing honesty notes ride in every answer, in fixed
order. No 404 case: an owner with no bindings answers
the honest zero census, and a binding whose definition
is gone still answers (its row carries definition_exists
false beside its chat state - the two axes are
independent, and a binding can be orphaned and stale at
once).

## Honest limitations

A census, not a cleanup: nothing is unbound, deleted or
repaired; orphaned bindings stay recorded until each is
unbound per chat under its own road. The census judges
existence only, at read time, for the caller: it reads
no chat content and no chat fact beyond existence - a
group room that exists reads live here, because custody
judges existence, not bindability (bind's refusal law is
bind's, judged by P-138 against one named chat).
Definition-side drift stays P-144's census; this census
carries no seeded content (the P-135 summaries never
do). No filters, sorts or paging: store order, the whole
owner set (the P-135 / P-144 / P-145 bounded-surface
precedent).

## Counts

Battery: 17 tests (tests/test_p148_chat_custody_census.py).
Neighbour fence (P-026 + P-131..P-146 + this battery):
351 passed. Full suite and machine state are recorded in
the team evidence file (hidden_files/P148_EVIDENCE.md).
Migration: NONE (head stays 0041, battery-pinned).
