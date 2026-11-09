"""Runmal workspaces subsystem (Part XI - Workspaces,
the Companion That Works).

- ``bindings`` - workspace bindings (P-169, Part XI
  opener, DERIVED scope): one owned chat bound to one
  real folder path, the binding kept as data in the
  house JSON store (no migration), the folder's state
  judged live at read time under a closed state law
  (ready / missing / not_a_directory / unreadable),
  custody on chat deletion. A binding reads no file
  contents, writes nothing into any folder and grants
  nothing - file tools, agent backends and the
  tool-calling guard are later Part XI slices.
- ``listing`` - the workspace folder listing
  (P-170, Part XI, DERIVED scope): the read-only
  files browser over the binding - entry names,
  kinds and honest sizes judged live at read, every
  listed path contained in the bound folder, no
  contents read and nothing written.
- ``content`` - the workspace file content read
  (P-172, Part XI, DERIVED scope): the read-only
  text read over the binding - one named file
  read as strict UTF-8 under a stated cap,
  containment re-judged at the moment of use,
  binary / oversize / unreadable named as
  outcomes, nothing written.
- ``folder_census`` + ``folder_census_router`` -
  the workspace folder census (P-174, Part XI,
  DERIVED scope): one chat's bound folder at one
  level as a pure read - P-170's listing composed
  verbatim and embedded whole, kind counts, total
  file bytes, extension counts from names only,
  hidden and escaping-symlink counts, the largest
  file, the level classified under a closed law
  (folder_not_ready / empty / no_files / has_files)
  on GET /workspaces/folder-census. It reads no
  file contents, writes nothing and grants nothing.
- ``tree`` + ``tree_router`` - the workspace folder
  tree (P-176, Part XI, DERIVED scope): one chat's
  bound folder as a depth-limited tree - every level
  composed verbatim from P-170's listing, directories
  expanded to a stated depth under a stated node cap,
  symlinks never descended, caps and mid-walk refusals
  carried as data - on GET /workspaces/tree. It opens
  no file, writes nothing and grants nothing.
- ``search`` + ``search_router`` - the workspace
  filename search (P-178, Part XI, DERIVED scope):
  one chat's bound folder searched by entry name -
  P-176's tree composed verbatim at its maximum
  depth and filtered by name only, each match
  carrying its folder-relative path (the input
  P-172's read consumes), coverage the expanded
  tree only and partiality named - on GET
  /workspaces/search. It opens no file, writes
  nothing and grants nothing.
- ``content_search`` + ``content_search_router`` -
  the workspace content search (P-180, Part XI,
  DERIVED scope): one chat's bound folder searched
  by file content - P-176's tree composed verbatim
  at its maximum depth, every candidate file read
  through P-172's own read under its stated cap,
  binary / oversize / unreadable / refused files
  named as skips (never searched in part, never
  silently omitted), partial coverage named by
  truncated / coverage_complete - on GET
  /workspaces/content-search. It writes nothing
  and grants nothing.
- ``tree_census`` + ``tree_census_router`` -
  the workspace tree census (P-181, Part XI,
  DERIVED scope): one chat's bound folder over
  P-176's whole depth-limited tree as a pure
  read - P-176's tree composed verbatim at its
  maximum depth and embedded whole, kind counts,
  total file bytes, extension counts from names
  only, hidden and escaping-symlink counts, the
  largest file with its folder-relative path,
  expanded / unexpanded / refused directory
  counts and counts by depth, the folder
  classified under a closed law
  (folder_not_ready / empty / no_files /
  has_files) on GET /workspaces/tree-census.
  It opens no file, reads no file contents,
  writes nothing and grants nothing.
- ``content_census`` + ``content_census_router`` -
  the workspace content census (P-183, Part XI,
  DERIVED scope): one chat's bound folder over
  P-176's whole depth-limited tree as a pure
  aggregate of P-172 readability - the tree composed
  verbatim at its maximum depth and embedded whole,
  every candidate file read only through P-172's own
  read under its stated cap and counted under its
  outcome (readable / binary / oversize / unreadable /
  refused), every non-readable file named, total
  readable bytes, the readable extension shape and
  the largest readable file, the folder classified
  under a closed law (folder_not_ready / empty /
  no_files / none_readable / some_readable /
  all_readable) on GET /workspaces/content-census.
  It retains and returns no file content and no
  excerpt, writes nothing and grants nothing.
- ``router`` - the owner-scoped HTTP road
  (/api/v1/workspaces/*).
- ``census`` + ``census_router`` - the workspace
  census (P-171, Part XI, DERIVED scope): one owner's
  whole workspace estate as a pure read - P-169's
  owner list composed verbatim, chats bound vs
  unbound, per-folder-state counts, shared folders
  named, the estate classified under a closed census
  law (no_chats / no_bindings / none_ready /
  some_ready / all_ready) on GET /workspaces/census.
  It reads no folder contents, lists no folder,
  writes nothing and grants nothing.
- ``history`` + ``history_router`` - the workspace
  binding history (P-173, Part XI, DERIVED scope):
  every ended binding - unbound, or purged when its
  chat was deleted - kept as data in the same store
  by the bindings amendment, served owner-scoped on
  GET /workspaces/history with the ending's moment
  and cause named; a deleted chat's entries are
  returned on purpose, judged live, never hidden.
  The owner can delete one history entry permanently
  on DELETE /workspaces/history/{entry_id} (P-175,
  Part XI, DERIVED scope): the P-173 named-open
  retention road in owner-hand form - no automatic
  retention policy is invented.
- ``history_census`` + ``history_census_router`` -
  the workspace binding-history census (P-177,
  Part XI, DERIVED scope): one owner whole history
  estate as a pure read - P-173 history document
  composed verbatim and embedded whole, ended
  bindings counted by cause, by the folders live
  states today, by whether their chats still
  exist, by folder sharing across endings and by
  label presence, the estate classified under a
  closed law (no_history / no_live_chats /
  all_live_chats / some_live_chats) on
  GET /workspaces/history-census. It deletes no
  history, writes nothing and grants nothing.
"""
