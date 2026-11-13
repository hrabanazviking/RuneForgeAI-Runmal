"""Face history census (P-165, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That
Speak", P-155..P-168); this slice's scope is derived
from Runmal's own in-tree record - see
docs/FACE_HISTORY_CENSUS_2026-11-08.md and
hidden_files/P165_SCOUT.md / P165_DESIGN.md.

What the derivation found: the banked Part X grid
fills every chat-keyed cell (P-155 current face,
P-157 speaking face, P-158 kept history, P-161
speaking history) and every character-keyed cell
(P-156 roster, P-159 speaking roster, P-160 current
chats board, P-162 history board, P-163 speaking
history board), and P-164 took the owner's CURRENT
faces as a silent census while naming an owner-wide
history census open in its own record. The one
subject x time cell no surface takes is OWNER x
HISTORY: across all of one owner's characters and
all of their chats, which faces were shown, in what
order, and would each still render today? What lives
here is that composition:

- one row per owned character, in the characters
  service's own order (creation order), composing
  P-162's character face-history board verbatim in
  substance - the character's own facts, the board
  state under P-162's closed law, the board's rows
  whole (each chat's P-158 history document), and
  the board's counts;
- the census classified under a closed law
  (HISTORY_CENSUS_STATES) that says honestly, at
  owner level, how the kept history is spread across
  the owner's chats;
- the counts summed from the boards' own arithmetic.

Honest boundaries: Runmal renders NOTHING here, and
there is NO owner-wide history stream - events stay
grouped under the chat that made them, inside that
chat's character row, in that chat's own order;
merging them would invent an ordering no owner
recorded. The kept window stays P-092's PER-CHAT law:
kept_limit is stated as that law and never summed
into an owner window, so this census never claims a
complete record of an owner's faces. The census is
SILENT: it names no voice (P-157 / P-159 / P-161 /
P-163 own the pairings). Selection is per chat and
always an explicit act (P-092's standing law). This
module draws, composites, animates and generates
nothing, reads no sprite bytes, selects nothing,
clears nothing, applies no default and scans no
message text. It is a pure read over the owning
surfaces: list_characters and P-162's board resolver
are composed verbatim, and no second history,
binding, selection or asset law is invented. No
store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

HISTORY_CENSUS_SCHEMA = "runmal-p165-face-history-census-v1"

HISTORY_CENSUS_STATE_NO_CHARACTERS = "no_characters"
HISTORY_CENSUS_STATE_NO_CHATS = "no_chats"
HISTORY_CENSUS_STATE_NO_HISTORY = "no_history"
HISTORY_CENSUS_STATE_SOME_HISTORY = "some_history"
HISTORY_CENSUS_STATE_ALL_HISTORY = "all_history"
HISTORY_CENSUS_STATES = frozenset({
    HISTORY_CENSUS_STATE_NO_CHARACTERS,
    HISTORY_CENSUS_STATE_NO_CHATS,
    HISTORY_CENSUS_STATE_NO_HISTORY,
    HISTORY_CENSUS_STATE_SOME_HISTORY,
    HISTORY_CENSUS_STATE_ALL_HISTORY,
})

NOTES = (
    "Runmal renders nothing: this census is data a "
    "client reads; it carries no image bytes - a kept "
    "event's descriptor carries the P-023 content and "
    "thumbnail URLs as data.",
    "Every character row is P-162's face-history board "
    "composed verbatim: no second history, binding, "
    "selection or fallback law is invented here, and "
    "each chat's events stay exactly as P-158 judged "
    "them against today.",
    "The kept window applies per chat: P-092 keeps at "
    "most kept_limit events for each chat and drops "
    "that chat's oldest, so this census never claims "
    "a complete record of an owner's faces, and "
    "kept_limit is never summed into an owner window.",
    "Events are never merged into one owner-wide or "
    "cross-character stream: they stay grouped under "
    "the chat that made them, inside that chat's "
    "character row, in that chat's own order. There "
    "is no owner-wide face and no owner-wide history "
    "stream - selection is per chat and stays "
    "P-092's explicit act.",
    "This census is silent and past only: it names no "
    "voice (voice is P-157's / P-159's / P-161's / "
    "P-163's pairings) and restates no current face "
    "beyond the per-chat history documents' own "
    "current rows. Pure read, owner scoped: only the "
    "caller's own characters and chats appear; this "
    "surface stores, generates and animates nothing, "
    "and scans no message text.",
)


async def resolve_face_history_census(
        session, user_id: str,
        *, base_dir: Path | None = None) -> dict:
    """The kept-history census for one owner.

    Always a document, never None: the subject is
    the caller themselves, so there is no foreign
    subject whose existence could leak, and an owner
    with no characters gets the honest empty census
    (state no_characters). Otherwise the envelope
    described in the module docstring: one row per
    owned character in the characters service's
    order with P-162's board composed verbatim in
    substance, the census classified under
    HISTORY_CENSUS_STATES, and the counts summed
    from the boards' own arithmetic.
    """
    from runmal.characters.service import list_characters
    from runmal.faces.character_history import (
        resolve_character_face_history,
    )
    from runmal.plugins import expressions as ex

    rows = []
    characters = await list_characters(session, user_id)
    for character in characters:
        board_doc = await resolve_character_face_history(
            session, user_id, character.id, base_dir=base_dir)
        if board_doc is None:
            continue
        rows.append({
            "character_id": board_doc["character_id"],
            "character": board_doc["character"],
            "board_state": board_doc["state"],
            "chats": board_doc["chats"],
            "chat_count": board_doc["chat_count"],
            "chats_with_history_count":
                board_doc["chats_with_history_count"],
            "event_count": board_doc["event_count"],
            "selection_count": board_doc["selection_count"],
            "cleared_count": board_doc["cleared_count"],
            "still_ready_count": board_doc["still_ready_count"],
            "chats_at_kept_limit":
                board_doc["chats_at_kept_limit"],
            "kept_limit": board_doc["kept_limit"],
        })
    chat_count = sum(row["chat_count"] for row in rows)
    chats_with_history = sum(
        row["chats_with_history_count"] for row in rows)
    if not rows:
        state = HISTORY_CENSUS_STATE_NO_CHARACTERS
    elif chat_count == 0:
        state = HISTORY_CENSUS_STATE_NO_CHATS
    elif chats_with_history == 0:
        state = HISTORY_CENSUS_STATE_NO_HISTORY
    elif chats_with_history == chat_count:
        state = HISTORY_CENSUS_STATE_ALL_HISTORY
    else:
        state = HISTORY_CENSUS_STATE_SOME_HISTORY
    return {
        "schema": HISTORY_CENSUS_SCHEMA,
        "state": state,
        "characters": rows,
        "counts": {
            "character_count": len(rows),
            "characters_with_chats_count": sum(
                1 for row in rows if row["chat_count"] > 0),
            "characters_with_history_count": sum(
                1 for row in rows
                if row["chats_with_history_count"] > 0),
            "chat_count": chat_count,
            "chats_with_history_count": chats_with_history,
            "event_count": sum(
                row["event_count"] for row in rows),
            "selection_count": sum(
                row["selection_count"] for row in rows),
            "cleared_count": sum(
                row["cleared_count"] for row in rows),
            "still_ready_count": sum(
                row["still_ready_count"] for row in rows),
            "chats_at_kept_limit": sum(
                row["chats_at_kept_limit"] for row in rows),
        },
        "kept_limit": ex.MAX_HISTORY_KEPT,
        "notes": list(NOTES),
    }


__all__ = [
    "HISTORY_CENSUS_SCHEMA",
    "HISTORY_CENSUS_STATE_ALL_HISTORY",
    "HISTORY_CENSUS_STATE_NO_CHARACTERS",
    "HISTORY_CENSUS_STATE_NO_CHATS",
    "HISTORY_CENSUS_STATE_NO_HISTORY",
    "HISTORY_CENSUS_STATE_SOME_HISTORY",
    "HISTORY_CENSUS_STATES", "NOTES",
    "resolve_face_history_census",
]
