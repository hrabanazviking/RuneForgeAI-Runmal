"""S413 (roadmap): contradiction + supersession engine.

Acceptance: "old residence -> new residence" fixture keeps history
while current-state queries prefer the new truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.supersession import apply_fact, current_fact, slot_memories

JAN = datetime(2026, 1, 15, tzinfo=UTC)
APR = datetime(2027, 4, 2, tzinfo=UTC)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def test_residence_timeline_keeps_history_prefers_new(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        r1 = await apply_fact(
            session, uid, subject="Volmarr", predicate="lives_in",
            content="Volmarr lives in Indiana.", valid_from=JAN,
            sources=(("message", "m1", "chat-1"),))
        assert r1.action == "inserted"
        r2 = await apply_fact(
            session, uid, subject="Volmarr", predicate="lives_in",
            content="Volmarr lives in New Mexico.", valid_from=APR,
            sources=(("message", "m2", "chat-1"),))
        await session.commit()
        assert r2.action == "superseded" and r2.superseded_id == r1.memory_id

        current = await current_fact(session, uid, "Volmarr", "lives_in")
        assert current is not None and current.id == r2.memory_id
        assert "New Mexico" in current.content

        history = await slot_memories(session, uid, "Volmarr", "lives_in")
        assert len(history) == 2
        old = await service.get_memory(session, uid, r1.memory_id)
        assert old.state == "superseded"
        assert old.valid_until.replace(tzinfo=UTC) == APR  # history kept, bounded
        new = await service.get_memory(session, uid, r2.memory_id)
        assert new.supersedes_id == r1.memory_id and new.state == "active"


async def test_duplicate_and_dispute_paths(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        r1 = await apply_fact(
            session, uid, subject="Yrsa", predicate="lives_in",
            content="Yrsa lives in Uppsala.", valid_from=JAN)
        dup = await apply_fact(
            session, uid, subject="Yrsa", predicate="lives_in",
            content="Yrsa lives in Uppsala.", valid_from=APR)
        assert dup.action == "duplicate" and dup.memory_id == r1.memory_id
        # Conflicting claim with NO temporal evidence -> dispute.
        r2 = await apply_fact(
            session, uid, subject="Yrsa", predicate="lives_in",
            content="Yrsa lives in Bergen.")
        await session.commit()
        assert r2.action == "disputed"
        states = {m.id: m.state for m in await slot_memories(session, uid, "Yrsa", "lives_in")}
        assert states[r1.memory_id] == "disputed" and states[r2.memory_id] == "disputed"
        assert await current_fact(session, uid, "Yrsa", "lives_in") is None
        # A later temporal fact resolves the dispute.
        r3 = await apply_fact(
            session, uid, subject="Yrsa", predicate="lives_in",
            content="Yrsa lives in Bergen.", valid_from=APR)
        await session.commit()
        assert r3.action in ("inserted", "duplicate")
        current = await current_fact(session, uid, "Yrsa", "lives_in")
        assert current is not None and "Bergen" in current.content
