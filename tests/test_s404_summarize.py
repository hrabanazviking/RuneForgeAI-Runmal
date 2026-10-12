"""S404 (roadmap): chat auto-summarization.

Acceptance: long fixture chat remains under prompt budget; summary
source range recorded.
"""

from __future__ import annotations

from sqlalchemy import select

from runmal.chats.service import append_message, create_chat
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import ChatSummary, User
from runmal.memory.summarize import latest_summary, roll_summaries
from runmal.tokens import estimate_tokens


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed_chat(factory, n=30):
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        chat = await create_chat(session, user.id, title="long")
        msgs = []
        for i in range(n):
            m = await append_message(
                session, user.id, chat.id, role="user",
                content=f"message number {i} with several extra words to spend tokens")
            msgs.append(m)
        await session.commit()
        return user.id, chat.id, msgs


async def test_long_chat_rolls_under_budget_with_source_range(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, msgs = await seed_chat(factory)
    budget = 120
    async with factory() as session:
        ordered = msgs  # append order is the canonical chronological order
        result = await roll_summaries(
            session, uid, chat_id, ordered, budget_tokens=budget, keep_recent=4)
        await session.commit()
        assert result.under_budget and result.total_tokens <= budget
        assert len(result.kept_ids) >= 4
        assert result.summarized_count == 30 - len(result.kept_ids)
        summary = await latest_summary(session, chat_id)
        assert summary is not None and summary.version == 1
        assert summary.source_count == result.summarized_count
        assert summary.source_first_id == msgs[0].id
        assert summary.source_last_id == msgs[result.summarized_count - 1].id
        # Summary + kept history is what the composer would spend.
        spent = estimate_tokens(summary.summary) + sum(
            estimate_tokens(m.content) for m in ordered if m.id in set(result.kept_ids))
        assert spent <= budget


async def test_second_roll_is_incremental(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, msgs = await seed_chat(factory, n=12)
    async with factory() as session:
        r1 = await roll_summaries(session, uid, chat_id, msgs, budget_tokens=60,
                                  keep_recent=2)
        await session.commit()
        assert r1.version == 1
        r2 = await roll_summaries(session, uid, chat_id, msgs, budget_tokens=60,
                                  keep_recent=2)
        await session.commit()
        assert r2.version == 1  # already under budget: no new version
        rows = list(await session.scalars(select(ChatSummary)))
        assert len(rows) == 1
