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
"""
