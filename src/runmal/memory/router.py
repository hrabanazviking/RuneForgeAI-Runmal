"""Memory browser API (S410): inspect/search memories with provenance.

JSON API under ``/api/v1/memories`` (bearer-gated). Every row shows
provenance (sources + extractor), witness/scope, and temporal state —
the MEMORY_ARCHITECTURE.md §12 browser contract in minimal form.
(R-16: the server-rendered ``/memories`` page is scrapped with the web
shell; the desktop memory panel consumes this API.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.memory import service
from runmal.memory.graph import provenance_graph
from runmal.memory.models import memory_to_dict, source_to_dict

router = APIRouter(tags=["memories"])


async def _describe(session: AsyncSession, memory) -> dict:
    data = memory_to_dict(memory)
    data["sources"] = [source_to_dict(s) for s in await service.list_sources(session, memory.id)]
    return data


@router.get("/memories")
async def list_memories(
    q: str = Query(default=""),
    state: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    memories = await service.list_memories(session, owner_id, state=state, kind=kind)
    if q:
        needle = q.lower()
        memories = [m for m in memories if needle in m.content.lower()]
    return {"memories": [await _describe(session, m) for m in memories]}


@router.get("/memories/{memory_id}")
async def get_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    memory = await service.get_memory(session, owner_id, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="memory not found")
    data = await _describe(session, memory)
    data["graph"] = await provenance_graph(session, owner_id, memory_id)
    return data
