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
"""
