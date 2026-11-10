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
- ``events`` - the Inspector events document (P-204):
  ONE read-only, schema-versioned document per owned
  chat joining the banked S107 durable chat event log
  into the Inspector as a by-kind census plus honest
  coverage sections for the roadmap's events / actions /
  flags triad. The service CALLS the banked chats-service
  read (list_events), never re-implements it, and carries
  NO event data payloads and NO message content;
  payloads stay on the banked raw road the document
  points at.
- ``reasoning`` - the Inspector reasoning document
  (P-210): ONE read-only, schema-versioned document per
  owned chat joining the banked P-205 reasoning record
  into the Inspector as a census - per-message active
  statuses, recorded swipe indexes, per-status counts
  over active views and over all swipe documents. The
  service CALLS the banked chats-service read
  (list_chat_reasoning), never re-implements it, and
  carries NO thinking text anywhere; the text stays on
  the banked raw road each entry points at.
- ``router`` - the HTTP roads: GET
  /inspector/chats/{chat_id}, GET
  /inspector/chats/{chat_id}/events and GET
  /inspector/chats/{chat_id}/reasoning, owner-scoped
  like every chat road; unknown or foreign chats answer
  the house 404 idiom.
"""

from __future__ import annotations

#: Schema id of the composed overview document.
OVERVIEW_SCHEMA = "runmal-p203-inspector-overview-v1"

#: Schema id of the Inspector events document.
EVENTS_SCHEMA = "runmal-p204-inspector-events-v1"

#: Schema id of the Inspector reasoning document.
REASONING_SCHEMA = "runmal-p210-inspector-reasoning-v1"

__all__ = ["EVENTS_SCHEMA", "OVERVIEW_SCHEMA", "REASONING_SCHEMA"]
