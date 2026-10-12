"""Hybrid retrieval (S403): vector + FTS5 + structured filtering.

Deterministic score fusion (MEMORY_ARCHITECTURE.md §7): under fixed
data/configuration the ranking is reproducible — fusion weights are
constants, each path's score is a pure function of stored state, and
ties break by memory id. Structured filters (state/kind/chat/character)
are applied to candidates from both paths before fusion.

Later slices layer on top without changing the fusion contract:
witness eligibility (S407) filters BEFORE scoring, salience/decay
(S406) multiplies retrieval strength, and the recall trace (S414)
explains each candidate's path contributions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import EmbeddingBackend, EmbeddingProvenance
from runmal.db.models import Memory, MemoryChunk
from runmal.memory.vectorstore import VectorStore

VECTOR_WEIGHT = 0.65
FTS_WEIGHT = 0.35


@dataclass(frozen=True)
class RetrievalHit:
    memory_id: str
    score: float
    vector_score: float = 0.0
    fts_score: float = 0.0
    paths: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"memory_id": self.memory_id, "score": self.score,
                "vector_score": self.vector_score, "fts_score": self.fts_score,
                "paths": list(self.paths)}


@dataclass
class RetrievalQuery:
    text: str = ""
    limit: int = 10
    states: tuple[str, ...] = ("active", "pinned")
    kind: str | None = None
    chat_id: str | None = None
    character_id: str | None = None
    extra_scores: dict = field(default_factory=dict)  # memory_id -> multiplier (S406)


def _fts_query(text_: str) -> str:
    terms = [t for t in "".join(
        ch if (ch.isalnum() or ch == "_") else " " for ch in text_).split() if t]
    return " OR ".join(f'"{t}"' for t in terms)


async def fts_hits(session: AsyncSession, user_id: str, query_text: str) -> dict[str, float]:
    """FTS5 path: memory_id -> normalized score in [0, 1]."""
    expr = _fts_query(query_text)
    if not expr:
        return {}
    rows = (await session.execute(
        text("SELECT memory_id, bm25(memory_fts) AS rank FROM memory_fts "
             "WHERE memory_fts MATCH :q ORDER BY rank"),
        {"q": expr})).fetchall()
    owned = set(await session.scalars(
        select(Memory.id).where(Memory.user_id == user_id)))
    out: dict[str, float] = {}
    for memory_id, rank in rows:
        if memory_id in owned:
            relevance = max(0.0, -float(rank))
            out[memory_id] = relevance / (1.0 + relevance)
    return out


async def vector_hits(
    session: AsyncSession, store: VectorStore, provenance: EmbeddingProvenance,
    query_vector, top_k: int = 50,
) -> dict[str, float]:
    """Vector path: chunk hits folded to their owning memory (max wins)."""
    raw = store.search(provenance, tuple(query_vector), top_k=top_k)
    if not raw:
        return {}
    chunk_ids = [doc for doc, _ in raw]
    rows = (await session.execute(
        select(MemoryChunk.id, MemoryChunk.memory_id).where(
            MemoryChunk.id.in_(chunk_ids)))).fetchall()
    owner = {cid: mid for cid, mid in rows}
    out: dict[str, float] = {}
    for doc_id, score in raw:
        mid = owner.get(doc_id)
        if mid is not None:
            out[mid] = max(out.get(mid, 0.0), float(score))
    return out


async def hybrid_retrieve(
    session: AsyncSession,
    user_id: str,
    query: RetrievalQuery,
    *,
    store: VectorStore | None = None,
    backend: EmbeddingBackend | None = None,
    query_vector=None,
    provenance: EmbeddingProvenance | None = None,
    eligible_ids: set[str] | None = None,
) -> list[RetrievalHit]:
    """Fuse both paths deterministically.

    ``eligible_ids`` (S407) restricts candidates BEFORE any scoring:
    ineligible memories never enter the fusion, even on a vector hit.
    """
    fts = await fts_hits(session, user_id, query.text) if query.text else {}
    vec: dict[str, float] = {}
    if store is not None and (query_vector is not None or backend is not None):
        if query_vector is None and backend is not None:
            result = await backend.embed([query.text])
            query_vector = result.vectors[0]
            provenance = result.provenance
        if query_vector is not None and provenance is not None:
            vec = await vector_hits(session, store, provenance, query_vector)

    candidate_ids = set(fts) | set(vec)
    if eligible_ids is not None:
        candidate_ids &= eligible_ids
    if not candidate_ids:
        return []
    rows = list(await session.scalars(
        select(Memory).where(Memory.id.in_(candidate_ids), Memory.user_id == user_id)))
    by_id = {m.id: m for m in rows}

    hits: list[RetrievalHit] = []
    for memory_id in candidate_ids:
        m = by_id.get(memory_id)
        if m is None:
            continue
        if m.state not in query.states:
            continue
        if query.kind and m.kind != query.kind:
            continue
        if query.chat_id and m.chat_id != query.chat_id:
            continue
        if query.character_id and m.character_id != query.character_id:
            continue
        v = vec.get(memory_id, 0.0)
        f = fts.get(memory_id, 0.0)
        score = VECTOR_WEIGHT * v + FTS_WEIGHT * f
        score *= query.extra_scores.get(memory_id, 1.0)
        paths = tuple(p for p, s in (("vector", v), ("fts", f)) if s > 0)
        hits.append(RetrievalHit(memory_id, score, v, f, paths))
    hits.sort(key=lambda h: (-h.score, h.memory_id))
    return hits[:query.limit]
