"""S406 (roadmap): salience + decay with an injected clock.

Acceptance: fake-clock scenarios prove decay and pinned/stable behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.retrieval import RetrievalQuery, hybrid_retrieve
from runmal.memory.salience import reinforce, strength_map, strength_multiplier

T0 = datetime(2026, 1, 1, tzinfo=UTC)


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
        fragile = await service.create_memory(
            session, uid, content="ephemeral fjord picnic plan", salience=0.9,
            stability=0.1)
        durable = await service.create_memory(
            session, uid, content="durable fjord home fact", salience=0.9,
            stability=0.9)
        pinned = await service.create_memory(
            session, uid, content="pinned fjord oath", salience=0.9,
            stability=0.1, pinned=True)
        for m in (fragile, durable, pinned):
            m.created_at = T0
        await session.commit()
        return uid, fragile.id, durable.id, pinned.id


async def test_fake_clock_decay_and_pinned_stability(tmp_path):
    factory = make_factory(tmp_path)
    uid, fragile_id, durable_id, pinned_id = await seed(factory)
    async with factory() as session:
        by_id = {m.id: m for m in await service.list_memories(session, uid)}
        later = T0 + timedelta(days=60)
        f = strength_multiplier(by_id[fragile_id], later)
        d = strength_multiplier(by_id[durable_id], later)
        p = strength_multiplier(by_id[pinned_id], later)
        assert f < 0.2 * 0.9  # low stability decays hard over 60 days
        assert d > 0.7 * 0.9  # high stability barely decays
        assert p == 0.9       # pinned never decays
        # At creation time nothing has decayed yet.
        assert strength_multiplier(by_id[fragile_id], T0) == 0.9


async def test_reinforcement_lifts_strength_and_retrieval_rank(tmp_path):
    factory = make_factory(tmp_path)
    uid, fragile_id, durable_id, _ = await seed(factory)
    later = T0 + timedelta(days=60)
    async with factory() as session:
        scores = await strength_map(session, uid, later)
        q = RetrievalQuery(text="fjord", extra_scores=scores)
        hits = await hybrid_retrieve(session, uid, q)
        rank = [h.memory_id for h in hits]
        assert rank.index(durable_id) < rank.index(fragile_id)
        # Reinforce the fragile memory repeatedly at the fake 'now'.
        fragile = await service.get_memory(session, uid, fragile_id)
        for _ in range(30):
            await reinforce(session, fragile, later)
        await session.commit()
        scores = await strength_map(session, uid, later)
        assert scores[fragile_id] > scores[durable_id]
        assert fragile.recall_count == 30
        assert fragile.last_recalled_at.replace(tzinfo=UTC) == later
