# P-171 - Workspace Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-171 entry exists anywhere in it. This slice's
scope is therefore DERIVED, not roadmap-verbatim, from Runmal's
own in-tree record only (full survey: hidden_files/P171_SCOUT.md;
design: hidden_files/P171_DESIGN.md):

- The census (P-003, docs/VOXTA_CENSUS_2026-10-30.md section H)
  names the part's ground: VX-54 (workspaces bind a chat to a
  real folder), VX-55 (coding-agent backends), VX-56 (assistant
  tooling breadth), VX-57 (the tool-calling security pass) and
  VX-58 (done notifications). The delta table (P-004,
  docs/DELTA_TABLE_2026-10-30.md) judges every row MISSING and
  homes them all in Part XI.
- P-169 banked the binding foundation and stated its own first
  honest limitation: the binding had NO consumer yet. P-170
  (team-02, in flight, not in this base) takes the read-only
  folder-listing / files-browser consumer. This slice is
  DISJOINT from it: no listing or browser files are touched,
  no folder is listed and no file contents are read.
- The cell no surface took is the owner's whole estate: P-169's
  owner list answers per-binding documents, but nothing judged
  the estate as a whole - how many owned chats exist, how many
  are bound vs unbound, how the bound folders distribute across
  the four folder states, and whether several chats share one
  folder (a fact P-169's law permits and no surface named).
  The house pattern for exactly this is the census (P-164 face
  census, P-148 custody census): a pure read composing the
  owning surface verbatim, classified under a closed law,
  counts summed from the composed documents' own arithmetic.

Weighed and not taken: rebind history kept as data (a
foundation amendment to P-169's store shape, not a consumer
cell; named open), the folder listing / files browser
(P-170's cell, in flight), a file read tool over a binding
(first file consumer should follow the census that names the
estate, and it stands nearer the VX-57 guard's ground), the
VX-57 guard itself (no tool calls exist to guard yet),
VX-55/56 backends and VX-58 notifications (execution/launch
is barred here by P-027; no notification surface exists
in-tree), folder watching, and any migration.

## What lands

- `src/runmal/workspaces/census.py` (new) - the pure-read
  service. `resolve_workspace_census(session, store, user_id)`
  always returns a document (schema
  `runmal-p171-workspace-census-v1`), never None: the subject
  is the caller, so nothing foreign can be named. The rows are
  P-169's `list_owner_workspaces` document composed VERBATIM -
  its rows whole, its `orphan_count` carried, never recomputed
  under a second law. The chat axis comes from
  `chats.service.list_chats` (`chat_count`, `bound_chat_count`,
  `unbound_chat_count`). The state axis sums the rows' own
  `folder_state` values under P-169's closed FOLDER_STATES law
  (`ready_count`, `missing_count`, `not_a_directory_count`,
  `unreadable_count`, `folder_state_counts`) - no second
  folder-state law. The sharing axis groups the rows' own
  `folder_path` values (`distinct_folder_count`,
  `shared_folder_count`, `bindings_on_shared_folders`). The
  estate is classified under the closed CENSUS_STATES law:
  `no_chats`, `no_bindings`, `none_ready`, `some_ready`,
  `all_ready`. Six standing honesty notes ride every document.
- `src/runmal/workspaces/census_router.py` (new) - the HTTP
  shape only: `GET /workspaces/census`, bearer-gated like
  every API through the app wiring. Every census state is
  DATA at 200, never an error.
- `src/runmal/app.py` (additive only) - the census router
  import and one include block beside the P-169 router's.
- `src/runmal/workspaces/__init__.py` (additive doc lines).
- `tests/test_p171_workspace_census.py` (new, 11 tests) -
  the empty axes, every census state, verbatim rows, live
  re-judgement, shared folders, orphans, owner scoping, the
  pure-read law, the HTTP road, and the migration pin.
- This doc, and one clean-room log entry.

## Honest boundaries

A census is a pure read: it stores, binds, unbinds, writes
and deletes nothing, reads no folder contents, lists no
folder, runs and launches nothing, and grants nothing - no
tool, backend or process inherits any access from a binding
existing (P-169's law). Folder states are P-169's live
read-time judgements, point-in-time at the census call.
Folder sharing is named as a fact, never judged an error:
P-169 permits several chats to bind one folder. No store
change, no migration: the head stays 0041. Named open for
later Part XI slices: the folder listing / files browser
(P-170, in flight), file tools (behind the VX-57 guard),
coding-agent backends (VX-55), tooling breadth (VX-56), and
done notifications (VX-58).
