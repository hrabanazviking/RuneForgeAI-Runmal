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
- ``router`` - the owner-scoped HTTP road
  (/api/v1/workspaces/*).
"""
