# P-169 - Workspace Binding Foundation (Part XI, Workspaces - the Companion That Works - opener)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-169 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P169_SCOUT.md;
design: hidden_files/P169_DESIGN.md):

- The census (P-003, docs/VOXTA_CENSUS_2026-10-30.md section H)
  names the part's ground: VX-54 (workspaces bind a chat to a
  real folder; the AI reads, writes and edits files in it, runs
  commands, launches programs), VX-55 (coding-agent backends),
  VX-56 (assistant tooling breadth), VX-57 (the tool-calling
  security pass) and VX-58 (done notifications). The delta
  table (P-004, docs/DELTA_TABLE_2026-10-30.md) judges every
  row MISSING and homes them all in Part XI.
- VX-54's first clause presupposes every other row: there is
  no file tool, agent backend, path rule or done-signal
  without a binding that says which folder a chat works in.
  Scouted: no workspace concept exists anywhere in src/, and
  no chat carries a folder field. The binding record is the
  part's missing first cell.
- The one chat-bound folder record the tree already kept, the
  P-121 vision watch registration, supplies the binding law
  kept here: the folder path is the operator's own path stored
  as data; registration never claims the folder exists -
  existence is a read-time fact; the store is the P-117
  versioned JSON index in the data dir with tolerant load; a
  chat's bound records die with the chat at the delete_chat
  custody anchor.
- Precedent for a new subsystem package + service + router +
  app wiring as a part opener: P-117 (vision), P-155 (faces).

The keeper reviews this derived scope at banking.

Base: 2bdaca62ea1cb03a324d62641a106b2578f76ffc (P-168 banking
record; PART X COMPLETE; P-001..P-168 banked). Migration:
NONE - head stays 0041, no 0042.

## What landed

New package `src/runmal/workspaces/` - a JSON store, no
migration:

- `bindings.py` -
  * `WorkspaceBinding` - one binding: {id, owner_id, chat_id,
    folder_path, label, created_at}. `folder_path` is stored
    verbatim after a surrounding-whitespace strip, as data -
    never normalised, resolved or rewritten.
  * `WorkspaceStore` - the versioned JSON index
    `workspaces.json` in the data dir (RUNMAL_DATA_DIR),
    tolerant load (a corrupt store reads as empty). Verbs:
    add / get by id / get for chat / list for owner / remove /
    `purge_chat` (custody, returns the count removed).
  * `register_binding(store, *, owner_id, chat_id,
    folder_path, label="")` - plain total refusals
    (`WorkspaceError`, nothing stored): an empty path, an
    empty chat id, and a chat that is already bound. ONE
    binding per chat; rebinding is unbind-then-bind, never a
    silent overwrite. The same folder may be bound by several
    chats. The folder is NOT required to exist and is never
    inspected at bind time.
  * `folder_state(folder_path)` - the folder judged LIVE on
    every call under the closed FOLDER_STATES law: `ready`
    (exists, is a directory, readable), `missing` (does not
    exist), `not_a_directory` (exists, not a directory),
    `unreadable` (a directory the process cannot read, or a
    stat failure for any reason other than non-existence).
    Symlinks are followed as the filesystem follows them.
  * `binding_document(binding, chat)` - schema
    `runmal-p169-workspace-binding-v1`: the binding verbatim,
    the chat's own facts {id, title, character_id} from the
    Chat row, `folder_state` judged at that moment, and the
    five standing honesty notes (below).
  * `resolve_chat_workspace(session, store, user_id,
    chat_id)` - the single document, or None when the chat
    is missing or foreign (existence never leaks) or the
    chat is unbound.
  * `list_owner_workspaces(session, store, user_id)` -
    schema `runmal-p169-workspace-list-v1`: one binding
    document per owned binding whose chat still exists, in
    store append order; `binding_count`, `ready_count`
    carried from the documents' own states, and
    `orphan_count` - bindings whose chat is gone are
    excluded and counted plainly, never silently dropped
    and never presented as live.
- `router.py` - on the /api/v1 mount via app.py,
  bearer-gated like every API:
  * POST /workspaces/bindings (201) {chat_id, folder_path,
    label?} - 404 "chat not found" for a missing or foreign
    chat; 422 for a register refusal (the watcher road's
    shape); the binding document on success.
  * GET /workspaces/bindings?chat_id= - the binding
    document; 404 "chat not found" when the chat is
    missing or foreign, 404 "workspace binding not found"
    when the chat exists but is unbound - two different
    facts, stated differently; a foreign chat reads exactly
    as missing, so existence never leaks.
  * GET /workspaces - the owner list document.
  * DELETE /workspaces/bindings/{binding_id} -
    {deleted: true, id} for an owned binding; 404 for
    unknown or foreign.
  * Every folder state is DATA at 200 on a read, never an
    error.
- `__init__.py` - the subsystem map.
- `app.py` - the router wired under /api/v1 with the
  local-auth dependency, after the speaking-census router
  (additive).
- `chats/service.py` - ONE additive custody hunk in
  delete_chat's established chain, after the P-121 watcher
  hunk, in the same lazy-import try/except shape: the
  chat's workspace binding dies with the chat.
- `tests/test_p169_workspace_binding.py` - the battery,
  authored fresh (P-005 discipline).

## The five standing honesty notes (fixed order, on every document)

1. A binding is data only: this surface reads no file
   contents, lists no folder, writes nothing into any folder,
   runs nothing and launches nothing - file tools,
   coding-agent backends and the tool-calling guard are later
   Part XI work, named open, not silently present.
2. The folder path is the operator's own path, stored as data
   and never claimed to exist; the folder state was judged
   live at read time, and a missing, not-a-directory or
   unreadable folder is a named state, never an error dressed
   as success.
3. One binding per chat: rebinding is unbind-then-bind, never
   a silent overwrite; the same folder may be bound by
   several chats.
4. A binding grants nothing: no tool, backend or process
   inherits any access from a binding existing - the path
   rules and scopes that will govern workspace tools are a
   later slice.
5. Owner scoped throughout: a chat's binding dies with the
   chat, and an orphaned binding is counted in the owner
   list, never presented as a live binding.

## Candidates weighed and not taken

- Folder listing / files browser (VX-54's second half): a
  real second cell with its own entry law (hidden files,
  ordering, caps, symlink law). Named open - the natural
  next Part XI slice.
- File read / write / edit tools: a write surface before the
  VX-57 guard exists would open exactly the hole the census
  flags; writes follow the guard, never precede it. Reads
  ride the listing cell. Named open.
- Run / launch / coding-agent backends (VX-55, VX-56):
  execution is the far end of the part, gated on binding +
  guard. Declined for the opener; P-027's law (content is
  data, never code) stands untouched.
- The tool-calling security pass (VX-57) in this slice:
  there are no workspace tool calls to guard yet; the guard
  lands with the first tool that needs it. Named open.
- Done notifications (VX-58): no notification surface exists
  in-tree. Named open.
- Reusing vision watcher registrations as workspaces: a
  watch is an image-ingest registration whose records are
  dedupe memory under P-120 custody, not a working folder;
  overloading it would corrupt both surfaces' honesty.
  Declined.
- A chats-table folder column (migration 0042): the house
  JSON store is the proven pattern for chat-bound folder
  records (P-121). Declined; head stays 0041.
- Binding by character, group or owner instead of chat:
  VX-54 binds a chat. Declined.
- Watching the folder for changes (daemon or polling): no
  watcher is claimed; state is judged on read only.
  Declined.
- Several folders per chat: VX-54 binds a chat to "a real
  folder" (singular). Declined.

## Honest limitations

- The binding is the whole slice: no folder contents are
  listed or read anywhere, and no Part XI successor exists
  yet to consume the binding. Until one lands, a workspace
  binding is a kept promise, not a working surface - stated
  plainly so no reader mistakes the foundation for the
  house.
- Folder state is a point-in-time judgement at read: a
  folder can change between the judgement and any later
  use, and no document here claims otherwise.
- The store is a whole-file JSON index (the house pattern):
  honest at this scale, with no locking story beyond the
  single-process server the house pattern already assumes -
  the same limitation every P-117-pattern store carries.
