"""S411 (roadmap): provenance graph.

Acceptance: every derived fixture memory traces to canonical evidence
(many-to-many sources + extractor/user-edit provenance).
"""

from __future__ import annotations

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.graph import provenance_graph, trace_to_evidence, verify_all_traced


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def test_many_to_many_evidence_and_extractor_nodes(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        fact = await service.create_memory(
            session, uid, content="Volmarr prefers local-first AI.",
            extractor={"kind": "fake", "provider": "fake", "model": "fx",
                       "version": "1", "prompt_version": "extract-v1"},
            sources=(("message", "a17", "chat-1"),
                     ("message", "c88", "chat-2"),
                     ("document", "p4", None)))
        await session.commit()
        graph = await provenance_graph(session, uid, fact.id)
        assert graph is not None
        source_nodes = [n for n in graph["nodes"] if n["type"] == "source"]
        assert {n["id"] for n in source_nodes} == {
            "message:a17", "message:c88", "document:p4"}
        extractor_nodes = [n for n in graph["nodes"] if n["type"] == "extractor"]
        assert extractor_nodes and extractor_nodes[0]["model"] == "fx"
        derived = [e for e in graph["edges"] if e["relation"] == "derived_from"]
        assert len(derived) == 3
        evidence = await trace_to_evidence(session, uid, fact.id)
        assert {e["source_id"] for e in evidence} == {"a17", "c88", "p4"}
        assert await verify_all_traced(session, uid) == []


async def test_untraced_derived_memory_is_flagged(tmp_path):
    factory = make_factory(tmp_path)
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        orphan = await service.create_memory(
            session, uid, content="Derived but sourceless.",
            extractor={"kind": "fake"})
        await session.commit()
        assert await verify_all_traced(session, uid) == [orphan.id]
        assert await provenance_graph(session, uid, "missing") is None
