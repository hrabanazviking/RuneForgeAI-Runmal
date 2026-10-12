"""Witness-scoped recall (S407): who may remember what.

Explicit witness/scope model (MEMORY_ARCHITECTURE.md §6, INV-014):

- ``global`` / ``user`` scope — known to the owner; any of the owner's
  characters may recall it.
- ``character`` scope — private to ``memory.character_id``.
- ``chat`` scope — known only inside ``memory.chat_id``.
- ``witnesses`` scope — known only to the explicit witness set
  (character ids, or the literal ``"user"``).

Eligibility is a PRE-SCORE filter: ``eligible_memory_ids`` computes the
eligible set first and hybrid retrieval intersects candidates with it
before any scoring, so a character cannot gain private knowledge even
when vector search would have found it. The owner (viewer character =
None) sees all of their own memories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory
from runmal.memory import service
from runmal.memory.retrieval import RetrievalQuery, hybrid_retrieve
from runmal.memory.vectorstore import VectorStore


@dataclass(frozen=True)
class Viewer:
    character_id: str | None = None  # None = the owner/user themselves
    chat_id: str | None = None

    @property
    def identity(self) -> str:
        return self.character_id or "user"


def is_eligible(memory: Memory, viewer: Viewer) -> bool:
    if viewer.character_id is None:
        return True  # the owner sees all of their own memories
    scope = memory.scope
    if scope in ("global", "user"):
        return True
    if scope == "character":
        return memory.character_id == viewer.character_id
    if scope == "chat":
        return viewer.chat_id is not None and memory.chat_id == viewer.chat_id
    if scope == "witnesses":
        witnesses = json.loads(memory.witnesses_json or "[]")
        return viewer.character_id in witnesses or viewer.identity in witnesses
    return False


async def eligible_memory_ids(
    session: AsyncSession, user_id: str, viewer: Viewer
) -> set[str]:
    memories = await service.list_memories(session, user_id)
    return {m.id for m in memories if is_eligible(m, viewer)}


async def scoped_retrieve(
    session: AsyncSession,
    user_id: str,
    viewer: Viewer,
    query: RetrievalQuery,
    *,
    store: VectorStore | None = None,
    backend=None,
    query_vector=None,
    provenance=None,
):
    """Hybrid retrieval with witness eligibility applied BEFORE scoring."""
    eligible = await eligible_memory_ids(session, user_id, viewer)
    return await hybrid_retrieve(
        session, user_id, query, store=store, backend=backend,
        query_vector=query_vector, provenance=provenance, eligible_ids=eligible)
