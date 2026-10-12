"""S415 (roadmap): full rebuild/reindex.

Acceptance: destroy derived indexes -> rebuild (including an
embedding-profile change) -> evaluation corpus remains semantically
correct.
"""

from __future__ import annotations

from runmal.backends.embeddings import EmbeddingProvenance, FakeEmbeddingBackend
from runmal.chats.service import append_message, create_chat
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.evaluator import run_corpus
from runmal.memory.extraction import ExtractionJob, FakeExtractor, persist_candidates
from runmal.memory.ingestion import ingest_document
from runmal.memory.rebuild import rebuild_memory
from runmal.memory.retrieval import RetrievalQuery
from runmal.memory.scope import Viewer, scoped_retrieve
from runmal.memory.supersession import apply_fact, current_fact
from runmal.memory.vectorstore import InMemoryVectorStore

PROV_A = EmbeddingProvenance("fake", "fake-embed-1", 8, "1")
PROV_B = EmbeddingProvenance("fake", "fake-embed-2", 16, "1")


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed_world(factory):
    backend_a = FakeEmbeddingBackend(dims=8, model="fake-embed-1")
    store = InMemoryVectorStore()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        chat = await create_chat(session, uid, title="c")
        m1 = await append_message(session, uid, chat.id, role="user",
                                  content="Volmarr lives in Schenectady.")
        extractor = FakeExtractor()
        candidates = await extractor.extract([m1])
        job = ExtractionJob(user_id=uid, chat_id=chat.id, messages=[m1])
        await persist_candidates(session, job, candidates, extractor)
        await ingest_document(
            session, uid, backend_a, store, document_id="doc-1",
            text="the secret amber key hangs behind the waterfall shrine",
            scope="character", character_id="char-b", chat_id=chat.id)
        await apply_fact(
            session, uid, subject="Volmarr", predicate="lives_in",
            content="Volmarr lives in New Mexico.",
            valid_from=None, sources=(("message", "mx", chat.id),))
        await session.commit()
        return uid, chat.id, store, backend_a


async def test_destroy_and_rebuild_under_new_embedding_profile(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store, backend_a = await seed_world(factory)
    backend_b = FakeEmbeddingBackend(dims=16, model="fake-embed-2")
    async with factory() as session:
        before = await scoped_retrieve(
            session, uid, Viewer(character_id="char-a"),
            RetrievalQuery(text="amber"), store=store, backend=backend_a)
        assert before == []  # witness scope holds pre-rebuild too

        report = await rebuild_memory(session, uid, backend_b, store)
        await session.commit()
        assert report.destroyed_memories >= 3
        assert report.restored_from_extraction >= 1  # re-derived from messages
        assert report.provenance == PROV_B.to_dict()
        assert store.count(PROV_B) >= 3
        assert store.count(PROV_A) == 0  # old space fully destroyed

        # Semantic correctness after rebuild, in the NEW space:
        hits_b = await scoped_retrieve(
            session, uid, Viewer(character_id="char-b"),
            RetrievalQuery(text="amber"), store=store, backend=backend_b)
        assert hits_b  # B can recall its private memory again
        hits_a = await scoped_retrieve(
            session, uid, Viewer(character_id="char-a"),
            RetrievalQuery(text="amber"), store=store, backend=backend_b)
        assert hits_a == []  # A still cannot (witness scenario)
        current = await current_fact(session, uid, "Volmarr", "lives_in")
        assert current is not None and "New Mexico" in current.content
        traced = [m for m in await service.list_memories(session, uid)]
        assert all(
            await service.list_sources(session, m.id) or m.kind == "nucleus"
            for m in traced)


async def test_corpus_still_passes_on_rebuilt_style_stores(tmp_path):
    # The deterministic corpus itself is the acceptance gate (S414);
    # run it here as the campaign-close check on fresh stores.
    def maker(name):
        db_path = tmp_path / name / "test.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        migrate_to_head(db_path)
        return create_session_factory(create_db_engine(db_path))

    report = await run_corpus(maker)
    assert report.passed, {r.name: r.detail for r in report.results if not r.passed}
