"""Character face chats (P-160, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/CHARACTER_FACE_CHATS_2026-11-08.md
and hidden_files/P160_DESIGN.md.

What the derivation found: the banked Part X grid resolves
one chat's presentation (P-155), one character's roster
(P-156), one chat's face + voice pairing (P-157) and one
chat's kept history (P-158), and P-159 (in flight) takes
the per-character speaking roster. The one join no surface
makes is CHARACTER -> ITS CHATS: P-092's selections are per
chat, so a character with several chats can be showing a
different face in each, and nothing answers the character-
side question - which chats does this character have, and
what face is each one currently showing? What lives here
is that composition:

- one row per owned chat bound to this character, in the
  chats service's own order (creation order), carrying the
  chat's title and message count as the chats service
  states them;
- each row's face truth is P-155's presentation document
  judged per chat, composed verbatim - the presentation
  state, the current row with its provenance, the current
  problem, and the current entry's descriptor named as
  ``face`` only when that chat is ready;
- the board classified under a closed law (BOARD_STATES)
  that says honestly how many of the character's chats
  show a ready face.

Honest boundaries: Runmal renders NOTHING here, and a
character has NO single current face - selection is per
chat and always an explicit act (P-092's standing law).
This module draws, composites, animates and generates
nothing, reads no sprite bytes, selects nothing, applies
no default and scans no message text. It is a pure read
over the owning surfaces: get_character, list_chats and
resolve_presentation are composed verbatim, and no second
binding, selection or asset law is invented. No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

CHATS_SCHEMA = "runmal-p160-character-face-chats-v1"

BOARD_STATE_NO_CHATS = "no_chats"
BOARD_STATE_NONE_READY = "none_ready"
BOARD_STATE_SOME_READY = "some_ready"
BOARD_STATE_ALL_READY = "all_ready"
BOARD_STATES = frozenset({
    BOARD_STATE_NO_CHATS, BOARD_STATE_NONE_READY,
    BOARD_STATE_SOME_READY, BOARD_STATE_ALL_READY,
})

NOTES = (
    "Runmal renders nothing: this board is data a client "
    "reads; it carries no image bytes - a ready face's "
    "descriptor carries the P-023 content and thumbnail "
    "URLs as data.",
    "Every row is P-155's presentation document judged "
    "per chat, composed verbatim: no second binding, "
    "selection or fallback law is invented here, and "
    "the full entries roster stays P-155's / P-156's "
    "document.",
    "A character has no single current face: selection "
    "is per chat and stays P-092's explicit act - this "
    "read selects, applies, clears and scans nothing, "
    "and no message text is read.",
    "face is a chat's current selection only when that "
    "chat is ready; when face is None the row's state "
    "and current_problem name why, and fallbacks are "
    "never silently substituted - they are P-155's / "
    "P-156's data to name.",
    "Pure read, owner scoped: only the owner's chats "
    "bound to this one character appear; this surface "
    "stores, generates and animates nothing.",
)


async def resolve_character_face_chats(session, user_id: str,
                                       character_id: str,
                                       *, base_dir: Path | None = None,
                                       ) -> dict | None:
    """The face-chats board for one character.

    None when the character is missing or foreign (the
    character service's law - existence never leaks).
    Otherwise the envelope described in the module
    docstring: the character's own facts verbatim, one
    row per owned chat bound to the character in the
    chats service's order with P-155's presentation
    truth composed verbatim per chat, the board
    classified under BOARD_STATES, and the counts.
    """
    from runmal.characters.service import character_to_dict, get_character
    from runmal.chats import service as chats_svc
    from runmal.faces.presentation import STATE_CURRENT_UNBOUND, STATE_READY, resolve_presentation

    character = await get_character(session, user_id, character_id)
    if character is None:
        return None
    rows = []
    pairs = await chats_svc.list_chats(session, user_id)
    for chat, message_count in pairs:
        if getattr(chat, "character_id", None) != character_id:
            continue
        presentation = await resolve_presentation(
            session, user_id, chat.id, base_dir=base_dir)
        if presentation is None:
            continue
        rows.append({
            "chat_id": presentation["chat_id"],
            "title": chat.title,
            "message_count": message_count,
            "presentation_state": presentation["state"],
            "current": presentation["current"],
            "current_problem": presentation["current_problem"],
            "face": presentation["face"],
        })
    ready_count = sum(
        1 for row in rows
        if row["presentation_state"] == STATE_READY)
    if not rows:
        state = BOARD_STATE_NO_CHATS
    elif ready_count == 0:
        state = BOARD_STATE_NONE_READY
    elif ready_count == len(rows):
        state = BOARD_STATE_ALL_READY
    else:
        state = BOARD_STATE_SOME_READY
    return {
        "schema": CHATS_SCHEMA,
        "character_id": character_id,
        "character": character_to_dict(character),
        "state": state,
        "chats": rows,
        "chat_count": len(rows),
        "ready_count": ready_count,
        "selection_count": sum(
            1 for row in rows if row["current"] is not None),
        "unbound_count": sum(
            1 for row in rows
            if row["presentation_state"] == STATE_CURRENT_UNBOUND),
        "notes": list(NOTES),
    }


__all__ = [
    "BOARD_STATE_ALL_READY", "BOARD_STATE_NO_CHATS",
    "BOARD_STATE_NONE_READY", "BOARD_STATE_SOME_READY",
    "BOARD_STATES", "CHATS_SCHEMA", "NOTES",
    "resolve_character_face_chats",
]
