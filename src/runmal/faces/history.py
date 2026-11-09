"""Face selection history (P-158, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/FACE_HISTORY_2026-11-08.md
and hidden_files/P158_SCOUT.md / P158_DESIGN.md.

What the derivation found: P-092 (plugins/expressions.py)
records every selection in a kept history - each event
with its provenance receipt (source, actor, reason,
message id, the expression it replaced) and every
clearing - and serves it through list_history, whose only
in-tree consumer is the plugin's own raw router road.
P-155 resolves the CURRENT face for a chat; P-156 the
per-character roster; P-157 the face + voice pairing.
What did not exist - and what lives here - is the
TEMPORAL resolution: for one chat, the kept history
resolved against TODAY's binding truth, so a client can
show which faces the chat showed, in what order, why,
and whether each named face would still render today:

- every kept event rides verbatim in substance (the
  P-092 row whole, provenance included, newest first);
- each event is classified under a closed entry-state
  law (ENTRY_STATES) judged against the chat's CURRENT
  set and bindings, composed from P-155's presentation
  document verbatim - never a second binding law;
- an event whose expression is still declared today
  names that entry's P-155 descriptor as data (today's
  truth about the name, never a claim about the past);
- the kept window is named honestly: P-092 keeps at
  most MAX_HISTORY_KEPT events, so this document never
  claims a complete record.

Honest boundaries: Runmal renders NOTHING here. This
module draws, composites, animates and generates
nothing, reads no sprite bytes, selects nothing, clears
nothing, applies no default and scans no message text
(P-092's standing laws). It is a pure read over the
owning surfaces: P-155's presentation document and
P-092's list_history are composed verbatim, and history
itself is never rewritten - a past face is never
retroactively repaired. No store, no migration: head
stays 0041.
"""

from __future__ import annotations

from pathlib import Path

HISTORY_SCHEMA = "runmal-p158-face-history-v1"

ENTRY_STATE_STILL_READY = "still_ready"
ENTRY_STATE_DECLARED_UNBOUND = "declared_unbound"
ENTRY_STATE_NO_LONGER_DECLARED = "no_longer_declared"
ENTRY_STATE_CLEARED = "cleared"
ENTRY_STATES = frozenset({
    ENTRY_STATE_STILL_READY, ENTRY_STATE_DECLARED_UNBOUND,
    ENTRY_STATE_NO_LONGER_DECLARED, ENTRY_STATE_CLEARED,
})

NOTES = (
    "Runmal renders nothing: this document is history "
    "data a client reads; it carries no image bytes - a "
    "still-declared entry's descriptor carries the P-023 "
    "content and thumbnail URLs as data.",
    "Rows are P-092's kept history verbatim: entry_state "
    "judges each name against TODAY's set and bindings - "
    "history itself is never rewritten, and a past face "
    "is never retroactively repaired.",
    "The kept window: P-092 keeps at most kept_limit "
    "events and drops the oldest, so this document never "
    "claims a complete record of a chat's faces.",
    "Pure read: this surface selects, clears, applies "
    "and scans nothing - no message text is read; a "
    "row's message_id is provenance data only.",
    "A cleared event is not a face: it names the moment "
    "a chat's face was removed, carries no descriptor, "
    "and is never counted as a selection.",
)


async def resolve_face_history(session, user_id: str, chat_id: str,
                               *, base_dir: Path | None = None) -> dict | None:
    """The face selection history document for one chat.

    None when the chat is missing or foreign (P-155's
    resolve law - existence never leaks). Otherwise the
    envelope described in the module docstring: P-155's
    presentation state and current row verbatim, P-092's
    kept history for the chat verbatim in substance with
    each event classified under ENTRY_STATES against
    today's set, and the kept window named as data.
    """
    from runmal.faces.presentation import (
        PROBLEM_NOT_DECLARED,
        resolve_presentation,
    )
    from runmal.plugins import expressions as ex

    presentation = await resolve_presentation(
        session, user_id, chat_id, base_dir=base_dir)
    if presentation is None:
        return None
    rows = ex.list_history(user_id, chat_id=chat_id, base_dir=base_dir)
    by_name = {row["name"]: row for row in presentation["entries"]}
    events = []
    for row in rows:
        event = dict(row)
        name = row.get("expression")
        if row.get("cleared") or name is None:
            event["entry_state"] = ENTRY_STATE_CLEARED
            event["problem_now"] = None
            event["descriptor"] = None
        elif name not in by_name:
            event["entry_state"] = ENTRY_STATE_NO_LONGER_DECLARED
            event["problem_now"] = PROBLEM_NOT_DECLARED
            event["descriptor"] = None
        else:
            descriptor = by_name[name]
            event["descriptor"] = descriptor
            if descriptor["bound"]:
                event["entry_state"] = ENTRY_STATE_STILL_READY
                event["problem_now"] = None
            else:
                event["entry_state"] = ENTRY_STATE_DECLARED_UNBOUND
                event["problem_now"] = descriptor["problem"]
        events.append(event)
    return {
        "schema": HISTORY_SCHEMA,
        "chat_id": presentation["chat_id"],
        "character_id": presentation["character_id"],
        "presentation_state": presentation["state"],
        "current": presentation["current"],
        "events": events,
        "event_count": len(events),
        "selection_count": sum(
            1 for event in events
            if event["entry_state"] != ENTRY_STATE_CLEARED),
        "cleared_count": sum(
            1 for event in events
            if event["entry_state"] == ENTRY_STATE_CLEARED),
        "still_ready_count": sum(
            1 for event in events
            if event["entry_state"] == ENTRY_STATE_STILL_READY),
        "kept_limit": ex.MAX_HISTORY_KEPT,
        "at_kept_limit": len(events) >= ex.MAX_HISTORY_KEPT,
        "notes": list(NOTES),
    }


__all__ = [
    "ENTRY_STATE_CLEARED", "ENTRY_STATE_DECLARED_UNBOUND",
    "ENTRY_STATE_NO_LONGER_DECLARED", "ENTRY_STATE_STILL_READY",
    "ENTRY_STATES", "HISTORY_SCHEMA", "NOTES",
    "resolve_face_history",
]
