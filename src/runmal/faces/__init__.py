"""Runmal faces subsystem (Part X - Faces That Speak).

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

Banking note: P-155 (team-01) creates this package with
its chat-keyed ``presentation`` module and its own router,
and P-156 (team-02) adds the ``roster`` module and roster
router, both on the same base; the keeper merges the
three package thirds - this __init__ gains the
presentation and roster lines and app.py gains all three
routers - when P-157 banks after P-155 and P-156.
"""

from runmal.faces.speaking import (
    FACE_STATES,
    NOTES,
    PROBLEM_NOT_DECLARED,
    SPEAKING_SCHEMA,
    STATE_CURRENT_UNBOUND,
    STATE_NO_CHARACTER,
    STATE_NO_SELECTION,
    STATE_NO_SET,
    STATE_READY,
    VOICE_DEFAULT,
    VOICE_PROFILE,
    VOICE_PROFILE_FALLBACK,
    VOICE_STATES,
    resolve_speaking_face,
)

__all__ = [
    "FACE_STATES",
    "NOTES",
    "PROBLEM_NOT_DECLARED",
    "SPEAKING_SCHEMA",
    "STATE_CURRENT_UNBOUND",
    "STATE_NO_CHARACTER",
    "STATE_NO_SELECTION",
    "STATE_NO_SET",
    "STATE_READY",
    "VOICE_DEFAULT",
    "VOICE_PROFILE",
    "VOICE_PROFILE_FALLBACK",
    "VOICE_STATES",
    "resolve_speaking_face",
]
