"""Character speaking roster resolution (P-159, Part X - DERIVED).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/SPEAKING_ROSTER_2026-11-08.md
and hidden_files/P159_DESIGN.md.

What the derivation found: the banked Part X grid had one
empty cell. Per chat, P-155 resolves the faces and P-157
pairs the current face with the character's voice; per
character, P-156 resolves the face roster - and stops
there, silent. Voice resolution is keyed by CHARACTER
(S512, voice/profiles.py): a per-character voice is a
backend/voice/params reference resolved with field-level
fallback to the default voice (a legacy removed backend
falls back whole; resolution never errors), and P-109
carries a voice affect as data with ``consumed: False``.
P-157's own design weighed a per-character chat-less
speaking document and named it open. What did not exist -
and what lives here - is that pairing, in one pure-read
document, of the faces a character CAN show with the
voice it speaks in:

- the roster half is composed from P-156's
  resolve_character_roster verbatim - the same document
  whole (character, set, every entry's descriptor, the
  counts, the state under the same closed ROSTER_STATES
  law, the declared default and the avatar as fallback
  data) with no second roster or binding law invented;
- the voice half is composed from S512 verbatim in
  substance, exactly as P-157 composes it:
  resolve_character_voice for the resolved reference and
  get_character_voice for the stored row, classified
  under the same closed voice-state law (VOICE_STATES),
  the row's named backend carried as ``stored_backend``
  so a fallback is visible, never silent, and the P-109
  affect view carried whole, consumed False and all;
- ``paired`` is True exactly when the roster is ready
  (at least one renderable face) and a voice resolved -
  the halves are independent modalities joined on their
  one shared key, the character, and neither is ever
  substituted for the other.

Honest boundaries: Runmal renders NOTHING here, and this
document names NO current face. Selection is per chat
and always an explicit act (P-092's standing law); a
speaking roster names what a character can show and the
voice it would speak in, never what some chat is
showing - that is P-155's / P-157's chat documents. This
module synthesizes NO audio, performs NO lip-sync or
animation (no timing contract exists in-tree), draws,
composites and generates nothing, reads no sprite
bytes, selects nothing, applies no default and scans no
message text. No store, no migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

SPEAKING_ROSTER_SCHEMA = "runmal-p159-speaking-roster-v1"

VOICE_PROFILE = "profile"
VOICE_PROFILE_FALLBACK = "profile_fallback"
VOICE_DEFAULT = "default_voice"
VOICE_STATES = frozenset({
    VOICE_PROFILE, VOICE_PROFILE_FALLBACK, VOICE_DEFAULT,
})

SELECTION_SCOPE = "per_chat"

NOTES = (
    "Pairing is data only: this document synthesizes no "
    "audio, renders no face, and performs no lip-sync or "
    "animation - no timing contract exists in-tree. Faces "
    "and voice are independent modalities, paired here by "
    "their shared key, the character.",
    "This roster names no current face: expression "
    "selection is per chat and stays P-092's explicit "
    "act - this read selects nothing, applies no "
    "declared default, and scans no message text to "
    "guess an expression. A chat's current face is the "
    "P-155 presentation document's to name.",
    "A voice always resolves: a missing profile is the "
    "default voice, a partial profile falls back field "
    "by field, and a legacy removed backend falls back "
    "whole - the voice state names which happened, and "
    "resolution is never an error.",
    "The affect is P-109 carried data with consumed "
    "False: no TTS backend renders an affect yet, so the "
    "named affect changes no synthesis.",
    "Pure read: this surface stores, generates and "
    "animates nothing; sets, selections and sprite "
    "bytes stay with P-092 and P-023, and voice rows "
    "stay with S512.",
)


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance (P-157's composition): the resolved
    reference, the stored row's existence and named
    backend, the closed voice state, and the P-109
    affect view carried whole."""
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


async def resolve_character_speaking_roster(
        session, user_id: str, character_id: str,
        *, base_dir: Path | None = None) -> dict | None:
    """The speaking roster document for one character.

    None when the character is missing or foreign
    (P-156's roster law - existence never leaks).
    Otherwise the envelope described in the module
    docstring: P-156's roster document composed whole,
    the character's voice resolved under S512 with its
    P-109 affect carried as data, and ``paired`` stating
    plainly whether a renderable face and a resolved
    voice stand together for this character. The
    document carries no current face: selection is
    per chat.
    """
    from runmal.faces.roster import STATE_READY as ROSTER_READY
    from runmal.faces.roster import resolve_character_roster

    roster = await resolve_character_roster(
        session, user_id, character_id, base_dir=base_dir)
    if roster is None:
        return None
    voice = await _voice_half(session, user_id, character_id)
    return {
        "schema": SPEAKING_ROSTER_SCHEMA,
        "character_id": roster["character_id"],
        "character": roster["character"],
        "state": roster["state"],
        "set": roster["set"],
        "entries": roster["entries"],
        "entry_count": roster["entry_count"],
        "bound_count": roster["bound_count"],
        "renderable_count": roster["renderable_count"],
        "unbound_count": roster["unbound_count"],
        "selection_scope": roster["selection_scope"],
        "default_entry": roster["default_entry"],
        "avatar": roster["avatar"],
        "voice": voice,
        "paired": bool(roster["state"] == ROSTER_READY
                       and voice is not None),
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "SELECTION_SCOPE", "SPEAKING_ROSTER_SCHEMA",
    "VOICE_DEFAULT", "VOICE_PROFILE", "VOICE_PROFILE_FALLBACK",
    "VOICE_STATES", "resolve_character_speaking_roster",
]
