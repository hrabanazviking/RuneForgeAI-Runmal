"""S512 — Per-character voice profiles: persona switch selects the
correct voice WITHOUT changing the chat backend; fallback is explicit."""

from __future__ import annotations

import asyncio

import pytest

from runmal.backends import profiles as backend_profiles
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Character
from runmal.db.owners import get_or_create_owner
from runmal.voice.profiles import (
    DEFAULT_VOICE,
    delete_character_voice,
    resolve_character_voice,
    set_character_voice,
)


def setup_db(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def seed(factory):
    async def go():
        async with factory() as session:
            owner = await get_or_create_owner(session)
            yrsa = Character(user_id=owner.id, name="Yrsa", card_json="{}")
            other = Character(user_id=owner.id, name="Other", card_json="{}")
            session.add_all([yrsa, other])
            await session.commit()
            return owner.id, yrsa.id, other.id

    return asyncio.run(go())


def test_resolve_falls_back_to_default_without_profile(tmp_path):
    factory = setup_db(tmp_path)
    owner_id, yrsa_id, _ = seed(factory)

    async def go():
        async with factory() as session:
            return await resolve_character_voice(session, owner_id, yrsa_id)

    resolved = asyncio.run(go())
    assert resolved.voice_id == DEFAULT_VOICE.voice_id
    assert resolved.tts_backend == DEFAULT_VOICE.backend_key


def test_persona_switch_selects_voice_without_touching_chat_backend(tmp_path):
    factory = setup_db(tmp_path)
    owner_id, yrsa_id, other_id = seed(factory)

    async def go():
        async with factory() as session:
            profile = await backend_profiles.create_profile(
                session, owner_id, name="Main", chat_backend="ollama",
                chat_model="llama3.1", embedding_backend="ollama",
                embedding_model="nomic-embed-text")
            before = backend_profiles.profile_to_dict(profile)
            await set_character_voice(
                session, owner_id, yrsa_id, tts_backend="kokoro-onnx",
                voice_id="bf_emma", language="en-gb", params={"speed": 1.1})
            await set_character_voice(
                session, owner_id, other_id, tts_backend="fake-tts",
                voice_id="fake-voice")
            yrsa_voice = await resolve_character_voice(session, owner_id, yrsa_id)
            other_voice = await resolve_character_voice(session, owner_id, other_id)
            after = backend_profiles.profile_to_dict(
                await backend_profiles.get_profile(session, owner_id, profile.id))
            return yrsa_voice, other_voice, before, after

    yrsa_voice, other_voice, before, after = asyncio.run(go())
    assert yrsa_voice.voice_id == "bf_emma" and yrsa_voice.language == "en-gb"
    assert yrsa_voice.params == {"speed": 1.1}
    assert yrsa_voice.to_voice_info().backend_key == "kokoro-onnx"
    assert other_voice.voice_id == "fake-voice"
    # THE acceptance invariant: chat composition is byte-identical.
    assert before == after
    assert after["chat_backend"] == "ollama" and after["chat_model"] == "llama3.1"


def test_partial_profile_falls_back_per_field(tmp_path):
    factory = setup_db(tmp_path)
    owner_id, yrsa_id, _ = seed(factory)

    async def go():
        async with factory() as session:
            await set_character_voice(session, owner_id, yrsa_id, voice_id="am_michael")
            return await resolve_character_voice(session, owner_id, yrsa_id)

    resolved = asyncio.run(go())
    assert resolved.voice_id == "am_michael"
    assert resolved.tts_backend == DEFAULT_VOICE.backend_key  # fell back


def test_unknown_backend_and_character_rejected(tmp_path):
    factory = setup_db(tmp_path)
    owner_id, yrsa_id, _ = seed(factory)

    async def go():
        async with factory() as session:
            with pytest.raises(ValueError):
                await set_character_voice(session, owner_id, yrsa_id,
                                          tts_backend="mystery-tts")
            with pytest.raises(ValueError):
                await set_character_voice(session, owner_id, "no-such-character",
                                          voice_id="x")

    asyncio.run(go())


def test_delete_restores_default_and_owner_isolation(tmp_path):
    factory = setup_db(tmp_path)
    owner_id, yrsa_id, _ = seed(factory)

    async def go():
        async with factory() as session:
            await set_character_voice(session, owner_id, yrsa_id, voice_id="bf_emma")
            assert await delete_character_voice(session, owner_id, yrsa_id)
            resolved = await resolve_character_voice(session, owner_id, yrsa_id)
            assert resolved.voice_id == DEFAULT_VOICE.voice_id
            other = await resolve_character_voice(session, "someone-else", yrsa_id)
            assert other.voice_id == DEFAULT_VOICE.voice_id  # no cross-owner leak

    asyncio.run(go())
