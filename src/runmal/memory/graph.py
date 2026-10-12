"""Provenance graph (S411): many-to-many source evidence.

Every derived memory traces to canonical evidence: this module renders
the memory -> sources graph (nodes + edges), including extractor
provenance and user-edit provenance, and can verify a whole owner's
graph: any derived memory (extractor kind != user curation) must have
at least one canonical source link (INV-013).
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.memory import service


async def provenance_graph(
    session: AsyncSession, user_id: str, memory_id: str
) -> dict | None:
    memory = await service.get_memory(session, user_id, memory_id)
    if memory is None:
        return None
    sources = await service.list_sources(session, memory_id)
    nodes = [{
        "id": memory.id, "type": "memory", "kind": memory.kind,
        "state": memory.state, "content": memory.content,
    }]
    edges = []
    for s in sources:
        node_id = f"{s.source_kind}:{s.source_id}"
        nodes.append({
            "id": node_id, "type": "source", "source_kind": s.source_kind,
            "source_id": s.source_id, "chat_id": s.chat_id,
        })
        edges.append({"from": memory.id, "to": node_id, "relation": "derived_from"})
    extractor = json.loads(memory.extractor_json or "{}")
    if extractor:
        nodes.append({
            "id": f"extractor:{extractor.get('kind', 'unknown')}",
            "type": "extractor", **extractor,
        })
        edges.append({"from": memory.id, "to": nodes[-1]["id"],
                      "relation": "extracted_by"})
    if memory.supersedes_id:
        edges.append({"from": memory.id, "to": memory.supersedes_id,
                      "relation": "supersedes"})
    return {"memory_id": memory.id, "nodes": nodes, "edges": edges}


async def trace_to_evidence(
    session: AsyncSession, user_id: str, memory_id: str
) -> list[dict]:
    """Canonical evidence rows behind a memory (its source links)."""
    sources = await service.list_sources(session, memory_id)
    return [{"source_kind": s.source_kind, "source_id": s.source_id,
             "chat_id": s.chat_id} for s in sources]


async def verify_all_traced(session: AsyncSession, user_id: str) -> list[str]:
    """Ids of derived memories with NO canonical evidence (must be [])."""
    offenders = []
    for memory in await service.list_memories(session, user_id):
        extractor = json.loads(memory.extractor_json or "{}")
        if extractor.get("kind") == "user_edit" or memory.kind == "nucleus":
            continue  # curated nucleus/user edits are their own provenance
        sources = await service.list_sources(session, memory.id)
        if not sources:
            offenders.append(memory.id)
    return offenders
