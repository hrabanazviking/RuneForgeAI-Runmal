"""Face speaking census (P-167, Part X - DERIVED).

The roadmap gives Part X one line only ("Faces That
Speak", P-155..P-168); this slice's scope is derived
from Runmal's own in-tree record - see
docs/FACE_SPEAKING_CENSUS_2026-11-08.md and
hidden_files/P167_SCOUT.md / P167_DESIGN.md.

What the derivation found: the banked Part X grid
fills every chat-keyed cell and every character-keyed
cell, P-166 (banking in parallel, not on this base)
takes the character speaking-chats board, and the
owner row stands silent-only - P-164's current census
and P-165's history census - with its two speaking
cells named open since P-164 under one objection,
restated in P-165's banked record as unanswered:
voice is per character under S512, so an owner
speaking census would blur per-character voice into
one pairing. This slice is the last before the
P-168 gate, and it takes OWNER x CURRENT x SPEAKING
in the one shape that answers that objection BY
CONSTRUCTION:

- one row per owned character, in the characters
  service's own order, composing P-164's census row
  verbatim in substance (P-160's board: the board
  state, the chats rows whole, the counts);
- PLUS, inside that row only, that character's OWN
  current S512 voice resolution, composed verbatim
  in substance exactly as P-157 / P-159 / P-161 /
  P-163 compose it, and that row's OWN paired flag
  (P-157's pairing law judged per row);
- the census envelope carries NO voice, NO paired,
  NO voice_scope and NO face: there is no owner-level
  voice for any row's voice to blur into, and the
  only voice-derived owner number is a COUNT of
  paired rows, carrying no voice value;
- the census state stays the FACE axis, judged
  exactly as P-164 judges; voice always resolves for
  an existing character, so no voice census state
  exists.

The owner speaking-HISTORY census is NOT taken: it
remains open, named for the P-168 gate (reasons in
the design) - the grid takes current speaking before
history speaking in every row, and the per-row voice
discipline is proven here, where no past can be
mis-dressed, first.

Honest boundaries: Runmal renders NOTHING here and
synthesizes NOTHING. Both halves are current, so -
like P-157 / P-159 / P-166 - this document carries
no voice_scope: current_only guards a present voice
beside a past, and this census reads no past; the
law is untouched wherever history is involved. No
chat row carries a voice field - S512 keys voice by
character, and a per-chat field would fabricate
per-chat voice records. There is NO owner-wide face:
selection is per chat and always an explicit act
(P-092). This module performs no lip-sync or
animation, draws and generates nothing, reads no
sprite bytes, selects nothing, applies no default
and scans no message text. It is a pure read over
the owning surfaces: list_characters, P-160's board
resolver and the S512 voice reads are composed
verbatim, and no second binding, selection, asset
or voice law is invented. No store, no migration:
head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

SPEAKING_CENSUS_SCHEMA = "runmal-p167-face-speaking-census-v1"

SPEAKING_CENSUS_STATE_NO_CHARACTERS = "no_characters"
SPEAKING_CENSUS_STATE_NO_CHATS = "no_chats"
SPEAKING_CENSUS_STATE_NONE_READY = "none_ready"
SPEAKING_CENSUS_STATE_SOME_READY = "some_ready"
SPEAKING_CENSUS_STATE_ALL_READY = "all_ready"
SPEAKING_CENSUS_STATES = frozenset({
    SPEAKING_CENSUS_STATE_NO_CHARACTERS,
    SPEAKING_CENSUS_STATE_NO_CHATS,
    SPEAKING_CENSUS_STATE_NONE_READY,
    SPEAKING_CENSUS_STATE_SOME_READY,
    SPEAKING_CENSUS_STATE_ALL_READY,
})

VOICE_PROFILE = "profile"
VOICE_PROFILE_FALLBACK = "profile_fallback"
VOICE_DEFAULT = "default_voice"
VOICE_STATES = frozenset({
    VOICE_PROFILE, VOICE_PROFILE_FALLBACK, VOICE_DEFAULT,
})

NOTES = (
    "Pairing is data only: this census synthesizes no "
    "audio, renders no face, and performs no lip-sync "
    "or animation - no timing contract exists "
    "in-tree. Each row's current faces and that "
    "character's current voice are independent "
    "modalities, paired inside the row by their "
    "shared key, the character.",
    "Voice is stated per character row only, never as "
    "one owner-level pairing: S512 keys voice by "
    "character, so each row carries that character's "
    "own resolution under the closed voice-state law, "
    "no row's voice is any other row's, and the "
    "census itself names no voice - a voice always "
    "resolves (a missing profile is the default "
    "voice, a partial profile falls back field by "
    "field, a legacy removed backend falls back "
    "whole), and the row's voice state names which "
    "happened.",
    "Every character row's face half is P-160's "
    "face-chats board composed verbatim, exactly as "
    "P-164's census composes it: no second binding, "
    "selection or fallback law is invented here, and "
    "the full entries roster stays P-155's / P-156's "
    "document.",
    "There is no owner-wide or character-wide single "
    "face: selection is per chat and stays P-092's "
    "explicit act - this read selects, applies, "
    "clears and scans nothing, and no message text "
    "is read.",
    "This census is current only: it reads no kept "
    "history (the owner speaking-history census "
    "remains open) and claims no earlier voice for "
    "any character. Pure read, owner scoped: only "
    "the caller's own characters and chats appear; "
    "this surface stores, generates and animates "
    "nothing, and the affect in each row's voice is "
    "P-109 carried data with consumed False.",
)


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance (P-157's / P-159's / P-161's / P-163's
    composition): the resolved reference, the stored
    row's existence and named backend, the closed
    voice state, and the P-109 affect view carried
    whole. This is TODAY'S resolution for THIS
    character only - S512 keys voice by character and
    keeps no other subject's voice here."""
    from runmal.voice import profiles as voice_profiles
    from runmal.voice.affects import affect_from_params, affect_view

    row = await voice_profiles.get_character_voice(
        session, user_id, character_id)
    resolved = await voice_profiles.resolve_character_voice(
        session, user_id, character_id)
    params = resolved.params if isinstance(resolved.params, dict) else {}
    if row is None:
        state = VOICE_DEFAULT
        stored_backend = None
    else:
        stored_backend = row.tts_backend or ""
        if stored_backend and stored_backend not in voice_profiles.KNOWN_TTS_BACKENDS:
            state = VOICE_PROFILE_FALLBACK
        else:
            state = VOICE_PROFILE
    affect_name, affect_source = affect_from_params(params)
    return {
        "state": state,
        "profile_exists": row is not None,
        "stored_backend": stored_backend,
        "tts_backend": resolved.tts_backend,
        "voice_id": resolved.voice_id,
        "language": resolved.language,
        "params": params,
        "affect": affect_view(affect_name, affect_source),
    }


async def resolve_face_speaking_census(session, user_id: str,
                                       *, base_dir: Path | None = None,
                                       ) -> dict:
    """The speaking census for one owner.

    Always a document, never None: the subject is
    the caller themselves, so there is no foreign
    subject whose existence could leak, and an owner
    with no characters gets the honest empty census
    (state no_characters). Otherwise the envelope
    described in the module docstring: one row per
    owned character in the characters service's
    order with P-164's census row composed verbatim
    in substance PLUS that character's own current
    voice and its own paired flag, the census
    classified under SPEAKING_CENSUS_STATES (the face
    axis only), and the counts summed from the
    boards' own arithmetic plus the count of paired
    rows. No voice stands at census level.
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
        voice = await _voice_half(session, user_id, character.id)
        ready_count = board_doc["ready_count"]
        rows.append({
            "character_id": board_doc["character_id"],
            "character": board_doc["character"],
            "board_state": board_doc["state"],
            "chats": board_doc["chats"],
            "chat_count": board_doc["chat_count"],
            "ready_count": ready_count,
            "selection_count": board_doc["selection_count"],
            "unbound_count": board_doc["unbound_count"],
            "voice": voice,
            "paired": bool(voice is not None and ready_count > 0),
        })
    chat_count = sum(row["chat_count"] for row in rows)
    ready_count = sum(row["ready_count"] for row in rows)
    if not rows:
        state = SPEAKING_CENSUS_STATE_NO_CHARACTERS
    elif chat_count == 0:
        state = SPEAKING_CENSUS_STATE_NO_CHATS
    elif ready_count == 0:
        state = SPEAKING_CENSUS_STATE_NONE_READY
    elif ready_count == chat_count:
        state = SPEAKING_CENSUS_STATE_ALL_READY
    else:
        state = SPEAKING_CENSUS_STATE_SOME_READY
    return {
        "schema": SPEAKING_CENSUS_SCHEMA,
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
            "paired_character_count": sum(
                1 for row in rows if row["paired"]),
        },
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "SPEAKING_CENSUS_SCHEMA",
    "SPEAKING_CENSUS_STATE_ALL_READY",
    "SPEAKING_CENSUS_STATE_NO_CHARACTERS",
    "SPEAKING_CENSUS_STATE_NO_CHATS",
    "SPEAKING_CENSUS_STATE_NONE_READY",
    "SPEAKING_CENSUS_STATE_SOME_READY",
    "SPEAKING_CENSUS_STATES", "VOICE_DEFAULT",
    "VOICE_PROFILE", "VOICE_PROFILE_FALLBACK",
    "VOICE_STATES", "resolve_face_speaking_census",
]
