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
"""
