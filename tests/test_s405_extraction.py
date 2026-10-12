"""S405 (roadmap): event/fact extraction.

Acceptance: fixture transcript -> expected candidates/provenance; the
reply path NEVER waits on extraction.
"""

from __future__ import annotations

import asyncio

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.extraction import (
    ExtractionJob,
    ExtractionQueue,
    FakeExtractor,
    persist_candidates,
)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


class Msg:
    def __init__(self, id, content):
        self.id = id
        self.content = content


TRANSCRIPT = [
    Msg("m1", "Volmarr lives in Schenectady."),
    Msg("m2", "Yrsa prefers local-first tools."),
    Msg("m3", "The weather is nice today."),
    Msg("m4", "Volmarr likes strong coffee."),
]


async def test_fixture_transcript_yields_expected_candidates(tmp_path):
    factory = make_factory(tmp_path)
    extractor = FakeExtractor()
    candidates = await extractor.extract(TRANSCRIPT)
    assert [(c.subject, c.predicate, c.object_text, c.source_message_id)
            for c in candidates] == [
        ("Volmarr", "lives_in", "Schenectady", "m1"),
        ("Yrsa", "prefers", "local-first tools", "m2"),
        ("Volmarr", "likes", "strong coffee", "m4"),
    ]
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        job = ExtractionJob(user_id=user.id, chat_id="chat-1", messages=TRANSCRIPT)
        ids = await persist_candidates(session, job, candidates, extractor)
        await session.commit()
        assert len(ids) == 3
        mem = await service.get_memory(session, user.id, ids[0])
        assert mem.subject == "Volmarr" and mem.predicate == "lives_in"
        assert mem.extractor_json.find("fake-extractor") >= 0
        sources = await service.list_sources(session, ids[0])
        assert [(s.source_kind, s.source_id) for s in sources] == [("message", "m1")]


class GatedExtractor(FakeExtractor):
    """Blocks inside extract until released — proves non-blocking enqueue."""

    def __init__(self):
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()

    async def extract(self, messages):
        self.entered.set()
        await self.gate.wait()
        return await super().extract(messages)


async def test_reply_path_never_waits_on_extraction(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
    extractor = GatedExtractor()
    queue = ExtractionQueue(factory, extractor)
    job = ExtractionJob(user_id=uid, chat_id="chat-1", messages=TRANSCRIPT)
    # Enqueue returns immediately even though the extractor will block.
    queue.enqueue(job)
    await asyncio.wait_for(extractor.entered.wait(), timeout=5)
    assert queue.completed == []  # extraction still gated; nothing persisted yet
    extractor.gate.set()
    await asyncio.wait_for(queue.drain(), timeout=5)
    await queue.stop()
    assert len(queue.completed) == 1 and len(queue.completed[0]) == 3
