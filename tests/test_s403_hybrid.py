"""S403 (roadmap): hybrid retrieval.

Acceptance: fixture queries exercise BOTH paths (vector-only, FTS-only,
both) and ranking is deterministic under fixed state.
"""

from __future__ import annotations

from runmal.backends.embeddings import FakeEmbeddingBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.ingestion import ingest_document
from runmal.memory.retrieval import RetrievalQuery, hybrid_retrieve
from runmal.memory.vectorstore import InMemoryVectorStore


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed(factory):
    backend = FakeEmbeddingBackend(dims=8)
    store = InMemoryVectorStore()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        # Vector-path memory: embedded chunk about fjords.
        ing = await ingest_document(
            session, uid, backend, store, document_id="d1",
            text="the fjord waters are cold and deep and still")
        # FTS-only memory: never embedded (no chunks in the vector store).
        fts_only = await service.create_memory(
            session, uid, content="the fjord festival serves honey mead",
            kind="semantic")
        # Superseded memory must be filtered out by structured state filter.
        await service.create_memory(
            session, uid, content="the fjord is warm in summer",
            kind="semantic", state="superseded")
        await session.commit()
        return uid, backend, store, ing.memory_ids[0], fts_only.id


async def test_both_paths_exercised_and_deterministic(tmp_path):
    factory = make_factory(tmp_path)
    uid, backend, store, vec_id, fts_id = await seed(factory)
    async with factory() as session:
        q = RetrievalQuery(text="fjord")
        hits1 = await hybrid_retrieve(session, uid, q, store=store, backend=backend)
        hits2 = await hybrid_retrieve(session, uid, q, store=store, backend=backend)
        assert [h.memory_id for h in hits1] == [h.memory_id for h in hits2]
        assert [h.score for h in hits1] == [h.score for h in hits2]
        by_id = {h.memory_id: h for h in hits1}
        assert set(by_id) == {vec_id, fts_id}
        assert by_id[vec_id].paths == ("vector", "fts") or "vector" in by_id[vec_id].paths
        assert by_id[fts_id].paths == ("fts",)
        assert all(h.score > 0 for h in hits1)


async def test_structured_filters(tmp_path):
    factory = make_factory(tmp_path)
    uid, backend, store, vec_id, fts_id = await seed(factory)
    async with factory() as session:
        hits = await hybrid_retrieve(
            session, uid, RetrievalQuery(text="fjord", kind="semantic"),
            store=store, backend=backend)
        assert [h.memory_id for h in hits] == [fts_id]
        hits = await hybrid_retrieve(
            session, uid, RetrievalQuery(text="fjord", states=("superseded",)),
            store=store, backend=backend)
        assert len(hits) == 1  # only the superseded fixture memory
