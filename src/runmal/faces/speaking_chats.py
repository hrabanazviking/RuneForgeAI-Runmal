"""Character speaking chats (P-166, Part X - DERIVED).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/CHARACTER_SPEAKING_CHATS_
2026-11-08.md and hidden_files/P166_SCOUT.md /
P166_DESIGN.md.

What the derivation found: the Part X grid resolves, per
chat, the current face (P-155), the current face + voice
(P-157), the kept history (P-158) and the kept history +
today's voice (P-161), and, per character, the roster
(P-156), the speaking roster (P-159), the current-face
chats board (P-160), the kept-history board (P-162) and
the speaking-history board (P-163), and, per owner, the
current census (P-164). The one subject x time x voice
cell no surface fills is CHARACTER x CURRENT x SPEAKING:
P-160 weighed the speaking board and declined it, and
P-162, P-163 and P-164 each named it open. What lives
here is that pairing:

- the board half is P-160's character face-chats board
  composed whole - one row per owned chat bound to this
  character, in the chats service's own order, each row
  carrying P-155's presentation truth verbatim (the
  presentation state, the current row, its problem, and
  the current descriptor named as ``face`` only when
  that chat is ready), the board state and the counts
  exactly as P-160 states them;
- the character's CURRENT voice resolution composed from
  S512 verbatim in substance, exactly as P-157 / P-159 /
  P-161 / P-163 compose it, stated ONCE at board level:
  S512 keys voice by character, so the voice is identical
  for every row, and repeating it per row would imply
  per-chat voice records that do not exist.

Both halves are CURRENT: this board reads no kept
history, so the P-161 / P-163 ``voice_scope:
current_only`` field - which exists to keep a present
voice from being claimed for past events - has no past
here to guard. Following P-157 / P-159, the two earlier
current pairings, this document carries no voice_scope;
its notes state plainly that the voice is the character's
current resolution. The current_only law itself is
untouched and binds wherever history is involved.

``paired`` is True exactly when a voice resolved (always,
for an existing character - a missing profile is the
default voice) and at least one of the character's chats
shows a ready face. A board whose chats hold selections
but none ready never pairs; a voice resolving beside an
empty or unready board is stated, never upgraded, and
neither half is ever substituted for the other.

Honest boundaries: Runmal renders NOTHING here and
synthesizes NOTHING, and a character has NO single
current face - selection is per chat and always an
explicit act (P-092's standing law). This module performs
no lip-sync or animation (no timing contract exists
in-tree), draws, composites and generates nothing, reads
no sprite bytes, selects nothing, applies no default and
scans no message text. It is a pure read over the owning
surfaces: P-160's board resolver and the S512 voice reads
are composed verbatim, and no second presentation,
binding, selection, asset or voice law is invented. No
store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

SPEAKING_CHATS_SCHEMA = "runmal-p166-character-speaking-chats-v1"

SPEAKING_CHATS_STATE_NO_CHATS = "no_chats"
SPEAKING_CHATS_STATE_NONE_READY = "none_ready"
SPEAKING_CHATS_STATE_SOME_READY = "some_ready"
SPEAKING_CHATS_STATE_ALL_READY = "all_ready"
SPEAKING_CHATS_STATES = frozenset({
    SPEAKING_CHATS_STATE_NO_CHATS, SPEAKING_CHATS_STATE_NONE_READY,
    SPEAKING_CHATS_STATE_SOME_READY, SPEAKING_CHATS_STATE_ALL_READY,
})

VOICE_PROFILE = "profile"
VOICE_PROFILE_FALLBACK = "profile_fallback"
VOICE_DEFAULT = "default_voice"
VOICE_STATES = frozenset({
    VOICE_PROFILE, VOICE_PROFILE_FALLBACK, VOICE_DEFAULT,
})

NOTES = (
    "Pairing is data only: this document synthesizes no "
    "audio, renders no face, and performs no lip-sync or "
    "animation - no timing contract exists in-tree. The "
    "current faces and the current voice are independent "
    "modalities, paired here by their shared key, the "
    "character.",
    "The voice is the character's CURRENT S512 "
    "resolution, stated once, at board level, because "
    "S512 keys voice by character - never per chat. A "
    "voice always resolves - a missing profile is the "
    "default voice, a partial profile falls back field "
    "by field, and a legacy removed backend falls back "
    "whole - and the voice state names which happened; "
    "resolution is never an error. This board reads no "
    "kept history, so no past event is dressed in any "
    "voice here.",
    "Every row is P-160's face-chats board composed "
    "verbatim - P-155's presentation document judged "
    "per chat: no second binding, selection or fallback "
    "law is invented here, face is a chat's current "
    "selection only when that chat is ready, and "
    "fallbacks are never silently substituted.",
    "A character has no single current face: selection "
    "is per chat and stays P-092's explicit act - this "
    "read selects, applies, clears and scans nothing, "
    "and no message text is read.",
    "Pure read, owner scoped: only the owner's chats "
    "bound to this one character appear; this surface "
    "stores, generates and animates nothing. The affect "
    "is P-109 carried data with consumed False: no TTS "
    "backend renders an affect yet, so the named affect "
    "changes no synthesis.",
)


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance (P-157's / P-159's / P-161's / P-163's
    composition): the resolved reference, the stored
    row's existence and named backend, the closed voice
    state, and the P-109 affect view carried whole. This
    is the character's CURRENT resolution."""
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


async def resolve_character_speaking_chats(
        session, user_id: str, character_id: str,
        *, base_dir: Path | None = None) -> dict | None:
    """The speaking-chats board for one character.

    None when the character is missing, foreign or
    deleted (P-160's law, via the character service -
    existence never leaks). Otherwise the envelope
    described in the module docstring: the character's
    own facts verbatim (via P-160), P-160's board rows
    whole in the chats service's order, the board
    classified under SPEAKING_CHATS_STATES (P-160's own
    judgement, carried), the counts carried from P-160's
    own arithmetic, and the character's voice resolved
    under S512 as its CURRENT resolution, stated once
    at board level, with ``paired`` stating plainly
    whether a resolved voice and at least one ready
    face stand together for this character.
    """
    from runmal.faces.chats import resolve_character_face_chats

    board_doc = await resolve_character_face_chats(
        session, user_id, character_id, base_dir=base_dir)
    if board_doc is None:
        return None
    voice = await _voice_half(session, user_id, character_id)
    return {
        "schema": SPEAKING_CHATS_SCHEMA,
        "character_id": board_doc["character_id"],
        "character": board_doc["character"],
        "state": board_doc["state"],
        "chats": board_doc["chats"],
        "chat_count": board_doc["chat_count"],
        "ready_count": board_doc["ready_count"],
        "selection_count": board_doc["selection_count"],
        "unbound_count": board_doc["unbound_count"],
        "voice": voice,
        "paired": bool(voice is not None and board_doc["ready_count"] > 0),
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "SPEAKING_CHATS_SCHEMA",
    "SPEAKING_CHATS_STATE_ALL_READY",
    "SPEAKING_CHATS_STATE_NO_CHATS",
    "SPEAKING_CHATS_STATE_NONE_READY",
    "SPEAKING_CHATS_STATE_SOME_READY", "SPEAKING_CHATS_STATES",
    "VOICE_DEFAULT", "VOICE_PROFILE", "VOICE_PROFILE_FALLBACK",
    "VOICE_STATES", "resolve_character_speaking_chats",
]
