"""S412 (roadmap): deduplication + consolidation.

Acceptance: repeated paraphrases consolidate IDEMPOTENTLY without
losing evidence.
"""

from __future__ import annotations

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.consolidation import consolidate


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
        variants = [
            ("Volmarr prefers local-first AI.", "m1"),
            ("Volmarr prefers local-first AI", "m2"),
            ("Volmarr really prefers local-first AI tools.", "m3"),
        ]
        ids = []
        for content, src in variants:
            m = await service.create_memory(
                session, uid, content=content, subject="Volmarr",
                predicate="prefers", confidence=0.7,
                sources=(("message", src, "chat-1"),))
            ids.append(m.id)
        other = await service.create_memory(
            session, uid, content="Yrsa tends the herb garden.",
            subject="Yrsa", predicate="tends", sources=(("message", "m9", "chat-1"),))
        await session.commit()
        return uid, ids, other.id


async def test_paraphrases_merge_preserving_all_evidence(tmp_path):
    factory = make_factory(tmp_path)
    uid, ids, other_id = await seed(factory)
    async with factory() as session:
        report = await consolidate(session, uid)
        await session.commit()
        assert report.groups == 1 and len(report.merged) == 2
        canonical_id = report.merged[0][1]
        assert canonical_id == ids[0]  # earliest created wins
        sources = await service.list_sources(session, canonical_id)
        assert {s.source_id for s in sources} == {"m1", "m2", "m3"}
        for from_id, into_id in report.merged:
            dup = await service.get_memory(session, uid, from_id)
            assert dup.state == "historical" and into_id == canonical_id
        untouched = await service.get_memory(session, uid, other_id)
        assert untouched.state == "active"


async def test_consolidation_is_idempotent(tmp_path):
    factory = make_factory(tmp_path)
    uid, ids, _ = await seed(factory)
    async with factory() as session:
        first = await consolidate(session, uid)
        await session.commit()
        second = await consolidate(session, uid)
        await session.commit()
        assert len(first.merged) == 2
        assert second.merged == [] and second.groups == 0
        canonical = await service.get_memory(session, uid, ids[0])
        assert len(await service.list_sources(session, canonical.id)) == 3
