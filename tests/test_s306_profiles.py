"""S306 (roadmap): backend profiles + secrets — references only, canary-safe."""

from __future__ import annotations

import json

import pytest

from runmal.backends.embeddings import OllamaEmbeddingBackend
from runmal.backends.fake import FakeChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.profiles import (
    build_chat_backend,
    build_embedding_backend,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    profile_to_dict,
    put_secret,
    resolve_secret,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User

CANARY = "SECRET-CANARY-306"


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


async def test_profile_crud_and_persistence(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(
            session, user_id, name="hearth", chat_backend="fake",
            chat_model="fake-1", embedding_backend="fake",
            stt_ref="whisper-local", tts_ref="piper-local")
        assert profile.id
        fetched = await get_profile(session, user_id, profile.id)
        assert fetched is not None and fetched.name == "hearth"
        assert [p.name for p in await list_profiles(session, user_id)] == ["hearth"]
        with pytest.raises(ValueError):
            await create_profile(session, user_id, name="hearth")
        with pytest.raises(ValueError):
            await create_profile(session, user_id, name="x", chat_backend="nope")
        assert await delete_profile(session, user_id, profile.id) is True
        assert await get_profile(session, user_id, profile.id) is None


async def test_secret_values_never_in_profile_serialization(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        ref = await put_secret(session, user_id, CANARY)
        profile = await create_profile(
            session, user_id, name="cloud", chat_backend="openrouter",
            chat_model="openai/gpt-4o-mini", chat_secret_ref=ref)
        blob = json.dumps(profile_to_dict(profile))
        assert CANARY not in blob
        assert profile_to_dict(profile)["has_chat_secret"] is True
        assert profile_to_dict(profile)["chat_secret_ref"] == ref
        # Server-side resolution works and is owner-scoped.
        assert await resolve_secret(session, user_id, ref) == CANARY
        assert await resolve_secret(session, "someone-else", ref) is None
        with pytest.raises(ValueError):
            await create_profile(session, user_id, name="bad",
                                 chat_secret_ref="secret:missing")


async def test_profile_pairs_cloud_chat_with_local_embeddings(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        ref = await put_secret(session, user_id, CANARY)
        profile = await create_profile(
            session, user_id, name="hybrid", chat_backend="openrouter",
            chat_model="openai/gpt-4o-mini", chat_secret_ref=ref,
            embedding_backend="ollama", embedding_model="nomic-embed-text")
        chat = await build_chat_backend(session, profile)
        assert isinstance(chat, OpenRouterChatBackend)
        assert chat._api_key == CANARY  # resolved server-side only
        embedding = await build_embedding_backend(session, profile)
        assert isinstance(embedding, OllamaEmbeddingBackend)
        # The resolved secret must not leak through backend public surfaces.
        assert CANARY not in repr(chat)
        assert CANARY not in json.dumps(profile_to_dict(profile))


async def test_fake_profile_builds_fake_backends(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(session, user_id, name="local")
        assert isinstance(await build_chat_backend(session, profile),
                          FakeChatBackend)
