# P-173 - Workspace Binding History (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-173 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P173_SCOUT.md;
design: hidden_files/P173_DESIGN.md):

- P-171's banked record declined one cell by name, in the same
  words in its banking record, its evidence and its slice doc:
  "rebind history (a foundation amendment to P-169's store
  shape) stays named open". This slice takes exactly that cell.
- P-169's law makes the gap concrete: rebinding is
  unbind-then-bind, never a silent overwrite - but the unbind
  half destroyed the record. remove_binding dropped the row,
  the chat-deletion custody purge dropped the row, and nothing
  anywhere remembered that a chat had ever been bound, to
  which folder, or when. A lifecycle with no memory is the
  missing depth beneath every later Part XI cell: the VX-57
  guard and any write surface will want an audit trail of
  which folder a chat worked in, and when.
- The scout weighed the other open cells: the VX-57 guard
  (still no workspace writes exist to guard), file writes /
  edits / deletes (fenced until VX-57), execution / launch /
  backends (VX-55/56; P-027 absolute), watching. None is
  named open by two banked records; rebind history is. No
  better-grounded cell was found, so the named thread is
  the slice.

Base: 204a0d0e47ec06e20dbef92c2e935ed28e70f6ff (P-171 banking
record; banked P-001..P-171). Migration: NONE - head stays
0041, no 0042. Disjoint from P-172 (team-01, in flight):
no content.py touched, no router.py touched - the new road
rides its own router module on the P-171 census pattern.

## What lands

- `src/runmal/workspaces/bindings.py` (amended, the
  foundation amendment P-171 named) - the store now keeps
  history in the SAME `workspaces.json` index:
  * `WorkspaceHistoryEntry` - one ended binding kept as
    data: {id (the entry's own uuid), binding_id, owner_id,
    chat_id, folder_path, label, bound_at, ended_at, event}.
    Every field except id / ended_at / event is the
    superseded binding's own field verbatim; bound_at is
    the binding's created_at. The store records no actor
    beyond owner_id, so no actor is invented: who is the
    owner (the only principal who can end a binding, via
    the owner-scoped roads), what and when are the fields
    above.
  * The closed event law HISTORY_EVENTS = {unbound,
    chat_deleted}: unbound = ended by the owner's explicit
    unbind; chat_deleted = ended by the delete_chat custody
    purge. No "bound" events exist - a live binding is its
    own record, and history begins at a binding's end. A
    rebind therefore reads as the history entry for the old
    folder beside the live binding for the new one, with
    succession visible from the two records' own timestamps
    and never asserted by a fabricated link field.
  * The index gains ONE top-level key, "history", beside
    "bindings"; the version stays 1 (an additive optional
    key under the house tolerant load: a pre-P-173 file with
    no history key, and a corrupt file, both read as empty
    history). NO second store file: the scout showed a
    sibling writer over the same file is unsound, because
    P-169's save rewrote the whole document - so the store's
    load/save discipline itself is amended (_load_doc /
    _save_all), and every bindings-only save (_save, the
    add_binding path) re-reads and preserves the on-disk
    history, pinned by the battery.
  * remove_binding archives on a hit (event unbound) in the
    same save that removes the row, and writes NO history on
    a miss; its return contract is P-169's unchanged.
    purge_chat archives one entry per dropped binding
    (event chat_deleted) in the same save; its return
    contract is P-169's unchanged (the count of live
    bindings removed; a repeat purge appends nothing).
  * Live-binding semantics are UNCHANGED and battery-pinned
    by the neighbours: register refusals, one binding per
    chat, the binding and list documents, their schemas,
    the five standing notes, and the folder_state law are
    exactly P-169's.
- `src/runmal/workspaces/history.py` (new) - the read
  surface's truth layer. `resolve_workspace_history(session,
  store, user_id, chat_id=None)` always returns a document
  (schema `runmal-p173-workspace-history-v1`), never None:
  the subject is the caller. Entries are the owner's own,
  in store (chronological append) order, optionally narrowed
  to one chat. Each entry document carries the entry
  verbatim plus two read-time judgements, both labelled as
  such in the notes: folder_state judged LIVE at the
  history read under P-169's law (never claimed as the state
  at the ending), and chat_exists / chat_title judged live
  through chats.service.get_chat. Counts are summed from the
  returned entries themselves (entry_count, unbound_count,
  chat_deleted_count, chat_count of distinct chats). Five
  standing honesty notes ride every document.
- `src/runmal/workspaces/history_router.py` (new) -
  GET /workspaces/history with an optional chat_id filter,
  bearer-gated like every API through the app wiring. Every
  outcome is DATA at 200, never an error.
- `src/runmal/app.py` (additive only) - the history router
  import and one include block beside the census router's.
- `src/runmal/workspaces/__init__.py` (additive doc lines).
- `tests/test_p173_workspace_history.py` (new, 16 tests).
- This doc, and one clean-room log entry.

## The custody judgement (chat deletion)

P-169's custody law - a chat's binding dies with the chat -
is carried, not changed: delete_chat already calls
WorkspaceStore.purge_chat, so the amendment makes that one
call archive-then-remove with NO chats/service.py change,
proven end-to-end by the battery through the real
delete_chat road. The history ITSELF is retained when its
chat is deleted, including earlier unbound entries for that
chat. The weighed alternative - purging history with the
chat, by analogy to live custody - was declined: it would
destroy the record at exactly the moment the chat_deleted
entry is created, making that event unreadable by
construction. Custody governs live bindings; history is the
owner's audit data, owner-scoped on every read. A
consequence, stated plainly: this read surface has NO
chat-existence gate, deliberately unlike the live-binding
roads - a deleted chat's entries are returned with
chat_exists judged live and false, because those entries
are the surface's reason to exist. A chat_id filter naming
a foreign or unknown chat yields an honest empty document:
the filter names only the caller's own entries, so nothing
foreign can be named and nothing leaks.

## Candidates weighed and not taken

- A second store file for history (workspaces-history.json):
  declined - two whole-file writers over one lifecycle would
  diverge, and P-171 named this an amendment to P-169's
  store shape, i.e. the same store's data. The history lives
  under the same index's roof.
- A sibling history store composing WorkspaceStore verbatim
  without amending it: unsound, not merely declined - the
  unamended _save rewrites the whole document and would
  erase any history key another writer added.
- "Bound" events in the history (a full event log): the
  live binding already records the start; duplicating it
  would give one fact two homes that can disagree.
  Declined.
- A successor / rebind link field on entries: succession is
  honestly derivable from the records' own timestamps; a
  stored link would assert a pairing the unbind-then-bind
  law never made atomic. Declined.
- Purging history at chat deletion: declined above, with
  reasons.
- A history-deletion / retention road: no retention policy
  exists in-tree to implement; named open below.
- File writes / edits / deletes in bound folders (wait for
  the VX-57 guard), execution / launch / backends (VX-55/56;
  P-027 absolute), watching: all hard-declined, untouched.

## Honest limitations

- History is retained without bound and without a deletion
  road: the whole-file JSON store grows by one entry per
  ended binding. Honest at this scale under the house
  pattern's single-process assumption (the same limitation
  every P-117-pattern store carries); a retention policy is
  named open for a later slice or Volmarr's ruling.
- ended_at is the store's own clock at the ending call;
  bound_at is the binding's recorded created_at. Both are
  the store's fields, judged honestly - no external time
  authority is claimed.
- A store file written by PRE-P-173 code after history
  exists would drop the history key on its next save (the
  old _save knew only bindings). Within any tree carrying
  this slice the amended store is the only writer; the
  downgrade hazard is stated, not hidden.
- Folder states on history entries are point-in-time
  judgements at the history read, never at the ending -
  labelled as such on the document itself.
