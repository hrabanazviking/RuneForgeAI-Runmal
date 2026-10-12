"""S409 (roadmap): mutation sync.

Acceptance: removing one of several sources preserves a supported
fact; removing ALL support invalidates the derived memory.
"""

from __future__ import annotations

from runmal.chats.service import (
    append_message,
    create_chat,
    delete_message,
    list_events,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.sync import apply_events, sync_chat_events


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed(factory):
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        chat = await create_chat(session, uid, title="c")
        m1 = await append_message(session, uid, chat.id, role="user",
                                  content="Volmarr lives in Schenectady.")
        m2 = await append_message(session, uid, chat.id, role="user",
                                  content="Yes, Volmarr lives in Schenectady.")
        fact = await service.create_memory(
            session, uid, content="Volmarr lives in Schenectady.",
            subject="Volmarr", predicate="lives_in", chat_id=chat.id,
            extractor={"kind": "fake"},
            sources=(("message", m1.id, chat.id), ("message", m2.id, chat.id)))
        await session.commit()
        return uid, chat.id, m1.id, m2.id, fact.id


async def test_partial_support_removal_preserves_fact(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, m1, m2, fact_id = await seed(factory)
    async with factory() as session:
        assert await delete_message(session, uid, chat_id, m1)
        events = await list_events(session, uid, chat_id)
        report = await sync_chat_events(session, uid, chat_id)
        await session.commit()
        assert events is not None
        assert report.sources_removed == 1
        fact = await service.get_memory(session, uid, fact_id)
        assert fact.state == "active"
        assert fact.confidence == 0.5  # 1 of 2 sources remain
        assert report.memories_preserved == [fact_id]
        assert report.memories_invalidated == []


async def test_full_support_removal_invalidates(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, m1, m2, fact_id = await seed(factory)
    async with factory() as session:
        assert await delete_message(session, uid, chat_id, m1)
        assert await delete_message(session, uid, chat_id, m2)
        events = await list_events(session, uid, chat_id)
        report = await apply_events(session, uid, events or [])
        await session.commit()
        assert report.sources_removed == 2
        fact = await service.get_memory(session, uid, fact_id)
        assert fact.state == "invalidated"
        assert fact_id in report.memories_invalidated
        # The record still exists: provenance history is never erased.
        sources = await service.list_sources(session, fact_id)
        assert sources == []
