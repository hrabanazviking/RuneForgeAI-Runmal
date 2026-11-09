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
- ``roster`` - the per-character (chat-less) face roster
  (P-156): a pure-read resolution of P-092's character-keyed
  binding report into presentation descriptors in the
  shape a client renders, the roster classified under a
  closed state law, the declared default and the avatar
  named as fallback data, and NO current face - selection
  is per chat and always an explicit act (P-092).
- ``roster_router`` - the owner-scoped HTTP road
  (GET /api/v1/faces/roster?character_id=).
- ``speaking`` - speaking-face resolution (P-157): one
  pure-read document pairing the face a chat shows
  (P-092 inspect_state under the P-155 state law, the
  current descriptor named only when ready) with the
  voice its character speaks in (S512 resolution with
  its fallback law named as a closed voice state, the
  P-109 affect carried as data, consumed False). The
  pairing synthesizes nothing, renders nothing and
  performs no lip-sync; face and voice stay independent
  modalities joined on the chat's bound character.
- ``speaking_router`` - the owner-scoped HTTP road
  (GET /api/v1/faces/speaking?chat_id=).
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
from runmal.faces.roster import (
    ROSTER_SCHEMA,
    ROSTER_STATES,
    SELECTION_SCOPE,
    STATE_EMPTY_SET,
    STATE_NO_RENDERABLE,
    resolve_character_roster,
)
from runmal.faces.speaking import (
    FACE_STATES,
    SPEAKING_SCHEMA,
    VOICE_DEFAULT,
    VOICE_PROFILE,
    VOICE_PROFILE_FALLBACK,
    VOICE_STATES,
    resolve_speaking_face,
)

__all__ = [
    "FACE_STATES",
    "NOTES",
    "PRESENTATION_SCHEMA",
    "PRESENTATION_STATES",
    "PROBLEM_NOT_DECLARED",
    "ROSTER_SCHEMA",
    "ROSTER_STATES",
    "SELECTION_SCOPE",
    "SPEAKING_SCHEMA",
    "STATE_CURRENT_UNBOUND",
    "STATE_EMPTY_SET",
    "STATE_NO_CHARACTER",
    "STATE_NO_RENDERABLE",
    "STATE_NO_SELECTION",
    "STATE_NO_SET",
    "STATE_READY",
    "VOICE_DEFAULT",
    "VOICE_PROFILE",
    "VOICE_PROFILE_FALLBACK",
    "VOICE_STATES",
    "resolve_character_roster",
    "resolve_presentation",
    "resolve_speaking_face",
]
