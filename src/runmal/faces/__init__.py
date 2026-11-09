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
- ``router`` - the owner-scoped HTTP road
  (/api/v1/faces/*).
"""

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
    "NOTES",
    "PRESENTATION_SCHEMA",
    "PRESENTATION_STATES",
    "PROBLEM_NOT_DECLARED",
    "STATE_CURRENT_UNBOUND",
    "STATE_NO_CHARACTER",
    "STATE_NO_SELECTION",
    "STATE_NO_SET",
    "STATE_READY",
    "resolve_presentation",
]
