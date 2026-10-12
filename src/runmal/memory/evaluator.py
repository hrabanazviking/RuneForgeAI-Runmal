"""Recall trace + memory evaluator (S414).

Two explainability artifacts:

1. **Recall trace** — for one retrieval, a per-memory explanation:
   eligibility, vector/FTS path scores, strength multiplier, final
   score, and a discard reason for everything not included
   (``witness_ineligible``, ``state:<state>``, ``filtered``,
   ``not_a_candidate``, ``below_threshold``). This is the memory-side
   companion to the S214 Prompt Trace (MEMORY_ARCHITECTURE.md §13).

2. **Deterministic evaluation corpus** — fixed scenarios covering
   witness scope, temporal truth, duplicate consolidation, deletion,
   decay and re-embedding (§14). Memory quality is measured against
   these scenarios, never against a demo's vibes. Each scenario builds
   an isolated store via the caller's factory maker and returns a
   pass/fail verdict with a detail string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import FakeEmbeddingBackend
from runmal.db.models import User
from runmal.memory import service
from runmal.memory.consolidation import consolidate
from runmal.memory.retrieval import (
    FTS_WEIGHT,
    VECTOR_WEIGHT,
    RetrievalQuery,
    fts_hits,
    vector_hits,
)
from runmal.memory.salience import strength_multiplier
from runmal.memory.scope import Viewer, eligible_memory_ids
from runmal.memory.supersession import apply_fact, current_fact
from runmal.memory.sync import apply_events
from runmal.memory.vectorstore import InMemoryVectorStore

MIN_SCORE = 0.0


@dataclass(frozen=True)
class RecallEntry:
    memory_id: str
    included: bool
    eligible: bool
    vector_score: float = 0.0
    fts_score: float = 0.0
    strength: float = 1.0
    final_score: float = 0.0
    discard_reason: str | None = None

    def to_dict(self) -> dict:
        return {"memory_id": self.memory_id, "included": self.included,
                "eligible": self.eligible, "vector_score": self.vector_score,
                "fts_score": self.fts_score, "strength": self.strength,
                "final_score": self.final_score,
                "discard_reason": self.discard_reason}


async def explain_retrieval(
    session: AsyncSession,
    user_id: str,
    viewer: Viewer,
    query: RetrievalQuery,
    *,
    store=None,
    backend=None,
    now: datetime | None = None,
) -> list[RecallEntry]:
    """Explain every memory's fate for one retrieval (deterministic)."""
    now = now or datetime.now(UTC)
    eligible = await eligible_memory_ids(session, user_id, viewer)
    fts = await fts_hits(session, user_id, query.text) if query.text else {}
    vec: dict[str, float] = {}
    if store is not None and backend is not None:
        result = await backend.embed([query.text])
        vec = await vector_hits(session, store, result.provenance, result.vectors[0])
    memories = await service.list_memories(session, user_id)
    entries: list[RecallEntry] = []
    for m in memories:
        v, f = vec.get(m.id, 0.0), fts.get(m.id, 0.0)
        strength = strength_multiplier(m, now) if query.extra_scores else 1.0
        if query.extra_scores:
            strength = query.extra_scores.get(m.id, strength)
        final = (VECTOR_WEIGHT * v + FTS_WEIGHT * f) * strength
        if m.id not in eligible:
            entries.append(RecallEntry(m.id, False, False, v, f, strength, final,
                                       "witness_ineligible"))
        elif m.state not in query.states:
            entries.append(RecallEntry(m.id, False, True, v, f, strength, final,
                                       f"state:{m.state}"))
        elif (query.kind and m.kind != query.kind) or (
            query.chat_id and m.chat_id != query.chat_id
        ) or (query.character_id and m.character_id != query.character_id):
            entries.append(RecallEntry(m.id, False, True, v, f, strength, final,
                                       "filtered"))
        elif v == 0.0 and f == 0.0:
            entries.append(RecallEntry(m.id, False, True, v, f, strength, final,
                                       "not_a_candidate"))
        elif final <= MIN_SCORE:
            entries.append(RecallEntry(m.id, False, True, v, f, strength, final,
                                       "below_threshold"))
        else:
            entries.append(RecallEntry(m.id, True, True, v, f, strength, final, None))
    included = sorted((e for e in entries if e.included),
                      key=lambda e: (-e.final_score, e.memory_id))[:query.limit]
    keep = {e.memory_id for e in included}
    return [
        e if (not e.included or e.memory_id in keep)
        else RecallEntry(e.memory_id, False, e.eligible, e.vector_score,
                         e.fts_score, e.strength, e.final_score, "over_limit")
        for e in entries
    ]


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class CorpusReport:
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict:
        return {"passed": self.passed,
                "results": [r.to_dict() for r in self.results]}


async def _user(session) -> str:
    user = User(name="volmarr")
    session.add(user)
    await session.commit()
    return user.id


async def _scenario_witness(factory) -> ScenarioResult:
    from runmal.memory.ingestion import ingest_document
    from runmal.memory.scope import scoped_retrieve

    backend, store = FakeEmbeddingBackend(dims=8), InMemoryVectorStore()
    async with factory() as session:
        uid = await _user(session)
        ing = await ingest_document(
            session, uid, backend, store, document_id="d",
            text="the secret amber key hangs behind the waterfall",
            scope="character", character_id="char-b")
        await session.commit()
        hits = await scoped_retrieve(
            session, uid, Viewer(character_id="char-a"),
            RetrievalQuery(text="amber"), store=store, backend=backend)
        ok = ing.memory_ids[0] not in {h.memory_id for h in hits}
        return ScenarioResult("witness", ok, "private memory leaked" if not ok else "")


async def _scenario_temporal(factory) -> ScenarioResult:
    async with factory() as session:
        uid = await _user(session)
        await apply_fact(session, uid, subject="Volmarr", predicate="lives_in",
                         content="Volmarr lives in Indiana.",
                         valid_from=datetime(2026, 1, 1, tzinfo=UTC))
        await apply_fact(session, uid, subject="Volmarr", predicate="lives_in",
                         content="Volmarr lives in New Mexico.",
                         valid_from=datetime(2027, 4, 1, tzinfo=UTC))
        await session.commit()
        current = await current_fact(session, uid, "Volmarr", "lives_in")
        ok = current is not None and "New Mexico" in current.content
        return ScenarioResult("temporal", ok, "" if ok else "current fact is stale")


async def _scenario_duplicate(factory) -> ScenarioResult:
    async with factory() as session:
        uid = await _user(session)
        for i, content in enumerate([
            "Volmarr prefers local-first AI.", "Volmarr prefers local-first AI",
            "Volmarr really prefers local-first AI tools.",
        ]):
            await service.create_memory(
                session, uid, content=content, subject="Volmarr",
                predicate="prefers", sources=(("message", f"m{i}", "c"),))
        await session.commit()
        report = await consolidate(session, uid)
        await session.commit()
        active = [m for m in await service.list_memories(session, uid)
                  if m.state == "active"]
        sources = await service.list_sources(session, active[0].id) if active else []
        ok = len(report.merged) == 2 and len(active) == 1 and len(sources) == 3
        return ScenarioResult("duplicate", ok,
                              "" if ok else f"merged={len(report.merged)} active={len(active)}")


async def _scenario_deletion(factory) -> ScenarioResult:
    from runmal.db.models import ChatEvent

    async with factory() as session:
        uid = await _user(session)
        fact = await service.create_memory(
            session, uid, content="Volmarr lives in Schenectady.", chat_id="c1",
            sources=(("message", "m1", "c1"), ("message", "m2", "c1")))
        await session.commit()
        events = [
            ChatEvent(chat_id="c1", message_id="m1", kind="message.deleted", data="{}"),
            ChatEvent(chat_id="c1", message_id="m2", kind="message.deleted", data="{}"),
        ]
        report = await apply_events(session, uid, events)
        await session.commit()
        fact = await service.get_memory(session, uid, fact.id)
        ok = fact.state == "invalidated" and fact.id in report.memories_invalidated
        return ScenarioResult("deletion", ok, "" if ok else f"state={fact.state}")


async def _scenario_decay(factory) -> ScenarioResult:
    async with factory() as session:
        uid = await _user(session)
        fragile = await service.create_memory(
            session, uid, content="fragile fjord note", salience=0.9, stability=0.1)
        durable = await service.create_memory(
            session, uid, content="durable fjord note", salience=0.9, stability=0.9)
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        fragile.created_at = durable.created_at = t0
        await session.commit()
        later = t0 + timedelta(days=60)
        ok = strength_multiplier(fragile, later) < strength_multiplier(durable, later)
        return ScenarioResult("decay", ok, "" if ok else "no decay separation")


async def _scenario_reembedding(factory) -> ScenarioResult:
    from runmal.memory.ingestion import ingest_document
    from runmal.memory.scope import scoped_retrieve

    store = InMemoryVectorStore()
    backend_a = FakeEmbeddingBackend(dims=8, model="fake-embed-1")
    backend_b = FakeEmbeddingBackend(dims=16, model="fake-embed-2")
    async with factory() as session:
        uid = await _user(session)
        text = "the amber key hangs behind the waterfall shrine"
        await ingest_document(session, uid, backend_a, store,
                              document_id="d", text=text)
        await session.commit()
        # Re-embed the same canonical text under the NEW profile/space.
        await ingest_document(session, uid, backend_b, store,
                              document_id="d", text=text)
        await session.commit()
        hits_b = await scoped_retrieve(
            session, uid, Viewer(), RetrievalQuery(text="amber"),
            store=store, backend=backend_b)
        ok = len(hits_b) >= 1
        return ScenarioResult("re_embedding", ok,
                              "" if ok else "new space retrieval failed")


SCENARIOS = (
    ("witness", _scenario_witness),
    ("temporal", _scenario_temporal),
    ("duplicate", _scenario_duplicate),
    ("deletion", _scenario_deletion),
    ("decay", _scenario_decay),
    ("re_embedding", _scenario_reembedding),
)


async def run_corpus(factory_maker) -> CorpusReport:
    """Run every scenario against an isolated store from ``factory_maker``.

    ``factory_maker(name)`` returns a fresh session factory per scenario.
    """
    report = CorpusReport()
    for name, scenario in SCENARIOS:
        try:
            report.results.append(await scenario(factory_maker(name)))
        except Exception as exc:  # a crashing scenario is a FAILED scenario
            report.results.append(ScenarioResult(name, False, f"{type(exc).__name__}: {exc}"))
    return report
