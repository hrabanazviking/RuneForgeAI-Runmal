"""Character speaking history (P-163, Part X - DERIVED).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/CHARACTER_SPEAKING_HISTORY_
2026-11-08.md and hidden_files/P163_SCOUT.md /
P163_DESIGN.md.

What the derivation found: the Part X grid resolves, per
chat, the current face (P-155), the current face + voice
(P-157), the kept history (P-158) and the kept history +
today's voice (P-161), and, per character, the roster
(P-156), the speaking roster (P-159), the current-face
chats board (P-160) and the kept-history board (P-162,
banked after this slice's base). The one subject x time
x voice cell no surface fills is CHARACTER x HISTORY x
SPEAKING: P-162's own design weighed this pairing,
declined it as the later slice (the silent cell lands
first in every grid row) and named it open under P-161's
voice honesty law. What lives here is that pairing:

- one row per owned chat bound to this character, in the
  chats service's own order (creation order), carrying
  the chat's title and message count as the chats service
  states them;
- each row is that chat's P-158 history document composed
  verbatim in substance - the kept events whole with
  their provenance, each judged against today under
  P-158's closed entry-state law, the counts and the kept
  window exactly as P-158 states them. P-162 is not on
  this slice's base, so the board is composed from P-158
  directly, exactly as P-162 composes it;
- the board classified under a closed law
  (SPEAKING_BOARD_STATES) that says honestly how the kept
  history is spread across the character's chats, with
  the totals summed from P-158's own arithmetic;
- the character's CURRENT voice resolution composed from
  S512 verbatim in substance, exactly as P-157 / P-159 /
  P-161 compose it, stated ONCE at board level: S512 keys
  voice by character, so the voice is identical for every
  row, and repeating it per row or per event would imply
  per-chat or per-event voice records that do not exist.

Voice honesty law (binding): S512 stores NO voice
history - there is no versioned row, change log or
per-event voice record anywhere in-tree. The voice half
is therefore TODAY'S resolution only, stated as data by
``voice_scope: current_only`` on every document. No kept
event in any chat is ever claimed to have been spoken in
today's voice, and no row or event carries a per-event
voice field: the pairing joins a kept PAST (faces across
the character's chats) with a resolved PRESENT (voice)
and says so plainly.

``paired`` is True exactly when a voice resolved (always,
for an existing character - a missing profile is the
default voice) and the board's kept history holds at
least one selection event. A cleared-only or empty
history never pairs; a voice resolving beside an empty
history is stated, never upgraded, and neither half is
ever substituted for the other.

Events are never merged into one cross-chat stream:
interleaving chats would invent an ordering no owner
recorded. They stay grouped under the chat that made
them, in that chat's own order.

Honest boundaries: Runmal renders NOTHING here and
synthesizes NOTHING, and a character has NO single face
history stream - selection is per chat and always an
explicit act (P-092's standing law). This module performs
no lip-sync or animation (no timing contract exists
in-tree), draws, composites and generates nothing, reads
no sprite bytes, selects nothing, clears nothing, applies
no default and scans no message text. It is a pure read
over the owning surfaces: get_character, list_chats,
resolve_face_history and the S512 voice reads are
composed verbatim, and no second history, binding,
selection, asset or voice law is invented. No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

CHARACTER_SPEAKING_HISTORY_SCHEMA = (
    "runmal-p163-character-speaking-history-v1")

SPEAKING_BOARD_STATE_NO_CHATS = "no_chats"
SPEAKING_BOARD_STATE_NO_HISTORY = "no_history"
SPEAKING_BOARD_STATE_SOME_HISTORY = "some_history"
SPEAKING_BOARD_STATE_ALL_HISTORY = "all_history"
SPEAKING_BOARD_STATES = frozenset({
    SPEAKING_BOARD_STATE_NO_CHATS,
    SPEAKING_BOARD_STATE_NO_HISTORY,
    SPEAKING_BOARD_STATE_SOME_HISTORY,
    SPEAKING_BOARD_STATE_ALL_HISTORY,
})

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
    "character.",
    "The voice is TODAY's resolution only (voice_scope: "
    "current_only): S512 stores no voice history, so no "
    "kept event in any chat is ever claimed to have been "
    "spoken in today's voice. The voice is stated once, "
    "at board level, because S512 keys voice by "
    "character - never per chat and never per event. A "
    "voice always resolves - a missing profile is the "
    "default voice, a partial profile falls back field "
    "by field, and a legacy removed backend falls back "
    "whole - and the voice state names which happened; "
    "resolution is never an error.",
    "Every row is P-158's history document for that "
    "chat, composed verbatim: entry_state judges each "
    "name against TODAY's set and bindings - history "
    "itself is never rewritten, and no second history "
    "or binding law is invented here. Events stay "
    "grouped under the chat that made them, in that "
    "chat's own order; they are never merged into one "
    "cross-chat stream.",
    "The kept window applies per chat: P-092 keeps at "
    "most kept_limit events for each chat and drops "
    "that chat's oldest, so this board never claims a "
    "complete record of a character's faces.",
    "Pure read, owner scoped: only the owner's chats "
    "bound to this one character appear; this surface "
    "selects, clears, applies, stores and synthesizes "
    "nothing, and scans no message text - a row's "
    "message_id is provenance data only. The affect is "
    "P-109 carried data with consumed False: no TTS "
    "backend renders an affect yet, so the named affect "
    "changes no synthesis.",
)


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance (P-157's / P-159's / P-161's composition):
    the resolved reference, the stored row's existence
    and named backend, the closed voice state, and the
    P-109 affect view carried whole. This is TODAY'S
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


async def resolve_character_speaking_history(
        session, user_id: str, character_id: str,
        *, base_dir: Path | None = None) -> dict | None:
    """The speaking-history board for one character.

    None when the character is missing, foreign or
    deleted (the character service's law - existence
    never leaks). Otherwise the envelope described in
    the module docstring: the character's own facts
    verbatim, one row per owned chat bound to the
    character in the chats service's order with P-158's
    history document composed verbatim in substance per
    chat, the board classified under
    SPEAKING_BOARD_STATES, the totals summed from
    P-158's own counts, and the character's voice
    resolved under S512 as TODAY'S resolution only
    (``voice_scope: current_only``, stated once at board
    level), with ``paired`` stating plainly whether a
    resolved voice and a kept selection history stand
    together for this character.
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
        state = SPEAKING_BOARD_STATE_NO_CHATS
    elif chats_with_history == 0:
        state = SPEAKING_BOARD_STATE_NO_HISTORY
    elif chats_with_history == len(rows):
        state = SPEAKING_BOARD_STATE_ALL_HISTORY
    else:
        state = SPEAKING_BOARD_STATE_SOME_HISTORY
    voice = await _voice_half(session, user_id, character_id)
    selection_count = sum(row["selection_count"] for row in rows)
    return {
        "schema": CHARACTER_SPEAKING_HISTORY_SCHEMA,
        "character_id": character_id,
        "character": character_to_dict(character),
        "state": state,
        "chats": rows,
        "chat_count": len(rows),
        "chats_with_history_count": chats_with_history,
        "event_count": sum(row["event_count"] for row in rows),
        "selection_count": selection_count,
        "cleared_count": sum(row["cleared_count"] for row in rows),
        "still_ready_count": sum(
            row["still_ready_count"] for row in rows),
        "chats_at_kept_limit": sum(
            1 for row in rows if row["at_kept_limit"]),
        "kept_limit": ex.MAX_HISTORY_KEPT,
        "voice": voice,
        "voice_scope": VOICE_SCOPE,
        "paired": bool(voice is not None and selection_count > 0),
        "notes": list(NOTES),
    }


__all__ = [
    "CHARACTER_SPEAKING_HISTORY_SCHEMA", "NOTES",
    "SPEAKING_BOARD_STATE_ALL_HISTORY",
    "SPEAKING_BOARD_STATE_NO_CHATS",
    "SPEAKING_BOARD_STATE_NO_HISTORY",
    "SPEAKING_BOARD_STATE_SOME_HISTORY", "SPEAKING_BOARD_STATES",
    "VOICE_DEFAULT", "VOICE_PROFILE", "VOICE_PROFILE_FALLBACK",
    "VOICE_SCOPE", "VOICE_STATES",
    "resolve_character_speaking_history",
]
