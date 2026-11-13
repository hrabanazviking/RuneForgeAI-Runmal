"""Speaking history resolution (P-161, Part X - DERIVED).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/SPEAKING_HISTORY_2026-11-08.md
and hidden_files/P161_SCOUT.md / P161_DESIGN.md.

What the derivation found: the banked Part X grid had one
empty per-chat cell. P-158 resolves a chat's kept face
history - which faces it showed, in what order, why, and
whether each would still render today - and is silent on
voice. P-157 pairs only the CURRENT face with the
character's voice; P-159 pairs the per-character roster
with voice and its banked record named per-chat speaking
history open after P-158 banks. What did not exist - and
what lives here - is that pairing, in one pure-read
document, of one chat's kept face history with its
character's CURRENT voice resolution:

- the history half is composed from P-158's
  resolve_face_history verbatim WHOLE - every field
  rides (presentation state, current row, every kept
  event verbatim with its provenance and its entry
  state judged against today, the counts, the kept
  window named honestly) with no second history or
  binding law invented;
- the voice half is composed from S512 verbatim in
  substance, exactly as P-157 / P-159 compose it:
  resolve_character_voice for the resolved reference and
  get_character_voice for the stored row, classified
  under the same closed voice-state law (VOICE_STATES),
  the row's named backend carried as ``stored_backend``
  so a fallback is visible, never silent, and the P-109
  affect view carried whole, consumed False and all.

Voice honesty law (binding): S512 stores NO voice
history - there is no versioned row, change log or
per-event voice record anywhere in-tree. The voice half
is therefore TODAY'S resolution only, stated as data by
``voice_scope: current_only`` on every document. No kept
event is ever claimed to have been spoken in today's
voice, and no event carries a per-event voice field:
the pairing joins a kept PAST (faces) with a resolved
PRESENT (voice) and says so plainly.

``paired`` is True exactly when a voice resolved (the
chat has a bound character) and the kept history holds
at least one selection event. A cleared-only or empty
history never pairs; a voice resolving beside an empty
history is stated, never upgraded, and neither half is
ever substituted for the other.

Honest boundaries: Runmal renders NOTHING here and
synthesizes NOTHING. This module performs no lip-sync
or animation (no timing contract exists in-tree), draws,
composites and generates nothing, reads no sprite
bytes, selects nothing, clears nothing, applies no
default and scans no message text. No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

SPEAKING_HISTORY_SCHEMA = "runmal-p161-speaking-history-v1"

VOICE_PROFILE = "profile"
VOICE_PROFILE_FALLBACK = "profile_fallback"
VOICE_DEFAULT = "default_voice"
VOICE_STATES = frozenset({
    VOICE_PROFILE, VOICE_PROFILE_FALLBACK, VOICE_DEFAULT,
})

VOICE_SCOPE = "current_only"

NOTES = (
    "Pairing is data only: this document synthesizes no "
    "audio, renders no face, and performs no lip-sync or "
    "animation - no timing contract exists in-tree. The "
    "kept faces and today's voice are independent "
    "modalities, paired here by their shared key, the "
    "chat's bound character.",
    "The voice is TODAY's resolution only (voice_scope: "
    "current_only): S512 stores no voice history, so no "
    "kept event is ever claimed to have been spoken in "
    "today's voice. A voice always resolves - a missing "
    "profile is the default voice, a partial profile "
    "falls back field by field, and a legacy removed "
    "backend falls back whole - and the voice state "
    "names which happened; resolution is never an error.",
    "Rows are P-092's kept history verbatim, composed "
    "through P-158: entry_state judges each name against "
    "TODAY's set and bindings - history itself is never "
    "rewritten, and a past face is never retroactively "
    "repaired.",
    "The kept window: P-092 keeps at most kept_limit "
    "events and drops the oldest, so this document never "
    "claims a complete record of a chat's faces.",
    "Pure read: this surface selects, clears, applies, "
    "stores and synthesizes nothing, and scans no "
    "message text - a row's message_id is provenance "
    "data only. The affect is P-109 carried data with "
    "consumed False: no TTS backend renders an affect "
    "yet, so the named affect changes no synthesis.",
)


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance (P-157's / P-159's composition): the
    resolved reference, the stored row's existence and
    named backend, the closed voice state, and the P-109
    affect view carried whole. This is TODAY'S
    resolution - S512 keeps no earlier one."""
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


async def resolve_speaking_history(
        session, user_id: str, chat_id: str,
        *, base_dir: Path | None = None) -> dict | None:
    """The speaking history document for one chat.

    None when the chat is missing or foreign (P-158's
    resolve law - existence never leaks). Otherwise the
    envelope described in the module docstring: P-158's
    face-history document composed whole, the bound
    character's voice resolved under S512 as TODAY'S
    resolution only (``voice_scope: current_only``;
    ``voice`` is None exactly when the chat has no bound
    character), and ``paired`` stating plainly whether a
    resolved voice and a kept selection history stand
    together.
    """
    from runmal.faces.history import resolve_face_history

    history = await resolve_face_history(
        session, user_id, chat_id, base_dir=base_dir)
    if history is None:
        return None
    character_id = history["character_id"]
    voice = None
    if character_id is not None:
        voice = await _voice_half(session, user_id, character_id)
    return {
        "schema": SPEAKING_HISTORY_SCHEMA,
        "chat_id": history["chat_id"],
        "character_id": character_id,
        "presentation_state": history["presentation_state"],
        "current": history["current"],
        "events": history["events"],
        "event_count": history["event_count"],
        "selection_count": history["selection_count"],
        "cleared_count": history["cleared_count"],
        "still_ready_count": history["still_ready_count"],
        "kept_limit": history["kept_limit"],
        "at_kept_limit": history["at_kept_limit"],
        "voice": voice,
        "voice_scope": VOICE_SCOPE,
        "paired": bool(voice is not None
                       and history["selection_count"] > 0),
        "notes": list(NOTES),
    }


__all__ = [
    "NOTES", "SPEAKING_HISTORY_SCHEMA", "VOICE_DEFAULT",
    "VOICE_PROFILE", "VOICE_PROFILE_FALLBACK", "VOICE_SCOPE",
    "VOICE_STATES", "resolve_speaking_history",
]
