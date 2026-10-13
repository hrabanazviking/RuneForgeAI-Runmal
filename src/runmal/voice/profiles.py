"""Per-character voice profiles (S512).

Personas carry a TTS backend/voice/params REFERENCE with fallback
(VOICE_ARCHITECTURE §8). Resolution order:

1. the character's own stored voice profile (complete entries win);
2. field-level fallback to :data:`DEFAULT_VOICE` for anything unset
   (empty backend/voice, missing profile row);
3. never the chat backend: voice selection is an independent modality
   (BACKEND_CONTRACT §1) — the acceptance test proves a persona switch
   changes the voice while the chat profile stays byte-identical.

ADR-0005 (2026-10-13): TTS is multi-backend and Kokoro was REMOVED
from the product. A stored profile naming a backend that no longer
exists (a legacy ``kokoro-onnx`` row) resolves through this same
fallback path to the default backend — its voice ids are meaningless
to any surviving engine, so the whole reference falls back; it never
errors and never resurrects the removed engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Character, CharacterVoiceProfile
from runmal.voice.backends import KNOWN_TTS_BACKENDS as _REGISTRY_TTS_BACKENDS
from runmal.voice.tts import VoiceInfo

#: Prompt transcript for the default zero-shot voice (corpus line 1;
#: the matching reference wav is the vendored default prompt asset —
#: see profiles/CosyVoice prompt resolution in backends.py).
DEFAULT_PROMPT_TEXT = "Hello, wanderer. The wind carried whispers of your arrival."

#: Fallback voice when a character has no (or a partial) voice profile.
#: CosyVoice zero-shot (ADR-0005 default-shipped backend); the prompt
#: wav resolves at synthesis time from the profile params or the
#: vendored default prompt asset.
DEFAULT_VOICE = VoiceInfo(voice_id="cosyvoice-zero-shot", language="en-us",
                          backend_key="cosyvoice",
                          prompt_text=DEFAULT_PROMPT_TEXT)
#: Selectable TTS backends = the ADR-0005 registry + the fake.
KNOWN_TTS_BACKENDS = _REGISTRY_TTS_BACKENDS


@dataclass(frozen=True)
class CharacterVoice:
    tts_backend: str
    voice_id: str
    language: str
    params: dict

    def to_voice_info(self) -> VoiceInfo:
        return VoiceInfo(
            voice_id=self.voice_id, language=self.language,
            backend_key=self.tts_backend,
            prompt_text=str(self.params.get("prompt_text", "") or ""),
            prompt_wav=str(self.params.get("prompt_wav", "") or ""))


async def set_character_voice(
    session: AsyncSession, user_id: str, character_id: str, *,
    tts_backend: str = "", voice_id: str = "", language: str = "en-us",
    params: dict | None = None,
) -> CharacterVoiceProfile:
    character = await session.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError(f"unknown character: {character_id}")
    if tts_backend and tts_backend not in KNOWN_TTS_BACKENDS:
        raise ValueError(f"unknown TTS backend: {tts_backend}")
    row = await session.get(CharacterVoiceProfile, character_id)
    if row is None:
        row = CharacterVoiceProfile(character_id=character_id, user_id=user_id)
        session.add(row)
    row.tts_backend = tts_backend
    row.voice_id = voice_id
    row.language = language or "en-us"
    row.params_json = json.dumps(params or {}, sort_keys=True)
    row.updated_at = datetime.now(UTC).isoformat()
    await session.commit()
    return row


async def get_character_voice(
    session: AsyncSession, user_id: str, character_id: str
) -> CharacterVoiceProfile | None:
    row = await session.get(CharacterVoiceProfile, character_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def delete_character_voice(
    session: AsyncSession, user_id: str, character_id: str
) -> bool:
    row = await get_character_voice(session, user_id, character_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def resolve_character_voice(
    session: AsyncSession, user_id: str, character_id: str
) -> CharacterVoice:
    """Resolve with field-level fallback to DEFAULT_VOICE."""
    row = await get_character_voice(session, user_id, character_id)
    if row is None:
        return CharacterVoice(DEFAULT_VOICE.backend_key, DEFAULT_VOICE.voice_id,
                              DEFAULT_VOICE.language, {})
    try:
        params = json.loads(row.params_json or "{}")
    except json.JSONDecodeError:
        params = {}
    backend = row.tts_backend or ""
    voice_id = row.voice_id or ""
    if backend and backend not in KNOWN_TTS_BACKENDS:
        # Legacy/removed backend (e.g. a stored 'kokoro-onnx' profile):
        # the whole voice reference falls back to the default — never
        # an error, never the removed engine.
        backend = DEFAULT_VOICE.backend_key
        voice_id = DEFAULT_VOICE.voice_id
    return CharacterVoice(
        tts_backend=backend or DEFAULT_VOICE.backend_key,
        voice_id=voice_id or DEFAULT_VOICE.voice_id,
        language=row.language or DEFAULT_VOICE.language,
        params=params if isinstance(params, dict) else {},
    )
