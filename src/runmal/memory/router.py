"""Memory browser (S410): inspect/search memories with provenance.

JSON API under ``/api/v1/memories`` plus a server-rendered browser page
at ``/memories`` (public page, loopback boundary per ADR-0003; the API
stays bearer-gated). Every row shows provenance (sources + extractor),
witness/scope, and temporal state — the MEMORY_ARCHITECTURE.md §12
browser contract in minimal form.
"""

from __future__ import annotations

import html
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
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


@router.get("/memories-browser", response_class=HTMLResponse)
async def memories_browser_page(
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Server-rendered browser page (owner-local; shows latest memories)."""
    from runmal.db.owners import get_or_create_owner

    owner = await get_or_create_owner(session)
    memories = await service.list_memories(session, owner.id)
    rows = []
    for m in memories:
        witnesses = html.escape(json.loads(m.witnesses_json or "[]").__str__())
        rows.append(
            "<tr>"
            f"<td>{html.escape(m.id[:8])}</td>"
            f"<td>{html.escape(m.kind)}</td>"
            f"<td>{html.escape(m.content)}</td>"
            f"<td>{html.escape(m.state)}</td>"
            f"<td>{html.escape(m.scope)}</td>"
            f"<td>{witnesses}</td>"
            f"<td>{html.escape(m.subject)}</td>"
            "</tr>")
    body = (
        "<!doctype html><html><head><title>Rúnmál — Memory Browser</title></head>"
        "<body><h1>Memory Browser</h1>"
        "<table><thead><tr><th>id</th><th>kind</th><th>content</th><th>state</th>"
        "<th>scope</th><th>witnesses</th><th>subject</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>")
    return HTMLResponse(body)
