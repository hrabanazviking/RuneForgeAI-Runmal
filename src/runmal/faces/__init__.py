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
- ``history_router`` - the owner-scoped history road
  (GET /api/v1/faces/history).
- ``speaking_roster`` - speaking-roster resolution
  (P-159): one pure-read document pairing the faces a
  character CAN show (P-156's roster document composed
  whole, under the same closed roster state law, with
  NO current face - selection is per chat) with the
  voice its character speaks in (S512 resolution with
  its fallback law named as a closed voice state, the
  P-109 affect carried as data, consumed False). The
  pairing synthesizes nothing, renders nothing and
  performs no lip-sync; faces and voice stay
  independent modalities joined on the character.
- ``speaking_roster_router`` - the owner-scoped HTTP
  road (GET /api/v1/faces/speaking-roster?character_id=).
- ``chats`` - character face chats (P-160): one pure-read
  board per character naming every owned chat bound to
  it, in the chats service's order, with P-155's
  presentation truth composed verbatim per chat - the
  presentation state, the current row, its problem, and
  the current descriptor named as ``face`` only when
  that chat is ready - the board classified under a
  closed law (no_chats / none_ready / some_ready /
  all_ready). A character has no single current face:
  selection stays per chat (P-092).
- ``chats_router`` - the owner-scoped board road
  (GET /api/v1/faces/chats?character_id=).
- ``speaking_history`` - speaking-history resolution
  (P-161): one pure-read document pairing one chat's
  kept face history (P-158's history document composed
  whole - every kept event verbatim with provenance,
  entry states judged against today, the kept window
  named honestly) with its character's CURRENT voice
  resolution (S512 with its fallback law named as a
  closed voice state, the P-109 affect carried as data,
  consumed False). Voice honesty law: S512 stores NO
  voice history, so the voice half is today's
  resolution only (voice_scope: current_only) and no
  kept event is ever claimed to have been spoken in
  today's voice. The pairing synthesizes nothing,
  renders nothing and performs no lip-sync.
- ``speaking_history_router`` - the owner-scoped HTTP
  road (GET /api/v1/faces/speaking-history?chat_id=).
"""

from runmal.faces.chats import (
    BOARD_STATE_ALL_READY,
    BOARD_STATE_NO_CHATS,
    BOARD_STATE_NONE_READY,
    BOARD_STATE_SOME_READY,
    BOARD_STATES,
    CHATS_SCHEMA,
    resolve_character_face_chats,
)
from runmal.faces.chats import NOTES as CHATS_NOTES
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
from runmal.faces.speaking_history import NOTES as SPEAKING_HISTORY_NOTES
from runmal.faces.speaking_history import (
    SPEAKING_HISTORY_SCHEMA,
    VOICE_SCOPE,
    resolve_speaking_history,
)
from runmal.faces.speaking_roster import (
    SPEAKING_ROSTER_SCHEMA,
    resolve_character_speaking_roster,
)

__all__ = [
    "BOARD_STATE_ALL_READY",
    "BOARD_STATE_NO_CHATS",
    "BOARD_STATE_NONE_READY",
    "BOARD_STATE_SOME_READY",
    "BOARD_STATES",
    "CHATS_NOTES",
    "CHATS_SCHEMA",
    "FACE_STATES",
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
    "ROSTER_SCHEMA",
    "ROSTER_STATES",
    "SELECTION_SCOPE",
    "SPEAKING_ROSTER_SCHEMA",
    "SPEAKING_HISTORY_NOTES",
    "SPEAKING_HISTORY_SCHEMA",
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
    "VOICE_SCOPE",
    "resolve_character_roster",
    "resolve_character_face_chats",
    "resolve_face_history",
    "resolve_character_speaking_roster",
    "resolve_presentation",
    "resolve_speaking_history",
    "resolve_speaking_face",
]
