"""Runmal inspector subsystem (Part XIII - Assistant View,
Inspector & Bots).

- ``overview`` - the composed Inspector overview (P-203,
  Part XIII opener, DERIVED scope): ONE read-only,
  schema-versioned document per owned chat joining the
  three roadmap-named banked inspection sources - P-043
  lore activation inspection, P-059 prompt preview /
  inspect, P-075 message provenance - plus the chat's
  scenario-binding state. The overview CALLS the banked
  surfaces, never re-implements them, persists nothing,
  composes no prompt and runs no activation inspection
  inside its GET (a read must not consume probability
  rolls or compose prompts as a side effect).
- ``router`` - the single HTTP road: GET
  /inspector/chats/{chat_id}, owner-scoped like every
  chat road; unknown or foreign chats answer the house
  404 idiom.
"""

from __future__ import annotations

#: Schema id of the composed overview document.
OVERVIEW_SCHEMA = "runmal-p203-inspector-overview-v1"

__all__ = ["OVERVIEW_SCHEMA"]
