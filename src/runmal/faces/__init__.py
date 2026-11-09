"""Runmal faces subsystem (Part X - Faces That Speak).

- ``roster`` - the per-character (chat-less) face roster
  (P-156): a pure-read resolution of P-092's character-keyed
  binding report into presentation descriptors in the
  shape a client renders, the roster classified under a
  closed state law, the declared default and the avatar
  named as fallback data, and NO current face - selection
  is per chat and always an explicit act (P-092).
- ``roster_router`` - the owner-scoped HTTP road
  (GET /api/v1/faces/roster?character_id=).

Banking note: P-155 (team-01) creates this package with
its chat-keyed ``presentation`` module and its own router
on the same base; the keeper merges the two package
halves - this __init__ gains the presentation lines and
app.py gains both routers - when P-156 banks after P-155.
"""
