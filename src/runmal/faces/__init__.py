"""Runmal faces subsystem (Part X - Faces That Speak).

- ``presentation`` - face presentation resolution: P-092's
  inspect surface composed verbatim and resolved into the
  one presentation document a client renders - per-entry
  renderable descriptors carrying the P-023 content /
  thumbnail roads as data, the current face classified
  under a closed state law (ready / current_unbound /
  no_selection / no_set / no_character), and the declared
  default + character avatar named as fallback data,
  never substituted. Runmal renders nothing itself; the
  document is the contract (P-155, Part X opener,
  DERIVED scope).
- ``history`` - face selection history resolution:
  P-092's kept selection history for one chat, composed
  with P-155's presentation document and resolved
  against today's binding truth - every kept event
  verbatim with its provenance, classified under a
  closed entry-state law (still_ready / declared_unbound
  / no_longer_declared / cleared), the still-declared
  entry's descriptor named as data, and the kept window
  (P-092's MAX_HISTORY_KEPT) named honestly, never as a
  complete record (P-158, DERIVED scope).
- ``router`` - the owner-scoped HTTP road
  (/api/v1/faces/*).
- ``history_router`` - the owner-scoped history road
  (GET /api/v1/faces/history).
"""

from runmal.faces.history import (
    ENTRY_STATE_CLEARED,
    ENTRY_STATE_DECLARED_UNBOUND,
    ENTRY_STATE_NO_LONGER_DECLARED,
    ENTRY_STATE_STILL_READY,
    ENTRY_STATES,
    HISTORY_SCHEMA,
    resolve_face_history,
)
from runmal.faces.history import NOTES as HISTORY_NOTES
from runmal.faces.presentation import (
    NOTES,
    PRESENTATION_SCHEMA,
    PRESENTATION_STATES,
    PROBLEM_NOT_DECLARED,
    STATE_CURRENT_UNBOUND,
    STATE_NO_CHARACTER,
    STATE_NO_SELECTION,
    STATE_NO_SET,
    STATE_READY,
    resolve_presentation,
)

__all__ = [
    "ENTRY_STATE_CLEARED",
    "ENTRY_STATE_DECLARED_UNBOUND",
    "ENTRY_STATE_NO_LONGER_DECLARED",
    "ENTRY_STATE_STILL_READY",
    "ENTRY_STATES",
    "HISTORY_NOTES",
    "HISTORY_SCHEMA",
    "NOTES",
    "PRESENTATION_SCHEMA",
    "PRESENTATION_STATES",
    "PROBLEM_NOT_DECLARED",
    "STATE_CURRENT_UNBOUND",
    "STATE_NO_CHARACTER",
    "STATE_NO_SELECTION",
    "STATE_NO_SET",
    "STATE_READY",
    "resolve_face_history",
    "resolve_presentation",
]
