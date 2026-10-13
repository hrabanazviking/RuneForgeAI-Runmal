"""S704 (roadmap): profile migration tooling — Ollama/OpenRouter -> Aesir.

Acceptance (migration fixture): migrating a profile creates an Aesir
profile with history/state intact — chats repoint, messages are never
touched — and the translation rules are honest: local model names
carry, namespaced cloud IDs require an explicit choice, embeddings are
an independent axis, and secret references never cross providers.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from runmal.backends.profile_migration import (
    apply_profile_migration,
    list_migratable_profiles,
    plan_profile_migration,
)
from runmal.backends.profiles import (
    create_profile,
    get_profile,
    put_secret,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Chat, Message, User

CANARY = "SECRET-CANARY-704"


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


async def seed_chat(factory, user_id: str, profile_id: str) -> tuple[str, list]:
    async with factory() as session:
        chat = Chat(user_id=user_id, title="cutover chat", backend_profile_id=profile_id)
        session.add(chat)
        await session.commit()
        rows = []
        for role, content in (
            ("user", "hello"),
            ("assistant", "hi there"),
            ("user", "remember this"),
        ):
            msg = Message(chat_id=chat.id, role=role, content=content)
            session.add(msg)
            rows.append(msg)
        await session.commit()
        return chat.id, [(m.id, m.role, m.content) for m in rows]


async def read_messages(factory, chat_id: str) -> list:
    async with factory() as session:
        rows = await session.scalars(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at, Message.id)
        )
        return [(m.id, m.role, m.content) for m in rows]


# --- planning rules (pure) ---------------------------------------------------


async def test_plan_ollama_carries_local_model_and_embeddings(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        ref = await put_secret(session, user_id, CANARY)
        profile = await create_profile(
            session,
            user_id,
            name="local",
            chat_backend="ollama",
            chat_model="llama3.1",
            embedding_backend="ollama",
            embedding_model="nomic-embed-text",
            stt_ref="faster-whisper",
            tts_ref="cosyvoice",
            chat_secret_ref=ref,
        )
        plan = plan_profile_migration(profile)
    assert plan.chat_backend == "aesir"
    assert plan.chat_model == "llama3.1"  # local name is user-owned: carries
    assert plan.requires_chat_model_choice is False
    assert plan.embedding_backend == "ollama"  # independent axis: stays
    assert plan.embedding_model == "nomic-embed-text"
    assert plan.stt_ref == "faster-whisper" and plan.tts_ref == "cosyvoice"
    assert plan.target_name == "local (Aesir)"
    assert any("secret" in w for w in plan.warnings)
    assert CANARY not in json.dumps(plan.to_dict())


async def test_plan_openrouter_requires_explicit_model(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(
            session,
            user_id,
            name="cloud",
            chat_backend="openrouter",
            chat_model="openai/gpt-4o-mini",
        )
        plan = plan_profile_migration(profile)
        assert plan.chat_model is None
        assert plan.requires_chat_model_choice is True
        plan2 = plan_profile_migration(profile, aesir_chat_model="llama-3.1-8b-instruct")
        assert plan2.chat_model == "llama-3.1-8b-instruct"
        assert plan2.requires_chat_model_choice is False
        with pytest.raises(ValueError):
            await apply_profile_migration(session, user_id, profile.id)
        result = await apply_profile_migration(
            session, user_id, profile.id, aesir_chat_model="llama-3.1-8b-instruct"
        )
        assert result.profile.chat_backend == "aesir"
        assert result.profile.chat_model == "llama-3.1-8b-instruct"


async def test_plan_embedding_migration_requires_model(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(
            session,
            user_id,
            name="local",
            chat_backend="ollama",
            chat_model="llama3.1",
            embedding_backend="ollama",
            embedding_model="nomic-embed-text",
        )
        plan = plan_profile_migration(profile, migrate_embeddings=True)
        assert plan.embedding_backend == "aesir"
        assert plan.requires_embedding_model_choice is True
        plan2 = plan_profile_migration(
            profile, migrate_embeddings=True, aesir_embedding_model="aesir-embed-1"
        )
        assert plan2.embedding_model == "aesir-embed-1"
        assert plan2.requires_embedding_model_choice is False


# --- the migration fixture: history/state intact ------------------------------


async def test_migration_fixture_history_intact(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(
            session,
            user_id,
            name="local",
            chat_backend="ollama",
            chat_model="llama3.1",
            embedding_backend="ollama",
            embedding_model="nomic-embed-text",
        )
        profile_id = profile.id
    chat_id, before = await seed_chat(factory, user_id, profile_id)

    async with factory() as session:
        result = await apply_profile_migration(session, user_id, profile_id, repoint_chats=True)
        target = result.profile
        assert result.repointed_chats == 1
        assert target.chat_backend == "aesir"
        assert target.chat_model == "llama3.1"
        # Source profile untouched: rollback path intact.
        source = await get_profile(session, user_id, profile_id)
        assert source is not None and source.chat_backend == "ollama"
        chat = await session.get(Chat, chat_id)
        assert chat.backend_profile_id == target.id

    after = await read_messages(factory, chat_id)
    assert after == before  # ids, roles, contents, order: byte-identical


async def test_migration_without_repoint_leaves_chats(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        profile = await create_profile(
            session, user_id, name="local", chat_backend="ollama", chat_model="llama3.1"
        )
    chat_id, _ = await seed_chat(factory, user_id, profile.id)
    async with factory() as session:
        result = await apply_profile_migration(session, user_id, profile.id)
        assert result.repointed_chats == 0
        chat = await session.get(Chat, chat_id)
        assert chat.backend_profile_id == profile.id
        names = [p.name for p in await list_migratable_profiles(session, user_id)]
        assert names == ["local"]  # the Aesir target is not migratable again
        with pytest.raises(ValueError):
            await apply_profile_migration(session, user_id, result.profile.id)


def test_cli_migrate_to_aesir(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "runmal.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))

    async def _seed() -> tuple[str, str]:
        user_id = await make_user(factory)
        async with factory() as session:
            profile = await create_profile(
                session, user_id, name="local", chat_backend="ollama", chat_model="llama3.1"
            )
            return user_id, profile.id

    import asyncio

    _user_id, profile_id = asyncio.run(_seed())

    env = dict(os.environ, RUNMAL_DATA_DIR=str(tmp_path))

    def run_cli(*argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "runmal", *argv],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    proc = run_cli("profiles", "migrate-to-aesir", "--profile-id", profile_id, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["dry_run"] is True and out["plan"]["chat_model"] == "llama3.1"

    proc = run_cli("profiles", "migrate-to-aesir", "--profile-id", profile_id)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["profile"]["chat_backend"] == "aesir"
    assert out["profile"]["name"] == "local (Aesir)"
    assert CANARY not in json.dumps(out)

    # A bogus profile id is a clean CLI failure, not a traceback.
    proc = run_cli("profiles", "migrate-to-aesir", "--profile-id", "nope")
    assert proc.returncode == 1
    assert "profile not found" in proc.stderr
