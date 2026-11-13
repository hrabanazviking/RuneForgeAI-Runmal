"""Character face history (P-162, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/CHARACTER_FACE_HISTORY_
2026-11-08.md and hidden_files/P162_SCOUT.md /
P162_DESIGN.md.

What the derivation found: the Part X grid resolves, per
chat, the current face (P-155), the current face + voice
(P-157), the kept history (P-158) and the kept history +
today's voice (P-161, in flight), and, per character, the
roster (P-156), the speaking roster (P-159) and the
current-face chats board (P-160). The one subject x time
cell no surface fills is CHARACTER x HISTORY: P-158 is
scoped to one chat and P-160 to current faces, so nothing
answers the character-side temporal question - across all
of this character's chats, which faces were shown, in
what order, why, and would each still render today? What
lives here is that composition:

- one row per owned chat bound to this character, in the
  chats service's own order (creation order), carrying
  the chat's title and message count as the chats service
  states them;
- each row is that chat's P-158 history document composed
  verbatim in substance - the kept events whole with
  their provenance, each judged against today under
  P-158's closed entry-state law, the counts and the kept
  window exactly as P-158 states them;
- the board classified under a closed law
  (HISTORY_BOARD_STATES) that says honestly how the kept
  history is spread across the character's chats, with
  the totals summed from P-158's own arithmetic.

Events are never merged into one cross-chat stream:
interleaving chats would invent an ordering no owner
recorded. They stay grouped under the chat that made
them, in that chat's own order.

Honest boundaries: Runmal renders NOTHING here, and a
character has NO single face history stream - selection
is per chat and always an explicit act (P-092's standing
law). This module draws, composites, animates and
generates nothing, reads no sprite bytes, selects
nothing, clears nothing, applies no default and scans no
message text. It is a pure read over the owning surfaces:
get_character, list_chats and resolve_face_history are
composed verbatim, and no second history, binding,
selection or asset law is invented. No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

CHARACTER_HISTORY_SCHEMA = "runmal-p162-character-face-history-v1"

HISTORY_BOARD_STATE_NO_CHATS = "no_chats"
HISTORY_BOARD_STATE_NO_HISTORY = "no_history"
HISTORY_BOARD_STATE_SOME_HISTORY = "some_history"
HISTORY_BOARD_STATE_ALL_HISTORY = "all_history"
HISTORY_BOARD_STATES = frozenset({
    HISTORY_BOARD_STATE_NO_CHATS, HISTORY_BOARD_STATE_NO_HISTORY,
    HISTORY_BOARD_STATE_SOME_HISTORY, HISTORY_BOARD_STATE_ALL_HISTORY,
})

NOTES = (
    "Runmal renders nothing: this board is history "
    "data a client reads; it carries no image bytes - a "
    "still-declared entry's descriptor carries the P-023 "
    "content and thumbnail URLs as data.",
    "Every row is P-158's history document for that "
    "chat, composed verbatim: entry_state judges each "
    "name against TODAY's set and bindings - history "
    "itself is never rewritten, and no second history "
    "or binding law is invented here.",
    "The kept window applies per chat: P-092 keeps at "
    "most kept_limit events for each chat and drops "
    "that chat's oldest, so this board never claims a "
    "complete record of a character's faces.",
    "A character has no single face history stream: "
    "selection is per chat and stays P-092's explicit "
    "act - events stay grouped under the chat that made "
    "them, in that chat's own order; this read selects, "
    "clears, applies and scans nothing, and no message "
    "text is read.",
    "Pure read, owner scoped: only the owner's chats "
    "bound to this one character appear; this surface "
    "stores, generates and animates nothing.",
)


async def resolve_character_face_history(session, user_id: str,
                                         character_id: str,
                                         *, base_dir: Path | None = None,
                                         ) -> dict | None:
    """The face-history board for one character.

    None when the character is missing or foreign (the
    character service's law - existence never leaks).
    Otherwise the envelope described in the module
    docstring: the character's own facts verbatim, one
    row per owned chat bound to the character in the
    chats service's order with P-158's history document
    composed verbatim in substance per chat, the board
    classified under HISTORY_BOARD_STATES, and the
    totals summed from P-158's own counts.
    """
    from runmal.characters.service import character_to_dict, get_character
    from runmal.chats import service as chats_svc
    from runmal.faces.history import resolve_face_history
    from runmal.plugins import expressions as ex

    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    rows = []
    pairs = await chats_svc.list_chats(session, user_id)
    for chat, message_count in pairs:
        if getattr(chat, "character_id", None) != character_id:
            continue
        history = await resolve_face_history(
            session, user_id, chat.id, base_dir=base_dir)
        if history is None:
            continue
        rows.append({
            "chat_id": history["chat_id"],
            "title": chat.title,
            "message_count": message_count,
            "presentation_state": history["presentation_state"],
            "current": history["current"],
            "events": history["events"],
            "event_count": history["event_count"],
            "selection_count": history["selection_count"],
            "cleared_count": history["cleared_count"],
            "still_ready_count": history["still_ready_count"],
            "kept_limit": history["kept_limit"],
            "at_kept_limit": history["at_kept_limit"],
        })
    chats_with_history = sum(1 for row in rows if row["event_count"] > 0)
    if not rows:
        state = HISTORY_BOARD_STATE_NO_CHATS
    elif chats_with_history == 0:
        state = HISTORY_BOARD_STATE_NO_HISTORY
    elif chats_with_history == len(rows):
        state = HISTORY_BOARD_STATE_ALL_HISTORY
    else:
        state = HISTORY_BOARD_STATE_SOME_HISTORY
    return {
        "schema": CHARACTER_HISTORY_SCHEMA,
        "character_id": character_id,
        "character": character_to_dict(character),
        "state": state,
        "chats": rows,
        "chat_count": len(rows),
        "chats_with_history_count": chats_with_history,
        "event_count": sum(row["event_count"] for row in rows),
        "selection_count": sum(row["selection_count"] for row in rows),
        "cleared_count": sum(row["cleared_count"] for row in rows),
        "still_ready_count": sum(
            row["still_ready_count"] for row in rows),
        "chats_at_kept_limit": sum(
            1 for row in rows if row["at_kept_limit"]),
        "kept_limit": ex.MAX_HISTORY_KEPT,
        "notes": list(NOTES),
    }


__all__ = [
    "CHARACTER_HISTORY_SCHEMA", "HISTORY_BOARD_STATE_ALL_HISTORY",
    "HISTORY_BOARD_STATE_NO_CHATS", "HISTORY_BOARD_STATE_NO_HISTORY",
    "HISTORY_BOARD_STATE_SOME_HISTORY", "HISTORY_BOARD_STATES",
    "NOTES", "resolve_character_face_history",
]
