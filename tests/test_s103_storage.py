"""S103 acceptance: storage core + migrations."""

import sqlite3

import pytest
import sqlalchemy
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import applied_revisions, current_revision, migrate_to_head
from runmal.db.models import Character, Chat, Message, User


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.db"


def test_fresh_db_migrates_to_head(db_path) -> None:
    # NOTE (S107/S201/S203/S207/S211/S303/S306): expectations extended --
    # migrations 0002 through 0009 now exist and a fresh DB must reach HEAD.
    applied = migrate_to_head(db_path)
    assert applied == ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011"]
    assert current_revision(db_path) == "0011"
    assert applied_revisions(db_path) == ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011"]
    inspector = inspect(sqlalchemy.create_engine(f"sqlite:///{db_path}"))
    tables = set(inspector.get_table_names())
    assert {"users", "characters", "chats", "messages", "schema_migrations"} <= tables


def test_migrate_is_idempotent(db_path) -> None:
    # NOTE (S203/S207/S211/S303/S306): appended through 0009; idempotency at HEAD.
    assert migrate_to_head(db_path) == ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011"]
    assert migrate_to_head(db_path) == []


def test_sqlite_policy_pragmas(db_path) -> None:
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)

    async def check() -> None:
        async with engine.connect() as conn:
            fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            assert fk == 1
            assert str(journal).lower() == "wal"

    import asyncio

    asyncio.run(check())


async def test_crud_round_trip(db_path) -> None:
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        user = User(name="Volmarr")
        session.add(user)
        await session.flush()
        character = Character(user_id=user.id, name="Yrsa")
        session.add(character)
        await session.flush()
        chat = Chat(user_id=user.id, character_id=character.id, title="First chat")
        session.add(chat)
        await session.flush()
        message = Message(chat_id=chat.id, role="user", content="Hail!")
        session.add(message)
        await session.commit()
        chat_id, user_id = chat.id, user.id
    async with factory() as session:
        got = await session.get(Message, message.id)
        assert got is not None and got.content == "Hail!" and got.role == "user"
        got_chat = await session.get(Chat, chat_id)
        assert got_chat is not None and got_chat.title == "First chat"
        assert got_chat.user_id == user_id
    await engine.dispose()


async def test_foreign_keys_enforced(db_path) -> None:
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        session.add(Message(chat_id="no-such-chat", role="user", content="x"))
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()


def test_raw_sqlite_sees_migrated_schema(db_path) -> None:
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
        assert {"id", "chat_id", "role", "content", "created_at"} <= set(cols)
    finally:
        conn.close()
