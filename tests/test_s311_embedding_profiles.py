"""S311 (roadmap): independent embedding profiles + migration hook.

- Switching the active embedding profile does NOT switch the chat model.
- A provenance change schedules a re-embedding job (hook fires) while
  the FTS fallback stays available.
- Provenance-keyed isolation: incompatible embedding spaces NEVER mix
  in one similarity query (INV-019).
"""

from __future__ import annotations

import pytest

from runmal.backends import embedding_profiles as ep
from runmal.backends.embeddings import (
    EmbeddingProvenance,
    FakeEmbeddingBackend,
    FtsFallbackResult,
    UnavailableEmbeddingBackend,
    embed_or_fallback,
)
from runmal.backends.profiles import build_chat_backend, create_profile
from runmal.chats.service import create_chat, get_chat, set_chat_backend_profile
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User


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


@pytest.fixture
def two_spaces(monkeypatch):
    """Second fake space (dims 16) behind the factory seam."""
    original = ep.build_embedding_backend

    async def dispatch(session, profile):
        if profile.embedding_model == "fake-embed-2":
            return FakeEmbeddingBackend(dims=16, model="fake-embed-2")
        return await original(session, profile)

    monkeypatch.setattr(ep, "build_embedding_backend", dispatch)


async def make_profiles(session, user_id):
    cloud = await create_profile(
        session, user_id, name="cloud-chat", chat_backend="openrouter",
        chat_model="openai/gpt-4o-mini", embedding_backend="fake",
        embedding_model="fake-embed-1")
    local = await create_profile(
        session, user_id, name="local", chat_backend="ollama",
        chat_model="llama3.1", embedding_backend="fake",
        embedding_model="fake-embed-2")
    return cloud, local


async def test_switching_embedding_profile_never_touches_chat(tmp_path, two_spaces):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        cloud, local = await make_profiles(session, user_id)
        chat = await create_chat(session, user_id, title="seam chat")
        await set_chat_backend_profile(session, user_id, chat.id, cloud.id)
        chat_backend_before = await build_chat_backend(session, cloud)

        await ep.switch_active_embedding_profile(session, user_id, cloud.id)
        result = await ep.switch_active_embedding_profile(session, user_id, local.id)
        await session.commit()

        # The embedding axis moved...
        activation = await ep.get_activation(session, user_id)
        assert activation.profile_id == local.id
        assert result.provenance.model == "fake-embed-2"
        # ...chat did not: profile chat fields, the built chat backend,
        # and the chat's pinned profile are all exactly as before.
        assert cloud.chat_backend == "openrouter"
        assert cloud.chat_model == "openai/gpt-4o-mini"
        chat_backend_after = await build_chat_backend(session, cloud)
        assert type(chat_backend_after) is type(chat_backend_before)
        assert chat_backend_after._model == chat_backend_before._model
        pinned = await get_chat(session, user_id, chat.id)
        assert pinned.backend_profile_id == cloud.id


async def test_provenance_change_schedules_job_and_fires_hook(tmp_path, two_spaces):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    fired: list[dict] = []
    async with factory() as session:
        cloud, local = await make_profiles(session, user_id)
        first = await ep.switch_active_embedding_profile(
            session, user_id, cloud.id, on_job=fired.append)
        assert first.job is not None and first.job["status"] == "scheduled"
        assert first.job["from_key"] == ""
        assert "fake-embed-1" in first.job["to_key"]
        second = await ep.switch_active_embedding_profile(
            session, user_id, local.id, on_job=fired.append)
        assert second.job["from_key"] == first.job["to_key"]
        assert "fake-embed-2" in second.job["to_key"]
        assert len(fired) == 2
        # Re-selecting the SAME space schedules nothing.
        again = await ep.switch_active_embedding_profile(
            session, user_id, local.id, on_job=fired.append)
        assert again.job is None
        assert len(fired) == 2
        jobs = await ep.list_jobs(session, user_id)
        assert [j["status"] for j in jobs] == ["scheduled", "scheduled"]
        assert second.fts_fallback_available is True


async def test_unavailable_embeddings_degrade_to_fts_not_crash(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        bare = await create_profile(
            session, user_id, name="bare", chat_backend="fake",
            embedding_backend="")
        result = await ep.switch_active_embedding_profile(session, user_id, bare.id)
        assert result.provenance is None
        assert result.fts_fallback_available is True
        assert result.job is not None
        assert "FTS" in result.job["detail"]
        fallback = await embed_or_fallback(UnavailableEmbeddingBackend(), ["x"])
        assert isinstance(fallback, FtsFallbackResult)
        assert fallback.degraded is True


async def test_switch_unknown_or_foreign_profile_raises(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        with pytest.raises(KeyError):
            await ep.switch_active_embedding_profile(session, user_id, "nope")


def test_vector_spaces_never_mix_in_one_query():
    store = ep.VectorSpaceStore()
    prov_a = EmbeddingProvenance("fake", "space-a", 2, "1")
    prov_b = EmbeddingProvenance("fake", "space-b", 2, "1")
    store.put("doc-a", (1.0, 0.0), prov_a)
    store.put("doc-b", (1.0, 0.0), prov_b)  # identical vector, other space
    hits_a = store.query((1.0, 0.0), prov_a)
    hits_b = store.query((1.0, 0.0), prov_b)
    assert [doc for doc, _ in hits_a] == ["doc-a"]
    assert [doc for doc, _ in hits_b] == ["doc-b"]
    assert store.count(prov_a) == 1 and store.count(prov_b) == 1
    assert len(store.spaces()) == 2
    assert ep.key_str(prov_a) != ep.key_str(prov_b)
    # Version alone makes a different space too.
    prov_a2 = EmbeddingProvenance("fake", "space-a", 2, "2")
    assert store.query((1.0, 0.0), prov_a2) == []
    with pytest.raises(ValueError):
        store.put("bad", (1.0, 0.0, 0.0), prov_a)
    with pytest.raises(ValueError):
        store.query((1.0, 0.0, 0.0), prov_a)
