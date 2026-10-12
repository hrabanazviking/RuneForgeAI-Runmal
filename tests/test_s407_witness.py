"""S407 (roadmap): witness-scoped recall.

Acceptance: character A cannot retrieve character B's private-chat
memory, INCLUDING through vector hits (filter before scoring).
"""

from __future__ import annotations

from runmal.backends.embeddings import FakeEmbeddingBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.ingestion import ingest_document
from runmal.memory.retrieval import RetrievalQuery, hybrid_retrieve
from runmal.memory.scope import Viewer, is_eligible, scoped_retrieve
from runmal.memory.vectorstore import InMemoryVectorStore


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def test_private_memory_invisible_to_other_character_even_via_vector(tmp_path):
    factory = make_factory(tmp_path)
    backend = FakeEmbeddingBackend(dims=8)
    store = InMemoryVectorStore()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        # B's private memory, fully embedded (a vector hit WAITING to leak).
        ing = await ingest_document(
            session, uid, backend, store, document_id="priv-b",
            text="the secret amber key hangs behind the waterfall shrine",
            scope="character", character_id="char-b", chat_id="chat-b")
        shared = await service.create_memory(
            session, uid, content="the amber market opens at dawn", scope="user")
        await session.commit()
        private_id = ing.memory_ids[0]

        q = RetrievalQuery(text="amber")
        # Unscoped retrieval WOULD find the private memory (both paths).
        raw = await hybrid_retrieve(session, uid, q, store=store, backend=backend)
        assert private_id in {h.memory_id for h in raw}

        # Character A's scoped view: private memory gone, shared remains.
        hits_a = await scoped_retrieve(
            session, uid, Viewer(character_id="char-a"), q,
            store=store, backend=backend)
        assert private_id not in {h.memory_id for h in hits_a}
        assert shared.id in {h.memory_id for h in hits_a}

        # Character B sees its own private memory.
        hits_b = await scoped_retrieve(
            session, uid, Viewer(character_id="char-b"), q,
            store=store, backend=backend)
        assert private_id in {h.memory_id for h in hits_b}

        # The owner sees everything.
        hits_owner = await scoped_retrieve(
            session, uid, Viewer(), q, store=store, backend=backend)
        assert private_id in {h.memory_id for h in hits_owner}


async def test_scope_rules_unit(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        chat_mem = await service.create_memory(
            session, uid, content="chat secret", scope="chat", chat_id="c1")
        wit_mem = await service.create_memory(
            session, uid, content="witnessed", scope="witnesses",
            witnesses=("char-a",))
        await session.commit()
        assert is_eligible(chat_mem, Viewer(character_id="char-a", chat_id="c1"))
        assert not is_eligible(chat_mem, Viewer(character_id="char-a", chat_id="c2"))
        assert not is_eligible(chat_mem, Viewer(character_id="char-a"))
        assert is_eligible(wit_mem, Viewer(character_id="char-a"))
        assert not is_eligible(wit_mem, Viewer(character_id="char-b"))
