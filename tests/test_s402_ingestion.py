"""S402 (roadmap): embedding ingestion.

Acceptance: fixture documents produce vectors with profile/model/dim/
version metadata (via the S304 EmbeddingBackend; fake backend in tests).
"""

from __future__ import annotations

from sqlalchemy import select

from runmal.backends.embeddings import FakeEmbeddingBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import MemoryChunk, User
from runmal.memory.ingestion import chunk_text, ingest_document
from runmal.memory.service import list_sources
from runmal.memory.vectorstore import InMemoryVectorStore

DOC = " ".join(f"word{i}" for i in range(90))


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert "0014" in applied
    return create_session_factory(create_db_engine(db_path))


def test_chunking_deterministic_and_overlapping():
    a = chunk_text(DOC, size=40, overlap=8)
    assert a == chunk_text(DOC, size=40, overlap=8)
    assert len(a) == 3  # 40 + 32-step windows over 90 words
    assert a[0].split()[0] == "word0" and a[1].split()[0] == "word32"
    assert chunk_text("") == []


async def test_ingest_produces_vectors_with_full_provenance(tmp_path):
    factory = make_factory(tmp_path)
    backend = FakeEmbeddingBackend(dims=8, model="fake-embed-1")
    store = InMemoryVectorStore()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        out = await ingest_document(
            session, user.id, backend, store,
            document_id="doc-1", text=DOC, chat_id="chat-1")
        await session.commit()
        assert len(out.memory_ids) == 3 and len(out.chunk_ids) == 3
        assert out.provenance == {
            "provider": "fake", "model": "fake-embed-1", "dims": 8, "version": "1"}
        chunks = list(await session.scalars(select(MemoryChunk)))
        assert len(chunks) == 3
        for chunk in chunks:
            assert (chunk.provider, chunk.model, chunk.dims, chunk.version) == (
                "fake", "fake-embed-1", 8, "1")
            from runmal.backends.embeddings import EmbeddingProvenance

            prov = EmbeddingProvenance("fake", "fake-embed-1", 8, "1")
            assert store.count(prov) == 3
        sources = await list_sources(session, out.memory_ids[0])
        assert [(s.source_kind, s.source_id, s.chat_id) for s in sources] == [
            ("document", "doc-1", "chat-1")]
