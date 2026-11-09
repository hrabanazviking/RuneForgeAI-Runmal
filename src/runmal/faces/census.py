"""Face census (P-164, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That
Speak", P-155..P-168); this slice's scope is derived
from Runmal's own in-tree record - see
docs/FACE_CENSUS_2026-11-08.md and
hidden_files/P164_DESIGN.md.

What the derivation found: the banked Part X grid
fills every chat-keyed cell (P-155 current face,
P-157 speaking face, P-158 kept history, P-161
speaking history) and every character-keyed cell
(P-156 roster, P-159 speaking roster, P-160 current
chats board, P-162 history board), and P-158, P-160
and P-162 each weighed an owner-wide face census and
named it open. The one subject no surface takes is
the OWNER: across all of one owner's characters and
all of their chats, what face is each chat currently
showing, and how many are ready? What lives here is
that composition:

- one row per owned character, in the characters
  service's own order (creation order), composing
  P-160's character face-chats board verbatim in
  substance - the character's own facts, the board
  state under P-160's closed law, and the board's
  rows whole (each chat's P-155 presentation truth);
- the census classified under a closed law
  (CENSUS_STATES) that says honestly, at owner
  level, how many of the owner's chats show a
  ready face;
- the counts summed from the boards' own arithmetic.

Honest boundaries: Runmal renders NOTHING here, and
there is NO owner-wide face - selection is per chat
and always an explicit act (P-092's standing law),
so the census never collapses its rows into one
face. The census is CURRENT only and SILENT: it
reads no kept history (P-158 / P-162 own the past)
and names no voice (P-157 / P-159 / P-161 own the
pairings, under the current_only law where history
is concerned). This module draws, composites,
animates and generates nothing, reads no sprite
bytes, selects nothing, applies no default and
scans no message text. It is a pure read over the
owning surfaces: list_characters and P-160's board
resolver are composed verbatim, and no second
binding, selection or asset law is invented. No
store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

CENSUS_SCHEMA = "runmal-p164-face-census-v1"

CENSUS_STATE_NO_CHARACTERS = "no_characters"
CENSUS_STATE_NO_CHATS = "no_chats"
CENSUS_STATE_NONE_READY = "none_ready"
CENSUS_STATE_SOME_READY = "some_ready"
CENSUS_STATE_ALL_READY = "all_ready"
CENSUS_STATES = frozenset({
    CENSUS_STATE_NO_CHARACTERS, CENSUS_STATE_NO_CHATS,
    CENSUS_STATE_NONE_READY, CENSUS_STATE_SOME_READY,
    CENSUS_STATE_ALL_READY,
})

NOTES = (
    "Runmal renders nothing: this census is data a "
    "client reads; it carries no image bytes - a "
    "ready face's descriptor carries the P-023 "
    "content and thumbnail URLs as data.",
    "Every character row is P-160's face-chats board "
    "composed verbatim: no second binding, selection "
    "or fallback law is invented here, and the full "
    "entries roster stays P-155's / P-156's document.",
    "There is no owner-wide or character-wide single "
    "face: selection is per chat and stays P-092's "
    "explicit act - this read selects, applies, "
    "clears and scans nothing, and no message text "
    "is read.",
    "This census is current only and silent: kept "
    "history is P-158's / P-162's documents and voice "
    "is P-157's / P-159's / P-161's; neither the past "
    "nor any voice is restated or claimed here.",
    "Pure read, owner scoped: only the caller's own "
    "characters and chats appear; this surface "
    "stores, generates and animates nothing.",
)


async def resolve_face_census(session, user_id: str,
                              *, base_dir: Path | None = None,
                              ) -> dict:
    """The current-face census for one owner.

    Always a document, never None: the subject is
    the caller themselves, so there is no foreign
    subject whose existence could leak, and an owner
    with no characters gets the honest empty census
    (state no_characters). Otherwise the envelope
    described in the module docstring: one row per
    owned character in the characters service's
    order with P-160's board composed verbatim in
    substance, the census classified under
    CENSUS_STATES, and the counts summed from the
    boards' own arithmetic.
    """
    from runmal.characters.service import list_characters
    from runmal.faces.chats import resolve_character_face_chats

    rows = []
    characters = await list_characters(session, user_id)
    for character in characters:
        board_doc = await resolve_character_face_chats(
            session, user_id, character.id, base_dir=base_dir)
        if board_doc is None:
            continue
        rows.append({
            "character_id": board_doc["character_id"],
            "character": board_doc["character"],
            "board_state": board_doc["state"],
            "chats": board_doc["chats"],
            "chat_count": board_doc["chat_count"],
            "ready_count": board_doc["ready_count"],
            "selection_count": board_doc["selection_count"],
            "unbound_count": board_doc["unbound_count"],
        })
    chat_count = sum(row["chat_count"] for row in rows)
    ready_count = sum(row["ready_count"] for row in rows)
    if not rows:
        state = CENSUS_STATE_NO_CHARACTERS
    elif chat_count == 0:
        state = CENSUS_STATE_NO_CHATS
    elif ready_count == 0:
        state = CENSUS_STATE_NONE_READY
    elif ready_count == chat_count:
        state = CENSUS_STATE_ALL_READY
    else:
        state = CENSUS_STATE_SOME_READY
    return {
        "schema": CENSUS_SCHEMA,
        "state": state,
        "characters": rows,
        "counts": {
            "character_count": len(rows),
            "characters_with_chats_count": sum(
                1 for row in rows if row["chat_count"] > 0),
            "chat_count": chat_count,
            "ready_count": ready_count,
            "selection_count": sum(
                row["selection_count"] for row in rows),
            "unbound_count": sum(
                row["unbound_count"] for row in rows),
        },
        "notes": list(NOTES),
    }


__all__ = [
    "CENSUS_SCHEMA", "CENSUS_STATE_ALL_READY",
    "CENSUS_STATE_NO_CHARACTERS", "CENSUS_STATE_NO_CHATS",
    "CENSUS_STATE_NONE_READY", "CENSUS_STATE_SOME_READY",
    "CENSUS_STATES", "NOTES", "resolve_face_census",
]
