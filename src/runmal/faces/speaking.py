"""Speaking-face resolution (P-157, Part X - DERIVED scope).

The roadmap gives Part X one line only ("Faces That Speak",
P-155..P-168); this slice's scope is derived from Runmal's
own in-tree record - see docs/SPEAKING_FACE_2026-11-08.md
and hidden_files/P157_SCOUT.md / P157_DESIGN.md.

What the derivation found: P-155 resolves the face a chat
shows and P-156 the faces a character can show, and
neither touches voice - the faces of Part X are silent so
far, under a part titled "Faces That Speak". The speaking
half already exists as banked truth on the other side of
the tree: S512 (voice/profiles.py) resolves a character's
voice as a backend/voice/params REFERENCE with field-level
fallback to the default voice (a legacy removed backend
falls back whole; resolution never errors), and P-109
(voice/affects.py) carries a voice affect as data with
``consumed: False`` stated plainly. Voice selection is an
independent modality (S512 doctrine): it is never the
chat backend and never derived from the face. What did
not exist - and what lives here - is the PAIRING, in one
pure-read document, of the face that would be seen with
the voice that would be heard, joined on their one shared
key: the chat's bound character.

- the face half is composed from P-092's inspect_state
  verbatim in substance and classified under the SAME
  closed five-state law P-155 uses, with ``face`` naming
  the current entry's descriptor only when ready - the
  full entries roster is P-155's / P-156's document and
  is not restated here;
- the voice half is composed from S512 verbatim:
  resolve_character_voice for the resolved reference and
  get_character_voice for the stored row, classified
  under a closed voice-state law (VOICE_STATES) that
  names whether the reference is a stored profile, a
  stored profile whose legacy backend fell back whole,
  or the default voice outright; the P-109 affect view
  rides whole, consumed False and all;
- ``paired`` is True exactly when the face is ready and
  a voice resolved - the halves are independent and
  neither is ever substituted for the other.

Honest boundaries: this module synthesizes NO audio,
renders NO face, and performs NO lip-sync or animation -
no timing contract exists in-tree to sync by. It selects
nothing, applies no default, stores nothing and scans no
message text (P-092's standing laws). No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from pathlib import Path

SPEAKING_SCHEMA = "runmal-p157-speaking-face-v1"

STATE_READY = "ready"
STATE_CURRENT_UNBOUND = "current_unbound"
STATE_NO_SELECTION = "no_selection"
STATE_NO_SET = "no_set"
STATE_NO_CHARACTER = "no_character"
FACE_STATES = frozenset({
    STATE_READY, STATE_CURRENT_UNBOUND, STATE_NO_SELECTION,
    STATE_NO_SET, STATE_NO_CHARACTER,
})
PROBLEM_NOT_DECLARED = "not_declared"

VOICE_PROFILE = "profile"
VOICE_PROFILE_FALLBACK = "profile_fallback"
VOICE_DEFAULT = "default_voice"
VOICE_STATES = frozenset({
    VOICE_PROFILE, VOICE_PROFILE_FALLBACK, VOICE_DEFAULT,
})

NOTES = (
    "Pairing is data only: this document synthesizes no "
    "audio, renders no face, and performs no lip-sync or "
    "animation - no timing contract exists in-tree. Face "
    "and voice are independent modalities, paired here by "
    "their shared key, the chat's bound character.",
    "Selection stays P-092's explicit act and voice "
    "resolution stays S512's fallback law: this read "
    "selects, applies, stores and synthesizes nothing, "
    "and scans no message text to guess an expression.",
    "A voice always resolves: a missing profile is the "
    "default voice, a partial profile falls back field "
    "by field, and a legacy removed backend falls back "
    "whole - the voice state names which happened, and "
    "resolution is never an error.",
    "The affect is P-109 carried data with consumed "
    "False: no TTS backend renders an affect yet, so the "
    "named affect changes no synthesis.",
    "face is the current selection only when it is "
    "bound; when face is None the voice still resolves "
    "on its own law - a character can speak without a "
    "ready face, and neither half is ever silently "
    "substituted for the other.",
)


def _asset_urls(character_id: str, asset: dict | None) -> tuple[str | None, str | None]:
    if not asset:
        return None, None
    asset_id = asset.get("id")
    if not asset_id:
        return None, None
    base = f"/api/v1/characters/{character_id}/assets/{asset_id}"
    return f"{base}/content", f"{base}/thumbnail"


def _descriptor(character_id: str, row: dict) -> dict:
    entry = row["entry"]
    bound = bool(row["bound"])
    asset = row["asset"]
    content_url, thumbnail_url = (
        _asset_urls(character_id, asset) if bound else (None, None))
    return {
        "name": entry["name"],
        "label": entry["label"],
        "notes": entry["notes"],
        "bound": bound,
        "problem": row["problem"],
        "asset": asset,
        "renderable": bound,
        "content_url": content_url,
        "thumbnail_url": thumbnail_url,
    }


async def _voice_half(session, user_id: str, character_id: str) -> dict:
    """The S512 voice half for one character, verbatim in
    substance: the resolved reference, the stored row's
    existence and named backend, the closed voice state,
    and the P-109 affect view carried whole."""
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


async def resolve_speaking_face(session, user_id: str, chat_id: str,
                                *, base_dir: Path | None = None) -> dict | None:
    """The speaking-face document for one chat.

    None when the chat is missing or foreign (P-092's
    inspect law - existence never leaks). Otherwise the
    envelope described in the module docstring: the
    chat's face classified under the P-155 state law
    with the current descriptor named only when ready,
    the bound character's voice resolved under S512 with
    its P-109 affect carried as data, and ``paired``
    stating plainly whether a ready face and a resolved
    voice stand together.
    """
    from runmal.plugins import expressions as ex

    inspected = await ex.inspect_state(
        session, user_id, chat_id, base_dir=base_dir)
    if inspected is None:
        return None
    character_id = inspected["character_id"]
    by_name = {}
    if character_id:
        by_name = {
            row["entry"]["name"]: _descriptor(character_id, row)
            for row in inspected["bindings"]
        }
    current = inspected["current"]
    current_binding = inspected["current_binding"]
    face = None
    current_problem = None
    if character_id is None:
        state = STATE_NO_CHARACTER
    elif (current is not None and current_binding is not None
          and current_binding["bound"]):
        state = STATE_READY
        face = by_name.get(current["expression"])
    elif current is not None:
        state = STATE_CURRENT_UNBOUND
        current_problem = (current_binding["problem"]
                           if current_binding is not None
                           else PROBLEM_NOT_DECLARED)
    elif inspected["set"] is None:
        state = STATE_NO_SET
    else:
        state = STATE_NO_SELECTION
    voice = None
    if character_id is not None:
        voice = await _voice_half(session, user_id, character_id)
    return {
        "schema": SPEAKING_SCHEMA,
        "chat_id": inspected["chat_id"],
        "character_id": character_id,
        "state": state,
        "current": current,
        "current_problem": current_problem,
        "face": face,
        "voice": voice,
        "paired": bool(state == STATE_READY and voice is not None),
        "notes": list(NOTES),
    }
