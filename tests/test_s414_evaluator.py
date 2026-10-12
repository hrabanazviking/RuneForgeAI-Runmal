"""S414 (roadmap): recall trace + memory evaluator.

Acceptance: per-memory eligibility/score/discard explanation +
deterministic evaluation corpus covering witness, temporal, duplicate,
deletion, decay and re-embedding scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runmal.backends.embeddings import FakeEmbeddingBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.evaluator import explain_retrieval, run_corpus
from runmal.memory.ingestion import ingest_document
from runmal.memory.retrieval import RetrievalQuery
from runmal.memory.scope import Viewer
from runmal.memory.vectorstore import InMemoryVectorStore


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def corpus_maker(tmp_path):
    def maker(name):
        db_path = tmp_path / name / "test.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        migrate_to_head(db_path)
        return create_session_factory(create_db_engine(db_path))
    return maker


async def test_recall_trace_explains_every_memory(tmp_path):
    factory = make_factory(tmp_path)
    backend, store = FakeEmbeddingBackend(dims=8), InMemoryVectorStore()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        ing = await ingest_document(
            session, uid, backend, store, document_id="d1",
            text="the amber key hangs behind the waterfall shrine",
            scope="character", character_id="char-b")
        shared = await service.create_memory(
            session, uid, content="the amber market opens at dawn")
        stale = await service.create_memory(
            session, uid, content="amber was sold out yesterday", state="superseded")
        await session.commit()
        entries = await explain_retrieval(
            session, uid, Viewer(character_id="char-a"),
            RetrievalQuery(text="amber"), store=store, backend=backend,
            now=datetime(2026, 10, 12, tzinfo=UTC))
        by_id = {e.memory_id: e for e in entries}
        assert by_id[ing.memory_ids[0]].discard_reason == "witness_ineligible"
        assert by_id[ing.memory_ids[0]].eligible is False
        assert by_id[shared.id].included is True
        assert by_id[shared.id].fts_score > 0
        assert by_id[stale.id].discard_reason == "state:superseded"
        # Deterministic: same inputs, same explanations.
        again = await explain_retrieval(
            session, uid, Viewer(character_id="char-a"),
            RetrievalQuery(text="amber"), store=store, backend=backend,
            now=datetime(2026, 10, 12, tzinfo=UTC))
        assert [e.to_dict() for e in again] == [e.to_dict() for e in entries]


async def test_evaluation_corpus_all_scenarios_pass(tmp_path):
    report = await run_corpus(corpus_maker(tmp_path))
    assert [r.name for r in report.results] == [
        "witness", "temporal", "duplicate", "deletion", "decay", "re_embedding"]
    failures = {r.name: r.detail for r in report.results if not r.passed}
    assert report.passed, failures
    # Deterministic corpus: a second run gives identical verdicts.
    report2 = await run_corpus(corpus_maker(tmp_path / "second"))
    assert [r.passed for r in report2.results] == [r.passed for r in report.results]
