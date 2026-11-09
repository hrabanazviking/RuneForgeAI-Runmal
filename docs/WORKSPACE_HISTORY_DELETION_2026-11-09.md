# P-175 - Workspace Binding History Deletion (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-175 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P175_SCOUT.md;
design: hidden_files/P175_DESIGN.md):

- P-173's banked record named this cell open in so many words:
  "History is retained WITHOUT bound and there is no
  history-deletion or retention road; history grows one entry
  per ended binding - NAMED OPEN for a future
  history-retention slice if Volmarr rules otherwise." The
  P-173 slice doc's declined list and history.py's module
  docstring said the same.
- P-174 weighed the same cell and declined it for one reason
  only: P-173's history store was "banking in parallel in
  team-02 and NOT in this base; named open behind banked
  P-173". In THIS base P-173 is banked (06cd7a5), so the
  sequencing condition P-174 itself stated is met.
- The gap is concrete, not decorative: history entries carry
  the operator's own folder paths verbatim, one per ended
  binding, forever, and until this slice the owner had no
  road to remove even a single entry from their own audit
  record - not a sensitive path, not a mistake, not anything.

Base: 06cd7a53911f573b68f175563cdb190b64709d3e (P-173 banking
record; banked P-001..P-173). Migration: NONE - head stays
0041, no 0042. Disjoint from P-174 (team-03, merged in the
forge, NOT in this base): no folder_census*.py, listing.py,
census*.py, content.py or router.py touched; app.py NOT
touched (the road rides the already wired history router).
Shared files with P-174: workspaces/__init__.py (additive
doc text) and the clean-room log (append +1 line) - flagged
for keeper reconciliation, the P-173/P-174 pattern.

## What lands

- `src/runmal/workspaces/bindings.py` (amended) - the store
  gains two methods, nothing else in its law moves:
  * `get_history_entry(entry_id)` - one history entry by its
    own id, or None.
  * `remove_history_entry(entry_id)` - on a hit, exactly
    that entry is dropped in the same `_save_all` that
    carries the live bindings verbatim, and the removed
    entry is returned; on a miss it returns None and writes
    NOTHING (no save at all - battery-pinned byte-identical
    file, and no file created on an empty store). Deletion
    is permanent: P-173's bindings-only save re-reads the
    on-disk history, so a deleted entry never resurrects,
    and a later ending appends after the survivors in store
    order (battery-pinned).
  * This is the ONLY road that deletes history: purge_chat
    still retains it (P-173's judged custody call,
    neighbour-pinned unchanged) and remove_binding still
    archives. The store document's shape and version are
    unchanged - one row fewer, no schema change.
- `src/runmal/workspaces/history.py` (amended) -
  `delete_workspace_history_entry(store, user_id, entry_id)`
  is the owner-scoped service: the removed entry on success,
  or None when the entry is unknown OR foreign (the two read
  exactly alike, so existence never leaks and a foreign
  entry is never deleted). The module docstring's
  "named open" paragraph is replaced by the P-175 fact, and
  the fifth of the five standing notes is reworded to say
  the read stays pure and deletion lives on its own road;
  the notes stay five, the schema stays
  `runmal-p173-workspace-history-v1`, and read counts are
  summed from the surviving entries (battery-pinned: after
  a deletion the history document's entry_count drops).
- `src/runmal/workspaces/history_router.py` (amended) -
  DELETE /workspaces/history/{entry_id}: 404 with detail
  "workspace history entry not found" when the service
  answers None; at 200, `{"deleted": True, "id": entry_id}` -
  the P-169 unbind shape verbatim. A second delete of the
  same entry is a 404, never a silent success.
- `src/runmal/workspaces/__init__.py` (additive doc text).
- `tests/test_p175_workspace_history_deletion.py` (new,
  15 tests).
- This doc, and one clean-room log entry.

## Candidates weighed and not taken

- An automatic retention policy (keep-last-N, an age
  cut-off, a scheduled prune): no retention policy exists
  in-tree to implement; inventing thresholds would
  fabricate a ruling that is Volmarr's to make. Owner-hand
  deletion is the retention road at this scale. Named open.
- A bulk clear-all road (DELETE /workspaces/history, or a
  per-chat clear): destroys the owner's whole audit record
  in one call with no per-entry judgement; not needed to
  close the named gap, since single entries are now
  deletable. Named open behind a ruling.
- Deleting history at chat deletion, or inside purge_chat:
  already weighed and declined by P-173 - it would destroy
  the chat_deleted record at the moment it is created. Not
  reopened; purge_chat's contract is neighbour-pinned.
- A composing surface over the banked roads (a history
  census, content/folder-census history): no banked record
  names such a gap, and it would compose a surface whose
  own named hole - unbounded, undeletable retention - it
  left untouched. Declined in the scout.
- File writes / edits / deletes in bound folders (fenced
  until the VX-57 guard exists), execution / launch /
  backends (VX-55/56; P-027 absolute), watching: all
  hard-declined, untouched.

## Honest limitations

- Retention is owner-hand only: history still grows one
  entry per ended binding until the owner deletes entries
  one at a time. No bulk or automatic form exists; both
  stay named open above for Volmarr's ruling.
- Deletion is permanent and unaudited by design of the
  smallest cell: no "history of deletions" is kept - such
  a record would recreate the retention problem one level
  up, and no banked record asks for it.
- The deletion road names entries by their own entry id,
  which the owner reads from GET /workspaces/history; there
  is no delete-by-chat or delete-by-folder form.
- Folder paths of LIVE bindings are untouched by this
  road, exactly as folder contents are: it deletes kept
  history data only, ends no binding and grants nothing.
